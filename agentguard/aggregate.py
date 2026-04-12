"""Trace aggregation — combine multiple traces for trend analysis.

When you run the same pipeline many times, aggregate analysis reveals:
- Success rate trends (is reliability improving?)
- Performance trends (is it getting faster?)
- Common failure patterns (what fails most?)
- Agent rankings (which agents need attention?)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.scoring import score_trace


@dataclass
class AgentStats:
    """Aggregated statistics for a single agent across traces."""
    name: str
    total_invocations: int = 0
    successes: int = 0
    failures: int = 0
    total_duration_ms: float = 0
    min_duration_ms: float = float("inf")
    max_duration_ms: float = 0
    total_retries: int = 0
    
    @property
    def success_rate(self) -> float:
        return self.successes / max(self.total_invocations, 1)
    
    @property
    def avg_duration_ms(self) -> float:
        return self.total_duration_ms / max(self.total_invocations, 1)
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "invocations": self.total_invocations,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "min_duration_ms": round(self.min_duration_ms, 1) if self.min_duration_ms != float("inf") else None,
            "max_duration_ms": round(self.max_duration_ms, 1),
            "total_retries": self.total_retries,
        }


@dataclass
class AggregateReport:
    """Aggregated analysis across multiple traces."""
    trace_count: int
    success_count: int
    failure_count: int
    avg_score: float
    score_trend: list[float]  # scores over time
    avg_duration_ms: float
    duration_trend: list[float]  # durations over time
    agent_stats: list[AgentStats]
    common_errors: list[dict]  # most frequent errors
    
    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.trace_count, 1)
    
    def to_dict(self) -> dict:
        return {
            "trace_count": self.trace_count,
            "success_rate": round(self.success_rate, 3),
            "avg_score": round(self.avg_score, 1),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "score_trend": [round(s, 1) for s in self.score_trend],
            "duration_trend": [round(d, 1) for d in self.duration_trend],
            "agent_stats": [a.to_dict() for a in self.agent_stats],
            "common_errors": self.common_errors[:10],
        }
    
    def to_report(self) -> str:
        lines = [
            f"# Aggregate Report ({self.trace_count} traces)",
            "",
            f"- **Success rate:** {self.success_rate:.0%}",
            f"- **Average score:** {self.avg_score:.0f}/100",
            f"- **Average duration:** {self.avg_duration_ms:.0f}ms",
            "",
            "## Agent Rankings (by success rate)",
            "",
        ]
        sorted_agents = sorted(self.agent_stats, key=lambda a: a.success_rate)
        for a in sorted_agents:
            icon = "🟢" if a.success_rate >= 0.9 else "🟡" if a.success_rate >= 0.7 else "🔴"
            lines.append(f"{icon} **{a.name}** — {a.success_rate:.0%} success, "
                        f"{a.avg_duration_ms:.0f}ms avg, {a.total_retries} retries")
        
        if self.common_errors:
            lines.append("")
            lines.append("## Common Errors")
            for err in self.common_errors[:5]:
                lines.append(f"- **{err['error'][:80]}** — {err['count']} occurrences ({err.get('agent', 'unknown')})")
        
        # Trend
        if len(self.score_trend) >= 2:
            lines.append("")
            first_half = sum(self.score_trend[:len(self.score_trend)//2]) / max(len(self.score_trend)//2, 1)
            second_half = sum(self.score_trend[len(self.score_trend)//2:]) / max(len(self.score_trend) - len(self.score_trend)//2, 1)
            if second_half > first_half + 5:
                lines.append("📈 **Trend: Improving** — scores are going up")
            elif second_half < first_half - 5:
                lines.append("📉 **Trend: Declining** — scores are going down")
            else:
                lines.append("➡️ **Trend: Stable** — scores are consistent")
        
        return "\n".join(lines)


def aggregate_traces(traces: list[ExecutionTrace]) -> AggregateReport:
    """Aggregate analysis across multiple traces.
    
    Args:
        traces: List of traces to aggregate (ideally from the same pipeline).
    
    Returns:
        AggregateReport with trends, agent stats, and common errors.
    """
    if not traces:
        return AggregateReport(
            trace_count=0, success_count=0, failure_count=0,
            avg_score=0, score_trend=[], avg_duration_ms=0,
            duration_trend=[], agent_stats=[], common_errors=[],
        )
    
    scores = []
    durations = []
    agent_map: dict[str, AgentStats] = {}
    error_counts: dict[str, dict] = {}
    success_count = 0
    
    for trace in traces:
        # Score each trace
        ts = score_trace(trace)
        scores.append(ts.overall)
        
        # Duration
        dur = trace.duration_ms or 0
        durations.append(dur)
        
        # Success
        if trace.status == SpanStatus.COMPLETED:
            success_count += 1
        
        # Per-agent stats
        for span in trace.spans:
            if span.span_type not in (SpanType.AGENT, SpanType.TOOL):
                continue
            
            name = span.name
            if name not in agent_map:
                agent_map[name] = AgentStats(name=name)
            
            stats = agent_map[name]
            stats.total_invocations += 1
            
            if span.status == SpanStatus.COMPLETED:
                stats.successes += 1
            elif span.status == SpanStatus.FAILED:
                stats.failures += 1
            
            if span.duration_ms:
                stats.total_duration_ms += span.duration_ms
                stats.min_duration_ms = min(stats.min_duration_ms, span.duration_ms)
                stats.max_duration_ms = max(stats.max_duration_ms, span.duration_ms)
            
            stats.total_retries += span.retry_count
            
            # Error tracking
            if span.error:
                key = span.error[:100]
                if key not in error_counts:
                    error_counts[key] = {"error": span.error, "count": 0, "agent": name}
                error_counts[key]["count"] += 1
    
    # Sort errors by frequency
    common_errors = sorted(error_counts.values(), key=lambda x: -x["count"])
    
    return AggregateReport(
        trace_count=len(traces),
        success_count=success_count,
        failure_count=len(traces) - success_count,
        avg_score=sum(scores) / len(scores) if scores else 0,
        score_trend=scores,
        avg_duration_ms=sum(durations) / len(durations) if durations else 0,
        duration_trend=durations,
        agent_stats=list(agent_map.values()),
        common_errors=common_errors,
    )
