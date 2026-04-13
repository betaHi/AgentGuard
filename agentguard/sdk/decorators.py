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

import logging

_logger = logging.getLogger(__name__)

import functools
import traceback
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.sdk.recorder import get_recorder
import random


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
            span = _try_start_span(name, version, metadata, args, kwargs)
            try:
                result = func(*args, **kwargs)
                _try_complete_span(span, result)
                return result
            except Exception as e:
                _try_fail_span(span, e)
                raise
            finally:
                _try_pop_span(span)
        
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
            span = _try_start_tool_span(name, metadata, args, kwargs)
            try:
                result = func(*args, **kwargs)
                _try_complete_span(span, result)
                return result
            except Exception as e:
                _try_fail_span(span, e)
                raise
            finally:
                _try_pop_span(span)
        
        return wrapper
    return decorator



def _should_sample() -> bool:
    """Check if this trace should be sampled based on global settings.

    Returns True if recording should proceed, False to skip.
    Uses random.random() < sampling_rate for probabilistic sampling.
    """
    try:
        from agentguard.settings import get_settings
        rate = get_settings().sampling_rate
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        return random.random() < rate
    except Exception:
        return True  # fail-open: record if settings unavailable


def _try_start_span(
    name: str, version: str, metadata: Optional[dict], args: tuple, kwargs: dict
) -> Optional[Span]:
    """Create and push an agent span, returning None on failure (fail-open).

    Why fail-open: recording is observability — it must never break the
    decorated function. If the recorder is misconfigured or OOM, the user's
    agent should still run.

    Respects agentguard.configure(sampling_rate=N) — if sampled out,
    returns None and no span is recorded.
    """
    try:
        if not _should_sample():
            return None
        recorder = get_recorder()
        span = Span(
            span_type=SpanType.AGENT,
            name=name,
            parent_span_id=recorder.current_span_id,
            input_data=_safe_serialize({"args": args, "kwargs": kwargs}),
            metadata={"agent_version": version, **(metadata or {})},
        )
        recorder.push_span(span)
        return span
    except Exception:
        _logger.debug("AgentGuard: failed to start agent span %s", name, exc_info=True)
        return None


def _try_start_tool_span(
    name: str, metadata: Optional[dict], args: tuple, kwargs: dict
) -> Optional[Span]:
    """Create and push a tool span, returning None on failure (fail-open)."""
    try:
        if not _should_sample():
            return None
        recorder = get_recorder()
        span = Span(
            span_type=SpanType.TOOL,
            name=name,
            parent_span_id=recorder.current_span_id,
            input_data=_safe_serialize({"args": args, "kwargs": kwargs}),
            metadata=metadata or {},
        )
        recorder.push_span(span)
        return span
    except Exception:
        _logger.debug("AgentGuard: failed to start tool span %s", name, exc_info=True)
        return None


def _try_complete_span(span: Optional[Span], result: Any) -> None:
    """Mark span completed, silently ignoring errors."""
    if span is None:
        return
    try:
        span.complete(output=_safe_serialize(result))
    except Exception:
        _logger.debug("AgentGuard: failed to complete span", exc_info=True)


def _try_fail_span(span: Optional[Span], error: Exception) -> None:
    """Mark span failed, silently ignoring recording errors."""
    if span is None:
        return
    try:
        span.fail(error=f"{type(error).__name__}: {str(error)}")
    except Exception:
        _logger.debug("AgentGuard: failed to record span failure", exc_info=True)


def _try_pop_span(span: Optional[Span]) -> None:
    """Pop span from recorder, silently ignoring errors."""
    if span is None:
        return
    try:
        recorder = get_recorder()
        recorder.pop_span(span)
    except Exception:
        _logger.debug("AgentGuard: failed to pop span", exc_info=True)


def _safe_serialize(data: Any) -> Any:
    """Attempt to make data JSON-serializable.

    Recursively converts data to JSON-safe types. Non-serializable objects
    are converted to their string representation.

    Args:
        data: Any Python object to serialize.

    Returns:
        A JSON-serializable version of the input, or ``"<unserializable>"``
        as a last resort.
    """
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
