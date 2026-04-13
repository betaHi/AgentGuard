"""Context flow tracking — compression, truncation, and bandwidth analysis.

Tracks how context (information) flows through a multi-agent pipeline:
- Context size at each handoff point
- Compression/truncation detection (context getting smaller = potential info loss)
- Bandwidth analysis (how much data flows between agents per unit time)
- Context bottleneck detection (where the pipeline narrows)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from agentguard.core.trace import ExecutionTrace, SpanType


@dataclass
class ContextSnapshot:
    """Context state at a specific point in the pipeline."""
    agent_name: str
    span_id: str
    direction: str  # "input" or "output"
    size_bytes: int
    key_count: int
    keys: list[str]
    timestamp: str | None = None

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "direction": self.direction,
            "size_bytes": self.size_bytes,
            "key_count": self.key_count,
            "keys": self.keys,
        }


@dataclass
class ContextTransition:
    """How context changed between two agents."""
    from_agent: str
    to_agent: str
    input_size: int
    output_size: int
    delta_bytes: int
    delta_pct: float  # percentage change (-100 to +inf)
    event: str  # "stable", "compression", "truncation", "expansion", "transformation"
    keys_added: list[str] = field(default_factory=list)
    keys_removed: list[str] = field(default_factory=list)
    keys_preserved: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "input_size": self.input_size,
            "output_size": self.output_size,
            "delta_bytes": self.delta_bytes,
            "delta_pct": round(self.delta_pct, 1),
            "event": self.event,
            "keys_added": self.keys_added,
            "keys_removed": self.keys_removed,
        }


@dataclass
class ContextBandwidth:
    """Bandwidth analysis for a section of the pipeline."""
    from_agent: str
    to_agent: str
    bytes_transferred: int
    duration_ms: float
    bandwidth_bps: float  # bytes per second

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "bytes": self.bytes_transferred,
            "duration_ms": round(self.duration_ms, 1),
            "bandwidth_bps": round(self.bandwidth_bps, 1),
        }


@dataclass
class ContextFlowAnalysis:
    """Complete context flow analysis for a trace."""
    snapshots: list[ContextSnapshot]
    transitions: list[ContextTransition]
    bandwidth: list[ContextBandwidth]
    total_bytes_in: int
    total_bytes_out: int
    compression_ratio: float  # output/input ratio (< 1 = compression)
    bottleneck_agent: str | None  # agent where context is most compressed
    truncation_events: int  # number of significant context reductions
    expansion_events: int  # number of significant context expansions

    def to_dict(self) -> dict:
        return {
            "snapshots": [s.to_dict() for s in self.snapshots],
            "transitions": [t.to_dict() for t in self.transitions],
            "bandwidth": [b.to_dict() for b in self.bandwidth],
            "total_bytes_in": self.total_bytes_in,
            "total_bytes_out": self.total_bytes_out,
            "compression_ratio": round(self.compression_ratio, 3),
            "bottleneck_agent": self.bottleneck_agent,
            "truncation_events": self.truncation_events,
            "expansion_events": self.expansion_events,
        }

    def to_report(self) -> str:
        lines = [
            "# Context Flow Analysis",
            "",
            f"- **Total bytes in:** {self.total_bytes_in:,}",
            f"- **Total bytes out:** {self.total_bytes_out:,}",
            f"- **Compression ratio:** {self.compression_ratio:.2f}x",
            f"- **Truncation events:** {self.truncation_events}",
            f"- **Expansion events:** {self.expansion_events}",
        ]
        if self.bottleneck_agent:
            lines.append(f"- **Context bottleneck:** {self.bottleneck_agent}")

        lines.append("")
        lines.append("## Context Transitions")
        for t in self.transitions:
            icon = {
                "stable": "🟢", "compression": "🟡",
                "truncation": "🔴", "expansion": "🔵",
                "transformation": "🟣",
            }.get(t.event, "⚪")
            lines.append(f"{icon} {t.from_agent} → {t.to_agent}: "
                        f"{t.input_size:,}B → {t.output_size:,}B ({t.delta_pct:+.0f}%) [{t.event}]")
            if t.keys_removed:
                lines.append(f"   ⚠ Keys removed: {', '.join(t.keys_removed)}")
            if t.keys_added:
                lines.append(f"   ➕ Keys added: {', '.join(t.keys_added)}")

        return "\n".join(lines)


def _measure_data(data: object | None) -> tuple[int, list[str]]:
    """Measure the size and keys of data."""
    if data is None:
        return 0, []
    try:
        serialized = json.dumps(data, default=str)
        size = len(serialized.encode("utf-8"))
    except Exception:
        size = 0
    keys = list(data.keys()) if isinstance(data, dict) else []
    return size, keys


def _classify_transition(input_size: int, output_size: int,
                          keys_removed: list, keys_added: list) -> str:
    """Classify what happened to context between two points."""
    if input_size == 0 and output_size == 0:
        return "stable"

    if input_size == 0:
        return "expansion"

    ratio = output_size / input_size
    key_change = len(keys_removed) > 0 or len(keys_added) > 0

    if ratio < 0.3 and len(keys_removed) > 0:
        return "truncation"  # severe reduction with key loss
    elif ratio < 0.7:
        return "compression"  # significant reduction
    elif ratio > 2.0:
        return "expansion"  # significant growth
    elif key_change and 0.7 <= ratio <= 1.5:
        return "transformation"  # similar size but different structure
    else:
        return "stable"


def analyze_context_flow_deep(trace: ExecutionTrace) -> ContextFlowAnalysis:
    """Deep analysis of context flow through the agent pipeline.

    Examines input_data and output_data of each agent span to track
    how information flows, compresses, and transforms across the pipeline.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}

    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

    # Collect snapshots: input and output of each agent
    snapshots: list[ContextSnapshot] = []
    agent_io: dict[str, dict] = {}  # span_id -> {input_size, output_size, ...}

    for s in trace.spans:
        if s.span_type != SpanType.AGENT:
            continue

        in_size, in_keys = _measure_data(s.input_data)
        out_size, out_keys = _measure_data(s.output_data)

        snapshots.append(ContextSnapshot(
            agent_name=s.name, span_id=s.span_id, direction="input",
            size_bytes=in_size, key_count=len(in_keys), keys=in_keys,
            timestamp=s.started_at,
        ))
        snapshots.append(ContextSnapshot(
            agent_name=s.name, span_id=s.span_id, direction="output",
            size_bytes=out_size, key_count=len(out_keys), keys=out_keys,
            timestamp=s.ended_at,
        ))

        agent_io[s.span_id] = {
            "name": s.name, "in_size": in_size, "out_size": out_size,
            "in_keys": in_keys, "out_keys": out_keys,
            "started_at": s.started_at, "ended_at": s.ended_at,
            "duration_ms": s.duration_ms or 0,
        }

    # Build transitions: sequential agent pairs under same parent
    transitions: list[ContextTransition] = []
    bandwidth_list: list[ContextBandwidth] = []

    for _parent_id, child_ids in children_map.items():
        agents = [(cid, span_map[cid]) for cid in child_ids
                  if cid in span_map and span_map[cid].span_type == SpanType.AGENT]
        agents.sort(key=lambda x: x[1].started_at or "")

        for i in range(len(agents) - 1):
            sid_a, span_a = agents[i]
            sid_b, span_b = agents[i + 1]

            if sid_a not in agent_io or sid_b not in agent_io:
                continue

            a_info = agent_io[sid_a]
            b_info = agent_io[sid_b]

            # Context flows from A's output to B's input
            out_size = a_info["out_size"]
            in_size = b_info["in_size"]

            out_keys = set(a_info["out_keys"])
            in_keys = set(b_info["in_keys"])

            keys_removed = list(out_keys - in_keys)
            keys_added = list(in_keys - out_keys)
            keys_preserved = list(out_keys & in_keys)

            delta = in_size - out_size
            delta_pct = ((in_size / max(out_size, 1)) - 1) * 100

            event = _classify_transition(out_size, in_size, keys_removed, keys_added)

            transitions.append(ContextTransition(
                from_agent=a_info["name"],
                to_agent=b_info["name"],
                input_size=out_size,  # sender's output
                output_size=in_size,  # receiver's input
                delta_bytes=delta,
                delta_pct=delta_pct,
                event=event,
                keys_added=keys_added,
                keys_removed=keys_removed,
                keys_preserved=keys_preserved,
            ))

            # Bandwidth: bytes transferred / time between spans
            # Time = gap between A's end and B's start, or B's duration
            gap_ms = b_info["duration_ms"] or 1
            if out_size > 0:
                bps = (out_size / gap_ms) * 1000
                bandwidth_list.append(ContextBandwidth(
                    from_agent=a_info["name"],
                    to_agent=b_info["name"],
                    bytes_transferred=out_size,
                    duration_ms=gap_ms,
                    bandwidth_bps=bps,
                ))

    # Also check explicit HANDOFF spans
    for s in trace.spans:
        if s.span_type == SpanType.HANDOFF:
            ctx_size = s.context_size_bytes or 0
            if ctx_size > 0:
                fr = s.handoff_from or "unknown"
                to = s.handoff_to or "unknown"

                # Check if receiver used the context
                used_keys = s.context_used_keys or []
                dropped_keys = s.context_dropped_keys or []

                if dropped_keys:
                    transitions.append(ContextTransition(
                        from_agent=fr, to_agent=to,
                        input_size=ctx_size, output_size=ctx_size,
                        delta_bytes=0, delta_pct=0,
                        event="truncation" if len(dropped_keys) > len(used_keys) else "transformation",
                        keys_removed=dropped_keys,
                        keys_preserved=used_keys,
                    ))

    # Aggregates
    total_in = sum(t.input_size for t in transitions)
    total_out = sum(t.output_size for t in transitions)
    compression_ratio = total_out / max(total_in, 1)

    truncation_events = sum(1 for t in transitions if t.event == "truncation")
    expansion_events = sum(1 for t in transitions if t.event == "expansion")

    # Find bottleneck: agent with the highest compression (most context lost)
    bottleneck = None
    max_loss = 0
    for t in transitions:
        loss = t.input_size - t.output_size
        if loss > max_loss:
            max_loss = loss
            bottleneck = t.to_agent  # the receiving agent is where context was lost

    return ContextFlowAnalysis(
        snapshots=snapshots,
        transitions=transitions,
        bandwidth=bandwidth_list,
        total_bytes_in=total_in,
        total_bytes_out=total_out,
        compression_ratio=compression_ratio,
        bottleneck_agent=bottleneck,
        truncation_events=truncation_events,
        expansion_events=expansion_events,
    )
