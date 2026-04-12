"""Thread helpers for preserving AgentGuard trace context.

Python thread-local state does not propagate into new threads automatically.
These helpers capture the active span stack at thread creation time and
restore it inside the worker thread so child spans keep the right parent.
"""

from __future__ import annotations

import threading
from typing import Any, Optional

from agentguard.sdk.recorder import bind_current_trace_context


class TraceThread(threading.Thread):
    """Thread that inherits the current AgentGuard trace context.

    Create this thread from inside an active agent span when child work should
    remain attached to that span in the trace tree.
    """

    def __init__(
        self,
        group: None = None,
        target: Optional[Any] = None,
        name: Optional[str] = None,
        args: tuple[Any, ...] = (),
        kwargs: Optional[dict[str, Any]] = None,
        *,
        daemon: Optional[bool] = None,
    ) -> None:
        wrapped_target = bind_current_trace_context(target) if target is not None else None
        super().__init__(
            group=group,
            target=wrapped_target,
            name=name,
            args=args,
            kwargs=kwargs or {},
            daemon=daemon,
        )
