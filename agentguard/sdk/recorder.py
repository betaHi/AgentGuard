"""Trace recorder — collects spans and assembles execution traces.

The recorder maintains a context stack to track parent-child span relationships
across nested agent and tool calls.
"""

from __future__ import annotations

import contextlib
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

from agentguard.core.trace import ExecutionTrace, Span


class TraceRecorder:
    """Records execution spans and assembles them into traces.

    Thread-safe via thread-local storage for the span stack.

    Attributes:
        trace: The current execution trace being recorded.
        output_dir: Directory to write trace files.
    """

    def __init__(self, task: str = "", trigger: str = "manual", output_dir: str = ".agentguard/traces"):
        self.trace = ExecutionTrace(task=task, trigger=trigger)
        self.output_dir = Path(output_dir)
        self._local = threading.local()
        self._sampled = self._decide_sampling()

    @staticmethod
    def _decide_sampling() -> bool:
        """Decide once whether this trace should be recorded.

        Uses agentguard.settings.sampling_rate. Decision is made per-trace
        (not per-span) to avoid corrupted partial traces.
        """
        try:
            import random

            from agentguard.settings import get_settings
            rate = get_settings().sampling_rate
            if rate >= 1.0:
                return True
            if rate <= 0.0:
                return False
            return random.random() < rate
        except Exception:
            return True  # fail-open

    @property
    def _span_stack(self) -> list[str]:
        """Thread-local span stack for tracking nesting."""
        if not hasattr(self._local, "span_stack"):
            self._local.span_stack = []
        return self._local.span_stack

    @property
    def current_span_id(self) -> str | None:
        """Get the current parent span ID (top of stack)."""
        stack = self._span_stack
        return stack[-1] if stack else None

    def set_correlation_id(self, correlation_id: str) -> None:
        """Set the correlation ID for this trace.

        Links this trace to other traces across service boundaries.
        Call this early, typically right after init_recorder().

        Args:
            correlation_id: Shared ID across related traces.
        """
        self.trace.correlation_id = correlation_id

    def set_parent_trace(self, parent_trace_id: str) -> None:
        """Set the parent trace ID for this trace.

        Indicates this trace was spawned by another trace.

        Args:
            parent_trace_id: ID of the trace that spawned this one.
        """
        self.trace.parent_trace_id = parent_trace_id

    def annotate_span(self, key: str, value: Any) -> None:
        """Attach a key-value annotation to the current span.

        If no span is active or recording is sampled out, this is a no-op.
        Annotations are stored in the span's metadata dict.

        Args:
            key: Annotation key (string).
            value: Annotation value (must be JSON-serializable).
        """
        span_id = self.current_span_id
        if span_id is None:
            return
        for s in self.trace.spans:
            if s.span_id == span_id:
                s.metadata[key] = value
                return

    def capture_context(self) -> tuple[str, ...]:
        """Capture the current span stack for later reuse.

        This is primarily used when work is spawned into another thread and
        the child needs to continue under the caller's current parent span.
        """
        return tuple(self._span_stack)

    def restore_context(self, span_stack: tuple[str, ...]) -> None:
        """Replace the current thread's span stack with a captured context.

        Args:
            token: Context token from a previous bind.
        """
        self._local.span_stack = list(span_stack)

    def bind_context(self, func: Callable[..., _T]) -> Callable[..., _T]:
        """Bind the current span stack to a callable for execution elsewhere.

        The returned callable restores the captured stack for the duration of
        the call, then puts the previous thread-local stack back.

        Args:
            trace: ExecutionTrace to bind.

        Returns:
            Context token for later restoration.
        """
        captured_stack = self.capture_context()

        def wrapped(*args, **kwargs) -> Any:
            """Wrap function with automatic span recording."""
            previous_stack = self.capture_context()
            self.restore_context(captured_stack)
            try:
                return func(*args, **kwargs)
            finally:
                self.restore_context(previous_stack)

        return wrapped

    def push_span(self, span: Span) -> None:
        """Add a span to the trace and push it onto the context stack.

        If this trace was sampled out, the span is NOT added to the trace
        but the stack is still maintained for correct current_span_id tracking.

        Args:
            span: Span to push onto the stack.
        """
        if self._sampled:
            self.trace.add_span(span)
        self._span_stack.append(span.span_id)

    def pop_span(self, span: Span) -> None:
        """Pop a span from the context stack.

        Always maintains stack regardless of sampling, so parent tracking
        stays correct for nested decorators.

        Returns:
            The popped Span, or None if stack is empty.
        """
        stack = self._span_stack
        if stack and stack[-1] == span.span_id:
            stack.pop()

    def finish(self) -> ExecutionTrace:
        """Finalize the trace and write to disk."""
        # Determine overall status
        # A trace is only FAILED if there are UNHANDLED failures.
        # Handled failures (failure_handled=True, or parent succeeded) don't count.
        span_map = {s.span_id: s for s in self.trace.spans}
        has_unhandled_failure = False

        for s in self.trace.spans:
            if s.status.value != "failed":
                continue

            # Check if this failure was explicitly handled
            if s.failure_handled:
                continue

            # Check if parent succeeded (implicit handling — circuit breaker)
            if s.parent_span_id and s.parent_span_id in span_map:
                parent = span_map[s.parent_span_id]
                if parent.status.value == "completed":
                    continue

            # This is an unhandled root-level failure
            has_unhandled_failure = True
            break

        if has_unhandled_failure:
            self.trace.fail()
        else:
            self.trace.complete()

        # Write trace file
        self.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = getattr(self, "_child_suffix", "")
        filename = f"{self.trace.trace_id}{suffix}.json"
        filepath = self.output_dir / filename
        filepath.write_text(self.trace.to_json(), encoding="utf-8")

        return self.trace


# Global recorder instance (per-thread via thread-local)
_global_recorder: TraceRecorder | None = None
_lock = threading.Lock()
_T = TypeVar("_T")


def init_recorder(task: str = "", trigger: str = "manual", output_dir: str = ".agentguard/traces") -> TraceRecorder:
    """Initialize a new global trace recorder.

    Args:
        config: Optional recorder configuration dict.

    Returns:
        Initialized Recorder instance.
    """
    global _global_recorder
    with _lock:
        _global_recorder = TraceRecorder(task=task, trigger=trigger, output_dir=output_dir)
        return _global_recorder


def get_recorder() -> TraceRecorder:
    """Get or create the global trace recorder."""
    global _global_recorder
    if _global_recorder is None:
        with _lock:
            if _global_recorder is None:
                _global_recorder = TraceRecorder()
    return _global_recorder


def set_correlation_id(correlation_id: str) -> None:
    """Set correlation ID on the current trace (links across services).

    Example:
        set_correlation_id(request.headers["X-Correlation-ID"])

    Args:
        correlation_id: External correlation identifier.
    """
    with contextlib.suppress(Exception):
        get_recorder().set_correlation_id(correlation_id)


def set_parent_trace(parent_trace_id: str) -> None:
    """Set parent trace ID (this trace was spawned by another).

    Args:
        parent_trace_id: Parent trace ID for distributed tracing.
    """
    with contextlib.suppress(Exception):
        get_recorder().set_parent_trace(parent_trace_id)


def annotate(key: str, value: Any) -> None:
    """Annotate the current span with a key-value pair.

    Convenience wrapper around get_recorder().annotate_span().
    Safe to call even if no recording is active (fail-open).

    Args:
        key: Annotation key.
        value: JSON-serializable value.

    Example:
        from agentguard.sdk.recorder import annotate
        annotate("model_version", "gpt-4")
        annotate("temperature", 0.7)
    """
    try:
        get_recorder().annotate_span(key, value)
    except Exception:
        pass  # fail-open


def finish_recording() -> ExecutionTrace:
    """Finalize the current recording and return the trace."""
    global _global_recorder
    recorder = get_recorder()
    trace = recorder.finish()
    with _lock:
        _global_recorder = None
    return trace


def bind_current_trace_context(func: Callable[..., _T]) -> Callable[..., _T]:
    """Capture the current trace context and bind it to a callable.

    Use this when scheduling work onto another thread so child spans remain
    attached to the active parent span from the caller's thread.

    Args:
        trace: ExecutionTrace to bind to current context.
    """
    return get_recorder().bind_context(func)
