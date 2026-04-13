"""Agent dependency graph — explicit and inferred dependencies.

Goes beyond parent-child to identify:
- Data dependencies (agent B needs output from agent A)
- Handoff dependencies (explicit handoff links)
- Temporal dependencies (B always starts after A)
- Shared resource dependencies (both use same tool)
"""

from __future__ import annotations

from dataclasses import dataclass

from agentguard.core.trace import ExecutionTrace, Span, SpanType


@dataclass
class Dependency:
    """A dependency between two agents."""
    from_agent: str
    to_agent: str
    dep_type: str  # "data", "handoff", "temporal", "shared_tool"
    confidence: float  # 0-1
    evidence: str

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "type": self.dep_type,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
        }


@dataclass
class DependencyGraph:
    """Complete dependency graph for a multi-agent trace."""
    dependencies: list[Dependency]
    agents: list[str]
    root_agents: list[str]  # agents with no incoming dependencies
    leaf_agents: list[str]  # agents with no outgoing dependencies

    def to_dict(self) -> dict:
        return {
            "agents": self.agents,
            "root_agents": self.root_agents,
            "leaf_agents": self.leaf_agents,
            "dependencies": [d.to_dict() for d in self.dependencies],
        }

    def to_mermaid(self) -> str:
        lines = ["graph LR"]
        for agent in self.agents:
            lines.append(f"    {agent.replace(' ', '_')}([{agent}])")
        for dep in self.dependencies:
            fr = dep.from_agent.replace(' ', '_')
            to = dep.to_agent.replace(' ', '_')
            lines.append(f"    {fr} -->|{dep.dep_type}| {to}")
        return "\n".join(lines)

    def to_report(self) -> str:
        lines = [
            "# Agent Dependency Graph",
            "",
            f"- **Agents:** {len(self.agents)}",
            f"- **Dependencies:** {len(self.dependencies)}",
            f"- **Roots (entry points):** {', '.join(self.root_agents) or 'none'}",
            f"- **Leaves (exit points):** {', '.join(self.leaf_agents) or 'none'}",
            "",
        ]
        for dep in self.dependencies:
            icon = {"data": "📦", "handoff": "🔀", "temporal": "⏱️", "shared_tool": "🔧"}.get(dep.dep_type, "📎")
            lines.append(f"{icon} {dep.from_agent} → {dep.to_agent} [{dep.dep_type}] ({dep.confidence:.0%})")
            lines.append(f"   {dep.evidence}")
        return "\n".join(lines)


def build_dependency_graph(trace: ExecutionTrace) -> DependencyGraph:
    """Build a dependency graph from a trace.

    Infers dependencies from:
    1. Explicit handoffs
    2. Sequential execution under same parent (temporal)
    3. Data flow (output keys of A match input keys of B)
    4. Shared tool usage
    """
    span_map = {s.span_id: s for s in trace.spans}
    agent_spans = [s for s in trace.spans if s.span_type == SpanType.AGENT]
    agents = list(set(s.name for s in agent_spans))

    deps: list[Dependency] = []
    seen_deps: set[tuple[str, str, str]] = set()

    def add_dep(fr: str, to: str, dtype: str, conf: float, evidence: str) -> None:
        key = (fr, to, dtype)
        if key not in seen_deps and fr != to:
            seen_deps.add(key)
            deps.append(Dependency(from_agent=fr, to_agent=to, dep_type=dtype,
                                  confidence=conf, evidence=evidence))

    # 1. Handoff dependencies
    for s in trace.spans:
        if s.span_type == SpanType.HANDOFF and s.handoff_from and s.handoff_to:
            add_dep(s.handoff_from, s.handoff_to, "handoff", 1.0,
                    f"Explicit handoff: {s.name}")

    # 2. Temporal dependencies (sequential agents under same parent)
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)

    for _parent_id, children in children_map.items():
        child_agents = sorted(
            [c for c in children if c.span_type == SpanType.AGENT],
            key=lambda s: s.started_at or ""
        )
        for i in range(len(child_agents) - 1):
            a = child_agents[i]
            b = child_agents[i + 1]
            # Check if B starts after A ends (sequential)
            if a.ended_at and b.started_at and b.started_at >= a.ended_at:
                add_dep(a.name, b.name, "temporal", 0.8,
                        "Sequential execution under same parent")

    # 3. Data dependencies (output keys → input keys match)
    for _i, a in enumerate(agent_spans):
        if not isinstance(a.output_data, dict):
            continue
        out_keys = set(a.output_data.keys())
        if not out_keys:
            continue

        for b in agent_spans:
            if a.span_id == b.span_id:
                continue
            if not isinstance(b.input_data, dict):
                continue
            in_keys = set(b.input_data.keys())
            overlap = out_keys & in_keys
            if overlap:
                conf = len(overlap) / max(len(out_keys), 1)
                add_dep(a.name, b.name, "data", min(conf, 1.0),
                        f"Shared keys: {sorted(overlap)}")

    # 4. Shared tool dependencies
    agent_tools: dict[str, set[str]] = {}
    for s in trace.spans:
        if s.span_type == SpanType.TOOL and s.parent_span_id:
            parent = span_map.get(s.parent_span_id)
            if parent and parent.span_type == SpanType.AGENT:
                agent_tools.setdefault(parent.name, set()).add(s.name)

    agent_names = list(agent_tools.keys())
    for i, a in enumerate(agent_names):
        for b in agent_names[i + 1:]:
            shared = agent_tools[a] & agent_tools[b]
            if shared:
                add_dep(a, b, "shared_tool", 0.5,
                        f"Both use: {sorted(shared)}")

    # Find roots and leaves
    has_incoming = {d.to_agent for d in deps}
    has_outgoing = {d.from_agent for d in deps}
    root_agents = [a for a in agents if a not in has_incoming]
    leaf_agents = [a for a in agents if a not in has_outgoing]

    return DependencyGraph(
        dependencies=deps,
        agents=agents,
        root_agents=root_agents,
        leaf_agents=leaf_agents,
    )
