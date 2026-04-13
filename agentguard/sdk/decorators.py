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
from collections.abc import Callable
from typing import Any

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.recorder import get_recorder


def record_agent(
    name: str,
    version: str = "latest",
    metadata: dict[str, Any] | None = None,
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
        """Apply tracing to the given function."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            """Wrap function call with span recording."""
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
    metadata: dict[str, Any] | None = None,
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
        """Apply tracing to the given function."""
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            """Wrap function call with span recording."""
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




def _try_start_span(
    name: str, version: str, metadata: dict | None, args: tuple, kwargs: dict
) -> Span | None:
    """Create and push an agent span, returning None on failure (fail-open).

    Why fail-open: recording is observability — it must never break the
    decorated function. If the recorder is misconfigured or OOM, the user's
    agent should still run.

    Respects agentguard.configure(sampling_rate=N) — if sampled out,
    returns None and no span is recorded.
    """
    try:
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
    name: str, metadata: dict | None, args: tuple, kwargs: dict
) -> Span | None:
    """Create and push a tool span, returning None on failure (fail-open)."""
    try:
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


def _try_complete_span(span: Span | None, result: Any) -> None:
    """Mark span completed and auto-extract cost/token metadata.

    If the function returns a dict containing known cost/token keys,
    they are automatically copied to span fields so cost-yield analysis
    works without manual SDK calls.
    """
    if span is None:
        return
    try:
        span.complete(output=_safe_serialize(result))
        _auto_extract_cost_fields(span, result)
    except Exception:
        _logger.debug("AgentGuard: failed to complete span", exc_info=True)



# Keys to auto-extract from output_data into span fields
_COST_KEYS = ("cost_usd", "cost", "estimated_cost_usd")
_TOKEN_KEYS = ("token_count", "tokens_used", "total_tokens", "tokens")


def _auto_extract_cost_fields(span: Span, result: Any) -> None:
    """Extract cost/token fields from result dict into span attributes.

    Why: Many agent functions return cost metadata in their output dict
    (e.g., {"result": ..., "cost_usd": 0.02, "tokens_used": 150}).
    Without extraction, cost-yield analysis sees all agents as free.

    Only extracts if span fields are still None (doesn't overwrite
    explicitly set values from TraceBuilder or manual SDK).
    """
    if not isinstance(result, dict):
        return
    if span.estimated_cost_usd is None:
        for key in _COST_KEYS:
            val = result.get(key)
            if isinstance(val, (int, float)) and val > 0:
                span.estimated_cost_usd = float(val)
                break
    if span.token_count is None:
        for key in _TOKEN_KEYS:
            val = result.get(key)
            if isinstance(val, int) and val > 0:
                span.token_count = val
                break


def _try_fail_span(span: Span | None, error: Exception) -> None:
    """Mark span failed, silently ignoring recording errors."""
    if span is None:
        return
    try:
        span.fail(error=f"{type(error).__name__}: {str(error)}")
    except Exception:
        _logger.debug("AgentGuard: failed to record span failure", exc_info=True)


def _try_pop_span(span: Span | None) -> None:
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
