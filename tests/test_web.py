"""Tests for web viewer — verifies analysis layer integration."""

import json
import tempfile
from pathlib import Path
from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.web.viewer import generate_timeline_html


def _write_trace(traces_dir: Path, trace: ExecutionTrace):
    traces_dir.mkdir(parents=True, exist_ok=True)
    (traces_dir / f"{trace.trace_id}.json").write_text(trace.to_json())


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
        t = ExecutionTrace(task="Test Task")
        a = Span(name="my-agent", span_type=SpanType.AGENT)
        tool = Span(name="search", span_type=SpanType.TOOL, parent_span_id=a.span_id)
        a.complete()
        tool.complete()
        t.add_span(a)
        t.add_span(tool)
        t.complete()
        _write_trace(traces_dir, t)
        
        output = generate_timeline_html(
            traces_dir=str(traces_dir),
            output=str(Path(tmpdir) / "report.html")
        )
        html = Path(output).read_text()
        assert "my-agent" in html
        assert "search" in html
        assert "Agents (" in html  # sidebar header shows agent count


def test_web_shows_failure_diagnostics():
    """Web panel shows failure analysis from analysis.py."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        t = ExecutionTrace(task="Failure Test")
        coord = Span(name="coordinator", span_type=SpanType.AGENT)
        
        agent_a = Span(name="agent-a", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
        tool = Span(name="search", span_type=SpanType.TOOL, parent_span_id=agent_a.span_id)
        tool.fail("timeout")
        agent_a.fail("search failed")
        
        agent_b = Span(name="agent-b", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
        agent_b.complete()
        coord.complete()
        
        for s in [coord, agent_a, tool, agent_b]:
            t.add_span(s)
        t.complete()
        _write_trace(traces_dir, t)
        
        output = generate_timeline_html(str(traces_dir), str(Path(tmpdir) / "r.html"))
        html = Path(output).read_text()
        
        # Should show unhandled failure from analysis layer
        assert "unhandled" in html.lower(), "Should show unhandled failure count"
        # Should show root cause
        assert "agent-a" in html, "Should show failed agent name"


def test_web_shows_handoff():
    """Web panel shows handoff from analysis.py."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        t = ExecutionTrace(task="Handoff Test")
        coord = Span(name="coordinator", span_type=SpanType.AGENT)
        a = Span(name="researcher", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
        a.complete(output={"data": [1, 2]})
        b = Span(name="analyst", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
        b.complete()
        coord.complete()
        for s in [coord, a, b]:
            t.add_span(s)
        t.complete()
        _write_trace(traces_dir, t)
        
        output = generate_timeline_html(str(traces_dir), str(Path(tmpdir) / "r.html"))
        html = Path(output).read_text()
        
        assert "handoff" in html.lower(), "Should show handoff indicator"
        assert "researcher" in html
        assert "analyst" in html


def test_web_shows_bottleneck():
    """Web panel shows bottleneck from analysis.py."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        t = ExecutionTrace(task="Bottleneck Test")
        coord = Span(name="coordinator", span_type=SpanType.AGENT)
        fast = Span(name="fast-agent", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
        fast.complete()
        slow = Span(name="slow-agent", span_type=SpanType.AGENT, parent_span_id=coord.span_id)
        slow.complete()
        coord.complete()
        for s in [coord, fast, slow]:
            t.add_span(s)
        t.complete()
        _write_trace(traces_dir, t)
        
        output = generate_timeline_html(str(traces_dir), str(Path(tmpdir) / "r.html"))
        html = Path(output).read_text()
        assert "bottleneck" in html.lower(), "Should show bottleneck indicator"


def test_web_xss_prevention():
    """All user-controlled fields are HTML-escaped."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        t = ExecutionTrace(task='<script>alert("xss")</script>')
        s = Span(name='<img onerror=alert(1)>', span_type=SpanType.AGENT,
                 metadata={"agent_version": '<script>v</script>'})
        s.fail(error='<script>cookie</script>')
        t.add_span(s)
        t.fail()
        _write_trace(traces_dir, t)
        
        output = generate_timeline_html(str(traces_dir), str(Path(tmpdir) / "r.html"))
        html = Path(output).read_text()
        assert '<script>alert' not in html
        assert '<img onerror' not in html
        assert '&lt;script&gt;' in html
