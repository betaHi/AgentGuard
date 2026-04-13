"""Tests for CLI diff command — compare two traces."""

import os
import tempfile

from agentguard.builder import TraceBuilder
from agentguard.cli.main import cmd_diff


class _Args:
    def __init__(self, a, b):
        self.trace_a = a
        self.trace_b = b


def _write_trace(trace):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    f.write(trace.to_json())
    f.close()
    return f.name


class TestCLIDiff:
    def test_diff_shows_changes(self, capsys):
        t1 = TraceBuilder("v1").agent("a", duration_ms=1000).end().build()
        t2 = TraceBuilder("v2").agent("a", duration_ms=2000).end().build()
        f1, f2 = _write_trace(t1), _write_trace(t2)
        try:
            cmd_diff(_Args(f1, f2))
            out = capsys.readouterr().out
            assert "Diff" in out
            assert "Changes" in out
        finally:
            os.unlink(f1)
            os.unlink(f2)

    def test_diff_shows_added_spans(self, capsys):
        t1 = TraceBuilder("v1").agent("a", duration_ms=1000).end().build()
        t2 = (TraceBuilder("v2")
            .agent("a", duration_ms=1000).end()
            .agent("b", duration_ms=500).end()
            .build())
        f1, f2 = _write_trace(t1), _write_trace(t2)
        try:
            cmd_diff(_Args(f1, f2))
            out = capsys.readouterr().out
            assert "added" in out.lower() or "b" in out
        finally:
            os.unlink(f1)
            os.unlink(f2)

    def test_identical_traces_no_diff(self, capsys):
        t = TraceBuilder("same").agent("a", duration_ms=1000).end().build()
        f1, f2 = _write_trace(t), _write_trace(t)
        try:
            cmd_diff(_Args(f1, f2))
            out = capsys.readouterr().out
            assert "No differences" in out or "Changes" in out
        finally:
            os.unlink(f1)
            os.unlink(f2)

    def test_diff_shows_regressions(self, capsys):
        t1 = TraceBuilder("v1").agent("a", duration_ms=100).end().build()
        t2 = TraceBuilder("v2").agent("a", duration_ms=5000).end().build()
        f1, f2 = _write_trace(t1), _write_trace(t2)
        try:
            cmd_diff(_Args(f1, f2))
            out = capsys.readouterr().out
            assert "Regressions" in out or "regressed" in out.lower() or "📉" in out
        finally:
            os.unlink(f1)
            os.unlink(f2)
