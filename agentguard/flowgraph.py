"""Multi-agent flow graph — dependency DAG, parallel/sequential detection, critical path.

Models the actual execution flow as a directed acyclic graph (DAG),
identifying:
- True parallel vs sequential execution (based on time overlap)
- Agent dependencies (data flow via handoffs or parent-child)
- Critical path (longest path through the DAG by duration)
- Execution phases (groups of spans that run together)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from agentguard.core.trace import ExecutionTrace, SpanType


@dataclass
class FlowNode:
    """A node in the flow graph representing an agent or key span."""
    span_id: str
    name: str
    span_type: str
    duration_ms: float
    status: str
    start_time: str | None = None
    end_time: str | None = None
    dependencies: list[str] = field(default_factory=list)  # span_ids this depends on
    dependents: list[str] = field(default_factory=list)     # span_ids that depend on this

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "type": self.span_type,
            "duration_ms": round(self.duration_ms, 1),
            "status": self.status,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
        }


@dataclass
class ExecutionPhase:
    """A phase of execution — a group of spans running concurrently."""
    phase_id: int
    span_names: list[str]
    span_ids: list[str]
    start_time: str
    end_time: str
    duration_ms: float
    is_parallel: bool  # True if multiple spans overlap in this phase

    def to_dict(self) -> dict:
        return {
            "phase_id": self.phase_id,
            "spans": self.span_names,
            "duration_ms": round(self.duration_ms, 1),
            "is_parallel": self.is_parallel,
            "parallelism": len(self.span_names),
        }


@dataclass
class FlowGraph:
    """Complete flow graph analysis for a multi-agent trace."""
    nodes: list[FlowNode]
    edges: list[dict]  # {"from": id, "to": id, "type": "sequential"|"handoff"|"parent_child"}
    phases: list[ExecutionPhase]
    critical_path: list[str]  # span names on the critical path
    critical_path_ms: float
    max_parallelism: int  # max number of concurrent spans
    sequential_fraction: float  # fraction of trace time that was sequential

    def to_dict(self) -> dict:
        return {
            "nodes": [n.to_dict() for n in self.nodes],
            "edges": self.edges,
            "phases": [p.to_dict() for p in self.phases],
            "critical_path": self.critical_path,
            "critical_path_ms": round(self.critical_path_ms, 1),
            "max_parallelism": self.max_parallelism,
            "sequential_fraction": round(self.sequential_fraction, 2),
        }

    def to_mermaid(self) -> str:
        """Generate a Mermaid flowchart representation."""
        lines = ["graph TD"]
        for node in self.nodes:
            shape = "([{}])" if node.span_type == "agent" else "[{}]"
            label = shape.format(node.name)
            style = ""
            if node.status == "failed":
                style = f"\n    style {node.span_id} fill:#ff6b6b"
            lines.append(f"    {node.span_id}{label}{style}")

        for edge in self.edges:
            label = edge.get("type", "")
            arrow = f"-->|{label}|" if label else "-->"
            lines.append(f"    {edge['from']} {arrow} {edge['to']}")

        return "\n".join(lines)

    def to_report(self) -> str:
        lines = [
            "# Flow Graph Analysis",
            "",
            f"- **Agents:** {sum(1 for n in self.nodes if n.span_type == 'agent')}",
            f"- **Max parallelism:** {self.max_parallelism}",
            f"- **Sequential fraction:** {self.sequential_fraction:.0%}",
            f"- **Critical path:** {' → '.join(self.critical_path)} ({self.critical_path_ms:.0f}ms)",
            "",
            "## Execution Phases",
            "",
        ]
        for phase in self.phases:
            mode = "⚡ parallel" if phase.is_parallel else "➡️ sequential"
            lines.append(f"Phase {phase.phase_id}: {', '.join(phase.span_names)} ({mode}, {phase.duration_ms:.0f}ms)")

        return "\n".join(lines)


def _parse_time(iso_str: str | None) -> datetime | None:
    """Parse ISO timestamp, return None on failure."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None


def _time_overlap(start1: datetime, end1: datetime, start2: datetime, end2: datetime) -> bool:
    """Check if two time ranges overlap."""
    return start1 < end2 and start2 < end1


def _extract_nodes(trace: ExecutionTrace) -> list[FlowNode]:
    """Extract FlowNodes from agent, tool, and handoff spans."""
    nodes = []
    for s in trace.spans:
        if s.span_type in (SpanType.AGENT, SpanType.TOOL, SpanType.HANDOFF):
            nodes.append(FlowNode(
                span_id=s.span_id, name=s.name,
                span_type=s.span_type.value,
                duration_ms=s.duration_ms or 0,
                status=s.status.value,
                start_time=s.started_at, end_time=s.ended_at,
            ))
    return nodes


def _extract_edges(
    trace: ExecutionTrace,
    node_ids: set[str],
    children_map: dict[str, list[str]],
    span_map: dict[str, Any],
) -> list[dict]:
    """Extract edges: parent-child, handoff, and sequential relationships."""
    edges = []
    # Parent-child
    for s in trace.spans:
        if s.parent_span_id and s.span_id in node_ids and s.parent_span_id in node_ids:
            edges.append({"from": s.parent_span_id, "to": s.span_id, "type": "parent_child"})
    # Handoff
    for s in trace.spans:
        if s.span_type == SpanType.HANDOFF and s.handoff_from and s.handoff_to:
            from_spans = [sp for sp in trace.spans if sp.name == s.handoff_from and sp.span_id in node_ids]
            to_spans = [sp for sp in trace.spans if sp.name == s.handoff_to and sp.span_id in node_ids]
            if from_spans and to_spans:
                edges.append({"from": from_spans[0].span_id, "to": to_spans[0].span_id, "type": "handoff"})
    # Sequential
    for _pid, child_ids in children_map.items():
        children = [span_map[cid] for cid in child_ids if cid in span_map]
        agents = sorted(
            [c for c in children if c.span_type == SpanType.AGENT and c.span_id in node_ids],
            key=lambda s: s.started_at or "",
        )
        for i in range(len(agents) - 1):
            a, b = agents[i], agents[i + 1]
            a_end, b_start = _parse_time(a.ended_at), _parse_time(b.started_at)
            if a_end and b_start and a_end <= b_start:
                edges.append({"from": a.span_id, "to": b.span_id, "type": "sequential"})
    return edges


def _detect_phases(
    trace: ExecutionTrace,
    children_map: dict[str, list[str]],
) -> list[ExecutionPhase]:
    """Group leaf spans into execution phases by time overlap."""
    parent_ids = set(children_map.keys())
    leaf_spans = [s for s in trace.spans
                  if s.span_type in (SpanType.AGENT, SpanType.TOOL, SpanType.HANDOFF)
                  and s.span_id not in parent_ids]
    timed = []
    for s in leaf_spans:
        start, end = _parse_time(s.started_at), _parse_time(s.ended_at)
        if start and end:
            timed.append((s, start, end))
    timed.sort(key=lambda x: x[1])
    if not timed:
        return []
    return _group_into_phases(timed)


def _group_into_phases(timed: list[tuple]) -> list[ExecutionPhase]:
    """Group time-sorted spans into phases by overlap detection."""
    phases: list[ExecutionPhase] = []
    current_group = [timed[0]]
    group_end = timed[0][2]
    for i in range(1, len(timed)):
        s, start, end = timed[i]
        if start < group_end:
            current_group.append(timed[i])
            group_end = max(group_end, end)
        else:
            phases.append(_make_phase(len(phases) + 1, current_group))
            current_group = [timed[i]]
            group_end = end
    if current_group:
        phases.append(_make_phase(len(phases) + 1, current_group))
    return phases


def _make_phase(phase_id: int, group: list[tuple]) -> ExecutionPhase:
    """Create an ExecutionPhase from a group of timed spans."""
    phase_start = min(t[1] for t in group)
    phase_end = max(t[2] for t in group)
    return ExecutionPhase(
        phase_id=phase_id,
        span_names=[t[0].name for t in group],
        span_ids=[t[0].span_id for t in group],
        start_time=phase_start.isoformat(),
        end_time=phase_end.isoformat(),
        duration_ms=(phase_end - phase_start).total_seconds() * 1000,
        is_parallel=len(group) > 1,
    )


def _find_dag_critical_path(
    nodes: list[FlowNode],
    edges: list[dict],
) -> tuple[list[str], float]:
    """Find the critical path (longest chain) in the DAG via topological DP.

    Returns:
        (path_names, total_duration_ms)
    """
    node_map = {n.span_id: n for n in nodes}
    in_degree: dict[str, int] = {n.span_id: 0 for n in nodes}
    adj: dict[str, list[str]] = {n.span_id: [] for n in nodes}
    for edge in edges:
        if edge["from"] in adj and edge["to"] in in_degree:
            adj[edge["from"]].append(edge["to"])
            in_degree[edge["to"]] += 1
    # Kahn's topological sort
    queue = [nid for nid, deg in in_degree.items() if deg == 0]
    topo_order = []
    while queue:
        nid = queue.pop(0)
        topo_order.append(nid)
        for neighbor in adj.get(nid, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)
    # Longest path DP
    dist: dict[str, float] = {nid: 0 for nid in dist} if False else {nid: 0 for nid in in_degree}
    pred: dict[str, str | None] = {nid: None for nid in in_degree}
    for nid in topo_order:
        if nid in node_map:
            for neighbor in adj.get(nid, []):
                new_dist = dist[nid] + node_map[nid].duration_ms
                if new_dist > dist.get(neighbor, 0):
                    dist[neighbor] = new_dist
                    pred[neighbor] = nid
    if not dist:
        return [], 0
    end_node = max(dist, key=lambda k: dist[k] + (node_map[k].duration_ms if k in node_map else 0))
    total_ms = dist[end_node] + (node_map[end_node].duration_ms if end_node in node_map else 0)
    path = []
    current: str | None = end_node
    while current is not None:
        if current in node_map:
            path.append(node_map[current].name)
        current = pred.get(current)
    path.reverse()
    return path, total_ms


def build_flow_graph(trace: ExecutionTrace) -> FlowGraph:
    """Build a flow graph from a trace.

    Analyzes dependencies, parallel execution, phases, and critical path.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

    nodes = _extract_nodes(trace)
    node_ids = {n.span_id for n in nodes}
    edges = _extract_edges(trace, node_ids, children_map, span_map)

    # Wire up dependencies
    node_map = {n.span_id: n for n in nodes}
    for edge in edges:
        if edge["from"] in node_map:
            node_map[edge["from"]].dependents.append(edge["to"])
        if edge["to"] in node_map:
            node_map[edge["to"]].dependencies.append(edge["from"])

    phases = _detect_phases(trace, children_map)
    critical_path, critical_path_ms = _find_dag_critical_path(nodes, edges)

    max_parallelism = max((len(p.span_names) for p in phases), default=1)
    total_phase_ms = sum(p.duration_ms for p in phases) or 1
    seq_ms = sum(p.duration_ms for p in phases if not p.is_parallel)

    return FlowGraph(
        nodes=nodes, edges=edges, phases=phases,
        critical_path=critical_path,
        critical_path_ms=critical_path_ms,
        max_parallelism=max_parallelism,
        sequential_fraction=seq_ms / total_phase_ms,
    )
