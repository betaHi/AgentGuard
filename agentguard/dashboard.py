"""Dashboard data provider — prepare data for monitoring dashboards.

Generates structured data suitable for rendering in web dashboards:
- System health overview
- Recent trace summary
- Top errors
- Performance trends
- Agent leaderboard
"""

from __future__ import annotations

from dataclasses import dataclass

from agentguard.aggregate import aggregate_traces
from agentguard.core.trace import ExecutionTrace
from agentguard.metrics import extract_metrics
from agentguard.scoring import score_trace
from agentguard.stats import detect_trend


@dataclass
class DashboardData:
    """Structured data for a monitoring dashboard."""
    health_status: str  # "healthy", "degraded", "critical"
    overall_score: float
    trace_count: int
    success_rate: float
    avg_duration_ms: float
    total_cost_usd: float
    recent_traces: list[dict]
    top_errors: list[dict]
    agent_leaderboard: list[dict]
    performance_trend: str  # "improving", "stable", "declining"

    def to_dict(self) -> dict:
        return {
            "health": self.health_status,
            "score": round(self.overall_score, 1),
            "trace_count": self.trace_count,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "recent_traces": self.recent_traces[:10],
            "top_errors": self.top_errors[:5],
            "agent_leaderboard": self.agent_leaderboard[:10],
            "trend": self.performance_trend,
        }


def build_dashboard(traces: list[ExecutionTrace]) -> DashboardData:
    """Build dashboard data from a list of traces."""
    if not traces:
        return DashboardData(
            health_status="unknown", overall_score=0, trace_count=0,
            success_rate=0, avg_duration_ms=0, total_cost_usd=0,
            recent_traces=[], top_errors=[], agent_leaderboard=[],
            performance_trend="insufficient_data",
        )

    agg = aggregate_traces(traces)

    # Health status
    if agg.success_rate >= 0.95 and agg.avg_score >= 70:
        health = "healthy"
    elif agg.success_rate >= 0.7:
        health = "degraded"
    else:
        health = "critical"

    # Recent traces summary
    recent = []
    for t in traces[-10:]:
        s = score_trace(t)
        m = extract_metrics(t)
        recent.append({
            "trace_id": t.trace_id,
            "task": t.task,
            "status": t.status.value,
            "score": round(s.overall, 1),
            "grade": s.grade,
            "duration_ms": t.duration_ms,
            "span_count": len(t.spans),
            "cost_usd": round(m.total_cost_usd, 4),
        })

    # Performance trend
    trend = detect_trend(agg.score_trend) if len(agg.score_trend) >= 3 else "insufficient_data"

    # Total cost
    total_cost = sum(m.total_cost_usd for m in [extract_metrics(t) for t in traces])

    return DashboardData(
        health_status=health,
        overall_score=agg.avg_score,
        trace_count=len(traces),
        success_rate=agg.success_rate,
        avg_duration_ms=agg.avg_duration_ms,
        total_cost_usd=total_cost,
        recent_traces=recent,
        top_errors=agg.common_errors[:5],
        agent_leaderboard=[a.to_dict() for a in agg.agent_stats[:10]],
        performance_trend=trend,
    )
