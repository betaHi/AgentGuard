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


def _collect_agent_snapshots(
    trace: ExecutionTrace,
) -> tuple[list[ContextSnapshot], dict[str, dict]]:
    """Collect input/output snapshots and IO metadata for each agent span.

    Returns:
        (snapshots, agent_io) where agent_io maps span_id → IO metadata dict.
    """
    snapshots: list[ContextSnapshot] = []
    agent_io: dict[str, dict] = {}
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
    return snapshots, agent_io


def _are_parallel(a_info: dict, b_info: dict) -> bool:
    """Check if two agents executed in parallel (overlapping time).

    Parallel siblings are independent — not a handoff chain.
    """
    from datetime import datetime
    try:
        a_start = datetime.fromisoformat(a_info["started_at"]) if a_info["started_at"] else None
        a_end = datetime.fromisoformat(a_info["ended_at"]) if a_info["ended_at"] else None
        b_start = datetime.fromisoformat(b_info["started_at"]) if b_info["started_at"] else None
        b_end = datetime.fromisoformat(b_info["ended_at"]) if b_info["ended_at"] else None
        if a_start and a_end and b_start and b_end:
            return a_start < b_end and b_start < a_end
    except Exception:
        pass
    return False


def _detect_transitions(
    children_map: dict[str, list[str]],
    span_map: dict[str, Any],
    agent_io: dict[str, dict],
) -> tuple[list[ContextTransition], list[ContextBandwidth]]:
    """Detect context transitions between sequential agent pairs.

    Skips parallel siblings to avoid false positive truncation reports.
    """
    transitions: list[ContextTransition] = []
    bandwidth: list[ContextBandwidth] = []
    for _pid, child_ids in children_map.items():
        agents = [(cid, span_map[cid]) for cid in child_ids
                  if cid in span_map and span_map[cid].span_type == SpanType.AGENT]
        agents.sort(key=lambda x: x[1].started_at or "")
        for i in range(len(agents) - 1):
            sid_a, _ = agents[i]
            sid_b, _ = agents[i + 1]
            if sid_a not in agent_io or sid_b not in agent_io:
                continue
            a_info, b_info = agent_io[sid_a], agent_io[sid_b]
            # Skip parallel siblings — they are independent, not a chain
            if _are_parallel(a_info, b_info):
                continue
            t, bw = _build_transition(a_info, b_info)
            transitions.append(t)
            if bw:
                bandwidth.append(bw)
    return transitions, bandwidth


# SDK/decorator noise keys that appear in input/output due to argument passing,
# not real context transfer. Excluded from transition analysis to avoid
# false positives in context loss/gain reporting.
_SDK_NOISE_KEYS: frozenset[str] = frozenset({
    "args", "kwargs", "self", "cls",
    "_args", "_kwargs", "__args__", "__kwargs__",
    "func_args", "func_kwargs",
})


def _build_transition(
    a_info: dict, b_info: dict,
) -> tuple[ContextTransition, ContextBandwidth | None]:
    """Build a single transition + optional bandwidth from sender→receiver IO.

    Filters out SDK noise keys (args, kwargs, self, cls) that appear
    from decorator argument passing, not real context transfer.
    """
    out_size, in_size = a_info["out_size"], b_info["in_size"]
    out_keys = set(a_info["out_keys"]) - _SDK_NOISE_KEYS
    in_keys = set(b_info["in_keys"]) - _SDK_NOISE_KEYS
    keys_removed = list(out_keys - in_keys)
    keys_added = list(in_keys - out_keys)
    delta = in_size - out_size
    delta_pct = ((in_size / max(out_size, 1)) - 1) * 100
    event = _classify_transition(out_size, in_size, keys_removed, keys_added)
    t = ContextTransition(
        from_agent=a_info["name"], to_agent=b_info["name"],
        input_size=out_size, output_size=in_size,
        delta_bytes=delta, delta_pct=delta_pct, event=event,
        keys_added=keys_added, keys_removed=keys_removed,
        keys_preserved=list(out_keys & in_keys),
    )
    bw = None
    gap_ms = b_info["duration_ms"] or 1
    if out_size > 0:
        bw = ContextBandwidth(
            from_agent=a_info["name"], to_agent=b_info["name"],
            bytes_transferred=out_size, duration_ms=gap_ms,
            bandwidth_bps=(out_size / gap_ms) * 1000,
        )
    return t, bw


def _detect_handoff_transitions(trace: ExecutionTrace) -> list[ContextTransition]:
    """Detect transitions from explicit HANDOFF spans with dropped keys."""
    transitions = []
    for s in trace.spans:
        if s.span_type != SpanType.HANDOFF:
            continue
        ctx_size = s.context_size_bytes or 0
        dropped = s.context_dropped_keys or []
        if ctx_size > 0 and dropped:
            used = s.context_used_keys or []
            transitions.append(ContextTransition(
                from_agent=s.handoff_from or "unknown",
                to_agent=s.handoff_to or "unknown",
                input_size=ctx_size, output_size=ctx_size,
                delta_bytes=0, delta_pct=0,
                event="truncation" if len(dropped) > len(used) else "transformation",
                keys_removed=dropped, keys_preserved=used,
            ))
    return transitions


def _compute_aggregates(
    transitions: list[ContextTransition],
) -> tuple[int, int, float, str | None, int, int]:
    """Compute aggregate metrics from transitions.

    Returns:
        (total_in, total_out, compression_ratio, bottleneck_agent,
         truncation_events, expansion_events)
    """
    total_in = sum(t.input_size for t in transitions)
    total_out = sum(t.output_size for t in transitions)
    bottleneck, max_loss = None, 0
    for t in transitions:
        loss = t.input_size - t.output_size
        if loss > max_loss:
            max_loss = loss
            bottleneck = t.to_agent
    return (
        total_in, total_out,
        total_out / max(total_in, 1),
        bottleneck,
        sum(1 for t in transitions if t.event == "truncation"),
        sum(1 for t in transitions if t.event == "expansion"),
    )


def analyze_context_flow_deep(trace: ExecutionTrace) -> ContextFlowAnalysis:
    """Deep analysis of context flow through the agent pipeline.

    Tracks how information flows, compresses, and transforms.
    Skips parallel siblings to avoid false truncation reports.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

    snapshots, agent_io = _collect_agent_snapshots(trace)
    transitions, bandwidth = _detect_transitions(children_map, span_map, agent_io)
    transitions.extend(_detect_handoff_transitions(trace))

    ti, to, cr, bn, trunc, exp = _compute_aggregates(transitions)
    return ContextFlowAnalysis(
        snapshots=snapshots, transitions=transitions, bandwidth=bandwidth,
        total_bytes_in=ti, total_bytes_out=to, compression_ratio=cr,
        bottleneck_agent=bn, truncation_events=trunc, expansion_events=exp,
    )
