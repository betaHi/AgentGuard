"""Trace scoring — aggregate quality score for execution traces.

Computes a single 0-100 quality score for a trace based on:
- Success rate (did spans complete?)
- Performance (how fast relative to expectations?)
- Context integrity (was context preserved across handoffs?)
- Resilience (were failures handled?)
- Efficiency (parallelism utilization, no wasted retries)
"""

from __future__ import annotations

from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace, SpanStatus, SpanType


@dataclass
class ScoreComponent:
    """A single component of the trace quality score."""
    name: str
    score: float  # 0-100
    weight: float  # 0-1
    details: str

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "score": round(self.score, 1),
            "weight": self.weight,
            "weighted_score": round(self.score * self.weight, 1),
            "details": self.details,
        }


@dataclass
class TraceScore:
    """Aggregate quality score for a trace."""
    overall: float  # 0-100
    grade: str  # A/B/C/D/F
    components: list[ScoreComponent]
    summary: str

    def to_dict(self) -> dict:
        return {
            "overall": round(self.overall, 1),
            "grade": self.grade,
            "components": [c.to_dict() for c in self.components],
            "summary": self.summary,
        }

    def to_report(self) -> str:
        lines = [
            f"# Trace Quality Score: {self.overall:.0f}/100 ({self.grade})",
            "",
            self.summary,
            "",
            "## Components",
            "",
        ]
        for c in self.components:
            bar_len = int(c.score / 5)
            bar = "█" * bar_len + "░" * (20 - bar_len)
            lines.append(f"**{c.name}** ({c.weight:.0%} weight)")
            lines.append(f"  {bar} {c.score:.0f}/100")
            lines.append(f"  {c.details}")
            lines.append("")
        return "\n".join(lines)


def _grade(score: float) -> str:
    """Convert numeric score to letter grade."""
    if score >= 90:
        return "A"
    elif score >= 80:
        return "B"
    elif score >= 70:
        return "C"
    elif score >= 60:
        return "D"
    else:
        return "F"


# Default component weights (must sum to 1.0)
DEFAULT_WEIGHTS: dict[str, float] = {
    "success_rate": 0.30,
    "performance": 0.20,
    "context_integrity": 0.20,
    "resilience": 0.15,
    "efficiency": 0.15,
}


def _score_success_rate(trace: ExecutionTrace) -> ScoreComponent:
    """Score based on ratio of completed spans to total spans."""
    total = len(trace.spans)
    if total == 0:
        return ScoreComponent(name="Success Rate", score=0.0, weight=0, details="No spans recorded")
    completed = sum(1 for s in trace.spans if s.status == SpanStatus.COMPLETED)
    rate = completed / total
    failed = total - completed
    return ScoreComponent(
        name="Success Rate", score=rate * 100, weight=0,
        details=f"{completed}/{total} spans completed ({failed} failed/running)",
    )


def _score_performance(trace: ExecutionTrace, expected_ms: float | None) -> ScoreComponent:
    """Score based on actual vs expected duration."""
    if expected_ms and trace.duration_ms:
        ratio = trace.duration_ms / expected_ms
        if ratio <= 1.0:
            score = 100.0
        elif ratio <= 2.0:
            score = 100 - (ratio - 1.0) * 50
        else:
            score = max(0, 50 - (ratio - 2.0) * 25)
        detail = f"{trace.duration_ms:.0f}ms vs {expected_ms:.0f}ms expected ({ratio:.1f}x)"
    elif trace.duration_ms:
        score = 80.0 if trace.status == SpanStatus.COMPLETED else 40.0
        detail = f"{trace.duration_ms:.0f}ms (no baseline)"
    else:
        score, detail = 50.0, "No duration data"
    return ScoreComponent(name="Performance", score=score, weight=0, details=detail)


def _score_context_integrity(trace: ExecutionTrace) -> ScoreComponent:
    """Score based on handoff context preservation and utilization."""
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    if not handoff_spans:
        return ScoreComponent(name="Context Integrity", score=100.0, weight=0,
                              details="No handoffs recorded (neutral)")
    utilizations = [s.metadata.get("handoff.utilization", 1.0) for s in handoff_spans]
    avg_util = sum(utilizations) / len(utilizations)
    dropped = sum(len(s.context_dropped_keys or []) for s in handoff_spans)
    total_keys = sum(len(s.metadata.get("handoff.context_keys", [])) for s in handoff_spans)
    preservation = 1.0 - (dropped / max(total_keys, 1))
    score = ((avg_util + preservation) / 2) * 100
    return ScoreComponent(
        name="Context Integrity", score=score, weight=0,
        details=f"Utilization: {avg_util:.0%}, Preservation: {preservation:.0%}, {len(handoff_spans)} handoffs",
    )


def _score_resilience(trace: ExecutionTrace) -> ScoreComponent:
    """Score based on ratio of handled failures to total failures."""
    failed_spans = [s for s in trace.spans if s.status == SpanStatus.FAILED]
    if not failed_spans:
        return ScoreComponent(name="Resilience", score=100.0, weight=0,
                              details="No failures (perfect resilience)")
    handled = sum(1 for s in failed_spans if s.failure_handled)
    span_map = {s.span_id: s for s in trace.spans}
    for s in failed_spans:
        if not s.failure_handled and s.parent_span_id:
            parent = span_map.get(s.parent_span_id)
            if parent and parent.status == SpanStatus.COMPLETED:
                handled += 1
    rate = handled / len(failed_spans)
    return ScoreComponent(
        name="Resilience", score=rate * 100, weight=0,
        details=f"{handled}/{len(failed_spans)} failures handled",
    )


def _score_efficiency(trace: ExecutionTrace) -> ScoreComponent:
    """Score based on retry count and parallelism utilization."""
    retries = sum(s.retry_count for s in trace.spans)
    agent_count = len(trace.agent_spans)
    retry_penalty = min(retries * 5, 50)
    parallel_bonus = 0.0
    if agent_count >= 2:
        from agentguard.flowgraph import build_flow_graph
        try:
            graph = build_flow_graph(trace)
            parallel_bonus = (1 - graph.sequential_fraction) * 20
        except Exception:
            pass
    score = max(0, min(100, 80 - retry_penalty + parallel_bonus))
    detail = f"{retries} retries, {agent_count} agents"
    if parallel_bonus > 0:
        detail += f", +{parallel_bonus:.0f} parallelism bonus"
    return ScoreComponent(name="Efficiency", score=score, weight=0, details=detail)


def _summarize_score(overall: float, grade: str, components: list[ScoreComponent]) -> str:
    """Generate a human-readable summary from score and components."""
    if grade in ("A", "B"):
        summary = "✅ Trace executed well with good quality metrics."
    elif grade == "C":
        summary = "⚠️ Trace completed but has areas for improvement."
    else:
        summary = "🔴 Trace has significant quality issues that need attention."
    weak = min(components, key=lambda c: c.score)
    if weak.score < 70:
        summary += f" Weakest area: {weak.name} ({weak.score:.0f}/100)."
    return summary


def score_trace(
    trace: ExecutionTrace,
    expected_duration_ms: float | None = None,
    weights: dict[str, float] | None = None,
) -> TraceScore:
    """Score a trace on multiple quality dimensions.

    Dimensions: success rate, performance, context integrity,
    resilience, and efficiency. Each scored 0-100, weighted.

    Args:
        trace: The execution trace to score.
        expected_duration_ms: Optional expected duration for performance scoring.
        weights: Custom component weights (keys: success_rate, performance,
            context_integrity, resilience, efficiency). Sum should be 1.0.
    """
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    scorers = [
        ("success_rate", _score_success_rate(trace)),
        ("performance", _score_performance(trace, expected_duration_ms)),
        ("context_integrity", _score_context_integrity(trace)),
        ("resilience", _score_resilience(trace)),
        ("efficiency", _score_efficiency(trace)),
    ]
    components = []
    for key, comp in scorers:
        comp.weight = w[key]
        components.append(comp)

    overall = sum(c.score * c.weight for c in components)
    grade = _grade(overall)
    return TraceScore(
        overall=overall, grade=grade, components=components,
        summary=_summarize_score(overall, grade, components),
    )
