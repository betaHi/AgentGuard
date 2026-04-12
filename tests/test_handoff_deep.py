"""Tests for deep handoff semantics — context usage tracking."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.sdk.handoff import record_handoff, detect_context_loss, mark_context_used
from agentguard.sdk.recorder import init_recorder, finish_recording, get_recorder


@pytest.fixture(autouse=True)
def setup_recorder():
    """Ensure a clean recorder for each test."""
    init_recorder(task="test")
    yield
    try:
        finish_recording()
    except Exception:
        pass


class TestMarkContextUsed:
    """Tests for mark_context_used tracking."""

    def test_basic_usage_tracking(self):
        """Track which keys the receiver actually used."""
        ctx = {"articles": [1, 2, 3], "topic": "AI", "metadata": {"source": "web"}}
        h = record_handoff("collector", "analyst", context=ctx, summary="3 articles")
        
        result = mark_context_used(h, used_keys=["articles", "topic"])
        
        assert result["used_keys"] == ["articles", "topic"]
        assert result["dropped_keys"] == ["metadata"]
        assert result["utilization_ratio"] == pytest.approx(0.67, abs=0.01)
        assert h.context_used_keys == ["articles", "topic"]
        assert h.context_dropped_keys == ["metadata"]

    def test_full_utilization(self):
        """All context keys used = 100% utilization."""
        ctx = {"query": "test", "results": [1]}
        h = record_handoff("search", "parser", context=ctx)
        
        result = mark_context_used(h, used_keys=["query", "results"])
        assert result["utilization_ratio"] == 1.0
        assert result["dropped_keys"] == []

    def test_zero_utilization(self):
        """No context keys used = 0% utilization."""
        ctx = {"a": 1, "b": 2, "c": 3}
        h = record_handoff("agent_a", "agent_b", context=ctx)
        
        result = mark_context_used(h, used_keys=[])
        assert result["utilization_ratio"] == 0.0
        assert set(result["dropped_keys"]) == {"a", "b", "c"}

    def test_extra_keys_used(self):
        """Receiver used keys not in the original context (e.g., enrichment)."""
        ctx = {"data": "raw"}
        h = record_handoff("fetcher", "enricher", context=ctx)
        
        result = mark_context_used(h, used_keys=["data", "external_source"])
        assert result["extra_used"] == ["external_source"]
        assert result["utilization_ratio"] == 1.0  # used all sent keys

    def test_with_received_context(self):
        """Track received context size for comparison."""
        ctx = {"articles": [1, 2, 3], "meta": "info"}
        h = record_handoff("collector", "analyst", context=ctx)
        
        received = {"articles": [1, 2, 3]}  # meta dropped during transfer
        result = mark_context_used(h, used_keys=["articles"], received_context=received)
        
        assert h.context_received is not None
        assert h.context_received["size_bytes"] > 0
        assert "articles" in h.context_received["keys"]

    def test_metadata_updated(self):
        """Handoff metadata should be updated with usage info."""
        ctx = {"x": 1, "y": 2}
        h = record_handoff("a", "b", context=ctx)
        mark_context_used(h, used_keys=["x"])
        
        assert h.metadata["handoff.used_keys"] == ["x"]
        assert h.metadata["handoff.dropped_keys"] == ["y"]
        assert h.metadata["handoff.utilization"] == 0.5


class TestDetectContextLossDeep:
    """Extended tests for context loss detection."""

    def test_no_loss(self):
        """No loss when all keys transferred."""
        result = detect_context_loss(
            sent_context={"a": 1, "b": 2},
            received_input={"a": 1, "b": 2},
        )
        assert result["loss_detected"] is False
        assert result["missing_keys"] == []

    def test_partial_loss(self):
        """Detect missing keys."""
        result = detect_context_loss(
            sent_context={"a": 1, "b": 2, "c": 3},
            received_input={"a": 1},
        )
        assert result["loss_detected"] is True
        assert set(result["missing_keys"]) == {"b", "c"}

    def test_required_keys_missing(self):
        """Required keys that are missing."""
        result = detect_context_loss(
            sent_context={"a": 1, "b": 2},
            received_input={"a": 1},
            required_keys=["b", "c"],
        )
        assert result["loss_detected"] is True
        assert "b" in result["required_missing"]
        assert "c" in result["required_missing"]

    def test_size_tracking(self):
        """Size delta should be calculated."""
        result = detect_context_loss(
            sent_context={"data": "x" * 1000},
            received_input={"data": "x" * 100},
        )
        assert result["sent_size_bytes"] > result["received_size_bytes"]
        assert result["size_delta_bytes"] < 0


class TestHandoffSerialization:
    """Test that new handoff fields survive serialization."""

    def test_context_used_roundtrip(self):
        """New fields should survive to_dict/from_dict roundtrip."""
        span = Span(
            span_type=SpanType.HANDOFF,
            name="a → b",
            context_used_keys=["data"],
            context_dropped_keys=["meta"],
            context_received={"size_bytes": 10, "keys": ["data"]},
            context_size_bytes=50,
            handoff_from="a",
            handoff_to="b",
        )
        
        trace = ExecutionTrace(task="test")
        trace.add_span(span)
        
        d = trace.to_dict()
        restored = ExecutionTrace.from_dict(d)
        rs = restored.spans[0]
        
        assert rs.context_used_keys == ["data"]
        assert rs.context_dropped_keys == ["meta"]
        assert rs.context_received == {"size_bytes": 10, "keys": ["data"]}
