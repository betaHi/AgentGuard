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


class TestViewerParallel:
    """Test that viewer correctly renders parallel traces."""
    
    def test_parallel_trace_renders(self):
        """Parallel trace should produce valid HTML with parallel indicators."""
        from agentguard.builder import TraceBuilder
        from agentguard.web.viewer import trace_to_html_string
        
        trace = (TraceBuilder("parallel viewer test")
            .agent("orchestrator", duration_ms=10000)
                .agent("worker_a", duration_ms=3000).end()
                .agent("worker_b", duration_ms=3000).end()
                .agent("worker_c", duration_ms=3000).end()
            .end()
            .build())
        
        html = trace_to_html_string(trace)
        assert "worker_a" in html
        assert "worker_b" in html
        assert "worker_c" in html
        assert "AgentGuard" in html
    
    def test_failed_trace_renders(self):
        """Failed trace should show error indicators."""
        from agentguard.builder import TraceBuilder
        from agentguard.web.viewer import trace_to_html_string
        
        trace = (TraceBuilder("fail viewer test")
            .agent("bad_agent", duration_ms=1000, status="failed", error="API timeout")
            .end()
            .build())
        
        html = trace_to_html_string(trace)
        assert "FAIL" in html
        assert "bad_agent" in html

    def test_handoff_renders(self):
        """Handoffs should be visible in HTML."""
        from agentguard.builder import TraceBuilder
        from agentguard.web.viewer import trace_to_html_string
        
        trace = (TraceBuilder("handoff viewer test")
            .agent("sender", duration_ms=2000).end()
            .handoff("sender", "receiver", context_size=1500)
            .agent("receiver", duration_ms=3000).end()
            .build())
        
        html = trace_to_html_string(trace)
        assert "sender" in html
        assert "receiver" in html

    def test_score_badge_renders(self):
        """Score badge should be in the HTML."""
        from agentguard.builder import TraceBuilder
        from agentguard.web.viewer import trace_to_html_string
        
        trace = (TraceBuilder("score test")
            .agent("a", duration_ms=1000).end()
            .build())
        
        html = trace_to_html_string(trace)
        assert "score-" in html  # score-a, score-b, etc.
        assert "/100" in html


class TestViewerDiagnostics:
    """Verify diagnostics panels contain expected data."""
    
    def test_cost_panel_shows_tokens(self):
        """Cost panel should show token count."""
        from agentguard.builder import TraceBuilder
        from agentguard.web.viewer import trace_to_html_string
        
        trace = (TraceBuilder("cost test")
            .agent("llm_agent", token_count=5000, cost_usd=0.15)
                .llm_call("gpt4", token_count=4000, cost_usd=0.12)
            .end()
            .build())
        
        html = trace_to_html_string(trace)
        assert "5,000" in html or "9,000" in html  # token count formatted
    
    def test_diagnostics_grid_exists(self):
        """Diagnostics section should be in output."""
        from agentguard.builder import TraceBuilder
        from agentguard.web.viewer import trace_to_html_string
        
        trace = (TraceBuilder("diag test")
            .agent("a", duration_ms=2000)
                .tool("t1", duration_ms=1000)
            .end()
            .agent("b", duration_ms=3000)
            .end()
            .build())
        
        html = trace_to_html_string(trace)
        assert "Orchestration Diagnostics" in html
        assert "Failure Propagation" in html
        assert "Bottleneck" in html
        assert "Handoff Flow" in html
    
    def test_empty_trace_no_crash(self):
        """Generating HTML for empty trace should not crash."""
        from agentguard.web.viewer import trace_to_html_string
        from agentguard.core.trace import ExecutionTrace
        
        html = trace_to_html_string(ExecutionTrace(task="empty"))
        assert "AgentGuard" in html
