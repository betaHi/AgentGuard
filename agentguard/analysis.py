"""Trace analysis — failure propagation, context flow, critical path.

Given a multi-agent execution trace, these functions answer:
- Where did the failure originate? (root cause)
- How did it propagate? (blast radius)
- Was it handled or did it bubble up? (resilience)
- How did context flow between agents? (handoff analysis)
- What was the critical path? (bottleneck)
"""

__all__ = ['FailureNode', 'FailureAnalysis', 'analyze_failures', 'HandoffInfo', 'FlowAnalysis', 'analyze_flow', 'BottleneckReport', 'analyze_bottleneck', 'ContextFlowPoint', 'ContextFlowReport', 'analyze_context_flow', 'analyze_retries', 'analyze_cost', 'analyze_timing']


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


@dataclass
class FailureNode:
    """A node in the failure propagation tree."""
    span_id: str
    span_name: str
    span_type: str
    error: str
    is_root_cause: bool = False
    was_handled: bool = False
    affected_children: list[FailureNode] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "name": self.span_name,
            "type": self.span_type,
            "error": self.error,
            "is_root_cause": self.is_root_cause,
            "was_handled": self.was_handled,
            "affected_children": [c.to_dict() for c in self.affected_children],
        }


@dataclass
class FailureAnalysis:
    """Complete failure analysis for a trace."""
    root_causes: list[FailureNode]
    total_failed_spans: int
    blast_radius: int  # number of spans affected by failures
    handled_count: int  # failures that were caught
    unhandled_count: int  # failures that propagated
    resilience_score: float  # 0-1, higher = more resilient

    def to_dict(self) -> dict:
        return {
            "root_causes": [r.to_dict() for r in self.root_causes],
            "total_failed_spans": self.total_failed_spans,
            "blast_radius": self.blast_radius,
            "handled_count": self.handled_count,
            "unhandled_count": self.unhandled_count,
            "resilience_score": round(self.resilience_score, 2),
        }

    def to_report(self) -> str:
        lines = [
            "# Failure Propagation Analysis",
            "",
            f"- **Failed spans:** {self.total_failed_spans}",
            f"- **Root causes:** {len(self.root_causes)}",
            f"- **Blast radius:** {self.blast_radius} spans affected",
            f"- **Handled:** {self.handled_count}, **Unhandled:** {self.unhandled_count}",
            f"- **Resilience score:** {self.resilience_score:.0%}",
            "",
        ]
        for rc in self.root_causes:
            icon = "🟡" if rc.was_handled else "🔴"
            lines.append(f"{icon} **Root cause:** {rc.span_name} ({rc.span_type})")
            lines.append(f"   Error: {rc.error}")
            if rc.affected_children:
                lines.append(f"   Affected: {len(rc.affected_children)} downstream spans")
        return "\n".join(lines)


def analyze_failures(trace: ExecutionTrace) -> FailureAnalysis:
    """Analyze failure propagation in a trace.
    
    Identifies root cause failures, tracks propagation paths,
    and computes resilience metrics.
    
    Args:
        trace: The execution trace to analyze.
    
    Returns:
        FailureAnalysis with root causes, blast radius, and resilience score.
    """
    failed = [s for s in trace.spans if s.status == SpanStatus.FAILED]
    if not failed:
        return FailureAnalysis(
            root_causes=[], total_failed_spans=0, blast_radius=0,
            handled_count=0, unhandled_count=0, resilience_score=1.0,
        )
    
    # Build parent map
    parent_map: dict[str, str] = {}
    children_map: dict[str, list[str]] = {}
    span_map: dict[str, Span] = {}
    
    for s in trace.spans:
        span_map[s.span_id] = s
        if s.parent_span_id:
            parent_map[s.span_id] = s.parent_span_id
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)
    
    failed_ids = {s.span_id for s in failed}
    
    # Find root causes: failed spans whose parent did NOT fail,
    # or failed spans with no parent
    root_cause_spans = []
    for s in failed:
        parent_id = parent_map.get(s.span_id)
        if parent_id is None or parent_id not in failed_ids:
            root_cause_spans.append(s)
    
    # For each root cause, find affected downstream spans
    def count_affected(span_id: str) -> list[str]:
        affected = []
        for child_id in children_map.get(span_id, []):
            if child_id in failed_ids:
                affected.append(child_id)
                affected.extend(count_affected(child_id))
        return affected
    
    root_causes = []
    total_affected = set()
    
    for rc_span in root_cause_spans:
        affected = count_affected(rc_span.span_id)
        total_affected.update(affected)
        total_affected.add(rc_span.span_id)
        
        # Determine if failure was handled:
        # - Tool failure where parent agent succeeded = handled (agent caught the error)
        # - Agent failure = unhandled (the agent itself failed, even if orchestrator continued)
        was_handled = False
        if rc_span.failure_handled:
            was_handled = True
        elif rc_span.span_type == SpanType.TOOL:
            # Tool failed — check if parent agent still succeeded
            parent_id = parent_map.get(rc_span.span_id)
            if parent_id and parent_id in span_map:
                parent_span = span_map[parent_id]
                if parent_span.status == SpanStatus.COMPLETED:
                    was_handled = True
        # Agent failures are unhandled by default — the agent couldn't cope
        
        node = FailureNode(
            span_id=rc_span.span_id,
            span_name=rc_span.name,
            span_type=rc_span.span_type.value,
            error=rc_span.error or "unknown error",
            is_root_cause=True,
            was_handled=was_handled,
            affected_children=[
                FailureNode(
                    span_id=aid, span_name=span_map[aid].name,
                    span_type=span_map[aid].span_type.value,
                    error=span_map[aid].error or "",
                ) for aid in affected if aid in span_map
            ],
        )
        root_causes.append(node)
    
    handled = sum(1 for rc in root_causes if rc.was_handled)
    unhandled = len(root_causes) - handled
    
    # Resilience score: ratio of handled failures to total root causes
    resilience = handled / max(len(root_causes), 1)
    
    return FailureAnalysis(
        root_causes=root_causes,
        total_failed_spans=len(failed),
        blast_radius=len(total_affected),
        handled_count=handled,
        unhandled_count=unhandled,
        resilience_score=resilience,
    )


@dataclass
class HandoffInfo:
    """Information about a handoff between agents."""
    from_agent: str
    to_agent: str
    context_keys: list[str]
    context_size_bytes: int
    duration_ms: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent,
            "to": self.to_agent,
            "context_keys": self.context_keys,
            "context_size_bytes": self.context_size_bytes,
            "duration_ms": self.duration_ms,
        }


@dataclass
class FlowAnalysis:
    """Analysis of multi-agent execution flow."""
    agent_count: int
    tool_count: int
    handoffs: list[HandoffInfo]
    critical_path: list[str]  # span names on the longest path
    critical_path_duration_ms: float
    parallel_groups: list[list[str]]  # groups of agents that ran in parallel

    def to_dict(self) -> dict:
        return {
            "agent_count": self.agent_count,
            "tool_count": self.tool_count,
            "handoffs": [h.to_dict() for h in self.handoffs],
            "critical_path": self.critical_path,
            "critical_path_duration_ms": round(self.critical_path_duration_ms, 1),
            "parallel_groups": self.parallel_groups,
        }


def analyze_flow(trace: ExecutionTrace) -> FlowAnalysis:
    """Analyze the execution flow of a multi-agent trace.
    
    Identifies:
    - Handoffs between agents (sequential agent pairs under same parent)
    - Critical path (longest execution chain)
    - Parallel execution groups
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)
    
    # Detect handoffs: sequential agent spans under same parent
    handoffs = []
    for parent_id, children in children_map.items():
        agent_children = [c for c in children if c.span_type == SpanType.AGENT]
        if len(agent_children) >= 2:
            # Sort by start time
            sorted_agents = sorted(agent_children, key=lambda s: s.started_at or "")
            for i in range(len(sorted_agents) - 1):
                from_agent = sorted_agents[i]
                to_agent = sorted_agents[i + 1]
                
                # Estimate context passed
                import json
                ctx_bytes = len(json.dumps(from_agent.output_data or {}, default=str).encode())
                ctx_keys = list((from_agent.output_data or {}).keys()) if isinstance(from_agent.output_data, dict) else []
                
                handoffs.append(HandoffInfo(
                    from_agent=from_agent.name,
                    to_agent=to_agent.name,
                    context_keys=ctx_keys,
                    context_size_bytes=ctx_bytes,
                ))
    
    # Critical path: find the longest chain from root to leaf
    def find_longest_path(span_id: str) -> tuple[list[str], float]:
        span = span_map.get(span_id)
        if not span:
            return [], 0
        
        children = children_map.get(span_id, [])
        if not children:
            return [span.name], span.duration_ms or 0
        
        best_path = []
        best_duration = 0
        for child in children:
            child_path, child_dur = find_longest_path(child.span_id)
            if child_dur > best_duration:
                best_path = child_path
                best_duration = child_dur
        
        return [span.name] + best_path, (span.duration_ms or 0)
    
    # Find roots
    roots = [s for s in trace.spans if s.parent_span_id is None or s.parent_span_id not in span_map]
    
    critical_path = []
    critical_duration = 0
    for root in roots:
        path, dur = find_longest_path(root.span_id)
        if dur > critical_duration:
            critical_path = path
            critical_duration = dur
    
    # Detect parallel groups
    parallel_groups = []
    for parent_id, children in children_map.items():
        agent_children = [c for c in children if c.span_type == SpanType.AGENT]
        if len(agent_children) >= 2:
            # Check if any overlap in time
            # Simplified: if they share same parent, consider them a group
            parallel_groups.append([c.name for c in agent_children])
    
    return FlowAnalysis(
        agent_count=len(trace.agent_spans),
        tool_count=len(trace.tool_spans),
        handoffs=handoffs,
        critical_path=critical_path,
        critical_path_duration_ms=critical_duration,
        parallel_groups=parallel_groups,
    )


@dataclass
class BottleneckReport:
    """Identifies performance bottlenecks in multi-agent execution."""
    critical_path: list[str]
    critical_path_duration_ms: float
    bottleneck_span: str  # name of the slowest span on the critical path
    bottleneck_duration_ms: float
    bottleneck_pct: float  # % of total trace time consumed by bottleneck
    agent_rankings: list[dict]  # agents sorted by duration

    def to_dict(self) -> dict:
        return {
            "critical_path": self.critical_path,
            "critical_path_duration_ms": round(self.critical_path_duration_ms, 1),
            "bottleneck": self.bottleneck_span,
            "bottleneck_duration_ms": round(self.bottleneck_duration_ms, 1),
            "bottleneck_pct": round(self.bottleneck_pct, 1),
            "agent_rankings": self.agent_rankings,
        }

    def to_report(self) -> str:
        lines = [
            "# Bottleneck Analysis",
            "",
            f"- **Critical path:** {' → '.join(self.critical_path)}",
            f"- **Bottleneck:** {self.bottleneck_span} ({self.bottleneck_duration_ms:.0f}ms, {self.bottleneck_pct:.0f}% of total)",
            "",
            "## Agent Rankings (slowest first)",
            "",
        ]
        for i, a in enumerate(self.agent_rankings):
            lines.append(f"{i+1}. **{a['name']}** — {a['duration_ms']:.0f}ms ({a['pct']:.0f}%)")
        return "\n".join(lines)


def analyze_bottleneck(trace: ExecutionTrace) -> BottleneckReport:
    """Identify the performance bottleneck in a trace.
    
    Answers: "Which agent is the performance bottleneck?"
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)
    
    # Find critical path (longest chain)
    def longest_path(span_id: str) -> tuple[list[str], float]:
        span = span_map.get(span_id)
        if not span:
            return [], 0
        children = children_map.get(span_id, [])
        if not children:
            return [span.name], span.duration_ms or 0
        best_path, best_dur = [], 0
        for child in children:
            cp, cd = longest_path(child.span_id)
            if cd > best_dur:
                best_path, best_dur = cp, cd
        return [span.name] + best_path, (span.duration_ms or 0)
    
    roots = [s for s in trace.spans if s.parent_span_id is None or s.parent_span_id not in span_map]
    critical_path, critical_dur = [], 0
    for root in roots:
        path, dur = longest_path(root.span_id)
        if dur > critical_dur:
            critical_path, critical_dur = path, dur
    
    # Find bottleneck: slowest span on critical path
    total_dur = trace.duration_ms or 1
    path_spans = [s for s in trace.spans if s.name in critical_path]
    bottleneck = max(path_spans, key=lambda s: s.duration_ms or 0) if path_spans else trace.spans[0] if trace.spans else None
    
    # Rank agents by duration
    agent_rankings = []
    for s in trace.agent_spans:
        d = s.duration_ms or 0
        agent_rankings.append({
            "name": s.name,
            "duration_ms": d,
            "pct": (d / max(total_dur, 1)) * 100,
            "status": s.status.value,
        })
    agent_rankings.sort(key=lambda x: x["duration_ms"], reverse=True)
    
    return BottleneckReport(
        critical_path=critical_path,
        critical_path_duration_ms=critical_dur,
        bottleneck_span=bottleneck.name if bottleneck else "",
        bottleneck_duration_ms=bottleneck.duration_ms or 0 if bottleneck else 0,
        bottleneck_pct=((bottleneck.duration_ms or 0) / max(total_dur, 1)) * 100 if bottleneck else 0,
        agent_rankings=agent_rankings,
    )


@dataclass
class ContextFlowPoint:
    """Context state at a single handoff point."""
    from_agent: str
    to_agent: str
    keys_sent: list[str]
    size_bytes: int
    keys_received: list[str] = field(default_factory=list)
    size_received_bytes: int = 0
    keys_lost: list[str] = field(default_factory=list)
    size_delta_bytes: int = 0
    anomaly: str = ""  # "loss", "bloat", "compression", "ok"

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent, "to": self.to_agent,
            "keys_sent": self.keys_sent, "size_bytes": self.size_bytes,
            "keys_lost": self.keys_lost, "size_delta_bytes": self.size_delta_bytes,
            "anomaly": self.anomaly,
        }


@dataclass  
class ContextFlowReport:
    """Analysis of context flow across all handoffs in a trace."""
    handoff_count: int
    total_context_bytes: int
    points: list[ContextFlowPoint]
    anomalies: list[ContextFlowPoint]  # points with loss or bloat
    
    def to_dict(self) -> dict:
        return {
            "handoff_count": self.handoff_count,
            "total_context_bytes": self.total_context_bytes,
            "anomaly_count": len(self.anomalies),
            "points": [p.to_dict() for p in self.points],
        }
    
    def to_report(self) -> str:
        lines = [
            "# Context Flow Analysis",
            "",
            f"- **Handoffs:** {self.handoff_count}",
            f"- **Total context:** {self.total_context_bytes:,} bytes",
            f"- **Anomalies:** {len(self.anomalies)}",
            "",
        ]
        for p in self.points:
            icon = "🟢" if p.anomaly == "ok" else "🔴" if p.anomaly == "loss" else "🟡"
            lines.append(f"{icon} {p.from_agent} → {p.to_agent}: {p.size_bytes:,}B")
            if p.keys_lost:
                lines.append(f"   ⚠ Lost keys: {p.keys_lost}")
            if p.anomaly == "bloat":
                lines.append(f"   ⚠ Context grew by {p.size_delta_bytes:,}B")
        return "\n".join(lines)


def analyze_context_flow(trace: ExecutionTrace) -> ContextFlowReport:
    """Analyze how context flows between agents via handoffs.
    
    Detects:
    - Context loss (keys present in sender output but missing in receiver input)
    - Context bloat (receiver input significantly larger than sender output)
    - Context compression (size reduction between handoffs)
    
    Answers: "Which handoff lost critical information?"
    """
    import json as _json
    
    span_map = {s.span_id: s for s in trace.spans}
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    
    points = []
    
    # Method 1: Use explicit HANDOFF spans
    for hs in handoff_spans:
        fr = hs.handoff_from or hs.metadata.get("handoff.from", "")
        to = hs.handoff_to or hs.metadata.get("handoff.to", "")
        ctx_keys = hs.metadata.get("handoff.context_keys", [])
        ctx_size = hs.context_size_bytes or hs.metadata.get("handoff.context_size_bytes", 0)
        
        points.append(ContextFlowPoint(
            from_agent=fr, to_agent=to,
            keys_sent=ctx_keys, size_bytes=ctx_size,
            anomaly="ok",
        ))
    
    # Method 2: If no explicit handoffs, infer from sequential agents
    if not points:
        children_map: dict[str, list[Span]] = {}
        for s in trace.spans:
            if s.parent_span_id:
                children_map.setdefault(s.parent_span_id, []).append(s)
        
        for parent_id, children in children_map.items():
            agents = sorted(
                [c for c in children if c.span_type == SpanType.AGENT],
                key=lambda s: s.started_at or ""
            )
            for i in range(len(agents) - 1):
                sender = agents[i]
                receiver = agents[i + 1]
                
                sender_output = sender.output_data or {}
                receiver_input = receiver.input_data or {}
                
                s_keys = list(sender_output.keys()) if isinstance(sender_output, dict) else []
                r_keys = list(receiver_input.keys()) if isinstance(receiver_input, dict) else []
                s_size = len(_json.dumps(sender_output, default=str).encode())
                r_size = len(_json.dumps(receiver_input, default=str).encode())
                
                lost = [k for k in s_keys if k not in r_keys] if s_keys and r_keys else []
                delta = r_size - s_size
                
                anomaly = "ok"
                if lost:
                    anomaly = "loss"
                elif delta > s_size * 2 and s_size > 0:
                    anomaly = "bloat"
                elif delta < -s_size * 0.5 and s_size > 100:
                    anomaly = "compression"  # significant shrinkage may indicate info loss
                
                points.append(ContextFlowPoint(
                    from_agent=sender.name, to_agent=receiver.name,
                    keys_sent=s_keys, size_bytes=s_size,
                    keys_received=r_keys, size_received_bytes=r_size,
                    keys_lost=lost, size_delta_bytes=delta,
                    anomaly=anomaly,
                ))
    
    total_bytes = sum(p.size_bytes for p in points)
    anomalies = [p for p in points if p.anomaly != "ok"]
    
    return ContextFlowReport(
        handoff_count=len(points),
        total_context_bytes=total_bytes,
        points=points,
        anomalies=anomalies,
    )


def analyze_retries(trace: ExecutionTrace) -> dict:
    """Detect retry patterns in a trace.
    
    Identifies spans that were retried (same name under same parent,
    first failed then succeeded).
    """
    parent_children: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            parent_children.setdefault(s.parent_span_id, []).append(s)
    
    retries = []
    for parent_id, children in parent_children.items():
        # Group by name
        by_name: dict[str, list[Span]] = {}
        for c in children:
            by_name.setdefault(c.name, []).append(c)
        
        for name, spans in by_name.items():
            if len(spans) >= 2:
                # Multiple spans with same name under same parent = likely retry
                failed = [s for s in spans if s.status == SpanStatus.FAILED]
                succeeded = [s for s in spans if s.status == SpanStatus.COMPLETED]
                if failed and succeeded:
                    retries.append({
                        "name": name,
                        "attempts": len(spans),
                        "failures": len(failed),
                        "final_status": "succeeded" if succeeded else "failed",
                        "parent": parent_id,
                    })
    
    return {
        "retry_count": len(retries),
        "retries": retries,
        "total_wasted_attempts": sum(r["failures"] for r in retries),
    }


def analyze_cost(trace: ExecutionTrace) -> dict:
    """Analyze cost distribution across agents and tools.
    
    Returns per-agent and per-tool cost breakdown.
    """
    agent_costs: dict[str, dict] = {}
    tool_costs: dict[str, dict] = {}
    
    for s in trace.spans:
        tokens = s.token_count or 0
        cost = s.estimated_cost_usd or 0
        
        target = agent_costs if s.span_type == SpanType.AGENT else tool_costs
        name = s.name
        
        if name not in target:
            target[name] = {"tokens": 0, "cost_usd": 0, "calls": 0}
        target[name]["tokens"] += tokens
        target[name]["cost_usd"] += cost
        target[name]["calls"] += 1
    
    total_tokens = sum(d["tokens"] for d in {**agent_costs, **tool_costs}.values())
    total_cost = sum(d["cost_usd"] for d in {**agent_costs, **tool_costs}.values())
    
    # Find most expensive
    all_items = {**agent_costs, **tool_costs}
    most_expensive = max(all_items.items(), key=lambda x: x[1]["cost_usd"])[0] if all_items else "N/A"
    
    return {
        "total_tokens": total_tokens,
        "total_cost_usd": round(total_cost, 4),
        "most_expensive": most_expensive,
        "agent_costs": {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in agent_costs.items()},
        "tool_costs": {k: {**v, "cost_usd": round(v["cost_usd"], 4)} for k, v in tool_costs.items()},
    }


def analyze_timing(trace: ExecutionTrace) -> dict:
    """Analyze timing patterns — detect gaps, overlaps, and idle time.
    
    Identifies:
    - Time gaps between sequential spans (potential idle/waiting time)
    - Overlapping spans (parallel execution)
    - Agent utilization (active vs idle time)
    """
    from datetime import datetime
    
    if not trace.spans or not trace.started_at:
        return {"gaps": [], "overlaps": 0, "utilization": 0}
    
    # Parse all span times
    timed = []
    for s in trace.spans:
        try:
            start = datetime.fromisoformat(s.started_at) if s.started_at else None
            end = datetime.fromisoformat(s.ended_at) if s.ended_at else None
            if start and end:
                timed.append({"name": s.name, "start": start, "end": end, "dur_ms": s.duration_ms or 0})
        except:
            pass
    
    if len(timed) < 2:
        return {"gaps": [], "overlaps": 0, "utilization": 1.0}
    
    # Sort by start time
    timed.sort(key=lambda x: x["start"])
    
    # Detect gaps
    gaps = []
    for i in range(len(timed) - 1):
        gap_ms = (timed[i+1]["start"] - timed[i]["end"]).total_seconds() * 1000
        if gap_ms > 10:  # >10ms gap is noteworthy
            gaps.append({
                "after": timed[i]["name"],
                "before": timed[i+1]["name"],
                "gap_ms": round(gap_ms, 1),
            })
    
    # Detect overlaps (parallel execution)
    overlaps = 0
    for i in range(len(timed)):
        for j in range(i+1, len(timed)):
            if timed[j]["start"] < timed[i]["end"]:
                overlaps += 1
    
    # Utilization: total span time / trace time
    total_span_ms = sum(t["dur_ms"] for t in timed)
    trace_ms = trace.duration_ms or 1
    utilization = min(1.0, total_span_ms / trace_ms)
    
    return {
        "gaps": gaps[:10],
        "gap_count": len(gaps),
        "total_gap_ms": sum(g["gap_ms"] for g in gaps),
        "overlaps": overlaps,
        "utilization": round(utilization, 2),
    }
