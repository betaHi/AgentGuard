"""Agent health report — aggregate metrics across multiple traces.

Produces a health report answering:
- Is each agent getting better or worse over time?
- Which agents have declining success rates?
- Which tools are unreliable?
"""

__all__ = ['AgentHealth', 'HealthReport', 'generate_health_report']


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.query import TraceStore


@dataclass
class AgentHealth:
    """Health metrics for a single agent."""
    name: str
    total_runs: int = 0
    success_rate: float = 0.0
    avg_duration_ms: float = 0.0
    max_duration_ms: float = 0.0
    recent_trend: str = "stable"  # improving, degrading, stable
    error_types: list[str] = field(default_factory=list)
    status: str = "healthy"  # healthy, warning, critical

    def to_dict(self) -> dict:
        return {
            "name": self.name, "runs": self.total_runs,
            "success_rate": round(self.success_rate, 2),
            "avg_duration_ms": round(self.avg_duration_ms),
            "status": self.status, "trend": self.recent_trend,
        }


@dataclass
class HealthReport:
    """Aggregate health report across all agents."""
    agents: list[AgentHealth] = field(default_factory=list)
    overall_health: str = "healthy"
    total_traces: int = 0
    
    def to_dict(self) -> dict:
        return {
            "overall": self.overall_health,
            "total_traces": self.total_traces,
            "agents": [a.to_dict() for a in self.agents],
        }
    
    def to_report(self) -> str:
        icon = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}.get(self.overall_health, "⚪")
        lines = [
            "# Agent Health Report",
            "",
            f"Overall: {icon} {self.overall_health.upper()}",
            f"Total traces analyzed: {self.total_traces}",
            "",
            "## Agents",
            "",
        ]
        for a in sorted(self.agents, key=lambda x: x.success_rate):
            a_icon = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}.get(a.status, "⚪")
            trend = {"improving": "📈", "degrading": "📉", "stable": "➡️"}.get(a.recent_trend, "")
            lines.append(f"- {a_icon} **{a.name}** — {a.success_rate:.0%} success, {a.avg_duration_ms:.0f}ms avg {trend}")
            if a.error_types:
                lines.append(f"  Errors: {', '.join(a.error_types[:3])}")
        return "\n".join(lines)


def generate_health_report(
    traces_dir: str = ".agentguard/traces",
    warning_threshold: float = 0.8,
    critical_threshold: float = 0.5,
) -> HealthReport:
    """Generate a health report from all traces on disk.
    
    Args:
        traces_dir: Directory containing trace files.
        warning_threshold: Success rate below this = warning.
        critical_threshold: Success rate below this = critical.
    """
    store = TraceStore(traces_dir)
    traces = store.load_all()
    agent_stats = store.agent_stats()
    
    agents = []
    worst_status = "healthy"
    
    for name, stats in agent_stats.items():
        rate = stats["success_rate"]
        
        if rate < critical_threshold:
            status = "critical"
        elif rate < warning_threshold:
            status = "warning"
        else:
            status = "healthy"
        
        if status == "critical":
            worst_status = "critical"
        elif status == "warning" and worst_status != "critical":
            worst_status = "warning"
        
        agents.append(AgentHealth(
            name=name,
            total_runs=stats["executions"],
            success_rate=rate,
            avg_duration_ms=stats["avg_duration_ms"],
            max_duration_ms=stats["max_duration_ms"],
            error_types=stats["error_types"],
            status=status,
        ))
    
    return HealthReport(
        agents=agents,
        overall_health=worst_status,
        total_traces=len(traces),
    )
