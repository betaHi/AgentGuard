"""Test that parallel siblings don't produce false truncation in context_flow_deep."""
import pytest
from agentguard.context_flow import analyze_context_flow_deep, _are_parallel
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from datetime import datetime, timedelta, timezone

UTC = timezone.utc

def _make_parallel_trace():
    """Build a trace with parallel agents under same parent."""
    t = ExecutionTrace(task="parallel_test")
    now = datetime.now(UTC)
    
    # Parent orchestrator
    t.add_span(Span(
        span_id="orch", span_type=SpanType.AGENT, name="orchestrator",
        status=SpanStatus.COMPLETED,
        started_at=now.isoformat(), ended_at=(now + timedelta(seconds=3)).isoformat(),
        input_data={"query": "test"}, output_data={"result": "done"},
    ))
    
    # Two parallel agents (overlapping timestamps, same parent)
    t.add_span(Span(
        span_id="a1", parent_span_id="orch", span_type=SpanType.AGENT, name="web_researcher",
        status=SpanStatus.COMPLETED,
        started_at=(now + timedelta(milliseconds=100)).isoformat(),
        ended_at=(now + timedelta(seconds=1)).isoformat(),
        input_data={"query": "test"}, output_data={"web_results": [1, 2, 3]},
    ))
    t.add_span(Span(
        span_id="a2", parent_span_id="orch", span_type=SpanType.AGENT, name="academic_researcher",
        status=SpanStatus.COMPLETED,
        started_at=(now + timedelta(milliseconds=150)).isoformat(),
        ended_at=(now + timedelta(seconds=1, milliseconds=200)).isoformat(),
        input_data={"topic": "science"}, output_data={"papers": [4, 5]},
    ))
    
    # Sequential agent after both complete
    t.add_span(Span(
        span_id="a3", parent_span_id="orch", span_type=SpanType.AGENT, name="merger",
        status=SpanStatus.COMPLETED,
        started_at=(now + timedelta(seconds=1, milliseconds=300)).isoformat(),
        ended_at=(now + timedelta(seconds=2)).isoformat(),
        input_data={"partial": "data"}, output_data={"merged": "result"},
    ))
    
    t.started_at = now.isoformat()
    t.ended_at = (now + timedelta(seconds=3)).isoformat()
    return t


def test_are_parallel_overlapping():
    """Overlapping timestamps should be detected as parallel."""
    a = {"started_at": "2025-01-01T00:00:00+00:00", "ended_at": "2025-01-01T00:00:01+00:00"}
    b = {"started_at": "2025-01-01T00:00:00.5+00:00", "ended_at": "2025-01-01T00:00:01.5+00:00"}
    assert _are_parallel(a, b) is True


def test_are_parallel_sequential():
    """Non-overlapping timestamps should not be parallel."""
    a = {"started_at": "2025-01-01T00:00:00+00:00", "ended_at": "2025-01-01T00:00:01+00:00"}
    b = {"started_at": "2025-01-01T00:00:02+00:00", "ended_at": "2025-01-01T00:00:03+00:00"}
    assert _are_parallel(a, b) is False


def test_no_false_truncation_for_parallel_siblings():
    """Parallel siblings must NOT produce transitions (they're independent)."""
    trace = _make_parallel_trace()
    result = analyze_context_flow_deep(trace)
    
    # Should NOT have web_researcher → academic_researcher transition
    for t in result.transitions:
        pair = (t.from_agent, t.to_agent)
        assert pair != ("web_researcher", "academic_researcher"), \
            f"False positive: parallel siblings {pair} should not have a transition"
        assert pair != ("academic_researcher", "web_researcher"), \
            f"False positive: parallel siblings {pair} should not have a transition"


def test_sequential_transitions_preserved():
    """Sequential agents should still produce transitions."""
    trace = _make_parallel_trace()
    result = analyze_context_flow_deep(trace)
    
    # academic_researcher → merger should exist (sequential, not parallel)
    sequential_pairs = {(t.from_agent, t.to_agent) for t in result.transitions}
    # At least one transition to merger should exist
    to_merger = [p for p in sequential_pairs if p[1] == "merger"]
    assert len(to_merger) >= 1, f"Expected at least one transition to merger, got {sequential_pairs}"
