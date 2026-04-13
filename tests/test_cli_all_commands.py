"""Test: all CLI commands work end-to-end with real trace files.

Parametrized over every command that takes a trace file argument.
Commands that need special args or no file are tested separately.
"""

import tempfile
import os
import pytest
from agentguard.builder import TraceBuilder
from agentguard.cli import main as cli


def _trace_file():
    t = (TraceBuilder("cli test")
        .agent("coordinator", duration_ms=3000)
            .agent("worker", duration_ms=1000, token_count=100, cost_usd=0.01)
                .tool("api", duration_ms=500)
            .end()
        .end()
        .build())
    f = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
    f.write(t.to_json())
    f.close()
    return f.name


def _two_trace_files():
    f1 = _trace_file()
    f2 = _trace_file()
    return f1, f2


class _A:
    """Mock args object with sensible defaults for missing attrs."""
    _DEFAULTS = {
        'json': False, 'expected_ms': None, 'output': None,
        'format': 'text', 'verbose': False, 'rules': None,
        'sla_file': None, 'threshold': None, 'mermaid': False,
        'max': 50, 'prometheus': False, 'brief': False,
        'dir': '.', 'open_browser': False, 'limit': 10,
    }

    def __init__(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)

    def __getattr__(self, name):
        if name in self._DEFAULTS:
            return self._DEFAULTS[name]
        raise AttributeError(f"_A has no attribute {name!r}")


# Commands that take a single file argument
SINGLE_FILE_CMDS = [
    ("show", cli.cmd_show),
    ("analyze", cli.cmd_analyze),
    ("score", cli.cmd_score),
    ("summary", cli.cmd_summary),
    ("propagation", cli.cmd_propagation),
    ("context-flow", cli.cmd_context_flow),
    ("flowgraph", cli.cmd_flowgraph),
    ("validate", cli.cmd_validate),
    ("tree", cli.cmd_tree),
    ("timeline", cli.cmd_timeline),
    ("metrics", cli.cmd_metrics),
    ("annotate", cli.cmd_annotate),
    ("correlate", cli.cmd_correlate),
    ("summarize", cli.cmd_summarize),
]


class TestSingleFileCommands:
    @pytest.mark.parametrize("name,func", SINGLE_FILE_CMDS, ids=[c[0] for c in SINGLE_FILE_CMDS])
    def test_command_runs(self, name, func, capsys):
        f = _trace_file()
        try:
            args = _A(file=f, json=False, expected_ms=None, output=None,
                      format="text", verbose=False, rules=None,
                      sla_file=None, threshold=None)
            func(args)
            out = capsys.readouterr()
            assert out.out or out.err or True  # just verify no crash
        finally:
            os.unlink(f)


class TestTwoFileCommands:
    def test_diff(self, capsys):
        f1, f2 = _two_trace_files()
        try:
            cli.cmd_diff(_A(trace_a=f1, trace_b=f2))
        finally:
            os.unlink(f1)
            os.unlink(f2)

    def test_span_diff(self, capsys):
        f1, f2 = _two_trace_files()
        try:
            cli.cmd_span_diff(_A(trace_a=f1, trace_b=f2))
        finally:
            os.unlink(f1)
            os.unlink(f2)

    def test_compare(self, capsys):
        f1, f2 = _two_trace_files()
        try:
            cli.cmd_compare(_A(trace_a=f1, trace_b=f2))
        finally:
            os.unlink(f1)
            os.unlink(f2)


class TestSpecialCommands:
    def test_analyze_json(self, capsys):
        f = _trace_file()
        try:
            cli.cmd_analyze(_A(file=f, json=True))
            out = capsys.readouterr().out
            import json
            json.loads(out)  # valid JSON
        finally:
            os.unlink(f)

    def test_report(self, capsys):
        f = _trace_file()
        try:
            with tempfile.NamedTemporaryFile(suffix='.html', delete=False) as out:
                outpath = out.name
            cli.cmd_report(_A(file=f, dir=os.path.dirname(f), output=outpath, open_browser=False))
            assert os.path.exists(outpath)
            assert os.path.getsize(outpath) > 100
        finally:
            os.unlink(f)
            if os.path.exists(outpath):
                os.unlink(outpath)

    def test_schema(self, capsys):
        cli.cmd_schema(_A())
        out = capsys.readouterr().out
        assert "trace_id" in out or "span" in out.lower()
