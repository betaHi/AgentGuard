"""Tests for fail-open behavior of @record_agent and @record_tool decorators.

The decorators must NEVER break the user's function, even when the recorder
is broken, misconfigured, or throws exceptions.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from agentguard.sdk.async_decorators import record_agent_async, record_tool_async
from agentguard.sdk.decorators import (
    _try_complete_span,
    _try_fail_span,
    _try_pop_span,
    _try_start_span,
    record_agent,
    record_tool,
)


class TestSyncFailOpen:
    """Sync decorators must be fail-open."""

    def test_agent_works_when_recorder_broken(self):
        """User function returns normally even if recorder throws."""
        @record_agent(name="test-agent")
        def my_agent(x):
            return x * 2

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            assert my_agent(5) == 10

    def test_tool_works_when_recorder_broken(self):
        @record_tool(name="test-tool")
        def my_tool(q):
            return [q]

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            assert my_tool("hello") == ["hello"]

    def test_agent_exception_still_raised(self):
        """User exceptions propagate even when recorder is broken."""
        @record_agent(name="test-agent")
        def failing_agent():
            raise ValueError("user error")

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            with pytest.raises(ValueError, match="user error"):
                failing_agent()

    def test_tool_exception_still_raised(self):
        @record_tool(name="test-tool")
        def failing_tool():
            raise TypeError("bad input")

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            with pytest.raises(TypeError, match="bad input"):
                failing_tool()

    def test_complete_span_fails_silently(self):
        """If span.complete() throws, the result still returns."""
        @record_agent(name="test-agent")
        def my_agent():
            return 42

        mock_recorder = MagicMock()
        mock_recorder.current_span_id = None
        with patch("agentguard.sdk.decorators.get_recorder", return_value=mock_recorder):
            # Make Span.complete throw
            with patch("agentguard.core.trace.Span.complete", side_effect=RuntimeError("oops")):
                assert my_agent() == 42

    def test_pop_span_fails_silently(self):
        """If pop_span throws, function still works."""
        mock_recorder = MagicMock()
        mock_recorder.current_span_id = None
        mock_recorder.pop_span.side_effect = RuntimeError("stack corrupt")
        with patch("agentguard.sdk.decorators.get_recorder", return_value=mock_recorder):
            @record_agent(name="test-agent")
            def my_agent():
                return "ok"
            assert my_agent() == "ok"


class TestAsyncFailOpen:
    """Async decorators must be fail-open."""

    def test_async_agent_works_when_recorder_broken(self):
        @record_agent_async(name="test-agent")
        async def my_agent(x):
            return x + 1

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            result = asyncio.run(my_agent(10))
            assert result == 11

    def test_async_tool_works_when_recorder_broken(self):
        @record_tool_async(name="test-tool")
        async def my_tool(q):
            return {"result": q}

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            result = asyncio.run(my_tool("test"))
            assert result == {"result": "test"}

    def test_async_exception_still_raised(self):
        @record_agent_async(name="test-agent")
        async def failing():
            raise ValueError("async error")

        with patch("agentguard.sdk.decorators.get_recorder", side_effect=RuntimeError("broken")):
            with pytest.raises(ValueError, match="async error"):
                asyncio.run(failing())


class TestHelpers:
    """Test fail-open helper functions directly."""

    def test_try_start_span_returns_none_on_error(self):
        with patch("agentguard.sdk.decorators.get_recorder", side_effect=Exception):
            assert _try_start_span("x", "v1", None, (), {}) is None

    def test_try_complete_span_none_is_noop(self):
        _try_complete_span(None, "result")  # should not raise

    def test_try_fail_span_none_is_noop(self):
        _try_fail_span(None, ValueError("x"))  # should not raise

    def test_try_pop_span_none_is_noop(self):
        _try_pop_span(None)  # should not raise
