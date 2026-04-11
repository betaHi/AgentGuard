"""Async instrumentation decorators for recording agent and tool executions.

Usage:
    @record_agent_async(name="my-agent", version="v1.0")
    async def my_agent(task: str) -> str:
        result = await my_tool("query")
        return result

    @record_tool_async(name="search")
    async def my_tool(query: str) -> list:
        ...
"""

from __future__ import annotations

import functools
from typing import Any, Callable, Optional

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.recorder import get_recorder
from agentguard.sdk.decorators import _safe_serialize


def record_agent_async(
    name: str,
    version: str = "latest",
    metadata: Optional[dict[str, Any]] = None,
) -> Callable:
    """Async decorator to record an agent's execution as a trace span.

    Args:
        name: Human-readable agent name.
        version: Agent version string.
        metadata: Additional metadata to attach.

    Returns:
        Decorated async function that automatically records execution.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            recorder = get_recorder()
            span = Span(
                span_type=SpanType.AGENT,
                name=name,
                parent_span_id=recorder.current_span_id,
                input_data=_safe_serialize({"args": args, "kwargs": kwargs}),
                metadata={"agent_version": version, **(metadata or {})},
            )
            recorder.push_span(span)
            try:
                result = await func(*args, **kwargs)
                span.complete(output=_safe_serialize(result))
                return result
            except Exception as e:
                span.fail(error=f"{type(e).__name__}: {str(e)}")
                raise
            finally:
                recorder.pop_span(span)
        return wrapper
    return decorator


def record_tool_async(
    name: str,
    metadata: Optional[dict[str, Any]] = None,
) -> Callable:
    """Async decorator to record a tool call as a trace span.

    Args:
        name: Tool name.
        metadata: Additional metadata.

    Returns:
        Decorated async function that automatically records execution.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> Any:
            recorder = get_recorder()
            span = Span(
                span_type=SpanType.TOOL,
                name=name,
                parent_span_id=recorder.current_span_id,
                input_data=_safe_serialize({"args": args, "kwargs": kwargs}),
                metadata=metadata or {},
            )
            recorder.push_span(span)
            try:
                result = await func(*args, **kwargs)
                span.complete(output=_safe_serialize(result))
                return result
            except Exception as e:
                span.fail(error=f"{type(e).__name__}: {str(e)}")
                raise
            finally:
                recorder.pop_span(span)
        return wrapper
    return decorator
