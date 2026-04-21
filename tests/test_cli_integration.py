"""CLI integration tests — verify commands work end-to-end."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from agentguard.builder import TraceBuilder


@pytest.fixture
def trace_file(tmp_path):
    """Create a trace JSON file for CLI testing."""
    trace = (TraceBuilder("CLI test pipeline")
        .agent("researcher", duration_ms=3000, token_count=1000, cost_usd=0.03)
            .tool("web_search", duration_ms=1000)
        .end()
        .handoff("researcher", "writer", context_size=500)
        .agent("writer", duration_ms=5000, status="failed", error="timeout")
        .end()
        .build())

    path = tmp_path / "test_trace.json"
    path.write_text(trace.to_json())
    return str(path)


def _run_cli(*args, timeout=10):
    """Run agentguard CLI command."""
    result = subprocess.run(
        [sys.executable, "-m", "agentguard"] + list(args),
        capture_output=True, text=True, timeout=timeout,
    )
    return result


def _run_cli_in_cwd(cwd, *args, timeout=10):
    """Run agentguard CLI command in an isolated working directory."""
    return subprocess.run(
        [sys.executable, "-m", "agentguard"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
    )


def _run_cli_in_cwd_with_env(cwd, env, *args, timeout=10):
    """Run agentguard CLI command in an isolated working directory with custom env."""
    return subprocess.run(
        [sys.executable, "-m", "agentguard"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=cwd,
        env=env,
    )


@pytest.fixture
def traces_workspace(tmp_path):
    """Create a realistic workspace with multiple trace files."""
    traces_dir = tmp_path / ".agentguard" / "traces"
    traces_dir.mkdir(parents=True)

    trace_a = (TraceBuilder("CLI workspace research")
        .agent("researcher", duration_ms=2500, token_count=800, cost_usd=0.02)
            .tool("web_search", duration_ms=900)
        .end()
        .agent("writer", duration_ms=1800, token_count=1200, cost_usd=0.03)
        .end()
        .build())
    trace_b = (TraceBuilder("CLI workspace review")
        .agent("reviewer", duration_ms=2200)
            .tool("llm_review", duration_ms=1300)
        .end()
        .build())

    path_a = traces_dir / "trace_a.json"
    path_b = traces_dir / "trace_b.json"
    path_a.write_text(trace_a.to_json(), encoding="utf-8")
    path_b.write_text(trace_b.to_json(), encoding="utf-8")

    return {
        "cwd": str(tmp_path),
        "traces_dir": str(traces_dir),
        "trace_a": str(path_a),
        "trace_b": str(path_b),
    }


class TestCLI:
    def test_version(self):
        result = _run_cli("version")
        assert result.returncode == 0
        assert "AgentGuard" in result.stdout

    def test_help(self):
        result = _run_cli("--help")
        assert result.returncode == 0
        assert "show" in result.stdout
        assert "score" in result.stdout

    def test_show(self, trace_file):
        result = _run_cli("show", trace_file)
        assert result.returncode == 0
        assert "researcher" in result.stdout

    def test_score(self, trace_file):
        result = _run_cli("score", trace_file)
        assert result.returncode == 0
        assert "/100" in result.stdout

    def test_analyze(self, trace_file):
        result = _run_cli("analyze", trace_file)
        assert result.returncode == 0

    def test_diagnose(self, trace_file):
        result = _run_cli("diagnose", trace_file)
        assert result.returncode == 0
        assert "AGENTGUARD DIAGNOSE" in result.stdout

    def test_timeline(self, trace_file):
        result = _run_cli("timeline", trace_file)
        assert result.returncode == 0
        assert "researcher" in result.stdout

    def test_tree(self, trace_file):
        result = _run_cli("tree", trace_file)
        assert result.returncode == 0

    def test_validate(self, trace_file):
        result = _run_cli("validate", trace_file)
        assert result.returncode == 0

    def test_summarize(self, trace_file):
        result = _run_cli("summarize", trace_file)
        assert result.returncode == 0

    def test_metrics(self, trace_file):
        result = _run_cli("metrics", trace_file)
        assert result.returncode == 0

    def test_schema(self):
        result = _run_cli("schema")
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "title" in data

    def test_diff(self, trace_file, tmp_path):
        """Test diff command with two traces."""
        # Create a second trace
        from agentguard.builder import TraceBuilder
        trace2 = (TraceBuilder("CLI diff test v2")
            .agent("researcher", duration_ms=5000)
            .end()
            .agent("editor", duration_ms=2000)
            .end()
            .build())
        path2 = tmp_path / "trace2.json"
        path2.write_text(trace2.to_json())

        result = _run_cli("diff", trace_file, str(path2))
        assert result.returncode == 0

    def test_flowgraph(self, trace_file):
        result = _run_cli("flowgraph", trace_file)
        assert result.returncode == 0

    def test_flowgraph_mermaid(self, trace_file):
        result = _run_cli("flowgraph", trace_file, "--mermaid")
        assert result.returncode == 0
        assert "graph" in result.stdout

    def test_propagation(self, trace_file):
        result = _run_cli("propagation", trace_file)
        assert result.returncode == 0

    def test_context_flow(self, trace_file):
        result = _run_cli("context-flow", trace_file)
        assert result.returncode == 0

    def test_annotate(self, trace_file):
        result = _run_cli("annotate", trace_file)
        assert result.returncode == 0

    def test_correlate(self, trace_file):
        result = _run_cli("correlate", trace_file)
        assert result.returncode == 0

    def test_dependencies(self, trace_file):
        result = _run_cli("dependencies", trace_file)
        assert result.returncode == 0

    def test_summarize_brief(self, trace_file):
        result = _run_cli("summarize", trace_file, "--brief")
        assert result.returncode == 0


class TestCLIRealSubprocessFlows:
    def test_init_and_doctor(self, tmp_path):
        result = _run_cli_in_cwd(str(tmp_path), "init")
        assert result.returncode == 0
        assert (tmp_path / ".agentguard" / "traces").exists()
        assert (tmp_path / ".agentguard" / "knowledge").exists()
        assert (tmp_path / "agentguard.json").exists()
        config = json.loads((tmp_path / "agentguard.json").read_text(encoding="utf-8"))
        assert config["knowledge_dir"] == ".agentguard/knowledge"

        doctor = _run_cli_in_cwd(str(tmp_path), "doctor")
        assert doctor.returncode == 0
        assert "AgentGuard Doctor" in doctor.stdout
        assert "Knowledge directory" in doctor.stdout

    def test_directory_commands(self, traces_workspace):
        cwd = traces_workspace["cwd"]
        traces_dir = traces_workspace["traces_dir"]

        list_result = _run_cli_in_cwd(cwd, "list", "--dir", traces_dir)
        assert list_result.returncode == 0
        assert "CLI workspace research" in list_result.stdout

        search_result = _run_cli_in_cwd(cwd, "search", "--dir", traces_dir, "--name", "writer")
        assert search_result.returncode == 0
        assert "writer" in search_result.stdout

        aggregate_result = _run_cli_in_cwd(cwd, "aggregate", "--dir", traces_dir)
        assert aggregate_result.returncode == 0
        assert aggregate_result.stdout.strip() != ""
        assert "No traces found." not in aggregate_result.stdout

        report_path = Path(cwd) / ".agentguard" / "workspace-report.html"
        report_result = _run_cli_in_cwd(
            cwd,
            "report",
            "--dir",
            traces_dir,
            "--output",
            str(report_path),
        )
        assert report_result.returncode == 0
        assert report_path.exists()
        assert report_path.stat().st_size > 100

    def test_compare_and_span_diff_subprocess(self, traces_workspace):
        result = _run_cli_in_cwd(
            traces_workspace["cwd"],
            "compare",
            traces_workspace["trace_a"],
            traces_workspace["trace_b"],
        )
        assert result.returncode == 0
        assert result.stdout.strip() != ""

        span_diff = _run_cli_in_cwd(
            traces_workspace["cwd"],
            "span-diff",
            traces_workspace["trace_a"],
            traces_workspace["trace_b"],
        )
        assert span_diff.returncode == 0
        assert span_diff.stdout.strip() != ""

    def test_merge_and_merge_dir_subprocess(self, tmp_path):
        traces_dir = tmp_path / ".agentguard" / "traces"
        traces_dir.mkdir(parents=True)

        parent = (TraceBuilder("distributed parent")
            .agent("coordinator", duration_ms=1000)
            .end()
            .build())
        parent_file = traces_dir / f"{parent.trace_id}.json"
        parent_file.write_text(parent.to_json(), encoding="utf-8")

        child = TraceBuilder("child work").agent("child-agent", duration_ms=500).end().build()
        child.trace_id = parent.trace_id
        for span in child.spans:
            span.trace_id = parent.trace_id
        child_file = traces_dir / f"{parent.trace_id}_child_123.json"
        child_file.write_text(child.to_json(), encoding="utf-8")

        merge_result = _run_cli_in_cwd(str(tmp_path), "merge", str(parent_file))
        assert merge_result.returncode == 0
        assert not child_file.exists()
        merged_data = json.loads(parent_file.read_text(encoding="utf-8"))
        assert any(span["name"] == "child-agent" for span in merged_data["spans"])

        extra_a = traces_dir / "extra_a.json"
        extra_b = traces_dir / "extra_b.json"
        extra_a.write_text(TraceBuilder("extra a").agent("a", duration_ms=100).end().build().to_json(), encoding="utf-8")
        extra_b.write_text(TraceBuilder("extra b").agent("b", duration_ms=120).end().build().to_json(), encoding="utf-8")
        output_file = tmp_path / "merged.json"

        merge_dir = _run_cli_in_cwd(str(tmp_path), "merge-dir", str(traces_dir), "--output", str(output_file))
        assert merge_dir.returncode == 0
        assert output_file.exists()
        merged_dir_data = json.loads(output_file.read_text(encoding="utf-8"))
        assert len(merged_dir_data["spans"]) >= 3

    def test_generate_command_subprocess(self, tmp_path):
        traces_dir = tmp_path / "synthetic-traces"
        result = _run_cli_in_cwd(
            str(tmp_path),
            "generate",
            "--count",
            "3",
            "--agents",
            "2",
            "--failure-rate",
            "0.2",
            "--dir",
            str(traces_dir),
        )
        assert result.returncode == 0
        assert "Saved 3 traces" in result.stdout
        assert len(list(traces_dir.glob("*.json"))) == 3

    def test_import_claude_session_subprocess(self, tmp_path, monkeypatch):
        sdk_root = tmp_path / "fake_sdk"
        sdk_pkg = sdk_root / "claude_agent_sdk"
        sdk_pkg.mkdir(parents=True)
        sdk_pkg.joinpath("__init__.py").write_text(
            """
from dataclasses import dataclass


@dataclass
class SessionMessage:
    type: str
    uuid: str
    session_id: str
    message: object
    parent_tool_use_id: str | None = None


@dataclass
class SessionInfo:
    session_id: str
    summary: str
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None


def get_session_messages(session_id, directory=None):
    return [
        SessionMessage(type=\"user\", uuid=\"u1\", session_id=session_id, message={\"text\": \"Refactor the auth flow\"}),
        SessionMessage(type=\"assistant\", uuid=\"a1\", session_id=session_id, message={\"content\": [{\"text\": \"Planned the refactor and called subagent.\"}]}),
    ]


def get_session_info(session_id, directory=None):
    return SessionInfo(
        session_id=session_id,
        summary=\"Auth refactor session\",
        custom_title=\"auth-refactor\",
        first_prompt=\"Refactor the auth flow\",
        git_branch=\"feature/auth\",
    )


def list_sessions(directory=None, limit=None, offset=0, include_worktrees=True):
    sessions = [
        SessionInfo(
            session_id=\"sess-subprocess\",
            summary=\"Auth refactor session\",
            custom_title=\"auth-refactor\",
            first_prompt=\"Refactor the auth flow\",
            git_branch=\"feature/auth\",
        ),
        SessionInfo(
            session_id=\"sess-other\",
            summary=\"Other session\",
            custom_title=None,
            first_prompt=\"Other prompt\",
            git_branch=\"main\",
        ),
    ]
    return sessions[:limit] if limit is not None else sessions


def list_subagents(session_id, directory=None):
    return [\"reviewer\"]


def get_subagent_messages(session_id, agent_id, directory=None):
    return [
        SessionMessage(type=\"user\", uuid=\"su1\", session_id=session_id, message={\"text\": \"Review the auth patch\"}),
        SessionMessage(type=\"assistant\", uuid=\"sa1\", session_id=session_id, message={\"content\": [{\"text\": \"Found one risky migration edge case.\"}]}),
    ]
""".strip()
            + "\n",
            encoding="utf-8",
        )

        env = dict(monkeypatch._setitem) if False else None
        env = dict(__import__("os").environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(sdk_root) if not existing_pythonpath else f"{sdk_root}:{existing_pythonpath}"

        trace_path = tmp_path / ".agentguard" / "traces" / "claude-session.json"
        report_path = tmp_path / ".agentguard" / "claude-session.html"
        result = _run_cli_in_cwd_with_env(
            str(tmp_path),
            env,
            "import-claude-session",
            "sess-subprocess",
            "--output",
            str(trace_path),
            "--report-output",
            str(report_path),
            "--analyze",
        )

        assert result.returncode == 0
        assert trace_path.exists()
        assert report_path.exists()
        trace = json.loads(trace_path.read_text(encoding="utf-8"))
        assert trace["trace_id"] == "sess-subprocess"
        assert any(span["name"] == "auth-refactor" for span in trace["spans"])
        assert any(span["name"] == "reviewer" for span in trace["spans"])
        assert "Claude Session Imported" in result.stdout
        assert "Failure Propagation Analysis" in result.stdout
        assert "Workflow Patterns" in result.stdout
        assert "Counterfactual" in result.stdout

    def test_diagnose_claude_session_subprocess(self, tmp_path):
        sdk_root = tmp_path / "fake_sdk"
        sdk_pkg = sdk_root / "claude_agent_sdk"
        sdk_pkg.mkdir(parents=True)
        sdk_pkg.joinpath("__init__.py").write_text(
            """
from dataclasses import dataclass


@dataclass
class SessionMessage:
    type: str
    uuid: str
    session_id: str
    message: object
    parent_tool_use_id: str | None = None


@dataclass
class SessionInfo:
    session_id: str
    summary: str
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None


def get_session_messages(session_id, directory=None):
    return [
        SessionMessage(type=\"user\", uuid=\"u1\", session_id=session_id, message={\"text\": \"Refactor the auth flow\"}),
        SessionMessage(type=\"assistant\", uuid=\"a1\", session_id=session_id, message={\"content\": [{\"text\": \"Planned the refactor and called subagent.\"}]})
    ]


def get_session_info(session_id, directory=None):
    return SessionInfo(
        session_id=session_id,
        summary=\"Auth refactor session\",
        custom_title=\"auth-refactor\",
        first_prompt=\"Refactor the auth flow\",
        git_branch=\"feature/auth\",
    )
""".strip()
            + "\n",
            encoding="utf-8",
        )

        env = dict(__import__("os").environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(sdk_root) if not existing_pythonpath else f"{sdk_root}:{existing_pythonpath}"

        trace_path = tmp_path / ".agentguard" / "traces" / "claude-session.json"
        report_path = tmp_path / ".agentguard" / "claude-session.html"
        result = _run_cli_in_cwd_with_env(
            str(tmp_path),
            env,
            "diagnose-claude-session",
            "sess-subprocess",
            "--output",
            str(trace_path),
            "--report-output",
            str(report_path),
        )

        assert result.returncode == 0
        assert trace_path.exists()
        assert report_path.exists()
        assert "AGENTGUARD DIAGNOSE" in result.stdout
        assert f"html={report_path}" in result.stdout

    def test_list_claude_sessions_subprocess(self, tmp_path, monkeypatch):
        sdk_root = tmp_path / "fake_sdk"
        sdk_pkg = sdk_root / "claude_agent_sdk"
        sdk_pkg.mkdir(parents=True)
        sdk_pkg.joinpath("__init__.py").write_text(
            """
from dataclasses import dataclass


@dataclass
class SessionInfo:
    session_id: str
    summary: str
    custom_title: str | None = None
    first_prompt: str | None = None
    git_branch: str | None = None
    cwd: str | None = None
    last_modified: int | None = None


def list_sessions(directory=None, limit=None, offset=0, include_worktrees=True):
    sessions = [
        SessionInfo(
            session_id="sess-1",
            summary="Propagation debugging",
            custom_title="propagation-debug",
            first_prompt="Investigate propagation issue",
            git_branch="main",
            cwd="/tmp/project-a",
            last_modified=1776676129178,
        ),
        SessionInfo(
            session_id="sess-2",
            summary="Other run",
            custom_title=None,
            first_prompt="Other prompt",
            git_branch="feature",
            cwd="/tmp/project-b",
            last_modified=1776676128000,
        ),
    ]
    return sessions[:limit] if limit is not None else sessions
""".strip()
            + "\n",
            encoding="utf-8",
        )

        env = dict(__import__("os").environ)
        existing_pythonpath = env.get("PYTHONPATH", "")
        env["PYTHONPATH"] = str(sdk_root) if not existing_pythonpath else f"{sdk_root}:{existing_pythonpath}"

        result = _run_cli_in_cwd_with_env(
            str(tmp_path),
            env,
            "list-claude-sessions",
            "--limit",
            "5",
            "--project",
            "/tmp/project-a",
        )

        assert result.returncode == 0
        assert "Claude Sessions" in result.stdout
        assert "sess-1" in result.stdout
        assert "propagation-debug" in result.stdout
        assert "sess-2" not in result.stdout

    def test_evolution_commands_persist_across_subprocesses(self, trace_file, tmp_path):
        knowledge_dir = tmp_path / "kb"

        first = _run_cli_in_cwd(str(tmp_path), "learn", trace_file, "--knowledge-dir", str(knowledge_dir))
        second = _run_cli_in_cwd(str(tmp_path), "learn", trace_file, "--knowledge-dir", str(knowledge_dir))
        assert first.returncode == 0
        assert second.returncode == 0

        kb_file = knowledge_dir / "knowledge.json"
        assert kb_file.exists()
        kb = json.loads(kb_file.read_text(encoding="utf-8"))
        assert kb["trace_count"] == 2
        assert any(lesson["occurrences"] == 2 for lesson in kb["lessons"].values())

        suggest = _run_cli_in_cwd(
            str(tmp_path),
            "suggest",
            "--knowledge-dir",
            str(knowledge_dir),
            "--min-confidence",
            "0.6",
        )
        assert suggest.returncode == 0
        assert "Evolution Suggestions" in suggest.stdout
        assert "seen 2x" in suggest.stdout

    def test_evolution_trends_prd_and_auto_apply(self, trace_file, tmp_path):
        knowledge_dir = tmp_path / "kb"
        _run_cli_in_cwd(str(tmp_path), "init")
        for _ in range(3):
            result = _run_cli_in_cwd(str(tmp_path), "learn", trace_file, "--knowledge-dir", str(knowledge_dir))
            assert result.returncode == 0

        trends = _run_cli_in_cwd(str(tmp_path), "trends", "--knowledge-dir", str(knowledge_dir))
        assert trends.returncode == 0
        assert "recurring_failure" in trends.stdout

        prd = _run_cli_in_cwd(
            str(tmp_path),
            "prd",
            "--knowledge-dir",
            str(knowledge_dir),
            "--min-occurrences",
            "2",
        )
        assert prd.returncode == 0
        assert "Improvement PRD" in prd.stdout

        auto_apply = _run_cli_in_cwd(
            str(tmp_path),
            "auto-apply",
            trace_file,
            "--knowledge-dir",
            str(knowledge_dir),
            "--min-confidence",
            "0.6",
            "--write",
        )
        assert auto_apply.returncode == 0
        assert "Updated:" in auto_apply.stdout

        config = json.loads((tmp_path / "agentguard.json").read_text(encoding="utf-8"))
        agent_names = {agent["name"] for agent in config["agents"]}
        assert "researcher" in agent_names or "writer" in agent_names

    def test_evolution_corrupt_kb_warns_and_recovers(self, tmp_path):
        knowledge_dir = tmp_path / "kb"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "knowledge.json").write_text("{broken", encoding="utf-8")

        result = _run_cli_in_cwd(
            str(tmp_path),
            "suggest",
            "--knowledge-dir",
            str(knowledge_dir),
        )
        assert result.returncode == 0
        assert "Recovered" in result.stdout
        assert list(knowledge_dir.glob("knowledge.corrupt.*.json"))

    def test_evolution_invalid_params_and_invalid_config_fail(self, trace_file, tmp_path):
        knowledge_dir = tmp_path / "kb"
        invalid = _run_cli_in_cwd(
            str(tmp_path),
            "suggest",
            "--knowledge-dir",
            str(knowledge_dir),
            "--min-confidence",
            "1.5",
        )
        assert invalid.returncode != 0
        assert "min_confidence must be between 0 and 1" in invalid.stderr

        _run_cli_in_cwd(str(tmp_path), "init")
        for _ in range(3):
            result = _run_cli_in_cwd(str(tmp_path), "learn", trace_file, "--knowledge-dir", str(knowledge_dir))
            assert result.returncode == 0

        (tmp_path / "agentguard.json").write_text("{broken", encoding="utf-8")
        auto_apply = _run_cli_in_cwd(
            str(tmp_path),
            "auto-apply",
            trace_file,
            "--knowledge-dir",
            str(knowledge_dir),
            "--min-confidence",
            "0.6",
            "--write",
        )
        assert auto_apply.returncode != 0
        assert "Invalid config JSON" in auto_apply.stderr
