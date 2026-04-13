"""Agent profiling — build performance profiles for individual agents.

Collects per-agent statistics across multiple traces to build
a performance profile:
- Baseline duration (normal range)
- Error patterns (common failure modes)
- Resource usage (tokens, cost)
- Interaction patterns (who does this agent hand off to?)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentguard.core.trace import ExecutionTrace, SpanStatus, SpanType


@dataclass
class AgentProfile:
    """Performance profile for a single agent."""
    name: str
    total_invocations: int = 0
    success_count: int = 0
    failure_count: int = 0
    durations_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    total_tokens: int = 0
    total_cost_usd: float = 0
    handoff_to: dict[str, int] = field(default_factory=dict)  # agent_name -> count
    handoff_from: dict[str, int] = field(default_factory=dict)
    tags_seen: set[str] = field(default_factory=set)

    @property
    def success_rate(self) -> float:
        return self.success_count / max(self.total_invocations, 1)

    @property
    def avg_duration_ms(self) -> float:
        return sum(self.durations_ms) / max(len(self.durations_ms), 1)

    @property
    def p95_duration_ms(self) -> float:
        if not self.durations_ms:
            return 0
        sorted_d = sorted(self.durations_ms)
        idx = int(len(sorted_d) * 0.95)
        return sorted_d[min(idx, len(sorted_d) - 1)]

    @property
    def common_errors(self) -> list[tuple[str, int]]:
        counts: dict[str, int] = {}
        for e in self.errors:
            key = e[:100]
            counts[key] = counts.get(key, 0) + 1
        return sorted(counts.items(), key=lambda x: -x[1])

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "invocations": self.total_invocations,
            "success_rate": round(self.success_rate, 3),
            "avg_duration_ms": round(self.avg_duration_ms, 1),
            "p95_duration_ms": round(self.p95_duration_ms, 1),
            "total_tokens": self.total_tokens,
            "total_cost_usd": round(self.total_cost_usd, 4),
            "common_errors": self.common_errors[:5],
            "handoff_to": dict(self.handoff_to),
            "handoff_from": dict(self.handoff_from),
        }

    def to_report(self) -> str:
        lines = [
            f"# Agent Profile: {self.name}",
            "",
            f"- **Invocations:** {self.total_invocations}",
            f"- **Success rate:** {self.success_rate:.0%}",
            f"- **Avg duration:** {self.avg_duration_ms:.0f}ms (p95: {self.p95_duration_ms:.0f}ms)",
            f"- **Tokens:** {self.total_tokens:,} (${self.total_cost_usd:.2f})",
        ]
        if self.common_errors:
            lines.append("")
            lines.append("## Common Errors")
            for err, count in self.common_errors[:3]:
                lines.append(f"- {err} ({count}x)")
        if self.handoff_to:
            lines.append("")
            lines.append("## Hands off to:")
            for agent, count in sorted(self.handoff_to.items(), key=lambda x: -x[1]):
                lines.append(f"- {agent} ({count}x)")
        return "\n".join(lines)


def build_agent_profiles(traces: list[ExecutionTrace]) -> dict[str, AgentProfile]:
    """Build profiles for all agents across multiple traces."""
    profiles: dict[str, AgentProfile] = {}

    for trace in traces:
        for span in trace.spans:
            if span.span_type != SpanType.AGENT:
                continue

            name = span.name
            if name not in profiles:
                profiles[name] = AgentProfile(name=name)

            p = profiles[name]
            p.total_invocations += 1

            if span.status == SpanStatus.COMPLETED:
                p.success_count += 1
            elif span.status == SpanStatus.FAILED:
                p.failure_count += 1
                if span.error:
                    p.errors.append(span.error)

            if span.duration_ms:
                p.durations_ms.append(span.duration_ms)

            p.total_tokens += span.token_count or 0
            p.total_cost_usd += span.estimated_cost_usd or 0
            p.tags_seen.update(span.tags)

        # Track handoffs
        for span in trace.spans:
            if span.span_type == SpanType.HANDOFF:
                fr = span.handoff_from or ""
                to = span.handoff_to or ""
                if fr and fr in profiles:
                    profiles[fr].handoff_to[to] = profiles[fr].handoff_to.get(to, 0) + 1
                if to and to in profiles:
                    profiles[to].handoff_from[fr] = profiles[to].handoff_from.get(fr, 0) + 1

    return profiles
