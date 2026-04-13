"""Batch processing — run analysis on multiple traces efficiently.

Provides:
- Batch analysis with progress tracking
- Parallel-friendly batch operations
- Summary statistics across batches
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from agentguard.core.trace import ExecutionTrace
from agentguard.metrics import extract_metrics
from agentguard.scoring import score_trace
from agentguard.stats import DescriptiveStats, describe


@dataclass
class BatchAnalysis:
    """Results of batch analysis across traces."""
    trace_count: int
    scores: DescriptiveStats
    durations: DescriptiveStats
    span_counts: DescriptiveStats
    success_rate: float
    total_tokens: int
    total_cost_usd: float
    custom_results: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "trace_count": self.trace_count,
            "scores": self.scores.to_dict(),
            "durations": self.durations.to_dict(),
            "span_counts": self.span_counts.to_dict(),
            "success_rate": round(self.success_rate, 3),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "custom": self.custom_results,
        }

    def to_report(self) -> str:
        lines = [
            f"# Batch Analysis ({self.trace_count} traces)",
            "",
            f"- **Success Rate:** {self.success_rate:.0%}",
            f"- **Score:** {self.scores.mean:.0f} avg (p50: {self.scores.median:.0f}, p90: {self.scores.p90:.0f})",
            f"- **Duration:** {self.durations.mean:.0f}ms avg (p90: {self.durations.p90:.0f}ms)",
            f"- **Spans:** {self.span_counts.mean:.0f} avg per trace",
            f"- **Total Tokens:** {self.total_tokens:,}",
            f"- **Total Cost:** ${self.total_cost_usd:.2f}",
        ]
        return "\n".join(lines)


def batch_analyze(
    traces: list[ExecutionTrace],
    custom_analyzers: dict[str, Callable] | None = None,
) -> BatchAnalysis:
    """Run batch analysis on multiple traces.

    Args:
        traces: Traces to analyze.
        custom_analyzers: Optional dict of name → function to run on each trace.
    """
    if not traces:
        return BatchAnalysis(
            trace_count=0,
            scores=describe([]),
            durations=describe([]),
            span_counts=describe([]),
            success_rate=0,
            total_tokens=0,
            total_cost_usd=0,
        )

    scores_list = []
    durations_list = []
    span_counts_list = []
    success_count = 0
    total_tokens = 0
    total_cost = 0.0
    custom_results: dict[str, list] = {name: [] for name in (custom_analyzers or {})}

    for trace in traces:
        s = score_trace(trace)
        m = extract_metrics(trace)

        scores_list.append(s.overall)
        if trace.duration_ms:
            durations_list.append(trace.duration_ms)
        span_counts_list.append(len(trace.spans))

        if trace.status.value == "completed":
            success_count += 1

        total_tokens += m.total_tokens
        total_cost += m.total_cost_usd

        for name, fn in (custom_analyzers or {}).items():
            try:
                custom_results[name].append(fn(trace))
            except Exception as e:
                custom_results[name].append({"error": str(e)})

    return BatchAnalysis(
        trace_count=len(traces),
        scores=describe(scores_list),
        durations=describe(durations_list),
        span_counts=describe(span_counts_list),
        success_rate=success_count / max(len(traces), 1),
        total_tokens=total_tokens,
        total_cost_usd=total_cost,
        custom_results=custom_results,
    )
