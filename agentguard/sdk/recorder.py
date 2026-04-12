"""Trace recorder — collects spans and assembles execution traces.

The recorder maintains a context stack to track parent-child span relationships
across nested agent and tool calls.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional, TypeVar

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

    @property
    def _span_stack(self) -> list[str]:
        """Thread-local span stack for tracking nesting."""
        if not hasattr(self._local, "span_stack"):
            self._local.span_stack = []
        return self._local.span_stack

    @property
    def current_span_id(self) -> Optional[str]:
        """Get the current parent span ID (top of stack)."""
        stack = self._span_stack
        return stack[-1] if stack else None

    def capture_context(self) -> tuple[str, ...]:
        """Capture the current span stack for later reuse.

        This is primarily used when work is spawned into another thread and
        the child needs to continue under the caller's current parent span.
        """
        return tuple(self._span_stack)

    def restore_context(self, span_stack: tuple[str, ...]) -> None:
        """Replace the current thread's span stack with a captured context."""
        self._local.span_stack = list(span_stack)

    def bind_context(self, func: Callable[..., _T]) -> Callable[..., _T]:
        """Bind the current span stack to a callable for execution elsewhere.

        The returned callable restores the captured stack for the duration of
        the call, then puts the previous thread-local stack back.
        """
        captured_stack = self.capture_context()

        def wrapped(*args, **kwargs):
            previous_stack = self.capture_context()
            self.restore_context(captured_stack)
            try:
                return func(*args, **kwargs)
            finally:
                self.restore_context(previous_stack)

        return wrapped

    def push_span(self, span: Span) -> None:
        """Add a span to the trace and push it onto the context stack."""
        self.trace.add_span(span)
        self._span_stack.append(span.span_id)

    def pop_span(self, span: Span) -> None:
        """Pop a span from the context stack."""
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
_global_recorder: Optional[TraceRecorder] = None
_lock = threading.Lock()
_T = TypeVar("_T")


def init_recorder(task: str = "", trigger: str = "manual", output_dir: str = ".agentguard/traces") -> TraceRecorder:
    """Initialize a new global trace recorder."""
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
    """
    return get_recorder().bind_context(func)
