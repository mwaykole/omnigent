"""Tests for the token saver tool-output compressor."""

from __future__ import annotations

import json

import pytest

from omnigent.runner.tool_output_compressor import (
    ALL_ALGO_KEYS,
    compress_tool_output,
    parse_algo_label,
)


# ── parse_algo_label ──────────────────────────────────────


class TestParseAlgoLabel:
    def test_all(self):
        assert parse_algo_label("all") == ALL_ALGO_KEYS

    def test_one(self):
        assert parse_algo_label("1") == ALL_ALGO_KEYS

    def test_off(self):
        assert parse_algo_label("off") == frozenset()

    def test_empty(self):
        assert parse_algo_label("") == frozenset()

    def test_csv(self):
        result = parse_algo_label("json,log,delta")
        assert result == frozenset({"json", "log", "delta"})

    def test_unknown_keys_ignored(self):
        result = parse_algo_label("json,bogus,log")
        assert result == frozenset({"json", "log"})

    def test_new_algos_in_registry(self):
        expected_new = {"stacktrace", "testoutput", "code", "tabular",
                        "pathfactor", "precision", "fuzzydedup"}
        assert expected_new.issubset(ALL_ALGO_KEYS)


# ── helpers ───────────────────────────────────────────────


def _compress(text: str, tool: str = "Bash", algos: str = "all") -> str:
    return compress_tool_output(
        text, tool, enabled_algos=parse_algo_label(algos),
    )


def _pad(text: str, min_len: int = 1500) -> str:
    """Pad text to exceed _MIN_COMPRESS_CHARS threshold."""
    if len(text) >= min_len:
        return text
    return text + "\n" + ("x" * (min_len - len(text)))


def _only(text: str, algo: str, tool: str = "Bash") -> str:
    return compress_tool_output(
        _pad(text), tool, enabled_algos=frozenset({algo}),
    )


# ── stack trace dedup ─────────────────────────────────────


class TestStackTraceDedup:
    TRACE = (
        "Traceback (most recent call last):\n"
        '  File "/app/main.py", line 42, in run\n'
        "    result = process(data)\n"
        '  File "/app/process.py", line 10, in process\n'
        "    return transform(data)\n"
        "ValueError: invalid data\n"
    )

    def test_single_trace_unchanged(self):
        result = _only(self.TRACE, "stacktrace")
        assert "Traceback" in result
        assert "repeated" not in result

    def test_duplicate_traces_collapsed(self):
        text = f"Error 1:\n{self.TRACE}\nError 2:\n{self.TRACE}\nError 3:\n{self.TRACE}"
        result = _only(text, "stacktrace")
        assert result.count("Traceback") < text.count("Traceback")

    def test_different_traces_kept(self):
        trace2 = (
            "Traceback (most recent call last):\n"
            '  File "/app/other.py", line 99, in handler\n'
            "    do_stuff()\n"
            "RuntimeError: failed\n"
        )
        text = f"{self.TRACE}\n{trace2}"
        result = _only(text, "stacktrace")
        assert result.count("Traceback") == 2


# ── test output compression ──────────────────────────────


class TestTestOutputCompression:
    def test_dot_lines_collapsed(self):
        dots = "\n".join(["." * 20] * 50)
        text = f"Running tests:\n{dots}\n======= 100 passed =======\n"
        result = _only(text, "testoutput", tool="Bash")
        assert "tests passed" in result

    def test_pass_lines_collapsed(self):
        passes = "\n".join(f"ok {i} test_{i}" for i in range(80))
        text = f"TAP output:\n{passes}\nFAIL: test_broken\n"
        result = _only(text, "testoutput", tool="Bash")
        assert "tests passed" in result
        assert "FAIL: test_broken" in result

    def test_failures_preserved(self):
        passes = "\n".join("PASSED" for _ in range(80))
        text = f"{passes}\nFAILED test_foo - expected 1 got 2\nPASSED\n"
        result = _only(text, "testoutput", tool="Bash")
        assert "FAILED test_foo" in result

    def test_short_output_unchanged(self):
        text = "ok 1 test_a\nok 2 test_b\n"
        result = compress_tool_output(text, "Bash", enabled_algos=frozenset({"testoutput"}))
        assert result == text


# ── code compression ──────────────────────────────────────


class TestCodeCompression:
    def test_comments_stripped(self):
        code = 'x = 1\n' + '\n'.join(f'# comment {i}' for i in range(50)) + '\ndef foo():\n    pass\n'
        # Pad to exceed _MIN_COMPRESS_CHARS.
        code += "\n" * 500 + "end = True\n"
        result = _only(code, "code", tool="Read")
        assert "# comment" not in result
        assert "def foo" in result

    def test_docstrings_collapsed(self):
        code = (
            'def bar():\n'
            '    """This is a very long docstring.\n\n'
            '    It has multiple paragraphs and is very detailed.\n'
            '    Lots and lots of text here.\n'
            '    """\n'
            '    return 42\n'
        )
        code += "\n" * 500 + "end = True\n"
        result = _only(code, "code", tool="Read")
        assert '"""..."""' in result
        assert "multiple paragraphs" not in result


# ── tabular output compression ────────────────────────────


class TestTabularCompression:
    def test_separator_rows_limited(self):
        header = "| Name | Age | City |"
        sep = "+------+-----+------+"
        text = f"{sep}\n{header}\n{sep}\n"
        text += "\n".join(f"| User{i} | {20+i} | City{i} |" for i in range(30))
        text += f"\n{sep}\n{sep}\n{sep}\n{sep}\n{sep}\n"
        result = _only(text, "tabular")
        assert result.count(sep) <= 3

    def test_pipe_cells_compressed(self):
        long_cell = "x" * 100
        text = f"| {long_cell} | short |\n" * 20
        result = _only(text, "tabular")
        # Each cell is truncated to 50 chars.
        assert ("x" * 100) not in result


# ── path prefix factoring ─────────────────────────────────


class TestPathFactoring:
    def test_repeated_paths_factored(self):
        prefix = "/home/user/projects/myapp/src/components"
        lines = [f"modified: {prefix}/file_{i}.tsx" for i in range(20)]
        text = "\n".join(lines)
        result = _only(text, "pathfactor")
        assert "$P" in result
        assert result.count(prefix) <= 1

    def test_few_paths_unchanged(self):
        text = "/a/b/c\n/d/e/f\n" + ("filler line\n" * 100)
        result = _only(text, "pathfactor")
        assert "$P" not in result


# ── numeric precision reduction ───────────────────────────


class TestPrecisionReduction:
    def test_long_floats_truncated(self):
        text = "accuracy: 0.98765432109 loss: 0.00012345678\n" * 30
        result = _only(text, "precision")
        assert "0.98765432109" not in result
        assert "0.988" in result or "0.9877" in result

    def test_short_floats_unchanged(self):
        text = "value: 3.14\n" * 30
        result = _only(text, "precision")
        assert "3.14" in result


# ── fuzzy line dedup ──────────────────────────────────────


class TestFuzzyDedup:
    def test_similar_lines_collapsed(self):
        lines = [f'Processing file "/app/data/file_{i}.csv" took {100+i}ms, status ok' for i in range(20)]
        text = "\n".join(lines)
        result = _only(text, "fuzzydedup")
        assert "similar line appears" in result
        assert result.count("Processing file") == 1

    def test_numbers_normalized_in_grouping(self):
        lines = [f"Request {i*100} completed in {i*10}.{i}ms for user_{i}" for i in range(20)]
        text = "\n".join(lines)
        result = _only(text, "fuzzydedup")
        assert "similar line appears" in result

    def test_short_lines_not_grouped(self):
        lines = ["x = 1"] * 15
        text = "\n".join(lines)
        result = _only(text, "fuzzydedup")
        assert "similar line" not in result


# ── integration: compress_tool_output ─────────────────────


class TestCompressIntegration:
    def test_all_algos_parse(self):
        algos = parse_algo_label("all")
        assert len(algos) == 12

    def test_large_json_compressed(self):
        data = [{"id": i, "name": f"item_{i}", "value": i * 1.111111}
                for i in range(50)]
        text = json.dumps(data, indent=2)
        result = _compress(text, tool="api_call", algos="json,precision")
        assert len(result) < len(text)

    def test_disabled_returns_unchanged(self):
        text = "x" * 2000
        result = compress_tool_output(text, "Bash", enabled_algos=frozenset())
        assert result == text

    def test_short_output_unchanged(self):
        text = "hello"
        result = _compress(text)
        assert result == text

    def test_stacktrace_plus_log(self):
        trace = (
            "Traceback (most recent call last):\n"
            '  File "/app/x.py", line 1, in f\n'
            "    g()\n"
            "Error: boom\n"
        )
        text = (trace * 4) + "\n" + ("INFO 2024-01-01 processing item 123\n" * 30)
        result = _compress(text, tool="Bash", algos="stacktrace,log")
        assert len(result) < len(text)
        assert "repeated" in result or result.count("Traceback") < 4
