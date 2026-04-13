"""Span lifecycle hooks — pre/post execution callbacks.

Allow users to attach callbacks that fire when spans start, complete, or fail.
Useful for:
- Custom logging/alerting during execution
- Injecting context at span boundaries
- Real-time monitoring without polling
- Metrics collection (Prometheus, StatsD, etc.)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agentguard.core.trace import Span, SpanType

# Type aliases for hook functions
SpanHook = Callable[[Span], None]
SpanErrorHook = Callable[[Span, Exception], None]


@dataclass
class HookRegistry:
    """Registry of span lifecycle hooks.

    Hooks are called in registration order. Exceptions in hooks
    are caught and logged (they don't affect span execution).
    """
    _on_start: list[SpanHook] = field(default_factory=list)
    _on_complete: list[SpanHook] = field(default_factory=list)
    _on_error: list[SpanErrorHook] = field(default_factory=list)
    _on_handoff: list[SpanHook] = field(default_factory=list)
    _filters: dict[str, list[SpanHook]] = field(default_factory=dict)  # type-specific hooks
    _errors: list[dict] = field(default_factory=list)  # captured hook errors

    def on_start(self, hook: SpanHook, span_type: SpanType | None = None) -> None:
        """Register a hook to fire when a span starts.

        Args:
            hook: Callback receiving the starting Span.
            span_type: Optional filter — only fire for this span type.
        """
        if span_type:
            key = f"start:{span_type.value}"
            self._filters.setdefault(key, []).append(hook)
        else:
            self._on_start.append(hook)

    def on_complete(self, hook: SpanHook, span_type: SpanType | None = None) -> None:
        """Register a hook to fire when a span completes successfully.

        Args:
            callback: Function called when a span completes successfully.
        """
        if span_type:
            key = f"complete:{span_type.value}"
            self._filters.setdefault(key, []).append(hook)
        else:
            self._on_complete.append(hook)

    def on_error(self, hook: SpanErrorHook) -> None:
        """Register a hook to fire when a span fails.

        Args:
            callback: Function called when a span fails.
        """
        self._on_error.append(hook)

    def on_handoff(self, hook: SpanHook) -> None:
        """Register a hook for handoff events.

        Args:
            callback: Function called on agent handoff.
        """
        self._on_handoff.append(hook)

    def fire_start(self, span: Span) -> None:
        """Fire all start hooks for a span.

        Args:
            span: The span that started.
        """
        for hook in self._on_start:
            self._safe_call(hook, span)
        for hook in self._filters.get(f"start:{span.span_type.value}", []):
            self._safe_call(hook, span)

    def fire_complete(self, span: Span) -> None:
        """Fire all completion hooks for a span.

        Args:
            span: The span that completed.
        """
        for hook in self._on_complete:
            self._safe_call(hook, span)
        for hook in self._filters.get(f"complete:{span.span_type.value}", []):
            self._safe_call(hook, span)

    def fire_error(self, span: Span, error: Exception) -> None:
        """Fire all error hooks for a span.

        Args:
            span: The span that failed.
            error: The exception.
        """
        for hook in self._on_error:
            self._safe_call_error(hook, span, error)

    def fire_handoff(self, span: Span) -> None:
        """Fire all handoff hooks.

        Args:
            from_agent: Source agent name.
            to_agent: Target agent name.
        """
        for hook in self._on_handoff:
            self._safe_call(hook, span)

    def clear(self) -> None:
        """Remove all registered hooks."""
        self._on_start.clear()
        self._on_complete.clear()
        self._on_error.clear()
        self._on_handoff.clear()
        self._filters.clear()
        self._errors.clear()

    @property
    def hook_count(self) -> int:
        """Total number of registered hooks."""
        return (len(self._on_start) + len(self._on_complete) +
                len(self._on_error) + len(self._on_handoff) +
                sum(len(v) for v in self._filters.values()))

    @property
    def error_count(self) -> int:
        """Number of errors captured from hooks."""
        return len(self._errors)

    def _safe_call(self, hook: SpanHook, span: Span) -> None:
        """Call a hook, catching any exceptions."""
        try:
            hook(span)
        except Exception as e:
            self._errors.append({
                "hook": hook.__name__ if hasattr(hook, '__name__') else str(hook),
                "span": span.name,
                "error": str(e),
            })

    def _safe_call_error(self, hook: SpanErrorHook, span: Span, error: Exception) -> None:
        """Call an error hook, catching any exceptions."""
        try:
            hook(span, error)
        except Exception as e:
            self._errors.append({
                "hook": hook.__name__ if hasattr(hook, '__name__') else str(hook),
                "span": span.name,
                "error": str(e),
            })


# Global registry
_global_registry = HookRegistry()


def get_hook_registry() -> HookRegistry:
    """Get the global hook registry."""
    return _global_registry


def reset_hooks() -> None:
    """Reset the global hook registry."""
    _global_registry.clear()
