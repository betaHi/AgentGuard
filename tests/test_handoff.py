"""Tests for handoff recording and context loss detection."""

from agentguard.core.trace import SpanType
from agentguard.sdk.handoff import detect_context_loss, record_handoff
from agentguard.sdk.recorder import finish_recording, init_recorder


def test_record_handoff():
    """record_handoff creates a HANDOFF span."""
    init_recorder(task="handoff-test")

    record_handoff(
        from_agent="researcher",
        to_agent="analyst",
        context={"articles": [1, 2, 3], "topic": "AI"},
        summary="Passing 3 articles",
    )

    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].span_type == SpanType.HANDOFF
    assert trace.spans[0].handoff_from == "researcher"
    assert trace.spans[0].handoff_to == "analyst"
    assert trace.spans[0].context_size_bytes > 0
    assert "articles" in trace.spans[0].metadata["handoff.context_keys"]


def test_detect_context_loss_none():
    """No loss when all keys present."""
    result = detect_context_loss(
        sent_context={"a": 1, "b": 2},
        received_input={"a": 1, "b": 2, "c": 3},
    )
    assert result["loss_detected"] is False
    assert result["missing_keys"] == []


def test_detect_context_loss_missing():
    """Detects missing keys."""
    result = detect_context_loss(
        sent_context={"articles": [1, 2], "topic": "AI", "metadata": {}},
        received_input={"articles": [1, 2]},
    )
    assert result["loss_detected"] is True
    assert "topic" in result["missing_keys"]
    assert "metadata" in result["missing_keys"]


def test_detect_context_loss_required():
    """Detects missing required keys."""
    result = detect_context_loss(
        sent_context={"a": 1},
        received_input={"a": 1},
        required_keys=["a", "b"],
    )
    assert result["loss_detected"] is True
    assert "b" in result["required_missing"]


def test_detect_context_loss_critical_keys():
    """Critical keys are surfaced separately from generic missing keys."""
    result = detect_context_loss(
        sent_context={"query": "refund", "notes": "verbose", "priority": "high"},
        received_input={"notes": "verbose"},
        critical_keys=["query", "priority"],
    )
    assert result["loss_detected"] is True
    assert set(result["critical_missing"]) == {"query", "priority"}


def test_analyze_flow_prefers_explicit_handoffs():
    """analyze_flow uses explicit HANDOFF spans instead of inferring from sequence."""
    from datetime import datetime, timedelta

    from agentguard.analysis import analyze_flow
    from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType

    now = datetime.fromisoformat("2026-01-01T00:00:00")

    # Create a trace with 3 sequential agents but only 1 explicit handoff
    root = Span(
        span_id="root", name="coordinator", span_type=SpanType.AGENT,
        started_at=now.isoformat(), ended_at=(now + timedelta(seconds=3)).isoformat(),
    )
    a = Span(
        span_id="a", name="agent_a", span_type=SpanType.AGENT,
        parent_span_id="root",
        started_at=now.isoformat(), ended_at=(now + timedelta(seconds=1)).isoformat(),
    )
    b = Span(
        span_id="b", name="agent_b", span_type=SpanType.AGENT,
        parent_span_id="root",
        started_at=(now + timedelta(seconds=1)).isoformat(),
        ended_at=(now + timedelta(seconds=2)).isoformat(),
    )
    c = Span(
        span_id="c", name="agent_c", span_type=SpanType.AGENT,
        parent_span_id="root",
        started_at=(now + timedelta(seconds=2)).isoformat(),
        ended_at=(now + timedelta(seconds=3)).isoformat(),
    )
    # Only one explicit handoff: a -> b (no handoff between b -> c)
    handoff_span = Span(
        span_id="h1", name="handoff_a_to_b", span_type=SpanType.HANDOFF,
        parent_span_id="root",
        handoff_from="agent_a", handoff_to="agent_b",
        context_size_bytes=100,
        started_at=(now + timedelta(seconds=1)).isoformat(),
        ended_at=(now + timedelta(seconds=1)).isoformat(),
        metadata={"handoff.context_keys": ["result"]},
    )

    trace = ExecutionTrace(
        trace_id="test-explicit-handoff",
        task="test",
        started_at=now.isoformat(),
        ended_at=(now + timedelta(seconds=3)).isoformat(),
        spans=[root, a, b, c, handoff_span],
        status=SpanStatus.COMPLETED,
    )

    flow = analyze_flow(trace)

    # Should only have 1 handoff (from explicit span), NOT 2 (inferred from sequence)
    assert len(flow.handoffs) == 1
    assert flow.handoffs[0].from_agent == "agent_a"
    assert flow.handoffs[0].to_agent == "agent_b"


def test_analyze_flow_falls_back_to_inference():
    """analyze_flow infers handoffs from sequence when no HANDOFF spans exist."""
    from datetime import datetime, timedelta

    from agentguard.analysis import analyze_flow
    from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType

    now = datetime.fromisoformat("2026-01-01T00:00:00")

    root = Span(
        span_id="root", name="coordinator", span_type=SpanType.AGENT,
        started_at=now.isoformat(), ended_at=(now + timedelta(seconds=2)).isoformat(),
    )
    a = Span(
        span_id="a", name="agent_a", span_type=SpanType.AGENT,
        parent_span_id="root",
        started_at=now.isoformat(), ended_at=(now + timedelta(seconds=1)).isoformat(),
    )
    b = Span(
        span_id="b", name="agent_b", span_type=SpanType.AGENT,
        parent_span_id="root",
        started_at=(now + timedelta(seconds=1)).isoformat(),
        ended_at=(now + timedelta(seconds=2)).isoformat(),
    )

    trace = ExecutionTrace(
        trace_id="test-inferred-handoff",
        task="test",
        started_at=now.isoformat(),
        ended_at=(now + timedelta(seconds=2)).isoformat(),
        spans=[root, a, b],
        status=SpanStatus.COMPLETED,
    )

    flow = analyze_flow(trace)

    # Should infer 1 handoff from sequential agents
    assert len(flow.handoffs) == 1
    assert flow.handoffs[0].from_agent == "agent_a"
    assert flow.handoffs[0].to_agent == "agent_b"
