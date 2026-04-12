"""Tests for cost tracking and tags."""
from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.export import trace_statistics


def test_span_tags():
    s = Span(name="agent", span_type=SpanType.AGENT, tags=["production", "v2"])
    assert "production" in s.tags


def test_span_cost():
    s = Span(name="llm", span_type=SpanType.TOOL, token_count=1500, estimated_cost_usd=0.03)
    assert s.token_count == 1500
    assert s.estimated_cost_usd == 0.03


def test_trace_statistics_cost():
    trace = ExecutionTrace(task="cost-test")
    s1 = Span(name="llm1", span_type=SpanType.TOOL, token_count=1000, estimated_cost_usd=0.02)
    s1.complete()
    s2 = Span(name="llm2", span_type=SpanType.TOOL, token_count=2000, estimated_cost_usd=0.04)
    s2.complete()
    trace.add_span(s1)
    trace.add_span(s2)
    trace.complete()
    
    stats = trace_statistics(trace)
    assert stats["total_tokens"] == 3000
    assert stats["total_cost_usd"] == 0.06


def test_tag_filter():
    import tempfile
    from pathlib import Path
    from agentguard.query import TraceStore
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        t1 = ExecutionTrace(task="tagged")
        s1 = Span(name="agent", span_type=SpanType.AGENT, tags=["prod"])
        s1.complete()
        t1.add_span(s1)
        t1.complete()
        (traces_dir / f"{t1.trace_id}.json").write_text(t1.to_json())
        
        t2 = ExecutionTrace(task="untagged")
        s2 = Span(name="agent", span_type=SpanType.AGENT)
        s2.complete()
        t2.add_span(s2)
        t2.complete()
        (traces_dir / f"{t2.trace_id}.json").write_text(t2.to_json())
        
        store = TraceStore(str(traces_dir))
        tagged = store.filter(tag="prod")
        assert len(tagged) == 1
        assert tagged[0].task == "tagged"
