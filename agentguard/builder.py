"""Trace builder — fluent API for constructing traces programmatically.

Makes it easy to build test traces or synthetic traces for benchmarking:

    trace = (TraceBuilder("my_pipeline")
        .agent("researcher", duration_ms=3000)
            .tool("web_search", duration_ms=1000)
            .tool("parser", duration_ms=500)
        .end()
        .handoff("researcher", "writer", context_size=2000)
        .agent("writer", duration_ms=5000, status="failed", error="out of tokens")
        .end()
        .build())
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


class TraceBuilder:
    """Fluent builder for constructing execution traces."""

    def __init__(self, task: str = "", trigger: str = "manual"):
        self._task = task
        self._trigger = trigger
        self._spans: list[Span] = []
        self._stack: list[str] = []  # span_id stack for nesting
        self._cursor = datetime.now(UTC)
        self._start = self._cursor

    def agent(
        self,
        name: str,
        duration_ms: float = 1000,
        status: str = "completed",
        error: str | None = None,
        input_data: Any = None,
        output_data: Any = None,
        tags: list[str] | None = None,
        token_count: int | None = None,
        cost_usd: float | None = None,
    ) -> TraceBuilder:
        """Add an agent span (pushes onto nesting stack)."""
        return self._add_span(
            SpanType.AGENT, name, duration_ms, status, error,
            input_data, output_data, tags, token_count, cost_usd,
            push=True,
        )

    def tool(
        self,
        name: str,
        duration_ms: float = 500,
        status: str = "completed",
        error: str | None = None,
        retry_count: int = 0,
    ) -> TraceBuilder:
        """Add a tool span (leaf, doesn't push onto stack)."""
        return self._add_span(
            SpanType.TOOL, name, duration_ms, status, error,
            retry_count=retry_count, push=False,
        )

    def llm_call(
        self,
        name: str = "llm_call",
        duration_ms: float = 2000,
        token_count: int = 0,
        cost_usd: float = 0,
    ) -> TraceBuilder:
        """Add an LLM call span."""
        return self._add_span(
            SpanType.LLM_CALL, name, duration_ms, "completed",
            token_count=token_count, cost_usd=cost_usd, push=False,
        )

    def handoff(
        self,
        from_agent: str,
        to_agent: str,
        context_size: int = 0,
        dropped_keys: list[str] | None = None,
        critical_keys: list[str] | None = None,
    ) -> TraceBuilder:
        """Add a handoff span."""
        span = Span(
            span_type=SpanType.HANDOFF,
            name=f"{from_agent} → {to_agent}",
            status=SpanStatus.COMPLETED,
            parent_span_id=self._stack[-1] if self._stack else None,
            started_at=self._cursor.isoformat(),
            ended_at=self._cursor.isoformat(),
            handoff_from=from_agent,
            handoff_to=to_agent,
            context_size_bytes=context_size,
            context_dropped_keys=dropped_keys or [],
        )
        span.metadata["handoff.context_keys"] = []
        span.metadata["handoff.context_size_bytes"] = context_size
        span.metadata["handoff.critical_keys"] = critical_keys or []
        self._spans.append(span)
        return self

    def parallel(self, *agents: dict) -> TraceBuilder:
        """Add multiple agent spans that execute in parallel (overlapping times).

        Each agent dict accepts the same kwargs as ``agent()``. All spans
        share the same start time; the cursor advances by the longest
        duration.

        Args:
            *agents: Dicts with agent kwargs, e.g.
                ``{"name": "a", "duration_ms": 500}``.

        Returns:
            self for chaining.

        Example::

            builder.parallel(
                {"name": "searcher", "duration_ms": 1000},
                {"name": "fetcher", "duration_ms": 800},
            )
        """
        start = self._cursor
        max_dur = 0
        parent_id = self._stack[-1] if self._stack else None

        for agent_kwargs in agents:
            name = agent_kwargs.pop("name")
            duration_ms = agent_kwargs.pop("duration_ms", 1000)
            status = agent_kwargs.pop("status", "completed")
            error = agent_kwargs.pop("error", None)

            end = start + timedelta(milliseconds=duration_ms)
            span = Span(
                span_type=SpanType.AGENT,
                name=name,
                status=SpanStatus(status),
                parent_span_id=parent_id,
                started_at=start.isoformat(),
                ended_at=end.isoformat(),
                error=error,
                input_data=agent_kwargs.pop("input_data", None),
                output_data=agent_kwargs.pop("output_data", None),
                tags=agent_kwargs.pop("tags", []),
                token_count=agent_kwargs.pop("token_count", None),
                estimated_cost_usd=agent_kwargs.pop("cost_usd", None),
            )
            if error and status == "failed":
                span.status = SpanStatus.FAILED
            self._spans.append(span)
            max_dur = max(max_dur, duration_ms)

        self._cursor = start + timedelta(milliseconds=max_dur)
        return self

    def end(self) -> TraceBuilder:
        """Pop the current nesting level (end the current agent)."""
        if self._stack:
            self._stack.pop()
        return self

    def wait(self, ms: float) -> TraceBuilder:
        """Advance the cursor by ms (simulate idle time)."""
        self._cursor += timedelta(milliseconds=ms)
        return self

    def build(self) -> ExecutionTrace:
        """Build the final ExecutionTrace."""
        trace = ExecutionTrace(
            task=self._task,
            trigger=self._trigger,
            started_at=self._start.isoformat(),
            ended_at=self._cursor.isoformat(),
            status=SpanStatus.COMPLETED,
        )

        # Check if any span failed
        has_failure = any(s.status == SpanStatus.FAILED for s in self._spans)
        if has_failure:
            trace.status = SpanStatus.FAILED

        for span in self._spans:
            trace.add_span(span)

        return trace

    def _add_span(
        self,
        span_type: SpanType,
        name: str,
        duration_ms: float = 1000,
        status: str = "completed",
        error: str | None = None,
        input_data: Any = None,
        output_data: Any = None,
        tags: list[str] | None = None,
        token_count: int | None = None,
        cost_usd: float | None = None,
        retry_count: int = 0,
        push: bool = False,
    ) -> TraceBuilder:
        start = self._cursor
        end = start + timedelta(milliseconds=duration_ms)

        span = Span(
            span_type=span_type,
            name=name,
            status=SpanStatus(status),
            parent_span_id=self._stack[-1] if self._stack else None,
            started_at=start.isoformat(),
            ended_at=end.isoformat(),
            error=error,
            input_data=input_data,
            output_data=output_data,
            tags=tags or [],
            token_count=token_count,
            estimated_cost_usd=cost_usd,
            retry_count=retry_count,
        )

        if error and status == "failed":
            span.status = SpanStatus.FAILED

        self._spans.append(span)
        self._cursor = end

        if push:
            self._stack.append(span.span_id)

        return self
