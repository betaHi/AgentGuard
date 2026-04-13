"""Span metrics collector — extract numeric metrics from traces.

Collects and organizes all quantitative metrics from a trace:
- Duration distribution (p50, p90, p99)
- Token counts and costs
- Context sizes
- Error rates
- Retry rates

Designed for dashboarding and monitoring integrations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace, SpanStatus, SpanType


def _percentile(sorted_values: list[float], p: float) -> float:
    """Calculate percentile from sorted values."""
    if not sorted_values:
        return 0
    k = (len(sorted_values) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_values[int(k)]
    return sorted_values[f] * (c - k) + sorted_values[c] * (k - f)


@dataclass
class DurationMetrics:
    """Duration distribution metrics."""
    count: int = 0
    total_ms: float = 0
    min_ms: float = float("inf")
    max_ms: float = 0
    avg_ms: float = 0
    p50_ms: float = 0
    p90_ms: float = 0
    p99_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "count": self.count,
            "total_ms": round(self.total_ms, 1),
            "min_ms": round(self.min_ms, 1) if self.min_ms != float("inf") else None,
            "max_ms": round(self.max_ms, 1),
            "avg_ms": round(self.avg_ms, 1),
            "p50_ms": round(self.p50_ms, 1),
            "p90_ms": round(self.p90_ms, 1),
            "p99_ms": round(self.p99_ms, 1),
        }


@dataclass
class TraceMetrics:
    """All extracted metrics from a trace."""
    trace_id: str
    span_count: int
    agent_count: int
    tool_count: int
    handoff_count: int
    overall_duration: DurationMetrics
    agent_duration: DurationMetrics
    tool_duration: DurationMetrics
    success_rate: float
    error_rate: float
    retry_rate: float  # fraction of spans with retries
    total_tokens: int
    total_cost_usd: float
    total_context_bytes: int

    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "span_count": self.span_count,
            "agent_count": self.agent_count,
            "tool_count": self.tool_count,
            "handoff_count": self.handoff_count,
            "overall_duration": self.overall_duration.to_dict(),
            "agent_duration": self.agent_duration.to_dict(),
            "tool_duration": self.tool_duration.to_dict(),
            "success_rate": round(self.success_rate, 3),
            "error_rate": round(self.error_rate, 3),
            "retry_rate": round(self.retry_rate, 3),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_context_bytes": self.total_context_bytes,
        }

    def to_prometheus(self) -> str:
        """Export as Prometheus text exposition format."""
        lines = [
            '# HELP agentguard_span_count Total number of spans',
            '# TYPE agentguard_span_count gauge',
            f'agentguard_span_count{{trace_id="{self.trace_id}"}} {self.span_count}',
            '# HELP agentguard_success_rate Success rate of spans',
            '# TYPE agentguard_success_rate gauge',
            f'agentguard_success_rate{{trace_id="{self.trace_id}"}} {self.success_rate}',
            '# HELP agentguard_duration_ms Trace duration in milliseconds',
            '# TYPE agentguard_duration_ms gauge',
            f'agentguard_duration_ms{{trace_id="{self.trace_id}",quantile="0.5"}} {self.overall_duration.p50_ms}',
            f'agentguard_duration_ms{{trace_id="{self.trace_id}",quantile="0.9"}} {self.overall_duration.p90_ms}',
            f'agentguard_duration_ms{{trace_id="{self.trace_id}",quantile="0.99"}} {self.overall_duration.p99_ms}',
            '# HELP agentguard_tokens_total Total tokens consumed',
            '# TYPE agentguard_tokens_total counter',
            f'agentguard_tokens_total{{trace_id="{self.trace_id}"}} {self.total_tokens}',
            '# HELP agentguard_cost_usd Total estimated cost in USD',
            '# TYPE agentguard_cost_usd counter',
            f'agentguard_cost_usd{{trace_id="{self.trace_id}"}} {self.total_cost_usd}',
        ]
        return "\n".join(lines)


def _compute_duration_metrics(durations: list[float]) -> DurationMetrics:
    """Compute duration distribution from a list of durations."""
    if not durations:
        return DurationMetrics()

    sorted_d = sorted(durations)
    return DurationMetrics(
        count=len(sorted_d),
        total_ms=sum(sorted_d),
        min_ms=sorted_d[0],
        max_ms=sorted_d[-1],
        avg_ms=sum(sorted_d) / len(sorted_d),
        p50_ms=_percentile(sorted_d, 50),
        p90_ms=_percentile(sorted_d, 90),
        p99_ms=_percentile(sorted_d, 99),
    )


def extract_metrics(trace: ExecutionTrace) -> TraceMetrics:
    """Extract all numeric metrics from a trace."""
    all_durations = []
    agent_durations = []
    tool_durations = []

    agent_count = 0
    tool_count = 0
    handoff_count = 0
    success_count = 0
    failure_count = 0
    retry_span_count = 0
    total_tokens = 0
    total_cost = 0.0
    total_context_bytes = 0

    for span in trace.spans:
        dur = span.duration_ms
        if dur is not None:
            all_durations.append(dur)
            if span.span_type == SpanType.AGENT:
                agent_durations.append(dur)
            elif span.span_type == SpanType.TOOL:
                tool_durations.append(dur)

        if span.span_type == SpanType.AGENT:
            agent_count += 1
        elif span.span_type == SpanType.TOOL:
            tool_count += 1
        elif span.span_type == SpanType.HANDOFF:
            handoff_count += 1

        if span.status == SpanStatus.COMPLETED:
            success_count += 1
        elif span.status == SpanStatus.FAILED:
            failure_count += 1

        if span.retry_count > 0:
            retry_span_count += 1

        total_tokens += span.token_count or 0
        total_cost += span.estimated_cost_usd or 0
        total_context_bytes += span.context_size_bytes or 0

    total = len(trace.spans) or 1

    return TraceMetrics(
        trace_id=trace.trace_id,
        span_count=len(trace.spans),
        agent_count=agent_count,
        tool_count=tool_count,
        handoff_count=handoff_count,
        overall_duration=_compute_duration_metrics(all_durations),
        agent_duration=_compute_duration_metrics(agent_durations),
        tool_duration=_compute_duration_metrics(tool_durations),
        success_rate=success_count / total,
        error_rate=failure_count / total,
        retry_rate=retry_span_count / total,
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        total_context_bytes=total_context_bytes,
    )
