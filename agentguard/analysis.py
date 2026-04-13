"""Trace analysis — failure propagation, context flow, critical path.

Given a multi-agent execution trace, these functions answer:
- Where did the failure originate? (root cause)
- How did it propagate? (blast radius)
- Was it handled or did it bubble up? (resilience)
- How did context flow between agents? (handoff analysis)
- What was the critical path? (bottleneck)
"""



from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus

__all__ = ['FailureNode', 'FailureAnalysis', 'analyze_failures', 'HandoffInfo', 'FlowAnalysis', 'analyze_flow', 'BottleneckReport', 'analyze_bottleneck', 'ContextFlowPoint', 'ContextFlowReport', 'analyze_context_flow', 'analyze_retries', 'analyze_cost', 'analyze_cost_yield', 'CostYieldEntry', 'CostYieldReport', 'DecisionRecord', 'DecisionAnalysis', 'analyze_decisions', 'DurationAnomaly', 'DurationAnomalyReport', 'detect_duration_anomalies', 'analyze_timing', 'CounterfactualResult', 'CounterfactualAnalysis', 'analyze_counterfactual', 'RepeatedBadDecision', 'detect_repeated_bad_decisions']


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
    - Handoffs between agents (from explicit HANDOFF spans, or inferred from sequence as fallback)
    - Critical path (longest execution chain)
    - Parallel execution groups
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)
    
    # Detect handoffs: prefer explicit HANDOFF spans, fall back to sequence inference
    import json as _json_flow
    handoffs = []
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    
    if handoff_spans:
        # Method 1: Use explicit HANDOFF spans (confirmed by instrumentation)
        for hs in handoff_spans:
            fr = hs.handoff_from or hs.metadata.get("handoff.from", "")
            to = hs.handoff_to or hs.metadata.get("handoff.to", "")
            ctx_keys = hs.metadata.get("handoff.context_keys", [])
            ctx_size = hs.context_size_bytes or hs.metadata.get("handoff.context_size_bytes", 0)
            handoffs.append(HandoffInfo(
                from_agent=fr,
                to_agent=to,
                context_keys=ctx_keys,
                context_size_bytes=ctx_size,
                duration_ms=hs.duration_ms,
            ))
    else:
        # Method 2: Infer from sequential agent spans under same parent
        for parent_id, children in children_map.items():
            agent_children = [c for c in children if c.span_type == SpanType.AGENT]
            if len(agent_children) >= 2:
                sorted_agents = sorted(agent_children, key=lambda s: s.started_at or "")
                for i in range(len(sorted_agents) - 1):
                    from_agent = sorted_agents[i]
                    to_agent = sorted_agents[i + 1]
                    ctx_bytes = len(_json_flow.dumps(from_agent.output_data or {}, default=str).encode())
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
    false_bottleneck: Optional[str] = None  # agent that looks slow but is waiting
    false_bottleneck_detail: str = ""  # explanation of why it is a false bottleneck

    def to_dict(self) -> dict:
        return {
            "critical_path": self.critical_path,
            "critical_path_duration_ms": round(self.critical_path_duration_ms, 1),
            "bottleneck": self.bottleneck_span,
            "bottleneck_duration_ms": round(self.bottleneck_duration_ms, 1),
            "bottleneck_pct": round(self.bottleneck_pct, 1),
            "agent_rankings": self.agent_rankings,
            "false_bottleneck": self.false_bottleneck,
            "false_bottleneck_detail": self.false_bottleneck_detail,
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
            own_ms = a.get("own_duration_ms", a["duration_ms"])
            own_pct = a.get("own_pct", a["pct"])
            container = " (container)" if a.get("is_container") else ""
            cat = a.get("category", "unknown")
            cat_icon = {"io": "\U0001f310", "cpu": "\u2699", "waiting": "\u23f3", "unknown": "\u2753"}.get(cat, "")
            lines.append(
                f"{i+1}. **{a['name']}**{container} [{cat_icon} {cat}] — "
                f"total: {a['duration_ms']:.0f}ms ({a['pct']:.0f}%) · "
                f"self: {own_ms:.0f}ms ({own_pct:.0f}%)"
            )
        return "\n".join(lines)


def _classify_span_category(
    span: Span,
    own_duration_ms: float,
    total_duration_ms: float,
    children: list[Span],
) -> str:
    """Classify a span's bottleneck category based on heuristics.

    Categories:
    - 'io': Span likely doing I/O (API calls, search, network).
      Detected by: tool type, or metadata hints (model, api, url, search).
    - 'cpu': Span doing computation with high self-time.
      Detected by: high own_time ratio, no IO children.
    - 'waiting': Span mostly waiting for children to complete.
      Detected by: low own_time ratio (< 20% of total).
    - 'unknown': Insufficient data to classify.

    This is a heuristic — accurate classification requires runtime
    profiling which AgentGuard intentionally avoids (zero-overhead).
    """
    if total_duration_ms <= 0:
        return "unknown"

    own_ratio = own_duration_ms / max(total_duration_ms, 1)

    # Tool spans are typically IO
    if span.span_type == SpanType.TOOL:
        return "io"

    # Check metadata hints for IO
    io_hints = {"model", "api", "url", "search", "fetch", "http", "db", "query"}
    meta_keys = {k.lower() for k in span.metadata.keys()}
    meta_vals = {str(v).lower() for v in span.metadata.values() if isinstance(v, str)}
    if io_hints & (meta_keys | meta_vals):
        return "io"

    # Check if children are IO-heavy
    io_children = [
        c for c in children
        if c.span_type == SpanType.TOOL
        or any(h in c.name.lower() for h in ("search", "api", "fetch", "call"))
    ]
    if io_children and len(io_children) >= len(children) * 0.5:
        return "io"

    # Low own-time = mostly waiting for children
    if children and own_ratio < 0.2:
        return "waiting"

    # High own-time with no IO children = likely CPU
    if own_ratio > 0.5:
        return "cpu"

    return "unknown"


def _detect_false_bottleneck(
    rankings: list[dict],
) -> tuple[Optional[str], str]:
    """Detect an agent that appears slow but is actually waiting on dependencies.

    A false bottleneck has the highest total wall time but <=20% of that
    is own work — the rest is children (dependency wait time).

    Returns:
        (agent_name, explanation) or (None, "") if no false bottleneck.
    """
    if not rankings:
        return None, ""
    # Find agent with highest total wall time
    by_total = sorted(rankings, key=lambda x: x["duration_ms"], reverse=True)
    candidate = by_total[0]
    total = candidate["duration_ms"]
    own = candidate["own_duration_ms"]
    if total <= 0:
        return None, ""
    own_ratio = own / total
    # False bottleneck: <20% own work AND is a container
    if own_ratio <= 0.2 and candidate.get("is_container"):
        wait_ms = total - own
        detail = (
            f"{candidate['name']} has {total:.0f}ms wall time but only "
            f"{own:.0f}ms ({own_ratio:.0%}) is own work. "
            f"{wait_ms:.0f}ms is dependency wait. "
            f"Optimize its children instead."
        )
        return candidate["name"], detail
    return None, ""


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
    
    # Find bottleneck: slowest WORK span on critical path
    # Exclude container/coordinator spans (spans that are parents of other spans)
    # because they naturally cover the entire duration and aren't the real bottleneck.
    total_dur = trace.duration_ms or 1
    parent_ids = set(children_map.keys())
    
    # Work spans = spans on critical path that are NOT container nodes
    path_spans = [s for s in trace.spans if s.name in critical_path]
    work_spans = [s for s in path_spans if s.span_id not in parent_ids]
    
    # If all spans are containers (unlikely), fall back to all path spans
    if not work_spans:
        work_spans = path_spans
    
    bottleneck = max(work_spans, key=lambda s: s.duration_ms or 0) if work_spans else (trace.spans[0] if trace.spans else None)
    
    # Rank agents by OWN duration (exclude time spent in children)
    agent_rankings = []
    for s in trace.agent_spans:
        total_d = s.duration_ms or 0
        # Calculate own time = total - sum of direct children durations
        child_dur = sum(c.duration_ms or 0 for c in children_map.get(s.span_id, []))
        own_d = max(total_d - child_dur, 0)
        
        # Use own duration for ranking, but show total for context
        agent_rankings.append({
            "name": s.name,
            "duration_ms": total_d,
            "own_duration_ms": own_d,
            "pct": (total_d / max(total_dur, 1)) * 100,
            "own_pct": (own_d / max(total_dur, 1)) * 100,
            "status": s.status.value,
            "is_container": s.span_id in parent_ids,
            "category": _classify_span_category(
                s, own_d, total_d, children_map.get(s.span_id, [])
            ),
        })
    # Sort by own duration (real work), not total duration
    agent_rankings.sort(key=lambda x: x["own_duration_ms"], reverse=True)
    
    # Detect false bottleneck: agent with highest wall time but <=20% own work
    fb_name, fb_detail = _detect_false_bottleneck(agent_rankings)

    return BottleneckReport(
        critical_path=critical_path,
        critical_path_duration_ms=critical_dur,
        bottleneck_span=bottleneck.name if bottleneck else "",
        bottleneck_duration_ms=bottleneck.duration_ms or 0 if bottleneck else 0,
        bottleneck_pct=((bottleneck.duration_ms or 0) / max(total_dur, 1)) * 100 if bottleneck else 0,
        agent_rankings=agent_rankings,
        false_bottleneck=fb_name,
        false_bottleneck_detail=fb_detail,
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
    anomaly: str = ""  # "loss", "bloat", "compression", "truncation", "ok"
    truncation_detail: str = ""  # description if truncation detected
    retention_ratio: Optional[float] = None  # bytes_received / bytes_sent (1.0 = perfect)
    transformations: list[dict] = field(default_factory=list)  # semantic changes detected

    def to_dict(self) -> dict:
        return {
            "from": self.from_agent, "to": self.to_agent,
            "keys_sent": self.keys_sent, "size_bytes": self.size_bytes,
            "keys_lost": self.keys_lost, "size_delta_bytes": self.size_delta_bytes,
            "anomaly": self.anomaly,
            "truncation_detail": self.truncation_detail,
            "retention_ratio": round(self.retention_ratio, 3) if self.retention_ratio is not None else None,
            "transformations": self.transformations,
        }


@dataclass  
class ContextFlowReport:
    """Analysis of context flow across all handoffs in a trace."""
    handoff_count: int
    total_context_bytes: int
    points: list[ContextFlowPoint]
    anomalies: list[ContextFlowPoint]  # points with loss or bloat
    
    @property
    def avg_retention_ratio(self) -> Optional[float]:
        """Average information retention across all handoffs with data."""
        ratios = [p.retention_ratio for p in self.points if p.retention_ratio is not None]
        return sum(ratios) / len(ratios) if ratios else None

    def to_dict(self) -> dict:
        return {
            "handoff_count": self.handoff_count,
            "total_context_bytes": self.total_context_bytes,
            "anomaly_count": len(self.anomalies),
            "avg_retention_ratio": round(self.avg_retention_ratio, 3) if self.avg_retention_ratio is not None else None,
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
            if p.anomaly == "truncation" and p.truncation_detail:
                lines.append(f"   ✂ Truncated: {p.truncation_detail}")
            if p.retention_ratio is not None:
                pct = p.retention_ratio * 100
                icon = "\u2705" if pct >= 90 else "\u26a0" if pct >= 50 else "\u274c"
                lines.append(f"   {icon} Retention: {pct:.0f}%")
        return "\n".join(lines)


def _detect_truncation(
    sender_output: Any,
    receiver_input: Any,
) -> tuple[bool, str]:
    """Detect if receiver input is a truncated version of sender output.

    Truncation occurs when:
    - A list was shortened (fewer items)
    - A string was cut (receiver is a prefix of sender)
    - Dict values were trimmed (same keys, smaller values)

    Returns:
        (is_truncated, description)
    """
    if isinstance(sender_output, dict) and isinstance(receiver_input, dict):
        for key in receiver_input:
            if key not in sender_output:
                continue
            sent_val = sender_output[key]
            recv_val = receiver_input[key]
            # List truncation
            if isinstance(sent_val, list) and isinstance(recv_val, list):
                if len(recv_val) < len(sent_val) and recv_val == sent_val[:len(recv_val)]:
                    return True, f"key '{key}': list truncated {len(sent_val)}→{len(recv_val)} items"
            # String truncation
            if isinstance(sent_val, str) and isinstance(recv_val, str):
                if len(recv_val) < len(sent_val) and sent_val.startswith(recv_val):
                    return True, f"key '{key}': string truncated {len(sent_val)}→{len(recv_val)} chars"
    # Top-level list truncation
    if isinstance(sender_output, list) and isinstance(receiver_input, list):
        if len(receiver_input) < len(sender_output) and receiver_input == sender_output[:len(receiver_input)]:
            return True, f"list truncated {len(sender_output)}→{len(receiver_input)} items"
    return False, ""


def _detect_transformations(
    sender_data: Any, receiver_data: Any,
    sent_keys: list[str], received_keys: list[str],
) -> list[dict]:
    """Detect semantic transformations between handoff sender and receiver.

    Checks for: summarization (value shrunk significantly),
    filtering (list shortened), type changes, and key renaming.

    Returns:
        List of dicts with 'type', 'key', and 'detail' for each transform.
    """
    if not isinstance(sender_data, dict) or not isinstance(receiver_data, dict):
        return []
    transforms: list[dict] = []
    common = set(sent_keys) & set(received_keys)
    for key in common:
        s_val = sender_data.get(key)
        r_val = receiver_data.get(key)
        t = _classify_value_transform(key, s_val, r_val)
        if t:
            transforms.append(t)
    # Check for possible key renaming
    transforms.extend(_detect_key_renames(sender_data, receiver_data, sent_keys, received_keys))
    return transforms


def _classify_value_transform(key: str, sent: Any, received: Any) -> Optional[dict]:
    """Classify how a value changed between sender and receiver."""
    if sent == received:
        return None
    if type(sent) != type(received):
        return {"type": "type_change", "key": key,
                "detail": f"{type(sent).__name__} -> {type(received).__name__}"}
    if isinstance(sent, str) and isinstance(received, str):
        return _classify_string_transform(key, sent, received)
    if isinstance(sent, list) and isinstance(received, list):
        return _classify_list_transform(key, sent, received)
    if isinstance(sent, dict) and isinstance(received, dict):
        if len(received) < len(sent):
            return {"type": "filtering", "key": key,
                    "detail": f"dict shrunk from {len(sent)} to {len(received)} keys"}
    return {"type": "modified", "key": key, "detail": "value changed"}


def _classify_string_transform(key: str, sent: str, received: str) -> Optional[dict]:
    """Detect summarization or truncation in string values."""
    ratio = len(received) / max(len(sent), 1)
    if ratio < 0.5 and len(sent) > 50:
        return {"type": "summarization", "key": key,
                "detail": f"{len(sent)} chars -> {len(received)} chars ({ratio:.0%} retained)"}
    if ratio < 0.9 and len(sent) > 20:
        return {"type": "compression", "key": key,
                "detail": f"{len(sent)} -> {len(received)} chars"}
    if ratio > 2.0:
        return {"type": "expansion", "key": key,
                "detail": f"{len(sent)} -> {len(received)} chars"}
    return {"type": "modified", "key": key, "detail": "string changed"}


def _classify_list_transform(key: str, sent: list, received: list) -> Optional[dict]:
    """Detect filtering in list values."""
    if len(received) < len(sent):
        return {"type": "filtering", "key": key,
                "detail": f"list filtered from {len(sent)} to {len(received)} items"}
    if len(received) > len(sent):
        return {"type": "expansion", "key": key,
                "detail": f"list grew from {len(sent)} to {len(received)} items"}
    if sent != received:
        return {"type": "reordered", "key": key, "detail": "list items changed"}
    return None


def _detect_key_renames(
    sender: dict, receiver: dict,
    sent_keys: list[str], received_keys: list[str],
) -> list[dict]:
    """Detect possible key renames (lost key + new key with similar value)."""
    lost = set(sent_keys) - set(received_keys)
    gained = set(received_keys) - set(sent_keys)
    renames: list[dict] = []
    for lk in lost:
        for gk in gained:
            if sender.get(lk) == receiver.get(gk) and sender.get(lk) is not None:
                renames.append({"type": "rename", "key": lk,
                                "detail": f"'{lk}' likely renamed to '{gk}'"})
                break
    return renames


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
        
        # Compute retention if receiver size is available
        recv_size = 0
        recv_info = hs.context_received
        if isinstance(recv_info, dict):
            recv_size = recv_info.get("size_bytes", 0)
        retention = recv_size / ctx_size if ctx_size > 0 and recv_size > 0 else None

        points.append(ContextFlowPoint(
            from_agent=fr, to_agent=to,
            keys_sent=ctx_keys, size_bytes=ctx_size,
            size_received_bytes=recv_size,
            anomaly="ok",
            retention_ratio=retention,
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
                    anomaly = "compression"

                # Check for truncation (subset detection)
                is_trunc, trunc_desc = _detect_truncation(sender_output, receiver_input)
                if is_trunc:
                    anomaly = "truncation"

                retention = r_size / s_size if s_size > 0 else None

                transforms = _detect_transformations(
                    sender_output, receiver_input, s_keys, r_keys
                )
                points.append(ContextFlowPoint(
                    from_agent=sender.name, to_agent=receiver.name,
                    keys_sent=s_keys, size_bytes=s_size,
                    keys_received=r_keys, size_received_bytes=r_size,
                    keys_lost=lost, size_delta_bytes=delta,
                    anomaly=anomaly,
                    truncation_detail=trunc_desc if is_trunc else "",
                    retention_ratio=retention,
                    transformations=transforms,
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



@dataclass
class CostYieldEntry:
    """Cost-yield analysis for a single agent."""
    agent: str
    tokens: int
    cost_usd: float
    status: str
    duration_ms: float
    has_output: bool
    output_size_bytes: int
    cost_per_success: float  # cost_usd / 1 if succeeded, else inf
    tokens_per_ms: float  # efficiency: tokens consumed per ms of work
    yield_score: float  # 0-100: composite quality signal


@dataclass
class CostYieldReport:
    """Cost-yield analysis across all agents in a trace."""
    entries: list[CostYieldEntry]
    total_cost_usd: float
    total_tokens: int
    highest_cost_agent: str
    lowest_yield_agent: str
    best_ratio_agent: str
    most_wasteful_agent: str = ""
    waste_score: float = 0.0  # 0-100: higher = more wasteful
    recommendations: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_tokens": self.total_tokens,
            "highest_cost_agent": self.highest_cost_agent,
            "lowest_yield_agent": self.lowest_yield_agent,
            "best_ratio_agent": self.best_ratio_agent,
            "most_wasteful_agent": self.most_wasteful_agent,
            "waste_score": round(self.waste_score, 1),
            "recommendations": self.recommendations,
            "agents": [
                {
                    "agent": e.agent, "tokens": e.tokens,
                    "cost_usd": round(e.cost_usd, 4),
                    "status": e.status, "duration_ms": round(e.duration_ms, 1),
                    "has_output": e.has_output,
                    "output_size_bytes": e.output_size_bytes,
                    "cost_per_success": round(e.cost_per_success, 4) if e.cost_per_success != float("inf") else "N/A",
                    "tokens_per_ms": round(e.tokens_per_ms, 2),
                    "yield_score": round(e.yield_score, 1),
                } for e in self.entries
            ],
        }

    def to_report(self) -> str:
        lines = [
            "# Cost-Yield Analysis", "",
            f"Total: {self.total_tokens:,} tokens, ${self.total_cost_usd:.4f}", "",
            f"- Highest cost: {self.highest_cost_agent}",
            f"- Lowest yield: {self.lowest_yield_agent}",
            f"- Best ratio:   {self.best_ratio_agent}",
            f"- **Most wasteful: {self.most_wasteful_agent}** (waste score: {self.waste_score:.0f}/100)" if self.most_wasteful_agent else "",
            "",
        ]
        if self.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for rec in self.recommendations:
                lines.append(f"  💡 {rec}")
            lines.append("")
        lines.extend([
            "## Per-Agent Breakdown", "",
        ])
        for e in sorted(self.entries, key=lambda x: -x.cost_usd):
            cps = f"${e.cost_per_success:.4f}" if e.cost_per_success != float("inf") else "N/A (failed)"
            lines.append(f"**{e.agent}** — {e.tokens:,} tokens, ${e.cost_usd:.4f}")
            lines.append(f"  yield: {e.yield_score:.0f}/100, cost/success: {cps}, {e.duration_ms:.0f}ms")
            lines.append("")
        return "\n".join(lines)


def _compute_waste_score(entry: CostYieldEntry, max_tokens: int = 1) -> float:
    """Compute waste score for one agent.

    Waste = cost_factor × (1 - yield_factor) × 100.
    High cost + low yield = high waste. Range: 0-100.
    Failed agents get maximum waste penalty.
    """
    if entry.status == "failed":
        return 100.0
    waste_factor = (100 - entry.yield_score) / 100
    cost_factor = (entry.tokens / max(max_tokens, 1)) if entry.tokens > 0 else 0.0
    return round(cost_factor * waste_factor * 100, 1)


def _find_most_wasteful(
    entries: list[CostYieldEntry],
) -> tuple[str, float]:
    """Find the agent with highest waste score."""
    if not entries:
        return "", 0.0
    max_tok = max((e.tokens for e in entries if e.tokens > 0), default=1)
    scored = [(e, _compute_waste_score(e, max_tok)) for e in entries]
    scored.sort(key=lambda x: -x[1])
    return scored[0][0].agent, scored[0][1]


def _generate_cost_recommendations(
    entries: list[CostYieldEntry],
) -> list[str]:
    """Generate actionable recommendations from cost-yield data.

    Each recommendation targets a specific inefficiency pattern
    with a concrete suggestion for improvement.
    """
    max_tok = max((e.tokens for e in entries if e.tokens > 0), default=1)
    recs = []
    for e in entries:
        waste = _compute_waste_score(e, max_tok)
        if e.status == "failed" and e.tokens > 0:
            recs.append(
                f"'{e.agent}' consumed {e.tokens:,} tokens but failed. "
                f"Add retry budget limits or fail-fast checks."
            )
        elif waste > 50 and e.yield_score < 50:
            recs.append(
                f"'{e.agent}' has low yield ({e.yield_score:.0f}/100). "
                f"Consider a cheaper model or caching results."
            )
        elif e.tokens > 0 and not e.has_output:
            recs.append(
                f"'{e.agent}' used {e.tokens:,} tokens but produced no output. "
                f"Check if this agent is needed in the pipeline."
            )
        elif e.cost_per_success > 0.01:
            recs.append(
                f"'{e.agent}' costs ${e.cost_per_success:.4f}/success. "
                f"Consider batching or using a smaller model."
            )
    return recs[:5]  # Cap at 5 recommendations


def analyze_cost_yield(trace: ExecutionTrace) -> CostYieldReport:
    """Compare token spend per agent vs output quality.

    Answers Q4: "Which execution path has the highest cost but worst yield?"

    For each agent computes:
    - Cost (tokens + USD)
    - Yield score (composite of: completed? has output? output size)
    - Cost-per-success ratio
    - Tokens-per-ms efficiency

    Args:
        trace: The execution trace to analyze.

    Returns:
        CostYieldReport with per-agent breakdown and summary.
    """
    import json as _json

    entries = []
    for s in trace.agent_spans:
        tokens = s.token_count or 0
        cost = s.estimated_cost_usd or 0.0
        dur = s.duration_ms or 0.0
        succeeded = s.status == SpanStatus.COMPLETED
        has_output = s.output_data is not None

        # Measure output size
        output_size = 0
        if s.output_data is not None:
            try:
                output_size = len(_json.dumps(s.output_data, default=str).encode("utf-8"))
            except Exception:
                output_size = 0

        # Yield score: 0-100 composite
        yield_score = 0.0
        if succeeded:
            yield_score += 50  # completed
        if has_output:
            yield_score += 30  # produced output
        if output_size > 100:
            yield_score += 10  # substantial output
        if output_size > 1000:
            yield_score += 10  # rich output

        cost_per_success = cost if succeeded and cost > 0 else (float("inf") if not succeeded else 0.0)
        tokens_per_ms = tokens / max(dur, 1)

        entries.append(CostYieldEntry(
            agent=s.name,
            tokens=tokens,
            cost_usd=cost,
            status=s.status.value,
            duration_ms=dur,
            has_output=has_output,
            output_size_bytes=output_size,
            cost_per_success=cost_per_success,
            tokens_per_ms=tokens_per_ms,
            yield_score=yield_score,
        ))

    total_cost = sum(e.cost_usd for e in entries)
    total_tokens = sum(e.tokens for e in entries)

    highest_cost = max(entries, key=lambda e: e.cost_usd).agent if entries else "N/A"
    lowest_yield = min(entries, key=lambda e: e.yield_score).agent if entries else "N/A"
    # Best ratio = highest yield_score / max(cost, 0.0001)
    best_ratio = max(entries, key=lambda e: e.yield_score / max(e.cost_usd, 0.0001)).agent if entries else "N/A"

    # Compute most wasteful agent: highest cost × lowest yield
    wasteful, waste_score = _find_most_wasteful(entries)
    recommendations = _generate_cost_recommendations(entries)

    return CostYieldReport(
        entries=entries,
        total_cost_usd=total_cost,
        total_tokens=total_tokens,
        highest_cost_agent=highest_cost,
        lowest_yield_agent=lowest_yield,
        best_ratio_agent=best_ratio,
        most_wasteful_agent=wasteful,
        waste_score=waste_score,
        recommendations=recommendations,
    )



@dataclass
class DecisionRecord:
    """A single orchestration decision and its downstream outcome."""
    coordinator: str
    chosen_agent: str
    alternatives: list[str]
    rationale: str
    criteria: dict
    confidence: Optional[float]
    downstream_status: str  # "completed", "failed", etc.
    downstream_duration_ms: Optional[float]
    led_to_failure: bool  # True if chosen agent (or its children) failed

    def to_dict(self) -> dict[str, Any]:
        return {
            "coordinator": self.coordinator,
            "chosen": self.chosen_agent,
            "alternatives": self.alternatives,
            "rationale": self.rationale,
            "criteria": self.criteria,
            "confidence": self.confidence,
            "downstream_status": self.downstream_status,
            "downstream_duration_ms": self.downstream_duration_ms,
            "led_to_failure": self.led_to_failure,
        }


@dataclass
class DecisionAnalysis:
    """Analysis of all orchestration decisions in a trace."""
    decisions: list[DecisionRecord]
    total_decisions: int
    decisions_leading_to_failure: int
    decision_quality_score: float  # 0-1: fraction of decisions with good outcomes

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "decisions_leading_to_failure": self.decisions_leading_to_failure,
            "decision_quality_score": round(self.decision_quality_score, 2),
            "decisions": [d.to_dict() for d in self.decisions],
        }

    def to_report(self) -> str:
        lines = [
            "# Orchestration Decision Analysis", "",
            f"Total decisions: {self.total_decisions}",
            f"Led to failure: {self.decisions_leading_to_failure}",
            f"Decision quality: {self.decision_quality_score:.0%}", "",
        ]
        for d in self.decisions:
            icon = "\u2717" if d.led_to_failure else "\u2713"
            alts = ", ".join(d.alternatives) if d.alternatives else "none"
            lines.append(f"{icon} **{d.coordinator}** chose **{d.chosen_agent}** over [{alts}]")
            if d.rationale:
                lines.append(f"  Rationale: {d.rationale}")
            lines.append(f"  Outcome: {d.downstream_status}"
                         f"{f' ({d.downstream_duration_ms:.0f}ms)' if d.downstream_duration_ms else ''}")
            lines.append("")
        return "\n".join(lines)


@dataclass
class RepeatedBadDecision:
    """Detection of an agent repeatedly chosen despite prior failures.

    This is a strong signal of Q5 degradation: the orchestrator
    keeps picking the same failing agent instead of learning.
    """
    agent: str
    times_chosen: int
    times_failed: int
    coordinators: list[str]  # which coordinators made this mistake
    failure_rate: float  # times_failed / times_chosen

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent": self.agent,
            "times_chosen": self.times_chosen,
            "times_failed": self.times_failed,
            "coordinators": self.coordinators,
            "failure_rate": round(self.failure_rate, 2),
        }


def detect_repeated_bad_decisions(
    trace: ExecutionTrace,
) -> list[RepeatedBadDecision]:
    """Detect agents chosen multiple times despite prior failures.

    Scans all orchestration decisions chronologically. If an agent
    was chosen after it previously failed, that's a repeated bad
    decision. Returns agents with failure_rate > 0 and times_chosen >= 2.

    Why this matters: orchestrators that don't learn from failures
    waste tokens and time on agents that keep failing.
    """
    da = analyze_decisions(trace)
    if not da.decisions:
        return []

    agent_stats = _collect_agent_decision_stats(da.decisions)
    return _filter_repeated_failures(agent_stats)


def _collect_agent_decision_stats(
    decisions: list[DecisionRecord],
) -> dict[str, dict]:
    """Aggregate per-agent decision outcomes."""
    stats: dict[str, dict] = {}
    for d in decisions:
        agent = d.chosen_agent
        if agent not in stats:
            stats[agent] = {
                "chosen": 0, "failed": 0, "coordinators": set()
            }
        stats[agent]["chosen"] += 1
        stats[agent]["coordinators"].add(d.coordinator)
        if d.led_to_failure:
            stats[agent]["failed"] += 1
    return stats


def _filter_repeated_failures(
    stats: dict[str, dict],
) -> list[RepeatedBadDecision]:
    """Filter to agents chosen ≥2 times with failures."""
    results = []
    for agent, s in stats.items():
        if s["chosen"] >= 2 and s["failed"] > 0:
            results.append(RepeatedBadDecision(
                agent=agent,
                times_chosen=s["chosen"],
                times_failed=s["failed"],
                coordinators=sorted(s["coordinators"]),
                failure_rate=s["failed"] / s["chosen"],
            ))
    results.sort(key=lambda r: -r.failure_rate)
    return results


def _has_descendant_failure(
    span_id: str,
    children_map: dict[str, list[Span]],
) -> bool:
    """Recursively check if any descendant span failed."""
    for child in children_map.get(span_id, []):
        if child.status == SpanStatus.FAILED:
            return True
        if _has_descendant_failure(child.span_id, children_map):
            return True
    return False


def _decision_span_to_record(
    ds: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> DecisionRecord:
    """Convert a decision span into a DecisionRecord with downstream outcome."""
    chosen = ds.metadata.get("decision.chosen", "")
    chosen_spans = [
        s for s in trace.spans
        if s.span_type == SpanType.AGENT and s.name == chosen
    ]

    if chosen_spans:
        agent = chosen_spans[0]
        led_to_failure = (
            agent.status == SpanStatus.FAILED
            or _has_descendant_failure(agent.span_id, children_map)
        )
        downstream_status = agent.status.value
        downstream_dur = agent.duration_ms
    else:
        downstream_status = "unknown"
        downstream_dur = None
        led_to_failure = False

    return DecisionRecord(
        coordinator=ds.metadata.get("decision.coordinator", ""),
        chosen_agent=chosen,
        alternatives=ds.metadata.get("decision.alternatives", []),
        rationale=ds.metadata.get("decision.rationale", ""),
        criteria=ds.metadata.get("decision.criteria", {}),
        confidence=ds.metadata.get("decision.confidence"),
        downstream_status=downstream_status,
        downstream_duration_ms=downstream_dur,
        led_to_failure=led_to_failure,
    )


def analyze_decisions(trace: ExecutionTrace) -> DecisionAnalysis:
    """Analyze orchestration decisions and their downstream outcomes.

    Answers GUARDRAILS Q5: "Which orchestration decision caused downstream
    degradation?"

    Args:
        trace: The execution trace to analyze.

    Returns:
        DecisionAnalysis with per-decision outcomes and quality score.
    """
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)

    decision_spans = [
        s for s in trace.spans
        if s.span_type == SpanType.HANDOFF
        and s.metadata.get("decision.type") == "orchestration"
    ]

    records = [
        _decision_span_to_record(ds, trace, children_map)
        for ds in decision_spans
    ]

    total = len(records)
    failures = sum(1 for r in records if r.led_to_failure)
    quality = 1.0 if total == 0 else (total - failures) / total

    return DecisionAnalysis(
        decisions=records,
        total_decisions=total,
        decisions_leading_to_failure=failures,
        decision_quality_score=quality,
    )


@dataclass
class DurationAnomaly:
    """A span flagged as anomalously slow compared to baseline."""
    span_name: str
    span_type: str
    duration_ms: float
    baseline_ms: float
    ratio: float  # duration / baseline
    severity: str  # "warning" (3x) or "critical" (10x)

    def to_dict(self) -> dict[str, Any]:
        return {
            "span_name": self.span_name,
            "span_type": self.span_type,
            "duration_ms": round(self.duration_ms, 1),
            "baseline_ms": round(self.baseline_ms, 1),
            "ratio": round(self.ratio, 1),
            "severity": self.severity,
        }


@dataclass
class DurationAnomalyReport:
    """Duration anomaly detection results."""
    anomalies: list[DurationAnomaly]
    total_spans_checked: int
    anomaly_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_spans_checked": self.total_spans_checked,
            "anomaly_count": self.anomaly_count,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }

    def to_report(self) -> str:
        if not self.anomalies:
            return f"# Duration Anomalies\n\nNo anomalies ({self.total_spans_checked} spans checked)."
        lines = [
            "# Duration Anomalies", "",
            f"{self.anomaly_count} anomalies in {self.total_spans_checked} spans:", "",
        ]
        for a in sorted(self.anomalies, key=lambda x: -x.ratio):
            icon = "\U0001f534" if a.severity == "critical" else "\U0001f7e1"
            lines.append(
                f"{icon} **{a.span_name}** ({a.span_type}): "
                f"{a.duration_ms:.0f}ms vs {a.baseline_ms:.0f}ms baseline "
                f"({a.ratio:.1f}x)"
            )
        return "\n".join(lines)


def _compute_baseline(
    reference_traces: list[ExecutionTrace],
) -> dict[str, float]:
    """Compute per-span-name average duration from reference traces.

    Args:
        reference_traces: Historical traces to derive baselines from.

    Returns:
        Dict mapping span name to average duration in ms.
    """
    totals: dict[str, list[float]] = {}
    for trace in reference_traces:
        for span in trace.spans:
            if span.duration_ms is not None and span.duration_ms > 0:
                totals.setdefault(span.name, []).append(span.duration_ms)
    return {
        name: sum(durs) / len(durs)
        for name, durs in totals.items()
    }


def detect_duration_anomalies(
    trace: ExecutionTrace,
    baseline: Optional[dict[str, float]] = None,
    reference_traces: Optional[list[ExecutionTrace]] = None,
    threshold: float = 3.0,
    critical_threshold: float = 10.0,
) -> DurationAnomalyReport:
    """Flag spans that are significantly slower than their historical baseline.

    Answers GUARDRAILS Q1/Q5: identifies performance degradation at span
    level. A span is flagged when its duration exceeds the baseline by
    the given threshold multiplier.

    Args:
        trace: The current trace to check.
        baseline: Pre-computed baselines {span_name: avg_ms}. If None,
            computed from reference_traces.
        reference_traces: Historical traces to compute baseline from.
            Ignored if baseline is provided.
        threshold: Multiplier for "warning" level (default 3x).
        critical_threshold: Multiplier for "critical" level (default 10x).

    Returns:
        DurationAnomalyReport with flagged spans.
    """
    if baseline is None and reference_traces:
        baseline = _compute_baseline(reference_traces)
    if baseline is None:
        baseline = {}

    anomalies: list[DurationAnomaly] = []
    checked = 0

    for span in trace.spans:
        if span.duration_ms is None or span.duration_ms <= 0:
            continue
        if span.name not in baseline:
            continue
        checked += 1
        base = baseline[span.name]
        if base <= 0:
            continue
        ratio = span.duration_ms / base

        if ratio >= critical_threshold:
            severity = "critical"
        elif ratio >= threshold:
            severity = "warning"
        else:
            continue

        anomalies.append(DurationAnomaly(
            span_name=span.name,
            span_type=span.span_type.value,
            duration_ms=span.duration_ms,
            baseline_ms=base,
            ratio=ratio,
            severity=severity,
        ))

    return DurationAnomalyReport(
        anomalies=anomalies,
        total_spans_checked=checked,
        anomaly_count=len(anomalies),
    )

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


@dataclass
class CounterfactualResult:
    """Comparison of actual decision vs best alternative path.

    Why counterfactual: knowing what DID happen isn't enough.
    Q5 asks whether the orchestrator chose optimally. We compare
    the chosen agent's actual outcome against alternatives that
    ran elsewhere in the trace (or historical data).
    """
    coordinator: str
    chosen_agent: str
    chosen_status: str
    chosen_duration_ms: Optional[float]
    best_alternative: Optional[str]
    best_alt_status: Optional[str]
    best_alt_duration_ms: Optional[float]
    regret_ms: Optional[float]  # chosen_duration - best_alt_duration (positive = regret)
    chosen_failed: bool
    best_alt_failed: bool
    verdict: str  # "optimal", "suboptimal", "catastrophic", "no_alternatives"

    def to_dict(self) -> dict[str, Any]:
        return {
            "coordinator": self.coordinator,
            "chosen": self.chosen_agent,
            "chosen_status": self.chosen_status,
            "chosen_duration_ms": self.chosen_duration_ms,
            "best_alternative": self.best_alternative,
            "best_alt_status": self.best_alt_status,
            "best_alt_duration_ms": self.best_alt_duration_ms,
            "regret_ms": round(self.regret_ms, 1) if self.regret_ms is not None else None,
            "chosen_failed": self.chosen_failed,
            "best_alt_failed": self.best_alt_failed,
            "verdict": self.verdict,
        }


@dataclass
class CounterfactualAnalysis:
    """Aggregated counterfactual analysis across all decisions."""
    results: list[CounterfactualResult]
    total_decisions: int
    optimal_count: int
    suboptimal_count: int
    catastrophic_count: int  # chose agent that failed, alternative succeeded
    total_regret_ms: float  # sum of positive regrets

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_decisions": self.total_decisions,
            "optimal": self.optimal_count,
            "suboptimal": self.suboptimal_count,
            "catastrophic": self.catastrophic_count,
            "total_regret_ms": round(self.total_regret_ms, 1),
            "results": [r.to_dict() for r in self.results],
        }

    def to_report(self) -> str:
        lines = [
            "# Counterfactual Decision Analysis", "",
            f"Decisions: {self.total_decisions}",
            f"Optimal: {self.optimal_count}, "
            f"Suboptimal: {self.suboptimal_count}, "
            f"Catastrophic: {self.catastrophic_count}",
            f"Total regret: {self.total_regret_ms:.0f}ms", "",
        ]
        for r in self.results:
            icon = _verdict_icon(r.verdict)
            lines.append(f"{icon} **{r.coordinator}** chose **{r.chosen_agent}**")
            dur = f" ({r.chosen_duration_ms:.0f}ms)" if r.chosen_duration_ms else ""
            lines.append(f"  Actual: {r.chosen_status}{dur}")
            if r.best_alternative:
                alt_dur = f" ({r.best_alt_duration_ms:.0f}ms)" if r.best_alt_duration_ms else ""
                lines.append(f"  Best alt: {r.best_alternative} → {r.best_alt_status}{alt_dur}")
            if r.regret_ms and r.regret_ms > 0:
                lines.append(f"  Regret: +{r.regret_ms:.0f}ms")
            lines.append("")
        return "\n".join(lines)


def _verdict_icon(verdict: str) -> str:
    """Map verdict to display icon."""
    return {"optimal": "\u2705", "suboptimal": "\u26a0\ufe0f",
            "catastrophic": "\u274c", "no_alternatives": "\u2796"}.get(verdict, "?")


def _find_agent_performance(
    agent_name: str, trace: ExecutionTrace
) -> tuple[Optional[str], Optional[float]]:
    """Find an agent's best performance in the trace.

    Searches all spans matching the agent name to get status and duration.
    Returns (status, duration_ms) or (None, None) if not found.
    """
    best_status = None
    best_duration = None
    for s in trace.spans:
        if s.name != agent_name or s.span_type != SpanType.AGENT:
            continue
        dur = s.duration_ms
        status = s.status.value if s.status else "unknown"
        # Prefer completed over failed, then shortest duration
        if best_status is None:
            best_status, best_duration = status, dur
        elif status == "completed" and best_status != "completed":
            best_status, best_duration = status, dur
        elif status == best_status and dur is not None:
            if best_duration is None or dur < best_duration:
                best_duration = dur
    return best_status, best_duration


def _evaluate_single_decision(
    decision: DecisionRecord, trace: ExecutionTrace
) -> CounterfactualResult:
    """Compare one decision's chosen agent against its alternatives."""
    chosen_dur = decision.downstream_duration_ms
    chosen_failed = decision.led_to_failure
    chosen_status = decision.downstream_status

    best_alt = None
    best_alt_status = None
    best_alt_dur = None
    best_alt_failed = True

    for alt_name in decision.alternatives:
        alt_status, alt_dur = _find_agent_performance(alt_name, trace)
        if alt_status is None:
            continue  # alternative never ran, can't compare
        alt_is_failed = alt_status == "failed"
        if _is_better(alt_is_failed, alt_dur, best_alt_failed, best_alt_dur):
            best_alt = alt_name
            best_alt_status = alt_status
            best_alt_dur = alt_dur
            best_alt_failed = alt_is_failed

    regret = _compute_regret(chosen_dur, best_alt_dur)
    verdict = _determine_verdict(
        chosen_failed, best_alt, best_alt_failed, regret
    )

    return CounterfactualResult(
        coordinator=decision.coordinator,
        chosen_agent=decision.chosen_agent,
        chosen_status=chosen_status,
        chosen_duration_ms=chosen_dur,
        best_alternative=best_alt,
        best_alt_status=best_alt_status,
        best_alt_duration_ms=best_alt_dur,
        regret_ms=regret,
        chosen_failed=chosen_failed,
        best_alt_failed=best_alt_failed if best_alt else True,
        verdict=verdict,
    )


def _is_better(
    alt_failed: bool, alt_dur: Optional[float],
    best_failed: bool, best_dur: Optional[float],
) -> bool:
    """Is this alternative better than current best?"""
    if not alt_failed and best_failed:
        return True
    if alt_failed == best_failed and alt_dur is not None:
        if best_dur is None or alt_dur < best_dur:
            return True
    return False


def _compute_regret(
    chosen_dur: Optional[float], best_alt_dur: Optional[float]
) -> Optional[float]:
    """Compute time regret (positive = chose slower path)."""
    if chosen_dur is not None and best_alt_dur is not None:
        return chosen_dur - best_alt_dur
    return None


def _determine_verdict(
    chosen_failed: bool,
    best_alt: Optional[str],
    best_alt_failed: bool,
    regret: Optional[float],
) -> str:
    """Classify decision quality."""
    if best_alt is None:
        return "no_alternatives"
    if chosen_failed and not best_alt_failed:
        return "catastrophic"
    if regret is not None and regret > 0:
        return "suboptimal"
    return "optimal"


def analyze_counterfactual(trace: ExecutionTrace) -> CounterfactualAnalysis:
    """Compare actual decisions against best alternative paths.

    For each orchestration decision, finds the best alternative that
    actually ran in the trace and compares outcomes. This answers Q5:
    'Was the orchestrator's decision optimal?'

    Limitations: can only compare against alternatives that ran.
    Alternatives that never executed get no counterfactual score.
    """
    da = analyze_decisions(trace)
    results = [_evaluate_single_decision(d, trace) for d in da.decisions]

    optimal = sum(1 for r in results if r.verdict == "optimal")
    suboptimal = sum(1 for r in results if r.verdict == "suboptimal")
    catastrophic = sum(1 for r in results if r.verdict == "catastrophic")
    total_regret = sum(
        r.regret_ms for r in results
        if r.regret_ms is not None and r.regret_ms > 0
    )

    return CounterfactualAnalysis(
        results=results,
        total_decisions=len(results),
        optimal_count=optimal,
        suboptimal_count=suboptimal,
        catastrophic_count=catastrophic,
        total_regret_ms=total_regret,
    )
