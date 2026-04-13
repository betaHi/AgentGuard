"""Tests for CLI summary command — one-line trace health."""

import os
import tempfile

from agentguard.builder import TraceBuilder
from agentguard.cli.main import _format_summary_line, cmd_summary


class _Args:
    def __init__(self, f):
        self.file = f


def _write(trace):
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    f.write(trace.to_json())
    f.close()
    return f.name


class TestCLISummary:
    def test_healthy_trace(self, capsys):
        t = TraceBuilder("my task").agent("a", duration_ms=1000).end().build()
        f = _write(t)
        try:
            cmd_summary(_Args(f))
            out = capsys.readouterr().out
            assert "my task" in out
            assert "/100" in out
        finally:
            os.unlink(f)

    def test_failed_trace(self, capsys):
        t = (TraceBuilder("fail task")
            .agent("a", duration_ms=500, status="failed", error="oops")
            .end().build())
        f = _write(t)
        try:
            cmd_summary(_Args(f))
            out = capsys.readouterr().out
            assert "fail task" in out
            assert "failure" in out.lower()
        finally:
            os.unlink(f)

    def test_format_contains_grade(self):
        t = TraceBuilder("x").agent("a", duration_ms=100).end().build()
        line = _format_summary_line(t)
        assert "[A]" in line or "[B]" in line or "[C]" in line

    def test_format_contains_duration(self):
        t = TraceBuilder("x").agent("a", duration_ms=2500).end().build()
        line = _format_summary_line(t)
        assert "s" in line  # duration in seconds

    def test_format_contains_agent_count(self):
        t = (TraceBuilder("x")
            .agent("a", duration_ms=100).end()
            .agent("b", duration_ms=100).end()
            .build())
        line = _format_summary_line(t)
        assert "2 agents" in line
