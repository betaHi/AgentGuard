"""Tests for handoff recording and context loss detection."""

from agentguard.sdk.handoff import record_handoff, detect_context_loss
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.core.trace import SpanType


def test_record_handoff():
    """record_handoff creates a HANDOFF span."""
    init_recorder(task="handoff-test")
    
    span = record_handoff(
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
