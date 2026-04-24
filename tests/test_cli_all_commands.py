"""Test: all CLI commands work end-to-end with real trace files.

Parametrized over every command that takes a trace file argument.
Commands that need special args or no file are tested separately.
"""

import os
import tempfile
from pathlib import Path

import pytest

from agentguard.builder import TraceBuilder
from agentguard.cli import main as cli
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.runtime.claude.session_import import ClaudeSessionImportError


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
            capsys.readouterr()
            assert True  # just verify no crash
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

    def test_diagnose_prints_dense_output_and_report(self, capsys, tmp_path):
        f = _trace_file()
        try:
            report_path = tmp_path / "diagnose-report.html"
            cli.cmd_diagnose(_A(file=f, report_output=str(report_path)))
            out = capsys.readouterr().out
            assert "AGENTGUARD DIAGNOSE" in out
            assert "\u25B8 failures" in out
            assert f"html={report_path}" in out
            assert report_path.exists()
        finally:
            os.unlink(f)

    def test_diagnose_auto_emits_html_next_to_trace(self, capsys, tmp_path):
        # Create a trace file in an isolated directory so we control the
        # adjacent HTML path the CLI should auto-derive.
        src = _trace_file()
        try:
            trace_path = tmp_path / "auto-html.json"
            trace_path.write_bytes(Path(src).read_bytes())
            cli.cmd_diagnose(_A(file=str(trace_path), report_output=None))
        finally:
            os.unlink(src)

        expected_html = trace_path.with_suffix(".html")
        out = capsys.readouterr().out
        assert "AGENTGUARD DIAGNOSE" in out
        assert f"html={expected_html}" in out
        assert expected_html.exists()

    def test_import_claude_session_writes_trace_and_report(self, capsys, monkeypatch, tmp_path):
        trace = ExecutionTrace(task="Imported Claude session")
        root = Span(name="claude-session", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        trace.add_span(root)
        trace.complete()

        captured = {}

        def _fake_import(session_id, directory=None, include_subagents=True):
            captured["session_id"] = session_id
            captured["directory"] = directory
            captured["include_subagents"] = include_subagents
            return trace

        def _fake_report(_trace, output):
            Path(output).write_text("<html>report</html>", encoding="utf-8")
            return output

        monkeypatch.setattr("agentguard.runtime.claude.import_claude_session", _fake_import)
        monkeypatch.setattr("agentguard.web.viewer.generate_report_from_trace", _fake_report)

        output_path = tmp_path / "imported-trace.json"
        report_path = tmp_path / "imported-report.html"
        cli.cmd_import_claude_session(
            _A(
                session_id="sess-123",
                directory="/tmp/claude",
                no_subagents=False,
                output=str(output_path),
                report_output=str(report_path),
            )
        )

        out = capsys.readouterr().out
        assert captured == {
            "session_id": "sess-123",
            "directory": "/tmp/claude",
            "include_subagents": True,
        }
        assert output_path.exists()
        assert report_path.exists()
        assert "Claude Session Imported" in out
        assert "sess-123" in out

    def test_import_claude_session_can_skip_subagents(self, monkeypatch, tmp_path):
        trace = ExecutionTrace(task="Imported Claude session")
        trace.add_span(Span(name="claude-session", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        trace.complete()
        captured = {}

        def _fake_import(session_id, directory=None, include_subagents=True):
            captured["include_subagents"] = include_subagents
            return trace

        monkeypatch.setattr("agentguard.runtime.claude.import_claude_session", _fake_import)

        cli.cmd_import_claude_session(
            _A(
                session_id="sess-456",
                directory=None,
                no_subagents=True,
                output=str(tmp_path / "trace.json"),
                report_output=None,
            )
        )

        assert captured["include_subagents"] is False

    def test_import_claude_session_can_print_analysis(self, capsys, monkeypatch, tmp_path):
        trace = ExecutionTrace(task="Imported Claude session")
        trace.add_span(Span(name="claude-session", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        trace.complete()

        monkeypatch.setattr("agentguard.runtime.claude.import_claude_session", lambda *args, **kwargs: trace)

        cli.cmd_import_claude_session(
            _A(
                session_id="sess-789",
                directory=None,
                no_subagents=False,
                output=str(tmp_path / "trace.json"),
                report_output=None,
                analyze=True,
            )
        )

        out = capsys.readouterr().out
        assert "Claude Session Imported" in out
        assert "Failure Propagation Analysis" in out
        assert "Workflow Patterns" in out
        assert "Counterfactual" in out

    def test_import_claude_session_reports_user_facing_error(self, capsys, monkeypatch):
        def _raise(*args, **kwargs):
            raise ClaudeSessionImportError("No Claude session messages found for session 'sess-missing'")

        monkeypatch.setattr("agentguard.runtime.claude.import_claude_session", _raise)

        with pytest.raises(SystemExit):
            cli.cmd_import_claude_session(
                _A(
                    session_id="sess-missing",
                    directory=None,
                    no_subagents=False,
                    output=None,
                    report_output=None,
                )
            )

        err = capsys.readouterr().err
        assert "No Claude session messages found" in err
        assert "--directory <claude-session-dir>" in err

    def test_diagnose_claude_session_prints_dense_output(self, capsys, monkeypatch, tmp_path):
        trace = ExecutionTrace(task="Imported Claude session")
        trace.add_span(Span(name="claude-session", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        trace.complete()

        monkeypatch.setattr("agentguard.runtime.claude.import_claude_session", lambda *args, **kwargs: trace)

        report_path = tmp_path / "claude-report.html"
        cli.cmd_diagnose_claude_session(
            _A(
                session_id="sess-dense",
                directory=None,
                no_subagents=False,
                output=str(tmp_path / "trace.json"),
                report_output=str(report_path),
            )
        )

        out = capsys.readouterr().out
        assert "AGENTGUARD DIAGNOSE" in out
        assert "trace=" in out
        assert f"html={report_path}" in out
        assert report_path.exists()

    def test_diagnose_claude_session_auto_emits_html_next_to_trace(self, capsys, monkeypatch, tmp_path):
        trace = ExecutionTrace(task="Imported Claude session")
        trace.add_span(Span(name="claude-session", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED))
        trace.complete()

        monkeypatch.setattr("agentguard.runtime.claude.import_claude_session", lambda *args, **kwargs: trace)

        trace_path = tmp_path / "auto-session.json"
        cli.cmd_diagnose_claude_session(
            _A(
                session_id="sess-auto-html",
                directory=None,
                no_subagents=False,
                output=str(trace_path),
                report_output=None,
            )
        )

        expected_html = trace_path.with_suffix(".html")
        out = capsys.readouterr().out
        assert "AGENTGUARD DIAGNOSE" in out
        assert f"trace={trace_path}" in out
        assert f"html={expected_html}" in out
        assert expected_html.exists()

    def test_list_claude_sessions_prints_recent_sessions(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agentguard.runtime.claude.list_claude_sessions",
            lambda directory=None, limit=None, include_worktrees=True: [
                type(
                    "Session",
                    (),
                    {
                        "session_id": "sess-1",
                        "summary": "Propagation debugging",
                        "cwd": "/tmp/project",
                        "git_branch": "main",
                        "custom_title": "propagation-debug",
                        "first_prompt": "Investigate propagation issue",
                        "last_modified": 1776676129178,
                    },
                )()
            ],
        )

        cli.cmd_list_claude_sessions(_A(directory=None, limit=10, project=None, no_worktrees=False))

        out = capsys.readouterr().out
        assert "Claude Sessions" in out
        assert "sess-1" in out
        assert "propagation-debug" in out

    def test_list_claude_sessions_filters_by_project(self, capsys, monkeypatch):
        monkeypatch.setattr(
            "agentguard.runtime.claude.list_claude_sessions",
            lambda directory=None, limit=None, include_worktrees=True: [
                type("Session", (), {"session_id": "sess-a", "summary": "A", "cwd": "/tmp/a", "git_branch": None, "custom_title": None, "first_prompt": None, "last_modified": None})(),
                type("Session", (), {"session_id": "sess-b", "summary": "B", "cwd": "/tmp/b", "git_branch": None, "custom_title": None, "first_prompt": None, "last_modified": None})(),
            ],
        )

        cli.cmd_list_claude_sessions(_A(directory=None, limit=10, project="/tmp/b", no_worktrees=False))

        out = capsys.readouterr().out
        assert "sess-b" in out
        assert "sess-a" not in out

    def test_list_claude_sessions_all_groups_by_project(self, capsys, monkeypatch):
        captured: dict = {}

        def fake_list(directory=None, limit=None, include_worktrees=True):
            captured["limit"] = limit
            return [
                type("Session", (), {"session_id": "sess-a1", "summary": "A1", "cwd": "/tmp/proj-a", "git_branch": "main", "custom_title": None, "first_prompt": None, "last_modified": 2000})(),
                type("Session", (), {"session_id": "sess-b1", "summary": "B1", "cwd": "/tmp/proj-b", "git_branch": None, "custom_title": None, "first_prompt": None, "last_modified": 3000})(),
                type("Session", (), {"session_id": "sess-a2", "summary": "A2", "cwd": "/tmp/proj-a", "git_branch": None, "custom_title": None, "first_prompt": None, "last_modified": 1000})(),
            ]

        monkeypatch.setattr("agentguard.runtime.claude.list_claude_sessions", fake_list)

        args = _A(
            directory=None,
            limit=10,
            project=None,
            no_worktrees=False,
        )
        args.all = True
        args.group_by_project = True
        cli.cmd_list_claude_sessions(args)

        out = capsys.readouterr().out
        # --all must disable the CLI limit when loading sessions.
        assert captured["limit"] is None
        # Grouping headers show project paths with session counts.
        assert "/tmp/proj-a" in out
        assert "/tmp/proj-b" in out
        assert "(2 sessions)" in out
        assert "(1 session)" in out
        # All three session ids are present.
        for sid in ("sess-a1", "sess-a2", "sess-b1"):
            assert sid in out
        # The more recently updated project group should come first.
        assert out.index("/tmp/proj-b") < out.index("/tmp/proj-a")

    def test_list_claude_sessions_compact_output_for_non_tty(self, capsys, monkeypatch):
        """Non-TTY output must be ANSI-free and one line per session.

        This keeps output cheap to ingest for LLM/pipeline consumers
        (e.g. the Claude Code plugin bash tool) even when listing many
        sessions.
        """
        def fake_list(directory=None, limit=None, include_worktrees=True):
            return [
                type("Session", (), {"session_id": "sess-a1", "summary": "Title A1", "cwd": "/tmp/proj-a", "git_branch": "main", "custom_title": None, "first_prompt": None, "last_modified": 2000})(),
                type("Session", (), {"session_id": "sess-b1", "summary": "Title B1", "cwd": "/tmp/proj-b", "git_branch": None, "custom_title": None, "first_prompt": None, "last_modified": 3000})(),
            ]

        monkeypatch.setattr("agentguard.runtime.claude.list_claude_sessions", fake_list)

        args = _A(directory=None, limit=10, project=None, no_worktrees=False)
        args.all = True
        args.group_by_project = True
        cli.cmd_list_claude_sessions(args)

        out = capsys.readouterr().out
        # capsys makes stdout non-tty -> compact format must kick in.
        assert "\x1b[" not in out, "compact output must not contain ANSI escapes"
        # Each session should live on a single line with tab-separated fields.
        a_line = next(line for line in out.splitlines() if "sess-a1" in line)
        b_line = next(line for line in out.splitlines() if "sess-b1" in line)
        assert "\t" in a_line and "\t" in b_line
        assert "Title A1" in a_line and "main" in a_line
        # Group header uses bracketed cwd instead of bold ANSI.
        assert "[/tmp/proj-a]" in out
        assert "[/tmp/proj-b]" in out

    def test_analyze_shows_evidence_reference_loss_and_grounding_breakdown(self, capsys):
        trace = ExecutionTrace(task="cli evidence risk")
        parent = Span(name="coordinator", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        sender = Span(
            name="reranker",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            output_data={
                "top_documents": [
                    {"doc_id": "doc-1", "title": "one"},
                    {"doc_id": "doc-2", "title": "two"},
                    {"doc_id": "doc-3", "title": "three"},
                ],
                "source_map": {"doc-1": "u1", "doc-2": "u2", "doc-3": "u3"},
                "summary": "brief",
            },
        )
        receiver = Span(
            name="generator",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            input_data={
                "top_documents": [
                    {"doc_id": "doc-1", "title": "one"},
                    {"doc_id": "doc-2", "title": "two"},
                ],
                "source_map": {"doc-1": "u1", "doc-2": "u2"},
                "summary": "brief",
            },
            output_data={
                "claims": ["c1", "c2", "c3"],
                "citations": ["doc-1", "doc-2"],
                "unverified_claims": ["c3"],
            },
            token_count=1200,
            estimated_cost_usd=0.05,
        )
        for span in [parent, sender, receiver]:
            trace.add_span(span)
        trace.complete()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            handle.write(trace.to_json())
            trace_file = handle.name
        try:
            cli.cmd_analyze(_A(file=trace_file, json=False))
            out = capsys.readouterr().out
            assert "evidence refs" in out
            assert "doc-3" in out
            assert "grounding issues" in out
            assert "missing refs" in out
        finally:
            os.unlink(trace_file)

    def test_analyze_shows_decision_impact(self, capsys):
        trace = ExecutionTrace(task="cli decision impact")
        router = Span(name="router", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        decision = Span(
            name="router → buggy-agent (decision)",
            span_type=SpanType.HANDOFF,
            parent_span_id=router.span_id,
            status=SpanStatus.COMPLETED,
            metadata={
                "decision.type": "orchestration",
                "decision.coordinator": "router",
                "decision.chosen": "buggy-agent",
                "decision.alternatives": ["stable-agent"],
            },
        )
        buggy = Span(
            name="buggy-agent",
            span_type=SpanType.AGENT,
            parent_span_id=router.span_id,
            status=SpanStatus.FAILED,
            error="crash",
        )
        stable = Span(
            name="stable-agent",
            span_type=SpanType.AGENT,
            parent_span_id=router.span_id,
            status=SpanStatus.COMPLETED,
        )
        for span in [router, decision, buggy, stable]:
            trace.add_span(span)
        trace.complete()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            handle.write(trace.to_json())
            trace_file = handle.name
        try:
            cli.cmd_analyze(_A(file=trace_file, json=False))
            out = capsys.readouterr().out
            assert "Context Flow" in out
            assert "Worst path" in out
            assert "Cost-Yield Analysis" in out
            assert "Decision Impact" in out
            assert "Counterfactual" in out
            assert "Consider" in out
            assert "stable-agent" in out
            assert "buggy-agent" in out
        finally:
            os.unlink(trace_file)

    def test_analyze_shows_high_risk_handoffs(self, capsys):
        trace = ExecutionTrace(task="cli context risk")
        parent = Span(name="coordinator", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        sender = Span(
            name="sender",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            output_data={"query": "refund", "priority": "high", "notes": "keep"},
        )
        receiver = Span(
            name="receiver",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.FAILED,
            error="missing query",
            input_data={"notes": "keep"},
        )
        for span in [parent, sender, receiver]:
            trace.add_span(span)
        trace.complete()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            handle.write(trace.to_json())
            trace_file = handle.name
        try:
            cli.cmd_analyze(_A(file=trace_file, json=False))
            out = capsys.readouterr().out
            assert "Context Flow" in out
            assert "sender" in out and "receiver" in out
            assert "downstream failure" in out
            assert "high" in out or "severe" in out
        finally:
            os.unlink(trace_file)
