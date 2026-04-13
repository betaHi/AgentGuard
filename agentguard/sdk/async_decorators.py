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

import logging

_logger = logging.getLogger(__name__)

import functools
from typing import Any, Callable, Optional

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.recorder import get_recorder
from agentguard.sdk.decorators import (
    _safe_serialize, _try_start_span, _try_start_tool_span,
    _try_complete_span, _try_fail_span, _try_pop_span,
)


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
            span = _try_start_span(name, version, metadata, args, kwargs)
            try:
                result = await func(*args, **kwargs)
                _try_complete_span(span, result)
                return result
            except Exception as e:
                _try_fail_span(span, e)
                raise
            finally:
                _try_pop_span(span)
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
            span = _try_start_tool_span(name, metadata, args, kwargs)
            try:
                result = await func(*args, **kwargs)
                _try_complete_span(span, result)
                return result
            except Exception as e:
                _try_fail_span(span, e)
                raise
            finally:
                _try_pop_span(span)
        return wrapper
    return decorator
