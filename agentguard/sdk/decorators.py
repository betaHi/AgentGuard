"""Instrumentation decorators for recording agent and tool executions.

Usage:
    @record_agent(name="my-agent", version="v1.0")
    def my_agent(task: str) -> str:
        result = my_tool("query")
        return result

    @record_tool(name="search")
    def my_tool(query: str) -> list:
        ...
"""

from __future__ import annotations

import functools
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.sdk.recorder import get_recorder


def record_agent(
    name: str,
    version: str = "latest",
    metadata: Optional[dict[str, Any]] = None,
) -> Callable:
    """Decorator to record an agent's execution as a trace span.

    Args:
        name: Human-readable agent name (e.g., "news-collector").
        version: Agent version string (e.g., "v1.0").
        metadata: Additional metadata to attach to the span.

    Returns:
        Decorated function that automatically records execution.

    Example:
        @record_agent(name="researcher", version="v2.1")
        def research(topic: str) -> dict:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            recorder = get_recorder()
            
            span = Span(
                span_type=SpanType.AGENT,
                name=name,
                parent_span_id=recorder.current_span_id,
                input_data=_safe_serialize({"args": args, "kwargs": kwargs}),
                metadata={
                    "agent_version": version,
                    **(metadata or {}),
                },
            )
            
            recorder.push_span(span)
            
            try:
                result = func(*args, **kwargs)
                span.complete(output=_safe_serialize(result))
                return result
            except Exception as e:
                span.fail(error=f"{type(e).__name__}: {str(e)}")
                raise
            finally:
                recorder.pop_span(span)
        
        return wrapper
    return decorator


def record_tool(
    name: str,
    metadata: Optional[dict[str, Any]] = None,
) -> Callable:
    """Decorator to record a tool call as a trace span.

    Args:
        name: Tool name (e.g., "web_search", "file_write").
        metadata: Additional metadata to attach to the span.

    Returns:
        Decorated function that automatically records execution.

    Example:
        @record_tool(name="web_search")
        def search(query: str) -> list[str]:
            ...
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
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
                result = func(*args, **kwargs)
                span.complete(output=_safe_serialize(result))
                return result
            except Exception as e:
                span.fail(error=f"{type(e).__name__}: {str(e)}")
                raise
            finally:
                recorder.pop_span(span)
        
        return wrapper
    return decorator


def _safe_serialize(data: Any) -> Any:
    """Attempt to make data JSON-serializable."""
    if data is None:
        return None
    if isinstance(data, (str, int, float, bool)):
        return data
    if isinstance(data, (list, tuple)):
        return [_safe_serialize(item) for item in data]
    if isinstance(data, dict):
        return {str(k): _safe_serialize(v) for k, v in data.items()}
    # Fallback: convert to string
    try:
        return str(data)
    except Exception:
        return "<unserializable>"
