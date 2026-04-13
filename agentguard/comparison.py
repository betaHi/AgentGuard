"""Trace comparison — comprehensive comparison report between two traces.

Combines all analysis modules to produce a rich comparison:
- Score comparison
- Metric deltas
- Flow graph diff
- Context flow diff
- New/removed spans
"""

from __future__ import annotations

from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace
from agentguard.metrics import extract_metrics
from agentguard.scoring import score_trace
from agentguard.tree import compute_tree_stats


@dataclass
class ComparisonReport:
    """Comprehensive comparison between two traces."""
    trace_a_id: str
    trace_b_id: str
    score_a: float
    score_b: float
    score_delta: float
    grade_a: str
    grade_b: str
    metric_deltas: dict
    structural_changes: dict
    summary: str

    def to_dict(self) -> dict:
        return {
            "trace_a": self.trace_a_id,
            "trace_b": self.trace_b_id,
            "scores": {"a": round(self.score_a, 1), "b": round(self.score_b, 1), "delta": round(self.score_delta, 1)},
            "grades": {"a": self.grade_a, "b": self.grade_b},
            "metric_deltas": self.metric_deltas,
            "structural_changes": self.structural_changes,
            "summary": self.summary,
        }

    def to_report(self) -> str:
        lines = [
            "# Trace Comparison",
            f"**{self.trace_a_id}** vs **{self.trace_b_id}**",
            "",
            "| Metric | Trace A | Trace B | Delta |",
            "|--------|---------|---------|-------|",
            f"| Score | {self.score_a:.0f} ({self.grade_a}) | {self.score_b:.0f} ({self.grade_b}) | {self.score_delta:+.0f} |",
        ]

        for key, delta in self.metric_deltas.items():
            lines.append(f"| {key} | {delta['a']} | {delta['b']} | {delta['delta']} |")

        lines.append("")
        lines.append(f"**{self.summary}**")

        if self.structural_changes:
            lines.append("")
            lines.append("## Structural Changes")
            for key, val in self.structural_changes.items():
                lines.append(f"- {key}: {val}")

        return "\n".join(lines)


def compare_traces(trace_a: ExecutionTrace, trace_b: ExecutionTrace) -> ComparisonReport:
    """Generate a comprehensive comparison between two traces."""
    score_a = score_trace(trace_a)
    score_b = score_trace(trace_b)

    metrics_a = extract_metrics(trace_a)
    metrics_b = extract_metrics(trace_b)

    stats_a = compute_tree_stats(trace_a)
    stats_b = compute_tree_stats(trace_b)

    # Metric deltas
    metric_deltas = {}

    metric_deltas["Spans"] = {
        "a": metrics_a.span_count, "b": metrics_b.span_count,
        "delta": metrics_b.span_count - metrics_a.span_count,
    }
    metric_deltas["Success Rate"] = {
        "a": f"{metrics_a.success_rate:.0%}", "b": f"{metrics_b.success_rate:.0%}",
        "delta": f"{(metrics_b.success_rate - metrics_a.success_rate):+.0%}",
    }
    metric_deltas["Tokens"] = {
        "a": metrics_a.total_tokens, "b": metrics_b.total_tokens,
        "delta": metrics_b.total_tokens - metrics_a.total_tokens,
    }
    metric_deltas["Cost"] = {
        "a": f"${metrics_a.total_cost_usd:.2f}", "b": f"${metrics_b.total_cost_usd:.2f}",
        "delta": f"${metrics_b.total_cost_usd - metrics_a.total_cost_usd:+.2f}",
    }

    # Structural changes
    structural = {}

    names_a = {s.name for s in trace_a.spans}
    names_b = {s.name for s in trace_b.spans}

    added = names_b - names_a
    removed = names_a - names_b

    if added:
        structural["Spans added"] = list(added)
    if removed:
        structural["Spans removed"] = list(removed)
    if stats_a.depth != stats_b.depth:
        structural["Depth change"] = f"{stats_a.depth} → {stats_b.depth}"
    if stats_a.root_count != stats_b.root_count:
        structural["Root count change"] = f"{stats_a.root_count} → {stats_b.root_count}"

    # Summary
    delta = score_b.overall - score_a.overall
    if delta > 10:
        summary = "📈 Significant improvement"
    elif delta > 0:
        summary = "📈 Slight improvement"
    elif delta > -10:
        summary = "➡️ Similar quality"
    else:
        summary = "📉 Regression detected"

    return ComparisonReport(
        trace_a_id=trace_a.trace_id,
        trace_b_id=trace_b.trace_id,
        score_a=score_a.overall,
        score_b=score_b.overall,
        score_delta=delta,
        grade_a=score_a.grade,
        grade_b=score_b.grade,
        metric_deltas=metric_deltas,
        structural_changes=structural,
        summary=summary,
    )
