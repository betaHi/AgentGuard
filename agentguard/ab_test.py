"""A/B testing support for agent versions.

Compare two versions of an agent pipeline to determine which performs better.
Supports:
- Side-by-side scoring comparison
- Statistical significance (basic)
- Regression detection
- Per-agent performance comparison
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.core.trace import ExecutionTrace, SpanStatus
from agentguard.scoring import score_trace
from agentguard.aggregate import aggregate_traces


@dataclass
class ABResult:
    """Result of an A/B test between two trace groups."""
    group_a_name: str
    group_b_name: str
    group_a_count: int
    group_b_count: int
    group_a_avg_score: float
    group_b_avg_score: float
    group_a_success_rate: float
    group_b_success_rate: float
    group_a_avg_duration_ms: float
    group_b_avg_duration_ms: float
    winner: str  # "a", "b", or "tie"
    score_delta: float
    regressions: list[dict]  # metrics where B is worse than A
    improvements: list[dict]  # metrics where B is better than A
    
    def to_dict(self) -> dict:
        return {
            "group_a": self.group_a_name,
            "group_b": self.group_b_name,
            "winner": self.winner,
            "score_delta": round(self.score_delta, 1),
            "comparison": {
                "scores": {"a": round(self.group_a_avg_score, 1), "b": round(self.group_b_avg_score, 1)},
                "success_rates": {"a": round(self.group_a_success_rate, 3), "b": round(self.group_b_success_rate, 3)},
                "durations_ms": {"a": round(self.group_a_avg_duration_ms, 1), "b": round(self.group_b_avg_duration_ms, 1)},
            },
            "regressions": self.regressions,
            "improvements": self.improvements,
        }
    
    def to_report(self) -> str:
        winner_icon = "🏆"
        lines = [
            f"# A/B Test: {self.group_a_name} vs {self.group_b_name}",
            "",
            f"| Metric | {self.group_a_name} | {self.group_b_name} |",
            f"|--------|{'-' * len(self.group_a_name)}--|{'-' * len(self.group_b_name)}--|",
            f"| Traces | {self.group_a_count} | {self.group_b_count} |",
            f"| Avg Score | {self.group_a_avg_score:.0f} | {self.group_b_avg_score:.0f} |",
            f"| Success Rate | {self.group_a_success_rate:.0%} | {self.group_b_success_rate:.0%} |",
            f"| Avg Duration | {self.group_a_avg_duration_ms:.0f}ms | {self.group_b_avg_duration_ms:.0f}ms |",
            "",
            f"{winner_icon} **Winner: {self.group_b_name if self.winner == 'b' else self.group_a_name if self.winner == 'a' else 'Tie'}** (Δ score: {self.score_delta:+.0f})",
        ]
        
        if self.improvements:
            lines.append("")
            lines.append("## Improvements ✅")
            for imp in self.improvements:
                lines.append(f"- {imp['metric']}: {imp['before']} → {imp['after']}")
        
        if self.regressions:
            lines.append("")
            lines.append("## Regressions 🔴")
            for reg in self.regressions:
                lines.append(f"- {reg['metric']}: {reg['before']} → {reg['after']}")
        
        return "\n".join(lines)


def ab_test(
    group_a: list[ExecutionTrace],
    group_b: list[ExecutionTrace],
    name_a: str = "Baseline",
    name_b: str = "Candidate",
    significance_threshold: float = 5.0,
) -> ABResult:
    """Run an A/B test comparing two groups of traces.
    
    Args:
        group_a: Baseline traces.
        group_b: Candidate traces.
        name_a: Name for group A.
        name_b: Name for group B.
        significance_threshold: Minimum score difference to declare a winner.
    
    Returns:
        ABResult with comparison metrics and winner.
    """
    agg_a = aggregate_traces(group_a)
    agg_b = aggregate_traces(group_b)
    
    score_delta = agg_b.avg_score - agg_a.avg_score
    
    # Determine winner
    if abs(score_delta) < significance_threshold:
        winner = "tie"
    elif score_delta > 0:
        winner = "b"
    else:
        winner = "a"
    
    # Find regressions and improvements
    regressions = []
    improvements = []
    
    metrics = [
        ("Score", agg_a.avg_score, agg_b.avg_score, True),  # higher is better
        ("Success Rate", agg_a.success_rate, agg_b.success_rate, True),
        ("Duration (ms)", agg_a.avg_duration_ms, agg_b.avg_duration_ms, False),  # lower is better
    ]
    
    for name, val_a, val_b, higher_better in metrics:
        delta = val_b - val_a
        if higher_better:
            is_better = delta > 0
        else:
            is_better = delta < 0
        
        entry = {
            "metric": name,
            "before": round(val_a, 2),
            "after": round(val_b, 2),
            "delta": round(delta, 2),
        }
        
        # Only flag significant changes
        if abs(delta) > 0.01:
            if is_better:
                improvements.append(entry)
            else:
                regressions.append(entry)
    
    return ABResult(
        group_a_name=name_a,
        group_b_name=name_b,
        group_a_count=len(group_a),
        group_b_count=len(group_b),
        group_a_avg_score=agg_a.avg_score,
        group_b_avg_score=agg_b.avg_score,
        group_a_success_rate=agg_a.success_rate,
        group_b_success_rate=agg_b.success_rate,
        group_a_avg_duration_ms=agg_a.avg_duration_ms,
        group_b_avg_duration_ms=agg_b.avg_duration_ms,
        winner=winner,
        score_delta=score_delta,
        regressions=regressions,
        improvements=improvements,
    )
