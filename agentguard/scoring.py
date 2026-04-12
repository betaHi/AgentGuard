"""Trace scoring — aggregate quality score for execution traces.

Computes a single 0-100 quality score for a trace based on:
- Success rate (did spans complete?)
- Performance (how fast relative to expectations?)
- Context integrity (was context preserved across handoffs?)
- Resilience (were failures handled?)
- Efficiency (parallelism utilization, no wasted retries)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


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


def score_trace(
    trace: ExecutionTrace,
    expected_duration_ms: Optional[float] = None,
) -> TraceScore:
    """Score a trace on multiple quality dimensions.
    
    Args:
        trace: The execution trace to score.
        expected_duration_ms: Optional expected duration for performance scoring.
    
    Returns:
        TraceScore with overall score, grade, and component breakdown.
    """
    components = []
    
    # 1. Success Rate (weight: 0.30)
    total_spans = len(trace.spans)
    if total_spans == 0:
        success_score = 0.0
        success_detail = "No spans recorded"
    else:
        completed = sum(1 for s in trace.spans if s.status == SpanStatus.COMPLETED)
        rate = completed / total_spans
        success_score = rate * 100
        failed = total_spans - completed
        success_detail = f"{completed}/{total_spans} spans completed ({failed} failed/running)"
    
    components.append(ScoreComponent(
        name="Success Rate", score=success_score, weight=0.30,
        details=success_detail,
    ))
    
    # 2. Performance (weight: 0.20)
    if expected_duration_ms and trace.duration_ms:
        ratio = trace.duration_ms / expected_duration_ms
        if ratio <= 1.0:
            perf_score = 100.0
        elif ratio <= 2.0:
            perf_score = 100 - (ratio - 1.0) * 50  # linear decay
        else:
            perf_score = max(0, 50 - (ratio - 2.0) * 25)
        perf_detail = f"{trace.duration_ms:.0f}ms vs {expected_duration_ms:.0f}ms expected ({ratio:.1f}x)"
    elif trace.duration_ms:
        # No expected duration — score based on whether it completed
        perf_score = 80.0 if trace.status == SpanStatus.COMPLETED else 40.0
        perf_detail = f"{trace.duration_ms:.0f}ms (no baseline)"
    else:
        perf_score = 50.0
        perf_detail = "No duration data"
    
    components.append(ScoreComponent(
        name="Performance", score=perf_score, weight=0.20,
        details=perf_detail,
    ))
    
    # 3. Context Integrity (weight: 0.20)
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    if handoff_spans:
        utilizations = [s.metadata.get("handoff.utilization", 1.0) for s in handoff_spans]
        avg_util = sum(utilizations) / len(utilizations)
        dropped = sum(len(s.context_dropped_keys or []) for s in handoff_spans)
        total_keys = sum(len(s.metadata.get("handoff.context_keys", [])) for s in handoff_spans)
        preservation = 1.0 - (dropped / max(total_keys, 1))
        ctx_score = ((avg_util + preservation) / 2) * 100
        ctx_detail = f"Utilization: {avg_util:.0%}, Preservation: {preservation:.0%}, {len(handoff_spans)} handoffs"
    else:
        ctx_score = 100.0  # no handoffs = no context issues (neutral)
        ctx_detail = "No handoffs recorded (neutral)"
    
    components.append(ScoreComponent(
        name="Context Integrity", score=ctx_score, weight=0.20,
        details=ctx_detail,
    ))
    
    # 4. Resilience (weight: 0.15)
    failed_spans = [s for s in trace.spans if s.status == SpanStatus.FAILED]
    if failed_spans:
        # Check how many failures were handled
        handled = sum(1 for s in failed_spans if s.failure_handled)
        # Also check if parent succeeded despite child failure
        span_map = {s.span_id: s for s in trace.spans}
        for s in failed_spans:
            if not s.failure_handled and s.parent_span_id:
                parent = span_map.get(s.parent_span_id)
                if parent and parent.status == SpanStatus.COMPLETED:
                    handled += 1
        
        resilience_rate = handled / len(failed_spans)
        res_score = resilience_rate * 100
        res_detail = f"{handled}/{len(failed_spans)} failures handled"
    else:
        res_score = 100.0
        res_detail = "No failures (perfect resilience)"
    
    components.append(ScoreComponent(
        name="Resilience", score=res_score, weight=0.15,
        details=res_detail,
    ))
    
    # 5. Efficiency (weight: 0.15)
    retries = sum(s.retry_count for s in trace.spans)
    agent_count = len(trace.agent_spans)
    
    # Penalize excessive retries
    retry_penalty = min(retries * 5, 50)  # max 50 point penalty
    
    # Reward parallelism (if multiple agents exist)
    if agent_count >= 2:
        # Check for parallel execution (simplified)
        from agentguard.flowgraph import build_flow_graph
        try:
            graph = build_flow_graph(trace)
            parallel_bonus = (1 - graph.sequential_fraction) * 20  # up to 20 bonus
        except Exception:
            parallel_bonus = 0
    else:
        parallel_bonus = 0
    
    eff_score = max(0, min(100, 80 - retry_penalty + parallel_bonus))
    eff_detail = f"{retries} retries, {agent_count} agents"
    if parallel_bonus > 0:
        eff_detail += f", +{parallel_bonus:.0f} parallelism bonus"
    
    components.append(ScoreComponent(
        name="Efficiency", score=eff_score, weight=0.15,
        details=eff_detail,
    ))
    
    # Calculate overall score
    overall = sum(c.score * c.weight for c in components)
    grade = _grade(overall)
    
    # Generate summary
    if grade in ("A", "B"):
        summary = "✅ Trace executed well with good quality metrics."
    elif grade == "C":
        summary = "⚠️ Trace completed but has areas for improvement."
    else:
        summary = "🔴 Trace has significant quality issues that need attention."
    
    weak = min(components, key=lambda c: c.score)
    if weak.score < 70:
        summary += f" Weakest area: {weak.name} ({weak.score:.0f}/100)."
    
    return TraceScore(
        overall=overall,
        grade=grade,
        components=components,
        summary=summary,
    )
