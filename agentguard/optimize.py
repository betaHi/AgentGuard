"""Trace optimization suggestions — identify cost and performance improvements.

Analyzes traces to suggest:
- Unnecessary retries that could be avoided
- Parallel execution opportunities
- Token/cost reduction strategies
- Handoff simplification
- Span consolidation
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentguard.core.trace import ExecutionTrace, Span, SpanType


@dataclass
class Suggestion:
    """A single optimization suggestion."""
    category: str  # "performance", "cost", "reliability", "simplification"
    priority: str  # "high", "medium", "low"
    title: str
    description: str
    estimated_impact: str  # human-readable impact estimate
    affected_spans: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "priority": self.priority,
            "title": self.title,
            "description": self.description,
            "estimated_impact": self.estimated_impact,
            "affected_spans": self.affected_spans,
        }


@dataclass
class OptimizationReport:
    """Collection of optimization suggestions."""
    suggestions: list[Suggestion]
    estimated_savings_pct: float  # overall estimated improvement

    def to_dict(self) -> dict:
        return {
            "suggestion_count": len(self.suggestions),
            "estimated_savings_pct": round(self.estimated_savings_pct, 1),
            "suggestions": [s.to_dict() for s in self.suggestions],
        }

    def to_report(self) -> str:
        lines = [
            f"# Optimization Suggestions ({len(self.suggestions)} found)",
            f"Estimated improvement: ~{self.estimated_savings_pct:.0f}%",
            "",
        ]
        for s in sorted(self.suggestions, key=lambda x: {"high": 0, "medium": 1, "low": 2}.get(x.priority, 3)):
            icon = {"high": "🔴", "medium": "🟡", "low": "🟢"}.get(s.priority, "⚪")
            lines.append(f"{icon} **[{s.priority.upper()}] {s.title}** ({s.category})")
            lines.append(f"   {s.description}")
            lines.append(f"   Impact: {s.estimated_impact}")
            lines.append("")
        return "\n".join(lines)


def _suggest_retry_fix(trace: ExecutionTrace) -> list[Suggestion]:
    """Suggest fixes for spans with excessive retries (>2)."""
    retry_spans = [s for s in trace.spans if s.retry_count > 2]
    if not retry_spans:
        return []
    total = sum(s.retry_count for s in retry_spans)
    return [Suggestion(
        category="reliability", priority="high",
        title="Excessive retries detected",
        description=f"{len(retry_spans)} spans have >2 retries ({total} total). Consider circuit breakers.",
        estimated_impact=f"Save ~{total * 500}ms in retry wait time",
        affected_spans=[s.name for s in retry_spans],
    )]


def _suggest_parallelization(children_map: dict[str, list[Span]]) -> list[Suggestion]:
    """Suggest parallelization for sequential agents without data dependencies."""
    suggestions = []
    for _pid, children in children_map.items():
        agents = sorted(
            [c for c in children if c.span_type == SpanType.AGENT],
            key=lambda s: s.started_at or "",
        )
        if len(agents) < 2:
            continue
        # Check sequential
        sequential = all(
            not agents[i+1].started_at or not agents[i].ended_at or
            agents[i+1].started_at >= agents[i].ended_at
            for i in range(len(agents) - 1)
        )
        if not sequential:
            continue
        # Check data dependencies
        has_dep = any(
            isinstance(a.output_data, dict) and isinstance(b.input_data, dict)
            and set(a.output_data.keys()) & set(b.input_data.keys())
            for i, a in enumerate(agents) for b in agents[i+1:]
        )
        if has_dep:
            continue
        total_dur = sum(s.duration_ms or 0 for s in agents)
        max_dur = max(s.duration_ms or 0 for s in agents)
        savings = total_dur - max_dur
        suggestions.append(Suggestion(
            category="performance", priority="high",
            title="Parallelization opportunity",
            description=f"{len(agents)} agents run sequentially without data dependencies.",
            estimated_impact=f"Save ~{savings:.0f}ms ({savings/max(total_dur,1)*100:.0f}%)",
            affected_spans=[s.name for s in agents],
        ))
    return suggestions


def _suggest_cost_reduction(trace: ExecutionTrace) -> list[Suggestion]:
    """Suggest cost reduction for spans dominating total cost."""
    if not trace.spans:
        return []
    costs = [(s.name, s.estimated_cost_usd or 0) for s in trace.spans]
    total = sum(c for _, c in costs)
    if total <= 0:
        return []
    top_name, top_cost = max(costs, key=lambda x: x[1])
    if top_cost <= total * 0.5:
        return []
    return [Suggestion(
        category="cost", priority="medium",
        title=f"'{top_name}' dominates cost",
        description=f"'{top_name}' is {top_cost/total*100:.0f}% of cost (${top_cost:.4f}/${total:.4f}).",
        estimated_impact=f"Potential savings: ${top_cost*0.3:.4f}",
        affected_spans=[top_name],
    )]


def _suggest_context_trimming(trace: ExecutionTrace) -> list[Suggestion]:
    """Suggest trimming unused context at handoff points."""
    suggestions = []
    for h in trace.spans:
        if h.span_type != SpanType.HANDOFF:
            continue
        dropped = h.context_dropped_keys or []
        sent = h.metadata.get("handoff.context_keys", [])
        if dropped and len(dropped) > len(sent) * 0.5:
            suggestions.append(Suggestion(
                category="simplification", priority="low",
                title="Excessive context at handoff",
                description=f"{h.handoff_from}→{h.handoff_to}: {len(dropped)}/{len(sent)} keys unused.",
                estimated_impact="Reduce context size", affected_spans=[h.name],
            ))
    return suggestions


def _suggest_slow_tool_fixes(trace: ExecutionTrace) -> list[Suggestion]:
    """Suggest optimization for tools significantly slower than average."""
    tools = [s for s in trace.spans if s.span_type == SpanType.TOOL and s.duration_ms]
    if not tools:
        return []
    avg = sum(s.duration_ms for s in tools) / len(tools)
    suggestions = []
    for t in tools:
        if t.duration_ms > avg * 3:
            suggestions.append(Suggestion(
                category="performance", priority="medium",
                title=f"Slow tool: {t.name}",
                description=f"{t.name} took {t.duration_ms:.0f}ms ({t.duration_ms/avg:.1f}x avg).",
                estimated_impact=f"Save ~{t.duration_ms - avg:.0f}ms",
                affected_spans=[t.name],
            ))
    return suggestions


def suggest_optimizations(trace: ExecutionTrace) -> OptimizationReport:
    """Analyze a trace and suggest optimizations across 5 dimensions."""
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)

    suggestions = (
        _suggest_retry_fix(trace)
        + _suggest_parallelization(children_map)
        + _suggest_cost_reduction(trace)
        + _suggest_context_trimming(trace)
        + _suggest_slow_tool_fixes(trace)
    )
    return OptimizationReport(
        suggestions=suggestions,
        estimated_savings_pct=min(len(suggestions) * 10, 50),
    )
