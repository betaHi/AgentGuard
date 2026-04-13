"""Tests for auto-extraction of cost/token fields from output_data."""

from unittest.mock import MagicMock, patch

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.decorators import _auto_extract_cost_fields, record_agent


class TestAutoExtractCost:
    def test_extracts_cost_usd(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"result": "ok", "cost_usd": 0.05})
        assert s.estimated_cost_usd == 0.05

    def test_extracts_cost_key(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"cost": 0.03})
        assert s.estimated_cost_usd == 0.03

    def test_extracts_token_count(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"token_count": 150})
        assert s.token_count == 150

    def test_extracts_tokens_used(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"tokens_used": 200})
        assert s.token_count == 200

    def test_extracts_total_tokens(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"total_tokens": 300})
        assert s.token_count == 300

    def test_no_overwrite_existing(self):
        """Don't overwrite explicitly set values."""
        s = Span(span_type=SpanType.AGENT, name="a")
        s.estimated_cost_usd = 1.0
        s.token_count = 999
        _auto_extract_cost_fields(s, {"cost_usd": 0.01, "token_count": 1})
        assert s.estimated_cost_usd == 1.0
        assert s.token_count == 999

    def test_non_dict_is_noop(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, "just a string")
        assert s.estimated_cost_usd is None

    def test_zero_cost_ignored(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"cost_usd": 0})
        assert s.estimated_cost_usd is None

    def test_negative_cost_ignored(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"cost_usd": -1.0})
        assert s.estimated_cost_usd is None

    def test_string_cost_ignored(self):
        s = Span(span_type=SpanType.AGENT, name="a")
        _auto_extract_cost_fields(s, {"cost_usd": "expensive"})
        assert s.estimated_cost_usd is None

    def test_decorated_fn_extracts(self):
        """End-to-end: decorated function returning cost dict."""
        mock_recorder = MagicMock()
        mock_recorder.current_span_id = None
        mock_recorder._sampled = True

        @record_agent(name="test")
        def my_agent():
            return {"answer": 42, "cost_usd": 0.02, "token_count": 100}

        with patch("agentguard.sdk.decorators.get_recorder", return_value=mock_recorder):
            result = my_agent()
        assert result == {"answer": 42, "cost_usd": 0.02, "token_count": 100}
