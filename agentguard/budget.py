"""Context budget tracking — monitor token/context consumption against limits.

In production multi-agent systems, each agent has a context window limit.
This module tracks how much of each agent's budget is consumed and warns
when approaching limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType


@dataclass
class BudgetUsage:
    """Context budget usage for a single agent."""
    agent_name: str
    budget_tokens: Optional[int]  # configured limit (None = unlimited)
    used_tokens: int
    input_tokens: int  # tokens in input
    output_tokens: int  # tokens generated
    utilization: float  # 0-1 (used/budget)
    over_budget: bool
    headroom_tokens: int  # remaining budget
    
    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "budget": self.budget_tokens,
            "used": self.used_tokens,
            "utilization": round(self.utilization, 3),
            "over_budget": self.over_budget,
            "headroom": self.headroom_tokens,
        }


@dataclass
class BudgetReport:
    """Context budget report for a trace."""
    agents: list[BudgetUsage]
    total_tokens: int
    total_budget: Optional[int]
    over_budget_count: int
    high_utilization_count: int  # agents using > 80% of budget
    
    def to_dict(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "total_budget": self.total_budget,
            "over_budget": self.over_budget_count,
            "high_utilization": self.high_utilization_count,
            "agents": [a.to_dict() for a in self.agents],
        }
    
    def to_report(self) -> str:
        lines = [
            f"# Context Budget Report",
            f"Total: {self.total_tokens:,} tokens",
            f"Over budget: {self.over_budget_count} agents",
            f"High utilization: {self.high_utilization_count} agents",
            "",
        ]
        for a in sorted(self.agents, key=lambda x: -x.utilization):
            icon = "🔴" if a.over_budget else "🟡" if a.utilization > 0.8 else "🟢"
            budget_str = f"{a.budget_tokens:,}" if a.budget_tokens else "unlimited"
            lines.append(f"{icon} **{a.agent_name}**: {a.used_tokens:,}/{budget_str} ({a.utilization:.0%})")
        return "\n".join(lines)


def analyze_budget(
    trace: ExecutionTrace,
    budgets: Optional[dict[str, int]] = None,
    default_budget: Optional[int] = None,
) -> BudgetReport:
    """Analyze token budget consumption for each agent.
    
    Args:
        trace: The execution trace.
        budgets: Dict of agent_name → token_limit.
        default_budget: Default budget for agents not in budgets dict.
    """
    budgets = budgets or {}
    agent_usage: dict[str, dict] = {}
    
    for span in trace.spans:
        if span.span_type != SpanType.AGENT:
            continue
        
        name = span.name
        if name not in agent_usage:
            agent_usage[name] = {"input": 0, "output": 0, "total": 0}
        
        tokens = span.token_count or 0
        agent_usage[name]["total"] += tokens
    
    # Also count LLM calls under each agent
    span_map = {s.span_id: s for s in trace.spans}
    for span in trace.spans:
        if span.span_type.value == "llm_call" and span.parent_span_id:
            parent = span_map.get(span.parent_span_id)
            if parent and parent.span_type == SpanType.AGENT:
                name = parent.name
                if name not in agent_usage:
                    agent_usage[name] = {"input": 0, "output": 0, "total": 0}
                agent_usage[name]["total"] += span.token_count or 0
    
    agents = []
    for name, usage in agent_usage.items():
        budget = budgets.get(name, default_budget)
        used = usage["total"]
        
        if budget:
            util = used / budget
            over = used > budget
            headroom = max(budget - used, 0)
        else:
            util = 0
            over = False
            headroom = 0
        
        agents.append(BudgetUsage(
            agent_name=name,
            budget_tokens=budget,
            used_tokens=used,
            input_tokens=usage["input"],
            output_tokens=usage["output"],
            utilization=util,
            over_budget=over,
            headroom_tokens=headroom,
        ))
    
    total = sum(a.used_tokens for a in agents)
    total_budget = sum(a.budget_tokens or 0 for a in agents) or None
    
    return BudgetReport(
        agents=agents,
        total_tokens=total,
        total_budget=total_budget,
        over_budget_count=sum(1 for a in agents if a.over_budget),
        high_utilization_count=sum(1 for a in agents if a.utilization > 0.8),
    )
