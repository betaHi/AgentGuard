"""CLI integration tests — verify commands work end-to-end."""

import pytest
import subprocess
import sys
import json
import tempfile
import os
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
