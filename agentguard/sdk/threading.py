"""Thread helpers for preserving AgentGuard trace context.

Python thread-local state does not propagate into new threads automatically.
These helpers capture the active span stack at thread creation time and
restore it inside the worker thread so child spans keep the right parent.
"""

from __future__ import annotations

import threading
from typing import Any

from agentguard.sdk.recorder import bind_current_trace_context

_ORIGINAL_THREAD_INIT = threading.Thread.__init__
_AUTO_THREADING_ENABLED = False


def _wrap_thread_target(target: Any | None) -> Any | None:
    """Bind AgentGuard trace context to a thread target when needed."""
    if target is None or getattr(target, "__agentguard_bound_context__", False):
        return target
    wrapped_target = bind_current_trace_context(target)
    setattr(wrapped_target, "__agentguard_bound_context__", True)
    return wrapped_target


def _patched_thread_init(
    self: threading.Thread,
    group: None = None,
    target: Any | None = None,
    name: str | None = None,
    args: tuple[Any, ...] = (),
    kwargs: dict[str, Any] | None = None,
    *,
    daemon: bool | None = None,
) -> None:
    """Patched Thread.__init__ that preserves active AgentGuard context."""
    _ORIGINAL_THREAD_INIT(
        self,
        group=group,
        target=_wrap_thread_target(target),
        name=name,
        args=args,
        kwargs=kwargs or {},
        daemon=daemon,
    )


def enable_auto_trace_threading() -> None:
    """Automatically propagate AgentGuard trace context to new threads.

    This monkey-patches ``threading.Thread`` so code using the standard
    library thread API inherits the active AgentGuard span stack without
    requiring ``TraceThread``.
    """
    global _AUTO_THREADING_ENABLED
    if _AUTO_THREADING_ENABLED:
        return
    threading.Thread.__init__ = _patched_thread_init
    _AUTO_THREADING_ENABLED = True


def disable_auto_trace_threading() -> None:
    """Restore the standard library threading behavior."""
    global _AUTO_THREADING_ENABLED
    if not _AUTO_THREADING_ENABLED:
        return
    threading.Thread.__init__ = _ORIGINAL_THREAD_INIT
    _AUTO_THREADING_ENABLED = False


def is_auto_trace_threading_enabled() -> bool:
    """Return whether automatic thread context propagation is enabled."""
    return _AUTO_THREADING_ENABLED


class TraceThread(threading.Thread):
    """Thread that inherits the current AgentGuard trace context.

    Create this thread from inside an active agent span when child work should
    remain attached to that span in the trace tree.
    """

    def __init__(
        self,
        group: None = None,
        target: Any | None = None,
        name: str | None = None,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        *,
        daemon: bool | None = None,
    ) -> None:
        wrapped_target = _wrap_thread_target(target)
        super().__init__(
            group=group,
            target=wrapped_target,
            name=name,
            args=args,
            kwargs=kwargs or {},
            daemon=daemon,
        )
