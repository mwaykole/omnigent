"""Deterministic tool-output compression to reduce LLM token consumption.

Applies content-type-aware compression to tool results before they enter the
harness context window.  No LLM calls, no external services — pure rule-based
transforms with near-zero latency overhead.

Techniques:
- TSCG columnar schema compilation (arXiv 2605.04107)
- DeLog pattern-signature grouping (arXiv 2601.15084)
- Delta encoding with content-addressed caching (Skim project)

Each algorithm can be individually toggled via the ``enabled_algos`` set
passed to :func:`compress_tool_output`.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import logging
import re
import threading
from collections import Counter

_logger = logging.getLogger(__name__)

# ── algorithm registry ──────────────────────────────────────

ALL_ALGO_KEYS = frozenset({
    "json", "log", "listing", "delta", "general",
    "stacktrace", "testoutput", "code", "tabular",
    "pathfactor", "precision", "fuzzydedup",
})

# ── thresholds ──────────────────────────────────────────────

_MIN_COMPRESS_CHARS = 1000
_HARD_CAP_CHARS = 80_000
_HARD_CAP_HEAD = 40_000
_HARD_CAP_TAIL = 10_000

_LOG_HEAD_TAIL_THRESHOLD = 30_000
_LOG_HEAD = 15_000
_LOG_TAIL = 5_000

_GENERAL_HEAD_TAIL_THRESHOLD = 50_000
_GENERAL_HEAD = 25_000
_GENERAL_TAIL = 8_000

_JSON_ARRAY_COLLAPSE_THRESHOLD = 20
_JSON_ARRAY_KEEP = 5
_JSON_COLUMNAR_THRESHOLD = 3

# Delta: similarity ratio above which we emit a unified diff.
_DELTA_SIMILARITY_THRESHOLD = 0.5
# Delta: maximum previous outputs to cache per session.
_DELTA_CACHE_MAX_ENTRIES = 64

# Tool names that produce shell/log output.
_SHELL_TOOLS = frozenset({
    "os_shell", "sys_os_shell",
    "sys_terminal", "sys_terminal_send", "sys_terminal_read",
    "terminal_command",
    "Bash",
})
_LISTING_TOOLS = frozenset({
    "list_files", "list_directory",
    "LS", "Glob",
})
_READ_TOOLS = frozenset({
    "read_file", "Read", "View",
    "cat_file", "file_read",
})

# ANSI escape sequence pattern.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_COMMENT_LINE_RE = re.compile(r"^\s*(?:#|//)[^\n]*$", re.MULTILINE)
_DOCSTRING_RE = re.compile(r'("""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\')', re.MULTILINE)
_LOG_VAR_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"
    r"|[0-9a-f]{7,40}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|\b\d+\.\d+(?:s|ms|MB|KB|GB)\b"
    r"|\b\d{4,}\b",
    re.IGNORECASE,
)

# Stack trace patterns.
_PY_TRACEBACK_START = re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)
_PY_FRAME_RE = re.compile(r'^\s+File ".*", line \d+', re.MULTILINE)
_JAVA_FRAME_RE = re.compile(r"^\s+at [\w.$]+\([\w.]+:\d+\)", re.MULTILINE)
_NODE_FRAME_RE = re.compile(r"^\s+at .+\(.+:\d+:\d+\)", re.MULTILINE)
_GO_GOROUTINE_RE = re.compile(r"^goroutine \d+ \[", re.MULTILINE)

# Test output patterns.
_PYTEST_PASS_RE = re.compile(r"^(?:PASSED|PASS|\.+)\s*$", re.MULTILINE)
_PYTEST_RESULT_RE = re.compile(
    r"^=+ (?:\d+ passed|.*(?:passed|failed|error|warning)).*=+\s*$",
    re.MULTILINE,
)
_TEST_OK_LINE_RE = re.compile(r"^(?:ok \d+|  ✓|  √|PASS:) ", re.MULTILINE)
_TEST_FAIL_LINE_RE = re.compile(
    r"^(?:FAIL|FAILED|ERROR|not ok \d+|  ✗|  ×|FAIL:) ", re.MULTILINE | re.IGNORECASE,
)

# Tabular output patterns.
_TABLE_SEP_RE = re.compile(r"^[+\-|─┼┤├┐┌┘└═╔╗╚╝╠╣╦╩╬]+$")
_TABLE_PIPE_RE = re.compile(r"^\|.*\|$")

# Path prefix patterns.
_LONG_PATH_RE = re.compile(r"(?:/[\w._-]+){4,}")
_FLOAT_RE = re.compile(r"\b\d+\.\d{4,}\b")


# ── per-session stats accumulator ──────────────────────────

_stats_lock = threading.Lock()
# session_id → {chars_saved, compressions, original_chars}
_session_stats: dict[str, dict[str, int]] = {}
# session_id → compressions count at last sync (avoids redundant PATCHes)
_stats_last_synced: dict[str, int] = {}

# Rough chars-to-tokens ratio (GPT/Claude tokenisers average ~3.5 chars/token).
_CHARS_PER_TOKEN = 3.5
# Approximate cost per 1K input tokens (blended across models).
_COST_PER_1K_INPUT_TOKENS = 0.003


def get_session_stats(session_id: str) -> dict[str, object]:
    """Return cumulative compression stats for *session_id*."""
    with _stats_lock:
        raw = _session_stats.get(session_id, {})
    chars_saved = raw.get("chars_saved", 0)
    compressions = raw.get("compressions", 0)
    original_chars = raw.get("original_chars", 0)
    tokens_saved = int(chars_saved / _CHARS_PER_TOKEN)
    cost_saved = round(tokens_saved / 1000 * _COST_PER_1K_INPUT_TOKENS, 4)
    return {
        "chars_saved": chars_saved,
        "original_chars": original_chars,
        "compressions": compressions,
        "tokens_saved": tokens_saved,
        "cost_saved_usd": cost_saved,
    }


def stats_changed_since_last_sync(session_id: str) -> bool:
    """Return True if stats were updated since the last sync check."""
    with _stats_lock:
        current = _session_stats.get(session_id, {}).get("compressions", 0)
        last = _stats_last_synced.get(session_id, 0)
        if current > last:
            _stats_last_synced[session_id] = current
            return True
        return False


def _record_stats(session_id: str, original_len: int, compressed_len: int) -> None:
    saved = max(0, original_len - compressed_len)
    if saved == 0:
        return
    with _stats_lock:
        entry = _session_stats.setdefault(session_id, {
            "chars_saved": 0, "compressions": 0, "original_chars": 0,
        })
        entry["chars_saved"] += saved
        entry["compressions"] += 1
        entry["original_chars"] += original_len


def clear_session_stats(session_id: str) -> None:
    """Remove stats for a finished session."""
    with _stats_lock:
        _session_stats.pop(session_id, None)
        _stats_last_synced.pop(session_id, None)


# ── delta encoding cache ───────────────────────────────────

_delta_lock = threading.Lock()
# session_id → {tool_name → (content_hash, content)}
_delta_cache: dict[str, dict[str, tuple[str, str]]] = {}


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()[:16]


def _delta_encode(
    output: str, tool_name: str, session_id: str,
) -> str | None:
    """Return a delta-compressed version, or ``None`` if no prior output."""
    key = tool_name
    h = _content_hash(output)

    with _delta_lock:
        session_cache = _delta_cache.get(session_id)
        if session_cache is None:
            _delta_cache[session_id] = {key: (h, output)}
            return None

        prev = session_cache.get(key)
        # Always update the cache with the latest output.
        if len(session_cache) >= _DELTA_CACHE_MAX_ENTRIES and key not in session_cache:
            oldest = next(iter(session_cache))
            del session_cache[oldest]
        session_cache[key] = (h, output)

    if prev is None:
        return None

    prev_hash, prev_output = prev
    if prev_hash == h:
        return f"[Output unchanged from previous {tool_name} call]"

    # Check similarity — only emit diff if outputs are similar enough.
    ratio = difflib.SequenceMatcher(
        None, prev_output[:5000], output[:5000],
    ).quick_ratio()
    if ratio < _DELTA_SIMILARITY_THRESHOLD:
        return None

    diff_lines = list(difflib.unified_diff(
        prev_output.splitlines(keepends=True),
        output.splitlines(keepends=True),
        fromfile="previous",
        tofile="current",
        n=1,
    ))

    if not diff_lines:
        return f"[Output unchanged from previous {tool_name} call]"

    diff_text = "".join(diff_lines)
    # Only use the diff if it's actually shorter.
    if len(diff_text) >= len(output) * 0.8:
        return None

    return (
        f"[Delta from previous {tool_name} output — "
        f"{len(output):,} chars → {len(diff_text):,} char diff]\n"
        + diff_text
    )


def clear_delta_cache(session_id: str) -> None:
    """Remove cached outputs and stats for a finished session."""
    with _delta_lock:
        _delta_cache.pop(session_id, None)
    clear_session_stats(session_id)


# ── public API ──────────────────────────────────────────────


def parse_algo_label(label_value: str) -> frozenset[str]:
    """Parse the ``omnigent.token_saver`` label value into an algo set.

    ``"all"`` or ``"1"`` → all algorithms.
    ``"off"`` or ``""``  → empty set (disabled).
    ``"json,log,delta"`` → those specific algorithms.
    """
    if not label_value or label_value == "off":
        return frozenset()
    if label_value in ("all", "1"):
        return ALL_ALGO_KEYS
    return frozenset(k.strip() for k in label_value.split(",") if k.strip() in ALL_ALGO_KEYS)


def compress_tool_output(
    output: str,
    tool_name: str,
    *,
    enabled_algos: frozenset[str] | None = None,
    session_id: str | None = None,
) -> str:
    """Compress *output* to reduce token consumption.

    :param enabled_algos: Set of algorithm keys to apply. ``None`` means
        all algorithms.  Pass an empty set to disable compression.
    :param session_id: Session identifier for delta encoding cache.
        Required when ``"delta"`` is in *enabled_algos*.
    """
    if enabled_algos is not None and not enabled_algos:
        return output

    algos = enabled_algos if enabled_algos is not None else ALL_ALGO_KEYS

    # Delta encoding runs first — on the raw output before any transforms.
    if "delta" in algos and session_id:
        delta = _delta_encode(output, tool_name, session_id)
        if delta is not None:
            _logger.debug(
                "token_saver: delta %s %d → %d",
                tool_name, len(output), len(delta),
            )
            _record_stats(session_id, len(output), len(delta))
            return delta

    if len(output) <= _MIN_COMPRESS_CHARS:
        return output

    original_len = len(output)

    if original_len > _HARD_CAP_CHARS:
        output = _head_tail(output, _HARD_CAP_HEAD, _HARD_CAP_TAIL)

    compressed = _dispatch(output, tool_name, algos)

    compressed_len = len(compressed)
    if compressed_len < original_len:
        saved_pct = round((1 - compressed_len / original_len) * 100)
        _logger.debug(
            "token_saver: %s %d → %d (%d%% saved)",
            tool_name, original_len, compressed_len, saved_pct,
        )

    if session_id:
        _record_stats(session_id, original_len, compressed_len)

    return compressed


# ── dispatch ────────────────────────────────────────────────


_LS_LINE_RE = re.compile(r"^[d\-lbcps][r\-][w\-][x\-]")


def _looks_like_ls(text: str) -> bool:
    """Heuristic: output is a directory listing if most lines match ls -la."""
    lines = [ln for ln in text.split("\n") if ln.strip()]
    if len(lines) < 3:
        return False
    matches = sum(1 for ln in lines if _LS_LINE_RE.match(ln))
    return matches >= len(lines) * 0.5


def _dispatch(output: str, tool_name: str, algos: frozenset[str]) -> str:
    if tool_name in _LISTING_TOOLS and "listing" in algos:
        return _compress_listing(output)

    if "listing" in algos and _looks_like_ls(output):
        return _compress_listing(output)

    # Stack trace dedup runs early — biggest wins on error-heavy output.
    if "stacktrace" in algos and _has_stacktrace(output):
        output = _compress_stacktraces(output)

    # Test output compression for shell tools producing test results.
    if tool_name in _SHELL_TOOLS and "testoutput" in algos and _has_test_output(output):
        return _compress_test_output(output)

    if tool_name in _SHELL_TOOLS and "log" in algos:
        output = _compress_log(output)

    # Code comment/docstring stripping for file-read tools.
    if tool_name in _READ_TOOLS and "code" in algos:
        output = _compress_code(output)

    stripped = output.lstrip()
    if stripped[:1] in ("{", "[") and "json" in algos:
        try:
            return _compress_json(output)
        except (json.JSONDecodeError, ValueError, RecursionError):
            pass

    # Tabular output compression.
    if "tabular" in algos and _has_table(output):
        output = _compress_tabular(output)

    # Path prefix factoring.
    if "pathfactor" in algos:
        output = _factor_paths(output)

    # Numeric precision reduction.
    if "precision" in algos:
        output = _reduce_precision(output)

    # Fuzzy line dedup.
    if "fuzzydedup" in algos:
        output = _fuzzy_dedup(output)

    if "general" in algos:
        return _compress_general(output)

    return output


# ── JSON compressor (TSCG-style schema compilation) ────────


def _compress_json(text: str) -> str:
    data = json.loads(text)
    data = _columnar_arrays(data)
    return json.dumps(data, separators=(",", ":"), ensure_ascii=False)


def _columnar_arrays(obj: object, depth: int = 0) -> object:
    """Convert arrays-of-uniform-objects to columnar header+rows format."""
    if depth > 20:
        return obj
    if isinstance(obj, list):
        if len(obj) >= _JSON_COLUMNAR_THRESHOLD and _is_uniform_object_array(obj):
            return _to_columnar(obj)
        if len(obj) > _JSON_ARRAY_COLLAPSE_THRESHOLD:
            kept = [_columnar_arrays(item, depth + 1) for item in obj[:_JSON_ARRAY_KEEP]]
            kept.append(f"...({len(obj) - _JSON_ARRAY_KEEP} more items)")
            return kept
        return [_columnar_arrays(item, depth + 1) for item in obj]
    if isinstance(obj, dict):
        return {k: _columnar_arrays(v, depth + 1) for k, v in obj.items()}
    return obj


def _is_uniform_object_array(arr: list[object]) -> bool:
    if not arr or not isinstance(arr[0], dict):
        return False
    keys = frozenset(arr[0].keys())
    return all(isinstance(item, dict) and frozenset(item.keys()) == keys for item in arr)


def _to_columnar(arr: list[dict[str, object]]) -> dict[str, object]:
    cols = list(arr[0].keys())
    rows: list[list[object]] = []
    for item in arr:
        rows.append([item[k] for k in cols])
    if len(rows) > _JSON_ARRAY_COLLAPSE_THRESHOLD:
        kept = rows[:_JSON_ARRAY_KEEP]
        kept.append([f"...({len(rows) - _JSON_ARRAY_KEEP} more rows)"])
        rows = kept
    return {"__cols": cols, "__rows": rows}


# ── log / shell compressor (DeLog-style pattern grouping) ──


def _compress_log(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    text = _pattern_group_lines(text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    text = _TRAILING_WS_RE.sub("", text)
    if len(text) > _LOG_HEAD_TAIL_THRESHOLD:
        text = _head_tail(text, _LOG_HEAD, _LOG_TAIL)
    return text


def _line_signature(line: str) -> str:
    return _LOG_VAR_RE.sub("<*>", line.rstrip())


def _pattern_group_lines(text: str) -> str:
    """Group non-adjacent lines with identical templates."""
    lines = text.split("\n")
    sigs = [_line_signature(line) for line in lines]
    sig_counts: Counter[str] = Counter(sigs)

    result: list[str] = []
    seen_sigs: dict[str, int] = {}
    prev_sig: str | None = None
    consecutive_count = 0

    for line, sig in zip(lines, sigs, strict=True):
        if sig == prev_sig and sig:
            consecutive_count += 1
            continue

        if consecutive_count > 1:
            result.append(f"  [repeated {consecutive_count}x]")
        consecutive_count = 1
        prev_sig = sig

        if sig and sig_counts[sig] > 2:
            seen_count = seen_sigs.get(sig, 0)
            if seen_count == 0:
                result.append(line)
                result.append(f"  [pattern appears {sig_counts[sig]}x total]")
                seen_sigs[sig] = 1
            else:
                seen_sigs[sig] = seen_count + 1
                continue
        else:
            result.append(line)

    if consecutive_count > 1:
        result.append(f"  [repeated {consecutive_count}x]")

    return "\n".join(result)


# ── directory listing compressor ────────────────────────────


def _compress_listing(text: str) -> str:
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    text = _TRAILING_WS_RE.sub("", text)
    lines = text.split("\n")
    compressed: list[str] = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 9 and re.match(r"^[d\-lbcps]r", line):
            compressed.append(parts[-1])
        else:
            compressed.append(line)
    return "\n".join(compressed)


# ── code compressor ─────────────────────────────────────────


def _compress_code(text: str) -> str:
    text = _DOCSTRING_RE.sub('"""..."""', text)
    text = _COMMENT_LINE_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    text = _TRAILING_WS_RE.sub("", text)
    return text


# ── stack trace dedup ──────────────────────────────────────


def _has_stacktrace(text: str) -> bool:
    return bool(
        _PY_TRACEBACK_START.search(text)
        or (_JAVA_FRAME_RE.search(text) and text.count("\n\tat ") > 3)
        or (_GO_GOROUTINE_RE.search(text) and text.count("\ngoroutine ") > 1)
        or (_NODE_FRAME_RE.search(text) and text.count("\n    at ") > 5)
    )


def _compress_stacktraces(text: str) -> str:
    traces = _extract_traces(text)
    if len(traces) < 2:
        return text

    seen: dict[str, int] = {}
    for start, end, signature in traces:
        seen[signature] = seen.get(signature, 0) + 1

    result_parts: list[str] = []
    last_end = 0
    emitted: set[str] = set()

    for start, end, signature in traces:
        result_parts.append(text[last_end:start])
        if signature not in emitted:
            result_parts.append(text[start:end])
            if seen[signature] > 1:
                result_parts.append(
                    f"\n  [identical trace repeated {seen[signature]}x total]"
                )
            emitted.add(signature)
        last_end = end

    result_parts.append(text[last_end:])
    return "".join(result_parts)


def _extract_traces(text: str) -> list[tuple[int, int, str]]:
    """Extract (start, end, signature) for each stack trace block."""
    traces: list[tuple[int, int, str]] = []

    for m in _PY_TRACEBACK_START.finditer(text):
        start = m.start()
        end = start
        lines = text[start:].split("\n")
        trace_lines: list[str] = []
        for i, line in enumerate(lines):
            if i == 0:
                trace_lines.append(line)
                continue
            if line.startswith("  ") or (
                not line.startswith(" ") and i > 0 and lines[i - 1].startswith("  ")
            ):
                trace_lines.append(line)
                end = start + sum(len(l) + 1 for l in lines[: i + 1])
            elif i > 1:
                break
        sig = _trace_signature(trace_lines)
        traces.append((start, end, sig))

    return traces


def _trace_signature(lines: list[str]) -> str:
    """Normalize a trace to a comparable signature."""
    normalized = []
    for line in lines:
        line = re.sub(r"line \d+", "line N", line)
        line = re.sub(r"0x[0-9a-fA-F]+", "0xN", line)
        normalized.append(line.strip())
    return "\n".join(normalized)


# ── test output compression ───────────────────────────────


def _has_test_output(text: str) -> bool:
    return bool(
        _PYTEST_RESULT_RE.search(text)
        or _TEST_OK_LINE_RE.search(text)
        or text.count("\nPASSED") > 2
        or text.count("\n.") > 10
    )


def _compress_test_output(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    pass_count = 0
    dot_count = 0

    for line in lines:
        stripped = line.strip()
        if stripped in (".", "..", "...", "PASSED", "PASS") or (
            len(stripped) > 3 and all(c == "." for c in stripped)
        ):
            dot_count += len(stripped.replace("PASSED", ".").replace("PASS", "."))
            continue
        if _TEST_OK_LINE_RE.match(line):
            pass_count += 1
            continue
        if _TEST_FAIL_LINE_RE.match(line) or _PYTEST_RESULT_RE.match(line):
            if pass_count + dot_count > 0:
                result.append(f"  [{pass_count + dot_count} tests passed]")
                pass_count = 0
                dot_count = 0
            result.append(line)
            continue
        if pass_count + dot_count > 0:
            result.append(f"  [{pass_count + dot_count} tests passed]")
            pass_count = 0
            dot_count = 0
        result.append(line)

    if pass_count + dot_count > 0:
        result.append(f"  [{pass_count + dot_count} tests passed]")

    return "\n".join(result)


# ── tabular output compression ─────────────────────────────


def _has_table(text: str) -> bool:
    lines = text.split("\n")
    sep_count = sum(1 for l in lines if _TABLE_SEP_RE.match(l.strip()))
    pipe_count = sum(1 for l in lines if _TABLE_PIPE_RE.match(l.strip()))
    return sep_count >= 2 or pipe_count >= 3


def _compress_tabular(text: str) -> str:
    lines = text.split("\n")
    result: list[str] = []
    sep_run = 0
    total_seps = 0

    for line in lines:
        stripped = line.strip()
        if _TABLE_SEP_RE.match(stripped):
            sep_run += 1
            total_seps += 1
            if sep_run <= 1 and total_seps <= 3:
                result.append(line)
            continue
        sep_run = 0

        if _TABLE_PIPE_RE.match(stripped):
            cells = [c.strip() for c in stripped.split("|")]
            compressed = "|".join(c[:50] for c in cells)
            result.append(compressed)
        else:
            result.append(line)

    return "\n".join(result)


# ── path prefix factoring ──────────────────────────────────


def _factor_paths(text: str) -> str:
    paths = _LONG_PATH_RE.findall(text)
    if len(paths) < 3:
        return text

    prefix_counts: Counter[str] = Counter()
    for p in paths:
        parts = p.split("/")
        for depth in range(3, len(parts)):
            prefix = "/".join(parts[:depth])
            if len(prefix) >= 20:
                prefix_counts[prefix] += 1

    if not prefix_counts:
        return text

    best_prefix = max(
        prefix_counts,
        key=lambda p: prefix_counts[p] * len(p),
    )
    if prefix_counts[best_prefix] < 3:
        return text

    alias = "$P"
    header = f"[{alias}={best_prefix}]\n"
    return header + text.replace(best_prefix, alias)


# ── numeric precision reduction ────────────────────────────


def _reduce_precision(text: str) -> str:
    def _trunc(m: re.Match[str]) -> str:
        val = m.group(0)
        try:
            f = float(val)
            if abs(f) < 1e-6:
                return "0.0"
            return f"{f:.3g}"
        except ValueError:
            return val

    return _FLOAT_RE.sub(_trunc, text)


# ── fuzzy line dedup ───────────────────────────────────────


def _fuzzy_dedup(text: str) -> str:
    lines = text.split("\n")
    if len(lines) < 10:
        return text

    bucket_counts: Counter[str] = Counter()
    for line in lines:
        sig = _fuzzy_signature(line)
        if sig:
            bucket_counts[sig] += 1

    result: list[str] = []
    emitted: set[str] = set()
    for line in lines:
        sig = _fuzzy_signature(line)
        if not sig:
            result.append(line)
            continue
        if sig not in emitted:
            emitted.add(sig)
            result.append(line)
            if bucket_counts[sig] > 2:
                result.append(f"  [similar line appears {bucket_counts[sig]}x]")

    return "\n".join(result)


def _fuzzy_signature(line: str) -> str:
    """Normalize a line to a fuzzy signature for grouping."""
    stripped = line.strip()
    if len(stripped) < 15:
        return ""
    sig = re.sub(r"\d+", "N", stripped)
    sig = re.sub(r"0x[0-9a-fA-F]+", "0xN", sig)
    sig = re.sub(r"['\"].*?['\"]", '"S"', sig)
    sig = re.sub(r"\s+", " ", sig)
    return sig


# ── general compressor ──────────────────────────────────────


def _compress_general(text: str) -> str:
    text = _ANSI_RE.sub("", text)
    text = _MULTI_BLANK_RE.sub("\n\n", text)
    text = _TRAILING_WS_RE.sub("", text)
    text = _pattern_group_lines(text)
    if len(text) > _GENERAL_HEAD_TAIL_THRESHOLD:
        text = _head_tail(text, _GENERAL_HEAD, _GENERAL_TAIL)
    return text


# ── shared helpers ──────────────────────────────────────────


def _head_tail(text: str, head: int, tail: int) -> str:
    omitted = len(text) - head - tail
    return (
        text[:head].rstrip()
        + f"\n\n...[{omitted:,} chars omitted for token savings]...\n\n"
        + text[-tail:].lstrip()
    )
