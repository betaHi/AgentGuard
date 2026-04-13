"""Tests for span lifecycle hooks."""

import pytest

from agentguard.core.trace import Span, SpanStatus, SpanType
from agentguard.sdk.hooks import HookRegistry, get_hook_registry, reset_hooks


@pytest.fixture(autouse=True)
def clean_hooks():
    reset_hooks()
    yield
    reset_hooks()


class TestHookRegistry:
    """Tests for HookRegistry."""

    def test_on_start(self):
        """Start hooks should fire when fire_start is called."""
        registry = HookRegistry()
        events = []
        registry.on_start(lambda span: events.append(f"start:{span.name}"))

        span = Span(name="test_agent", span_type=SpanType.AGENT)
        registry.fire_start(span)

        assert events == ["start:test_agent"]

    def test_on_complete(self):
        """Completion hooks should fire."""
        registry = HookRegistry()
        events = []
        registry.on_complete(lambda span: events.append(f"complete:{span.name}"))

        span = Span(name="test_agent", status=SpanStatus.COMPLETED)
        registry.fire_complete(span)

        assert events == ["complete:test_agent"]

    def test_on_error(self):
        """Error hooks should receive span and exception."""
        registry = HookRegistry()
        captured = []
        registry.on_error(lambda span, err: captured.append((span.name, str(err))))

        span = Span(name="failing_agent", status=SpanStatus.FAILED)
        registry.fire_error(span, ValueError("test error"))

        assert len(captured) == 1
        assert captured[0] == ("failing_agent", "test error")

    def test_on_handoff(self):
        """Handoff hooks should fire."""
        registry = HookRegistry()
        events = []
        registry.on_handoff(lambda span: events.append(span.name))

        span = Span(name="a → b", span_type=SpanType.HANDOFF)
        registry.fire_handoff(span)

        assert events == ["a → b"]

    def test_type_filter(self):
        """Type-filtered hooks should only fire for matching span types."""
        registry = HookRegistry()
        agent_events = []
        tool_events = []

        registry.on_start(lambda span: agent_events.append(span.name), span_type=SpanType.AGENT)
        registry.on_start(lambda span: tool_events.append(span.name), span_type=SpanType.TOOL)

        agent_span = Span(name="my_agent", span_type=SpanType.AGENT)
        tool_span = Span(name="my_tool", span_type=SpanType.TOOL)

        registry.fire_start(agent_span)
        registry.fire_start(tool_span)

        assert agent_events == ["my_agent"]
        assert tool_events == ["my_tool"]

    def test_multiple_hooks(self):
        """Multiple hooks should fire in order."""
        registry = HookRegistry()
        order = []

        registry.on_start(lambda s: order.append("first"))
        registry.on_start(lambda s: order.append("second"))
        registry.on_start(lambda s: order.append("third"))

        registry.fire_start(Span(name="test"))
        assert order == ["first", "second", "third"]

    def test_hook_exception_caught(self):
        """Exceptions in hooks should be caught, not propagated."""
        registry = HookRegistry()
        events = []

        registry.on_start(lambda s: events.append("before"))
        registry.on_start(lambda s: (_ for _ in ()).throw(ValueError("boom")))
        registry.on_start(lambda s: events.append("after"))

        span = Span(name="test")
        registry.fire_start(span)  # should not raise

        assert "before" in events
        # "after" should still fire
        assert "after" in events
        assert registry.error_count >= 1

    def test_clear(self):
        """Clear should remove all hooks."""
        registry = HookRegistry()
        registry.on_start(lambda s: None)
        registry.on_complete(lambda s: None)
        registry.on_error(lambda s, e: None)

        assert registry.hook_count == 3
        registry.clear()
        assert registry.hook_count == 0

    def test_hook_count(self):
        """Hook count should reflect all registered hooks."""
        registry = HookRegistry()
        registry.on_start(lambda s: None)
        registry.on_complete(lambda s: None)
        registry.on_error(lambda s, e: None)
        registry.on_handoff(lambda s: None)
        registry.on_start(lambda s: None, span_type=SpanType.AGENT)

        assert registry.hook_count == 5

    def test_global_registry(self):
        """Global registry should be accessible and resettable."""
        reg = get_hook_registry()
        reg.on_start(lambda s: None)
        assert reg.hook_count >= 1

        reset_hooks()
        assert reg.hook_count == 0
