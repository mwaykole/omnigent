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

ALL_ALGO_KEYS = frozenset({"json", "log", "listing", "delta", "general"})

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

# ANSI escape sequence pattern.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")
_MULTI_BLANK_RE = re.compile(r"\n{3,}")
_TRAILING_WS_RE = re.compile(r"[ \t]+$", re.MULTILINE)
_COMMENT_LINE_RE = re.compile(r"^\s*(?:#|//)[^\n]*$", re.MULTILINE)
_LOG_VAR_RE = re.compile(
    r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}[.\d]*Z?"
    r"|[0-9a-f]{7,40}"
    r"|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
    r"|\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|\b\d+\.\d+(?:s|ms|MB|KB|GB)\b"
    r"|\b\d{4,}\b",
    re.IGNORECASE,
)


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

    # Content-based detection: directory listing from any tool.
    if "listing" in algos and _looks_like_ls(output):
        return _compress_listing(output)

    if tool_name in _SHELL_TOOLS and "log" in algos:
        return _compress_log(output)

    stripped = output.lstrip()
    if stripped[:1] in ("{", "[") and "json" in algos:
        try:
            return _compress_json(output)
        except (json.JSONDecodeError, ValueError, RecursionError):
            pass

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
    return _TRAILING_WS_RE.sub(
        "", _MULTI_BLANK_RE.sub("\n\n", _COMMENT_LINE_RE.sub("", text))
    )


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
