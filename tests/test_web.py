"""Tests for web viewer."""

import json
import tempfile
from pathlib import Path
from agentguard.web.viewer import generate_timeline_html
from agentguard.core.trace import ExecutionTrace, Span, SpanType


def test_generate_html_empty():
    """HTML generation works with no traces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        output = generate_timeline_html(
            traces_dir=str(Path(tmpdir) / "traces"),
            output=str(Path(tmpdir) / "report.html")
        )
        html = Path(output).read_text()
        assert "AgentGuard" in html
        assert "No traces found" in html


def test_generate_html_with_traces():
    """HTML generation works with traces."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        trace = ExecutionTrace(task="Test Task")
        agent = Span(name="my-agent", span_type=SpanType.AGENT)
        tool = Span(name="search", span_type=SpanType.TOOL, parent_span_id=agent.span_id)
        agent.complete()
        tool.complete()
        trace.add_span(agent)
        trace.add_span(tool)
        trace.complete()
        (traces_dir / f"{trace.trace_id}.json").write_text(trace.to_json())
        
        output = generate_timeline_html(
            traces_dir=str(traces_dir),
            output=str(Path(tmpdir) / "report.html")
        )
        html = Path(output).read_text()
        assert "my-agent" in html
        assert "search" in html
        assert "Test Task" in html
