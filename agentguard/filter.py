"""Trace filtering and sampling — query DSL for large trace stores.

Provides a composable filter API for querying spans and traces:
- Filter by span type, status, name pattern
- Filter by duration range
- Filter by tags or metadata keys
- Sample traces (random, head, tail)
- Compose filters with AND/OR logic
"""

from __future__ import annotations

import random
import re
from collections.abc import Callable

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType

# Type alias for filter functions
SpanFilter = Callable[[Span], bool]
TraceFilter = Callable[[ExecutionTrace], bool]


def by_type(*types: SpanType) -> SpanFilter:
    """Filter spans by type."""
    type_set = set(types)
    return lambda span: span.span_type in type_set


def by_status(*statuses: SpanStatus) -> SpanFilter:
    """Filter spans by status."""
    status_set = set(statuses)
    return lambda span: span.status in status_set


def by_name(pattern: str) -> SpanFilter:
    """Filter spans by name (supports regex)."""
    compiled = re.compile(pattern, re.IGNORECASE)
    return lambda span: bool(compiled.search(span.name))


def by_duration(min_ms: float | None = None, max_ms: float | None = None) -> SpanFilter:
    """Filter spans by duration range."""
    def _filter(span: Span) -> bool:
        dur = span.duration_ms
        if dur is None:
            return False
        if min_ms is not None and dur < min_ms:
            return False
        return not (max_ms is not None and dur > max_ms)
    return _filter


def by_tag(*tags: str) -> SpanFilter:
    """Filter spans that have ALL specified tags."""
    tag_set = set(tags)
    return lambda span: tag_set.issubset(set(span.tags))


def by_metadata(key: str, value: object | None = None) -> SpanFilter:
    """Filter spans by metadata key (and optionally value)."""
    def _filter(span: Span) -> bool:
        if key not in span.metadata:
            return False
        return not (value is not None and span.metadata[key] != value)
    return _filter


def has_error() -> SpanFilter:
    """Filter spans that have errors."""
    return lambda span: span.error is not None


def has_retries() -> SpanFilter:
    """Filter spans with retry count > 0."""
    return lambda span: span.retry_count > 0


def is_handoff() -> SpanFilter:
    """Filter handoff spans."""
    return lambda span: span.span_type == SpanType.HANDOFF


def is_slow(threshold_ms: float) -> SpanFilter:
    """Filter spans slower than threshold."""
    return lambda span: (span.duration_ms or 0) > threshold_ms


# Composition
def and_filter(*filters: SpanFilter) -> SpanFilter:
    """Combine filters with AND logic (all must match)."""
    return lambda span: all(f(span) for f in filters)


def or_filter(*filters: SpanFilter) -> SpanFilter:
    """Combine filters with OR logic (any must match)."""
    return lambda span: any(f(span) for f in filters)


def not_filter(f: SpanFilter) -> SpanFilter:
    """Negate a filter."""
    return lambda span: not f(span)


# Trace-level filters
def trace_has_failures() -> TraceFilter:
    """Filter traces that contain at least one failed span."""
    return lambda trace: any(s.status == SpanStatus.FAILED for s in trace.spans)


def trace_duration(min_ms: float | None = None, max_ms: float | None = None) -> TraceFilter:
    """Filter traces by total duration."""
    def _filter(trace: ExecutionTrace) -> bool:
        dur = trace.duration_ms
        if dur is None:
            return False
        if min_ms is not None and dur < min_ms:
            return False
        return not (max_ms is not None and dur > max_ms)
    return _filter


def trace_has_agent(name: str) -> TraceFilter:
    """Filter traces containing a specific agent."""
    return lambda trace: any(s.name == name and s.span_type == SpanType.AGENT for s in trace.spans)


# Query execution
def filter_spans(trace: ExecutionTrace, *filters: SpanFilter) -> list[Span]:
    """Apply filters to get matching spans from a trace."""
    combined = and_filter(*filters) if filters else lambda s: True
    return [s for s in trace.spans if combined(s)]


def filter_traces(traces: list[ExecutionTrace], *filters: TraceFilter) -> list[ExecutionTrace]:
    """Apply filters to get matching traces."""
    def combined(t) -> bool:
        return all(f(t) for f in filters)
    return [t for t in traces if combined(t)]


def sample_traces(traces: list[ExecutionTrace], n: int, method: str = "random") -> list[ExecutionTrace]:
    """Sample n traces from a list.

    Args:
        traces: Source traces.
        n: Number to sample.
        method: "random", "head" (first n), "tail" (last n), "worst" (lowest score)
    """
    if n >= len(traces):
        return traces

    if method == "head":
        return traces[:n]
    elif method == "tail":
        return traces[-n:]
    elif method == "worst":
        from agentguard.scoring import score_trace
        scored = [(t, score_trace(t).overall) for t in traces]
        scored.sort(key=lambda x: x[1])
        return [t for t, _ in scored[:n]]
    else:  # random
        return random.sample(traces, n)
