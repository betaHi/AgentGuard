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
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


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


def suggest_optimizations(trace: ExecutionTrace) -> OptimizationReport:
    """Analyze a trace and suggest optimizations."""
    suggestions: list[Suggestion] = []
    
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)
    
    # 1. Excessive retries
    retry_spans = [s for s in trace.spans if s.retry_count > 2]
    if retry_spans:
        total_retries = sum(s.retry_count for s in retry_spans)
        suggestions.append(Suggestion(
            category="reliability",
            priority="high",
            title="Excessive retries detected",
            description=f"{len(retry_spans)} spans have >2 retries ({total_retries} total). Consider circuit breakers or fallback strategies.",
            estimated_impact=f"Save ~{total_retries * 500}ms in retry wait time",
            affected_spans=[s.name for s in retry_spans],
        ))
    
    # 2. Sequential execution that could be parallel
    for parent_id, children in children_map.items():
        agent_children = [c for c in children if c.span_type == SpanType.AGENT]
        if len(agent_children) >= 2:
            # Check if they're sequential
            sorted_children = sorted(agent_children, key=lambda s: s.started_at or "")
            sequential = True
            for i in range(len(sorted_children) - 1):
                if sorted_children[i + 1].started_at and sorted_children[i].ended_at:
                    if sorted_children[i + 1].started_at < sorted_children[i].ended_at:
                        sequential = False
                        break
            
            if sequential and len(agent_children) >= 2:
                # Check if any agent uses output of another
                has_dependency = False
                for i, a in enumerate(sorted_children):
                    for b in sorted_children[i + 1:]:
                        if isinstance(a.output_data, dict) and isinstance(b.input_data, dict):
                            if set(a.output_data.keys()) & set(b.input_data.keys()):
                                has_dependency = True
                
                if not has_dependency:
                    total_dur = sum(s.duration_ms or 0 for s in agent_children)
                    max_dur = max(s.duration_ms or 0 for s in agent_children)
                    savings = total_dur - max_dur
                    suggestions.append(Suggestion(
                        category="performance",
                        priority="high",
                        title="Parallelization opportunity",
                        description=f"{len(agent_children)} agents run sequentially without data dependencies. They could run in parallel.",
                        estimated_impact=f"Save ~{savings:.0f}ms ({savings/max(total_dur,1)*100:.0f}% of current time)",
                        affected_spans=[s.name for s in agent_children],
                    ))
    
    # 3. High-cost spans
    if trace.spans:
        costs = [(s.name, s.estimated_cost_usd or 0) for s in trace.spans]
        total_cost = sum(c for _, c in costs)
        if total_cost > 0:
            sorted_costs = sorted(costs, key=lambda x: -x[1])
            top = sorted_costs[0]
            if top[1] > total_cost * 0.5:
                suggestions.append(Suggestion(
                    category="cost",
                    priority="medium",
                    title=f"'{top[0]}' dominates cost",
                    description=f"'{top[0]}' accounts for {top[1]/total_cost*100:.0f}% of total cost (${top[1]:.4f} of ${total_cost:.4f}). Consider using a cheaper model or reducing token usage.",
                    estimated_impact=f"Potential savings: ${top[1]*0.3:.4f} (30% reduction)",
                    affected_spans=[top[0]],
                ))
    
    # 4. Unnecessary context passing
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    for h in handoff_spans:
        dropped = h.context_dropped_keys or []
        sent_keys = h.metadata.get("handoff.context_keys", [])
        if dropped and len(dropped) > len(sent_keys) * 0.5:
            suggestions.append(Suggestion(
                category="simplification",
                priority="low",
                title=f"Excessive context at handoff",
                description=f"Handoff from {h.handoff_from} to {h.handoff_to}: {len(dropped)} of {len(sent_keys)} keys were unused. Filter context before handoff.",
                estimated_impact="Reduce context size and processing overhead",
                affected_spans=[h.name],
            ))
    
    # 5. Slow tools
    avg_tool_dur = 0
    tool_spans = [s for s in trace.spans if s.span_type == SpanType.TOOL and s.duration_ms]
    if tool_spans:
        avg_tool_dur = sum(s.duration_ms for s in tool_spans) / len(tool_spans)
        slow_tools = [s for s in tool_spans if s.duration_ms > avg_tool_dur * 3]
        for t in slow_tools:
            suggestions.append(Suggestion(
                category="performance",
                priority="medium",
                title=f"Slow tool: {t.name}",
                description=f"{t.name} took {t.duration_ms:.0f}ms ({t.duration_ms/avg_tool_dur:.1f}x average). Consider caching or optimization.",
                estimated_impact=f"Save ~{t.duration_ms - avg_tool_dur:.0f}ms",
                affected_spans=[t.name],
            ))
    
    # Estimate overall savings
    savings_pct = min(len(suggestions) * 10, 50)  # rough estimate
    
    return OptimizationReport(
        suggestions=suggestions,
        estimated_savings_pct=savings_pct,
    )
