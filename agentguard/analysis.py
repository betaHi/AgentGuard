"""Trace analysis — failure propagation, context flow, critical path.

Given a multi-agent execution trace, these functions answer:
- Where did the failure originate? (root cause)
- How did it propagate? (blast radius)
- Was it handled or did it bubble up? (resilience)
- How did context flow between agents? (handoff analysis)
- What was the critical path? (bottleneck)
"""



from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType

__all__ = ['FailureNode', 'FailureAnalysis', 'analyze_failures', 'HandoffInfo', 'FlowAnalysis', 'analyze_flow', 'WorkflowPattern', 'WorkflowPatternAnalysis', 'analyze_workflow_patterns', 'BottleneckReport', 'analyze_bottleneck', 'ContextFlowPoint', 'ContextFlowReport', 'analyze_context_flow', 'analyze_retries', 'analyze_cost', 'analyze_cost_yield', 'CostYieldEntry', 'CostYieldPathSummary', 'CostYieldReport', 'DecisionRecord', 'DecisionAnalysis', 'analyze_decisions', 'DurationAnomaly', 'DurationAnomalyReport', 'detect_duration_anomalies', 'analyze_timing', 'CounterfactualResult', 'CounterfactualAnalysis', 'analyze_counterfactual', 'RepeatedBadDecision', 'detect_repeated_bad_decisions']


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
        """Serialize to dictionary."""
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
        """Serialize to dictionary."""
        return {
            "root_causes": [r.to_dict() for r in self.root_causes],
            "total_failed_spans": self.total_failed_spans,
            "blast_radius": self.blast_radius,
            "handled_count": self.handled_count,
            "unhandled_count": self.unhandled_count,
            "resilience_score": round(self.resilience_score, 2),
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
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


def _build_span_maps(trace: ExecutionTrace) -> tuple[
    dict[str, str], dict[str, list[str]], dict[str, Span]
]:
    """Build parent, children, and span lookup maps from a trace.

    Returns:
        (parent_map, children_map, span_map) where parent_map maps
        span_id → parent_span_id, children_map maps parent → [child_ids],
        and span_map maps span_id → Span.
    """
    parent_map: dict[str, str] = {}
    children_map: dict[str, list[str]] = {}
    span_map: dict[str, Span] = {}
    for s in trace.spans:
        span_map[s.span_id] = s
        if s.parent_span_id:
            parent_map[s.span_id] = s.parent_span_id
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)
    return parent_map, children_map, span_map


def _find_root_causes(
    failed: list[Span],
    parent_map: dict[str, str],
    failed_ids: set[str],
) -> list[Span]:
    """Identify root cause failures — the deepest failing span in each chain.

    A "root cause" here is the span that actually broke, not the span
    closest to the trace root. If an agent failed *because* its child tool
    raised, the tool is the root cause — that is the span the user needs
    to look at. We therefore walk down from each topmost failed span
    following the chain of failed descendants, and pick the leaf-most
    failed span in that chain.
    """
    parent_map_ids: dict[str, str] = {}
    children_map: dict[str, list[Span]] = {}
    # Build a child lookup restricted to the failed set to keep the walk
    # cheap; the real children_map lives on the caller side.
    for s in failed:
        pid = parent_map.get(s.span_id)
        if pid is not None:
            parent_map_ids[s.span_id] = pid
    failed_by_id = {s.span_id: s for s in failed}
    for s in failed:
        pid = parent_map.get(s.span_id)
        if pid in failed_by_id:
            children_map.setdefault(pid, []).append(s)

    root_causes: list[Span] = []
    for s in failed:
        pid = parent_map.get(s.span_id)
        if pid is not None and pid in failed_ids:
            # Not a top — its parent is already carrying the chain.
            continue
        # Walk down the chain of failed descendants, picking the leaf.
        current = s
        while True:
            failed_kids = children_map.get(current.span_id, [])
            if len(failed_kids) != 1:
                # Zero failed kids → current is the leaf.
                # >1 failed kids → ambiguous; stop here rather than guess.
                break
            current = failed_kids[0]
        root_causes.append(current)
    return root_causes


def _compute_blast_radius(
    root_cause_spans: list[Span],
    children_map: dict[str, list[str]],
    span_map: dict[str, Span],
    parent_map: dict[str, str],
    failed_ids: set[str],
) -> tuple[list[FailureNode], set[str]]:
    """Compute blast radius: for each root cause, find affected downstream spans.

    Returns:
        (root_cause_nodes, total_affected_ids) — FailureNode trees and
        the set of all span IDs affected by failures.
    """
    def _collect_affected(span_id: str) -> list[str]:
        affected = []
        for child_id in children_map.get(span_id, []):
            if child_id in failed_ids:
                affected.append(child_id)
                affected.extend(_collect_affected(child_id))
        return affected

    root_causes = []
    total_affected: set[str] = set()
    for rc_span in root_cause_spans:
        affected = _collect_affected(rc_span.span_id)
        total_affected.update(affected)
        total_affected.add(rc_span.span_id)
        was_handled = _is_failure_handled(rc_span, parent_map, span_map)
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
    return root_causes, total_affected


def _is_failure_handled(
    span: Span,
    parent_map: dict[str, str],
    span_map: dict[str, Span],
) -> bool:
    """Determine if a failure was handled by its parent.

    A tool failure is considered handled if the parent agent still completed
    successfully (i.e., the agent caught and recovered from the error).
    Agent failures are unhandled by default.
    """
    if span.failure_handled:
        return True
    if span.span_type == SpanType.TOOL:
        parent_id = parent_map.get(span.span_id)
        if parent_id and parent_id in span_map:
            parent_span = span_map[parent_id]
            if parent_span.status == SpanStatus.COMPLETED:
                return True
    return False


def _compute_resilience(root_causes: list[FailureNode]) -> tuple[int, int, float]:
    """Compute resilience metrics from root cause failure nodes.

    Returns:
        (handled_count, unhandled_count, resilience_score) where
        resilience_score is the ratio of handled to total root causes.
    """
    handled = sum(1 for rc in root_causes if rc.was_handled)
    unhandled = len(root_causes) - handled
    resilience = handled / max(len(root_causes), 1)
    return handled, unhandled, resilience


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

    parent_map, children_map, span_map = _build_span_maps(trace)
    failed_ids = {s.span_id for s in failed}
    root_cause_spans = _find_root_causes(failed, parent_map, failed_ids)
    root_causes, total_affected = _compute_blast_radius(
        root_cause_spans, children_map, span_map, parent_map, failed_ids,
    )
    handled, unhandled, resilience = _compute_resilience(root_causes)

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
    duration_ms: float | None = None

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
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
        """Serialize to dictionary."""
        return {
            "agent_count": self.agent_count,
            "tool_count": self.tool_count,
            "handoffs": [h.to_dict() for h in self.handoffs],
            "critical_path": self.critical_path,
            "critical_path_duration_ms": round(self.critical_path_duration_ms, 1),
            "parallel_groups": self.parallel_groups,
        }


@dataclass
class WorkflowPattern:
    """A detected orchestration workflow pattern."""
    name: str
    confidence: float
    evidence: str
    rationale: str
    heuristic: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "name": self.name,
            "confidence": round(self.confidence, 2),
            "evidence": self.evidence,
            "rationale": self.rationale,
            "heuristic": self.heuristic,
        }


@dataclass
class WorkflowPatternAnalysis:
    """Heuristic workflow taxonomy for a trace."""
    patterns: list[WorkflowPattern]
    primary_pattern: str
    caveats: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "primary_pattern": self.primary_pattern,
            "patterns": [p.to_dict() for p in self.patterns],
            "caveats": self.caveats,
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
        lines = [
            "# Workflow Pattern Analysis", "",
            f"Primary pattern: {self.primary_pattern}", "",
        ]
        for pattern in self.patterns:
            heur = " (heuristic)" if pattern.heuristic else ""
            lines.append(
                f"- **{pattern.name}**{heur}: {pattern.confidence:.0%} confidence — {pattern.evidence}"
            )
            lines.append(f"  {pattern.rationale}")
        if self.caveats:
            lines.append("")
            lines.append("Caveats:")
            for caveat in self.caveats:
                lines.append(f"- {caveat}")
        return "\n".join(lines)


def _extract_handoffs(
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> list[HandoffInfo]:
    """Extract handoffs from explicit HANDOFF spans or infer from agent sequence.

    Prefers explicit HANDOFF spans (from record_handoff instrumentation).
    Falls back to inferring handoffs from sequential agent children
    under the same parent.
    """
    import json as _json_flow

    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    if handoff_spans:
        return _handoffs_from_explicit(handoff_spans)
    return _handoffs_from_sequence(children_map, _json_flow)


def _handoffs_from_explicit(handoff_spans: list[Span]) -> list[HandoffInfo]:
    """Build HandoffInfo list from explicit HANDOFF spans."""
    handoffs = []
    for hs in handoff_spans:
        fr = hs.handoff_from or hs.metadata.get("handoff.from", "")
        to = hs.handoff_to or hs.metadata.get("handoff.to", "")
        ctx_keys = hs.metadata.get("handoff.context_keys", [])
        ctx_size = hs.context_size_bytes or hs.metadata.get("handoff.context_size_bytes", 0)
        handoffs.append(HandoffInfo(
            from_agent=fr, to_agent=to, context_keys=ctx_keys,
            context_size_bytes=ctx_size, duration_ms=hs.duration_ms,
        ))
    return handoffs


def _handoffs_from_sequence(
    children_map: dict[str, list[Span]],
    json_mod: Any,
) -> list[HandoffInfo]:
    """Infer handoffs from sequential agent spans under the same parent."""
    handoffs = []
    for _parent_id, children in children_map.items():
        agent_children = [c for c in children if c.span_type == SpanType.AGENT]
        if len(agent_children) < 2:
            continue
        sorted_agents = sorted(agent_children, key=lambda s: s.started_at or "")
        for i in range(len(sorted_agents) - 1):
            src, dst = sorted_agents[i], sorted_agents[i + 1]
            ctx_bytes = len(json_mod.dumps(src.output_data or {}, default=str).encode())
            ctx_keys = list((src.output_data or {}).keys()) if isinstance(src.output_data, dict) else []
            handoffs.append(HandoffInfo(
                from_agent=src.name, to_agent=dst.name,
                context_keys=ctx_keys, context_size_bytes=ctx_bytes,
            ))
    return handoffs


def _find_critical_path(
    trace: ExecutionTrace,
    span_map: dict[str, Span],
    children_map: dict[str, list[Span]],
) -> tuple[list[str], float]:
    """Find the longest execution chain from root to leaf.

    Returns:
        (path_names, total_duration_ms) for the critical path.
    """
    def _longest(span_id: str) -> tuple[list[str], float]:
        span = span_map.get(span_id)
        if not span:
            return [], 0
        kids = children_map.get(span_id, [])
        if not kids:
            return [span.name], span.duration_ms or 0
        best_path, best_dur = [], 0.0
        for child in kids:
            p, d = _longest(child.span_id)
            if d > best_dur:
                best_path, best_dur = p, d
        return [span.name] + best_path, span.duration_ms or 0

    roots = [s for s in trace.spans
             if s.parent_span_id is None or s.parent_span_id not in span_map]
    crit_path, crit_dur = [], 0.0
    for root in roots:
        path, dur = _longest(root.span_id)
        if dur > crit_dur:
            crit_path, crit_dur = path, dur
    return crit_path, crit_dur


def _detect_parallel_groups(
    children_map: dict[str, list[Span]],
) -> list[list[str]]:
    """Detect groups of agents that execute under the same parent.

    Simplified heuristic: 2+ agent children under the same parent
    are considered a parallel group.
    """
    groups = []
    for _parent_id, children in children_map.items():
        agents = [c for c in children if c.span_type == SpanType.AGENT]
        if len(agents) >= 2:
            groups.append([c.name for c in agents])
    return groups


def analyze_flow(trace: ExecutionTrace) -> FlowAnalysis:
    """Analyze the execution flow of a multi-agent trace.

    Identifies handoffs between agents, the critical path (longest
    execution chain), and parallel execution groups.

    Args:
        trace: The execution trace to analyze.

    Returns:
        FlowAnalysis with critical path, parallelism metrics, and phase detection.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)

    handoffs = _extract_handoffs(trace, children_map)
    critical_path, critical_duration = _find_critical_path(trace, span_map, children_map)
    parallel_groups = _detect_parallel_groups(children_map)

    return FlowAnalysis(
        agent_count=len(trace.agent_spans),
        tool_count=len(trace.tool_spans),
        handoffs=handoffs,
        critical_path=critical_path,
        critical_path_duration_ms=critical_duration,
        parallel_groups=parallel_groups,
    )


def _pattern_prompt_chaining(flow: FlowAnalysis, decisions: "DecisionAnalysis") -> WorkflowPattern | None:
    """Detect sequential prompt chaining."""
    if flow.handoffs and not flow.parallel_groups and decisions.total_decisions == 0:
        return WorkflowPattern(
            name="prompt_chaining",
            confidence=0.8,
            evidence=f"{len(flow.handoffs)} handoffs with no parallel groups or routing decisions",
            rationale="The trace progresses as a sequential chain of agents passing context downstream.",
        )
    return None


def _pattern_parallelization(flow: FlowAnalysis) -> WorkflowPattern | None:
    """Detect parallelized execution groups."""
    if flow.parallel_groups:
        size = max(len(group) for group in flow.parallel_groups)
        return WorkflowPattern(
            name="parallelization",
            confidence=0.95,
            evidence=f"{len(flow.parallel_groups)} parallel groups detected (largest group: {size} agents)",
            rationale="Multiple sibling agents execute under the same parent, indicating sectioning or parallel fan-out.",
        )
    return None


def _pattern_routing(decisions: "DecisionAnalysis") -> WorkflowPattern | None:
    """Detect routing based on orchestration decisions."""
    if decisions.total_decisions > 0:
        return WorkflowPattern(
            name="routing",
            confidence=0.95,
            evidence=f"{decisions.total_decisions} orchestration decisions were explicitly recorded",
            rationale="A coordinator selected downstream agents based on a routing decision rather than fixed sequencing alone.",
        )
    return None


def _pattern_orchestrator_workers(trace: ExecutionTrace) -> WorkflowPattern | None:
    """Detect orchestrator-workers topology."""
    fanouts = []
    for span in trace.agent_spans:
        child_agents = [s for s in trace.spans if s.parent_span_id == span.span_id and s.span_type == SpanType.AGENT]
        if len(child_agents) >= 2:
            fanouts.append((span.name, len(child_agents)))
    if fanouts:
        leader, count = max(fanouts, key=lambda item: item[1])
        return WorkflowPattern(
            name="orchestrator_workers",
            confidence=0.9,
            evidence=f"Agent '{leader}' fans out to {count} worker agents",
            rationale="A central coordinator delegates work to multiple child agents within the same trace.",
        )
    return None


def _pattern_evaluator_optimizer(trace: ExecutionTrace, flow: FlowAnalysis) -> tuple[WorkflowPattern | None, str | None]:
    """Detect evaluator-optimizer loops using conservative heuristics."""
    names = [span.name.lower() for span in trace.agent_spans]
    keywords = ("review", "critic", "judge", "evaluator", "fact-check")
    if flow.handoffs and any(keyword in name for name in names for keyword in keywords):
        return (
            WorkflowPattern(
                name="evaluator_optimizer",
                confidence=0.6,
                evidence="Reviewer/evaluator-style agent names appear in a multi-step handoff chain",
                rationale="The trace includes an evaluation stage that likely critiques or refines upstream work.",
                heuristic=True,
            ),
            "Evaluator-optimizer is inferred from agent naming and handoff structure, not explicit loop instrumentation.",
        )
    return None, None


def analyze_workflow_patterns(trace: ExecutionTrace) -> WorkflowPatternAnalysis:
    """Classify the orchestration shape of a trace using conservative heuristics."""
    flow = analyze_flow(trace)
    decisions = analyze_decisions(trace)
    patterns = []
    caveats = []

    for pattern in (
        _pattern_prompt_chaining(flow, decisions),
        _pattern_parallelization(flow),
        _pattern_routing(decisions),
        _pattern_orchestrator_workers(trace),
    ):
        if pattern:
            patterns.append(pattern)

    eval_pattern, caveat = _pattern_evaluator_optimizer(trace, flow)
    if eval_pattern:
        patterns.append(eval_pattern)
    if caveat:
        caveats.append(caveat)

    primary = max(patterns, key=lambda item: item.confidence).name if patterns else "unknown"
    if not patterns:
        caveats.append("No strong workflow pattern matched; the trace may be too small or only partially instrumented.")
    return WorkflowPatternAnalysis(patterns=patterns, primary_pattern=primary, caveats=caveats)


@dataclass
class BottleneckReport:
    """Identifies performance bottlenecks in multi-agent execution."""
    critical_path: list[str]
    critical_path_duration_ms: float
    bottleneck_span: str  # name of the slowest span on the critical path
    bottleneck_agent: str = ""  # parent agent if bottleneck is a tool/llm span
    bottleneck_duration_ms: float = 0
    bottleneck_pct: float = 0  # % of total trace time consumed by bottleneck
    agent_rankings: list[dict] = field(default_factory=list)  # agents sorted by duration
    false_bottleneck: str | None = None  # agent that looks slow but is waiting
    false_bottleneck_detail: str = ""  # explanation of why it is a false bottleneck

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "critical_path": self.critical_path,
            "critical_path_duration_ms": round(self.critical_path_duration_ms, 1),
            "bottleneck": self.bottleneck_span,
            "bottleneck_agent": self.bottleneck_agent,
            "bottleneck_duration_ms": round(self.bottleneck_duration_ms, 1),
            "bottleneck_pct": round(self.bottleneck_pct, 1),
            "agent_rankings": self.agent_rankings,
            "false_bottleneck": self.false_bottleneck,
            "false_bottleneck_detail": self.false_bottleneck_detail,
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
        lines = [
            "# Bottleneck Analysis",
            "",
            f"- **Critical path:** {' → '.join(self.critical_path)}",
            f"- **Bottleneck:** {self.bottleneck_span} ({self.bottleneck_duration_ms:.0f}ms, {self.bottleneck_pct:.0f}% of total)"
            + (f" [agent: {self.bottleneck_agent}]" if self.bottleneck_agent and self.bottleneck_agent != self.bottleneck_span else ""),
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
    meta_keys = {k.lower() for k in span.metadata}
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
) -> tuple[str | None, str]:
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


def _identify_bottleneck_span(
    trace: ExecutionTrace,
    critical_path: list[str],
    children_map: dict[str, list[Span]],
) -> Span | None:
    """Find the slowest leaf-work span on the critical path.

    Excludes container/coordinator spans (parents of other spans) because
    they cover the entire subtree duration and aren't the real bottleneck.
    Falls back to all path spans if everything is a container.
    """
    parent_ids = set(children_map.keys())
    path_spans = [s for s in trace.spans if s.name in critical_path]
    work_spans = [s for s in path_spans if s.span_id not in parent_ids]
    if not work_spans:
        work_spans = path_spans
    if not work_spans:
        return trace.spans[0] if trace.spans else None
    return max(work_spans, key=lambda s: s.duration_ms or 0)


def _compute_work_wait(span: Span, children: list[Span]) -> tuple[float, float]:
    """Compute work_time vs wait_time for an agent span.

    work_time: time children are actively executing (sum of child durations).
    wait_time: agent wall time minus work_time — gaps, scheduling, overhead.

    This distinguishes "slow because LLM call is slow" (high work_time)
    from "slow because waiting for dependency" (high wait_time).

    Returns:
        (work_time_ms, wait_time_ms)
    """
    total = span.duration_ms or 0
    work = sum(c.duration_ms or 0 for c in children)
    # Work can exceed total if children overlap (parallel), cap at total
    work = min(work, total)
    wait = max(total - work, 0)
    return work, wait


def _rank_bottlenecks(
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> list[dict]:
    """Rank agents by own duration with work/wait breakdown.

    - own_duration_ms: total minus children (agent's own CPU work)
    - work_time_ms: time children are executing (LLM calls, tools)
    - wait_time_ms: idle time — gaps, scheduling, dependency waits
    """
    total_dur = trace.duration_ms or 1
    parent_ids = set(children_map.keys())
    rankings = []
    for s in trace.agent_spans:
        total_d = s.duration_ms or 0
        children = children_map.get(s.span_id, [])
        child_dur = sum(c.duration_ms or 0 for c in children)
        own_d = max(total_d - child_dur, 0)
        work, wait = _compute_work_wait(s, children)
        rankings.append({
            "name": s.name,
            "duration_ms": total_d,
            "own_duration_ms": own_d,
            "work_time_ms": work,
            "wait_time_ms": wait,
            "pct": (total_d / max(total_dur, 1)) * 100,
            "own_pct": (own_d / max(total_dur, 1)) * 100,
            "status": s.status.value,
            "is_container": s.span_id in parent_ids,
            "category": _classify_span_category(s, own_d, total_d, children),
        })
    rankings.sort(key=lambda x: x["own_duration_ms"], reverse=True)
    return rankings


def analyze_bottleneck(trace: ExecutionTrace) -> BottleneckReport:
    """Identify the performance bottleneck in a trace.

    Answers Q1: "Which agent is the performance bottleneck?"
    Uses critical path analysis + own-duration ranking to separate
    real work from container/delegation overhead.

    Args:
        trace: The execution trace to analyze.

    Returns:
        BottleneckAnalysis identifying the slowest agent and optimization targets.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)

    critical_path, critical_dur = _find_critical_path(trace, span_map, children_map)
    bottleneck = _identify_bottleneck_span(trace, critical_path, children_map)
    agent_rankings = _rank_bottlenecks(trace, children_map)
    fb_name, fb_detail = _detect_false_bottleneck(agent_rankings)
    total_dur = trace.duration_ms or 1

    # Resolve tool/llm bottleneck back to parent agent for viewer compatibility
    bottleneck_agent = ""
    if bottleneck and bottleneck.span_type != SpanType.AGENT:
        parent = span_map.get(bottleneck.parent_span_id or "")
        while parent and parent.span_type != SpanType.AGENT:
            parent = span_map.get(parent.parent_span_id or "")
        bottleneck_agent = parent.name if parent else ""

    return BottleneckReport(
        critical_path=critical_path,
        critical_path_duration_ms=critical_dur,
        bottleneck_span=bottleneck.name if bottleneck else "",
        bottleneck_agent=bottleneck_agent,
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
    retention_ratio: float | None = None  # bytes_received / bytes_sent (1.0 = perfect)
    transformations: list[dict] = field(default_factory=list)  # semantic changes detected
    info_units_sent: int = 0
    info_units_received: int = 0
    critical_keys_sent: list[str] = field(default_factory=list)
    critical_keys_lost: list[str] = field(default_factory=list)
    reference_ids_sent: list[str] = field(default_factory=list)
    reference_ids_lost: list[str] = field(default_factory=list)
    semantic_retention_score: float | None = None  # 0-1: higher = more semantics preserved
    semantic_loss_reason: str = ""
    downstream_impact_score: float | None = None  # 0-1: higher = stronger downstream degradation evidence
    downstream_impact_reason: str = ""
    # Provenance for the critical-key decision. One of:
    #   "explicit" — user set critical_keys on the trace metadata
    #   "learned"  — key appeared in ≥2 output_data blocks in this trace
    #   "heuristic" — English keyword match on the key name
    #   ""         — no critical keys identified
    # Surface this in the viewer so users can see WHY the tool flagged a
    # key as critical — and reject the verdict if the provenance is weak.
    critical_key_source: str = ""

    @property
    def risk_score(self) -> float:
        """Conservative composite risk for prioritizing suspicious handoffs."""
        anomaly_base = {
            "ok": 0.0,
            "bloat": 0.18,
            "compression": 0.22,
            "loss": 0.45,
            "truncation": 0.5,
        }.get(self.anomaly, 0.15)
        critical_boost = min(0.12 * len(self.critical_keys_lost), 0.3)
        semantic_boost = 0.0
        if self.semantic_retention_score is not None:
            semantic_boost = (1.0 - self.semantic_retention_score) * 0.35
        impact_boost = (self.downstream_impact_score or 0.0) * 0.45
        return min(anomaly_base + critical_boost + semantic_boost + impact_boost, 1.0)

    @property
    def risk_label(self) -> str:
        """Bucketized label for user-facing handoff prioritization."""
        score = self.risk_score
        if score >= 0.75:
            return "severe"
        if score >= 0.55:
            return "high"
        if score >= 0.3:
            return "medium"
        if score > 0:
            return "low"
        return "ok"

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "from": self.from_agent, "to": self.to_agent,
            "keys_sent": self.keys_sent, "size_bytes": self.size_bytes,
            "keys_lost": self.keys_lost, "size_delta_bytes": self.size_delta_bytes,
            "anomaly": self.anomaly,
            "truncation_detail": self.truncation_detail,
            "retention_ratio": round(self.retention_ratio, 3) if self.retention_ratio is not None else None,
            "transformations": self.transformations,
            "info_units_sent": self.info_units_sent,
            "info_units_received": self.info_units_received,
            "critical_keys_sent": self.critical_keys_sent,
            "critical_keys_lost": self.critical_keys_lost,
            "reference_ids_sent": self.reference_ids_sent,
            "reference_ids_lost": self.reference_ids_lost,
            "semantic_retention_score": round(self.semantic_retention_score, 3) if self.semantic_retention_score is not None else None,
            "semantic_loss_reason": self.semantic_loss_reason,
            "downstream_impact_score": round(self.downstream_impact_score, 3) if self.downstream_impact_score is not None else None,
            "downstream_impact_reason": self.downstream_impact_reason,
            "risk_score": round(self.risk_score, 3),
            "risk_label": self.risk_label,
        }


@dataclass
class ContextFlowReport:
    """Analysis of context flow across all handoffs in a trace."""
    handoff_count: int
    total_context_bytes: int
    points: list[ContextFlowPoint]
    anomalies: list[ContextFlowPoint]  # points with loss or bloat

    @property
    def avg_retention_ratio(self) -> float | None:
        """Average information retention across all handoffs with data."""
        ratios = [p.retention_ratio for p in self.points if p.retention_ratio is not None]
        return sum(ratios) / len(ratios) if ratios else None

    @property
    def ranked_points(self) -> list[ContextFlowPoint]:
        """Return handoffs ordered from highest to lowest diagnostic risk."""
        return sorted(
            self.points,
            key=lambda point: (-point.risk_score, point.from_agent, point.to_agent),
        )

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "handoff_count": self.handoff_count,
            "total_context_bytes": self.total_context_bytes,
            "anomaly_count": len(self.anomalies),
            "avg_retention_ratio": round(self.avg_retention_ratio, 3) if self.avg_retention_ratio is not None else None,
            "points": [p.to_dict() for p in self.points],
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
        lines = [
            "# Context Flow Analysis",
            "",
            f"- **Handoffs:** {self.handoff_count}",
            f"- **Total context:** {self.total_context_bytes:,} bytes",
            f"- **Anomalies:** {len(self.anomalies)}",
            "",
        ]
        for p in self.ranked_points:
            icon = "🟢" if p.anomaly == "ok" else "🔴" if p.anomaly == "loss" else "🟡"
            lines.append(f"{icon} {p.from_agent} → {p.to_agent}: {p.size_bytes:,}B [{p.risk_label}]")
            if p.keys_lost:
                lines.append(f"   ⚠ Lost keys: {p.keys_lost}")
            if p.critical_keys_lost:
                lines.append(f"   🔴 Critical loss: {p.critical_keys_lost}")
            if p.reference_ids_lost:
                lines.append(f"   📚 Evidence refs lost: {p.reference_ids_lost}")
            if p.anomaly == "bloat":
                lines.append(f"   ⚠ Context grew by {p.size_delta_bytes:,}B")
            if p.anomaly == "truncation" and p.truncation_detail:
                lines.append(f"   ✂ Truncated: {p.truncation_detail}")
            if p.retention_ratio is not None:
                pct = p.retention_ratio * 100
                icon = "\u2705" if pct >= 90 else "\u26a0" if pct >= 50 else "\u274c"
                lines.append(f"   {icon} Retention: {pct:.0f}%")
            if p.semantic_retention_score is not None:
                semantic_pct = p.semantic_retention_score * 100
                semantic_icon = "\u2705" if semantic_pct >= 80 else "\u26a0" if semantic_pct >= 55 else "\u274c"
                lines.append(f"   {semantic_icon} Semantic retention: {semantic_pct:.0f}%")
            if p.semantic_loss_reason:
                lines.append(f"   🧠 {p.semantic_loss_reason}")
            if p.downstream_impact_score is not None:
                lines.append(f"   📉 Downstream impact: {p.downstream_impact_score * 100:.0f}%")
            if p.downstream_impact_reason:
                lines.append(f"   ↳ {p.downstream_impact_reason}")
        return "\n".join(lines)


def _info_unit_count(data: Any) -> int:
    """Count unique scalar values as a lightweight semantic-richness proxy."""
    leaves: set[str] = set()

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            for item in value.values():
                _walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)
        elif value is not None:
            leaves.add(str(value))

    _walk(data)
    return len(leaves)


def _tokenize_key_name(key: str) -> set[str]:
    """Break a context key into lowercase tokens for heuristic matching."""
    parts = re.split(r"[^a-zA-Z0-9]+", key.replace("-", "_").lower())
    return {part for part in parts if part}


def _infer_critical_keys(data: Any, explicit_keys: list[str] | None = None) -> list[str]:
    """Infer likely critical context keys conservatively.

    Explicit keys always win; trace-learned keys (populated by
    :func:`_learn_critical_keys_from_trace` and stored in the active
    trace's metadata) are checked next; a small English-keyword
    heuristic is the final fallback so tests that don't set learned
    keys still get a reasonable answer.
    """
    keys, _ = _infer_critical_keys_with_provenance(data, explicit_keys)
    return keys


def _infer_critical_keys_with_provenance(
    data: Any, explicit_keys: list[str] | None = None,
) -> tuple[list[str], str]:
    """Same as ``_infer_critical_keys`` but also returns a provenance label.

    Returned label is one of ``"explicit"`` / ``"learned"`` /
    ``"heuristic"`` / ``""`` (when no keys were identified).
    The label is used to expose the *why* behind each Q2 verdict in the
    HTML viewer so users can judge the weight of the evidence.
    """
    if explicit_keys:
        return sorted({str(key) for key in explicit_keys if key}), "explicit"
    if not isinstance(data, dict):
        return [], ""
    payload_keys = {str(k) for k in data if isinstance(k, str)}
    learned = _current_learned_critical_keys() & payload_keys
    keywords = {
        "query", "question", "task", "goal", "request", "requirement",
        "requirements", "constraint", "constraints", "policy", "plan",
        "decision", "rationale", "reason", "evidence", "citation",
        "citations", "fact", "facts", "budget", "priority", "error",
        "issue", "problem", "selected", "choice", "criteria", "source",
        "sources", "document", "documents", "claim", "claims", "passage",
        "passages", "quote", "quotes",
    }
    heuristic: set[str] = set()
    for key in data:
        tokens = _tokenize_key_name(str(key))
        if tokens & keywords:
            heuristic.add(str(key))
    merged = sorted(learned | heuristic)
    if not merged:
        return [], ""
    # Learned wins over heuristic for provenance because trace-specific
    # evidence is stronger than name-guessing.
    if learned:
        return merged, "learned"
    return merged, "heuristic"


_LEARNED_KEYS_STATE: dict[str, frozenset[str]] = {}


def _current_learned_critical_keys() -> set[str]:
    """Return the learned critical-key set for the trace being analysed."""
    return set(_LEARNED_KEYS_STATE.get("keys", frozenset()))


def _critical_key_loss(
    sender_data: Any,
    keys_lost: list[str],
    explicit_critical_keys: list[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Return critical keys in the payload and which of them were lost."""
    critical_sent = _infer_critical_keys(sender_data, explicit_critical_keys)
    critical_lost = sorted(key for key in critical_sent if key in set(keys_lost))
    return critical_sent, critical_lost


def _collect_reference_ids(data: Any) -> set[str]:
    """Collect citation and document ids that anchor evidence across a handoff."""
    references: set[str] = set()

    def _add(value: Any) -> None:
        if isinstance(value, (str, int, float)) and str(value).strip():
            references.add(str(value))

    def _walk(value: Any) -> None:
        if isinstance(value, dict):
            doc_id = value.get("doc_id")
            if doc_id is not None:
                _add(doc_id)
            for key, item in value.items():
                if key in {"source_map", "retrieval_scores"} and isinstance(item, dict):
                    for ref_key in item:
                        _add(ref_key)
                elif key in {"citations", "missing_citation_ids", "rejected_doc_ids"} and isinstance(item, list):
                    for ref in item:
                        _add(ref)
                _walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                _walk(item)

    _walk(data)
    return references


def _reference_retention(sender_data: Any, receiver_data: Any) -> tuple[list[str], list[str], float | None, str]:
    """Estimate how much citation and document coverage survived a handoff."""
    sender_refs = _collect_reference_ids(sender_data)
    if not sender_refs:
        return [], [], None, ""
    receiver_refs = _collect_reference_ids(receiver_data)
    retained = sender_refs & receiver_refs
    lost = sorted(sender_refs - receiver_refs)
    ratio = len(retained) / max(len(sender_refs), 1)
    if not lost:
        return sorted(sender_refs), [], ratio, ""
    sample = ", ".join(lost[:3])
    return sorted(sender_refs), lost, ratio, f"lost evidence references: {sample}"


def _semantic_penalty(
    transformations: list[dict],
    anomaly: str,
    keys_lost: list[str],
    critical_keys_lost: list[str],
    reference_ratio: float | None,
    reference_reason: str,
) -> tuple[float, str]:
    """Convert context-flow signals into a conservative semantic-loss penalty."""
    penalty = 0.0
    reasons: list[str] = []
    transform_types = {t.get("type", "") for t in transformations}
    if keys_lost:
        penalty += min(0.15 * len(keys_lost), 0.45)
        reasons.append(f"lost {len(keys_lost)} key(s)")
    if critical_keys_lost:
        penalty += min(0.22 * len(critical_keys_lost), 0.55)
        reasons.append(f"critical keys lost: {', '.join(critical_keys_lost[:3])}")
    if reference_ratio is not None and reference_ratio < 1.0:
        penalty += (1.0 - reference_ratio) * 0.5
        reasons.append(reference_reason or "evidence references were lost")
    if anomaly == "truncation":
        penalty += 0.2
        reasons.append("payload was truncated")
    elif anomaly == "compression":
        penalty += 0.08
    if "filtering" in transform_types:
        penalty += 0.12
        reasons.append("content was filtered")
    if "type_change" in transform_types:
        penalty += 0.08
        reasons.append("value types changed")
    if "summarization" in transform_types:
        penalty += 0.03
    return min(penalty, 0.7), "; ".join(reasons)


def _semantic_retention(
    keys_sent: list[str],
    keys_received: list[str],
    size_bytes: int,
    size_received_bytes: int,
    anomaly: str,
    keys_lost: list[str],
    transformations: list[dict],
    sender_data: Any,
    receiver_data: Any,
    explicit_critical_keys: list[str] | None = None,
) -> tuple[int, int, list[str], list[str], list[str], list[str], float | None, str]:
    """Estimate how much meaning survived a handoff.

    This intentionally stays conservative. Summarization can lower byte
    retention without implying severe semantic loss, while dropped keys and
    truncation are stronger signals.
    """
    sent_units = _info_unit_count(sender_data)
    recv_units = _info_unit_count(receiver_data)
    if not keys_sent and sent_units == 0 and size_bytes <= 0:
        return sent_units, recv_units, [], [], [], [], None, ""

    key_ratio = 1.0 if not keys_sent else len(set(keys_sent) & set(keys_received)) / max(len(set(keys_sent)), 1)
    byte_ratio = 1.0 if size_bytes <= 0 else min(size_received_bytes / max(size_bytes, 1), 1.0)
    info_ratio = 1.0 if sent_units <= 0 else min(recv_units / max(sent_units, 1), 1.0)
    critical_sent, critical_lost = _critical_key_loss(sender_data, keys_lost, explicit_critical_keys)
    reference_sent, reference_lost, reference_ratio, reference_reason = _reference_retention(sender_data, receiver_data)
    critical_ratio = 1.0
    if critical_sent:
        retained_critical = len(set(critical_sent) - set(critical_lost))
        critical_ratio = retained_critical / max(len(critical_sent), 1)
    base_score = (critical_ratio * 0.35) + (key_ratio * 0.3) + (info_ratio * 0.25) + (byte_ratio * 0.1)
    penalty, reason = _semantic_penalty(
        transformations,
        anomaly,
        keys_lost,
        critical_lost,
        reference_ratio,
        reference_reason,
    )
    return (
        sent_units,
        recv_units,
        critical_sent,
        critical_lost,
        reference_sent,
        reference_lost,
        max(0.0, min(base_score - penalty, 1.0)),
        reason,
    )


def _build_children_span_map(trace: ExecutionTrace) -> dict[str, list[Span]]:
    """Build a parent -> child span map for subtree reasoning."""
    children_map: dict[str, list[Span]] = {}
    for span in trace.spans:
        if span.parent_span_id:
            children_map.setdefault(span.parent_span_id, []).append(span)
    return children_map


def _should_measure_downstream_impact(
    anomaly: str,
    critical_lost: list[str],
    semantic_score: float | None,
) -> bool:
    """Only attribute downstream impact when the handoff itself looks suspicious."""
    if anomaly in {"loss", "truncation"}:
        return True
    if critical_lost:
        return True
    return semantic_score is not None and semantic_score < 0.75


def _subtree_spans(
    root_span: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> list[Span]:
    """Collect subtree spans in stable order."""
    subtree_ids = _collect_subtree_ids(root_span.span_id, children_map)
    return sorted(
        [span for span in trace.spans if span.span_id in subtree_ids],
        key=_span_sort_key,
    )


def _quality_degradation_in_subtree(spans: list[Span]) -> tuple[float | None, str]:
    """Return the strongest low-quality signal within a receiver subtree."""
    worst_signal: tuple[float, str, str] | None = None
    for span in spans:
        if not isinstance(span.output_data, dict):
            continue
        signal, evidence = _extract_quality_signal(span.output_data, span.metadata)
        if signal is None:
            continue
        candidate = (signal, evidence, span.name)
        if worst_signal is None or signal < worst_signal[0]:
            worst_signal = candidate
    if worst_signal is None or worst_signal[0] >= 0.55:
        return None, ""
    return 1.0 - worst_signal[0], f"downstream quality degraded at {worst_signal[2]} ({worst_signal[1]})"


def _resolve_handoff_receiver_span(
    handoff_span: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> Span | None:
    """Resolve the receiving agent span for an explicit handoff."""
    to_agent = handoff_span.handoff_to or handoff_span.metadata.get("handoff.to", "")
    if not to_agent:
        return None
    candidates = [span for span in trace.agent_spans if span.name == to_agent]
    if not candidates:
        return None
    if handoff_span.parent_span_id:
        local_ids = _collect_subtree_ids(handoff_span.parent_span_id, children_map)
        local = [span for span in candidates if span.span_id in local_ids]
        if local:
            candidates = local
    candidates.sort(key=_span_sort_key)
    return candidates[0] if candidates else None


def _downstream_impact(
    receiver_span: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> tuple[float | None, str]:
    """Estimate whether handoff degradation manifested inside the receiver subtree."""
    spans = _subtree_spans(receiver_span, trace, children_map)
    failed = next((span for span in spans if span.status == SpanStatus.FAILED), None)
    quality_impact, quality_reason = _quality_degradation_in_subtree(spans)
    reasons: list[str] = []
    impact = 0.0
    if failed is not None:
        impact = max(impact, 1.0)
        reasons.append(f"downstream failure at {failed.name}")
    if quality_impact is not None:
        impact = max(impact, quality_impact)
        reasons.append(quality_reason)
    if impact <= 0:
        return None, ""
    return min(impact, 1.0), "; ".join(reasons[:2])


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


def _classify_value_transform(key: str, sent: Any, received: Any) -> dict | None:
    """Classify how a value changed between sender and receiver."""
    if sent == received:
        return None
    if not isinstance(sent, type(received)): # noqa: E721
        return {"type": "type_change", "key": key,
                "detail": f"{type(sent).__name__} -> {type(received).__name__}"}
    if isinstance(sent, str) and isinstance(received, str):
        return _classify_string_transform(key, sent, received)
    if isinstance(sent, list) and isinstance(received, list):
        return _classify_list_transform(key, sent, received)
    if isinstance(sent, dict) and isinstance(received, dict) and len(received) < len(sent):
        return {"type": "filtering", "key": key,
                "detail": f"dict shrunk from {len(sent)} to {len(received)} keys"}
    return {"type": "modified", "key": key, "detail": "value changed"}


def _classify_string_transform(key: str, sent: str, received: str) -> dict | None:
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


def _classify_list_transform(key: str, sent: list, received: list) -> dict | None:
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


def _is_likely_handoff(
    sender_keys: list[str], receiver_keys: list[str],
    receiver_input: Any, sibling_count: int = 2,
) -> bool:
    """Determine if two sequential siblings have a handoff relationship.

    Returns True if there's evidence the receiver depends on the sender's
    output. Returns False only for clear fan-out patterns (3+ siblings
    with completely disjoint data).

    Why 3+ siblings: with only 2 siblings, we can't distinguish A→B handoff
    from A||B parallelism, so we conservatively assume handoff.
    With 3+ siblings under one parent and no shared keys, it's fan-out.
    """
    if not sender_keys or not receiver_keys:
        return True  # ambiguous, allow analysis
    shared = set(sender_keys) & set(receiver_keys)
    if shared:
        return True  # receiver uses sender's output keys
    # Only skip for fan-out patterns (3+ parallel siblings)
    if sibling_count >= 3:
        return False
    return True  # conservative: assume handoff for 2 siblings


def _trace_explicit_handoffs(
    handoff_spans: list[Span],
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> list[ContextFlowPoint]:
    """Build context flow points from explicit HANDOFF spans.

    Uses instrumented handoff metadata (from record_handoff) which
    provides exact context keys, sizes, and receiver info.
    """
    points = []
    for hs in handoff_spans:
        fr = hs.handoff_from or hs.metadata.get("handoff.from", "")
        to = hs.handoff_to or hs.metadata.get("handoff.to", "")
        ctx_keys = hs.metadata.get("handoff.context_keys", [])
        ctx_size = hs.context_size_bytes or hs.metadata.get("handoff.context_size_bytes", 0)
        critical_keys = hs.metadata.get("handoff.critical_keys", [])
        dropped = hs.context_dropped_keys or hs.metadata.get("handoff.dropped_keys", [])
        used = hs.context_used_keys or hs.metadata.get("handoff.used_keys", [])
        recv_size = 0
        recv_info = hs.context_received
        recv_keys: list[str] = []
        if isinstance(recv_info, dict):
            recv_size = recv_info.get("size_bytes", 0)
            recv_keys = recv_info.get("keys", []) or []
        retention = recv_size / ctx_size if ctx_size > 0 and recv_size > 0 else None
        anomaly = "loss" if dropped else "ok"
        sent_units = len(set(ctx_keys))
        recv_units = len(set(used or recv_keys))
        critical_sent = sorted({str(key) for key in critical_keys if key})
        critical_lost = sorted(key for key in critical_sent if key in set(dropped))
        semantic_score = None
        reason = ""
        if sent_units > 0:
            base = ((len(set(critical_sent) - set(critical_lost)) / max(len(critical_sent), 1)) * 0.45 if critical_sent else 0.45)
            base += (recv_units / max(sent_units, 1)) * 0.55
            penalty = min(0.15 * len(dropped), 0.45) + min(0.22 * len(critical_lost), 0.55)
            semantic_score = max(0.0, min(base - penalty, 1.0))
            if critical_lost:
                reason = f"critical keys lost during explicit handoff: {', '.join(critical_lost[:3])}"
            elif dropped:
                reason = f"lost {len(dropped)} key(s) during explicit handoff"
        impact_score = None
        impact_reason = ""
        if _should_measure_downstream_impact(anomaly, critical_lost, semantic_score):
            receiver_span = _resolve_handoff_receiver_span(hs, trace, children_map)
            if receiver_span is not None:
                impact_score, impact_reason = _downstream_impact(receiver_span, trace, children_map)
        if impact_reason:
            reason = f"{reason}; downstream impact: {impact_reason}" if reason else f"downstream impact: {impact_reason}"
        # Explicit handoffs always have the user's hand on the wheel.
        critical_source = "explicit" if critical_sent else ""
        points.append(ContextFlowPoint(
            from_agent=fr, to_agent=to,
            keys_sent=ctx_keys, size_bytes=ctx_size,
            keys_received=used or recv_keys,
            size_received_bytes=recv_size,
            keys_lost=dropped,
            size_delta_bytes=recv_size - ctx_size,
            anomaly=anomaly,
            retention_ratio=retention,
            info_units_sent=sent_units,
            info_units_received=recv_units,
            critical_keys_sent=critical_sent,
            critical_keys_lost=critical_lost,
            semantic_retention_score=semantic_score,
            semantic_loss_reason=reason,
            downstream_impact_score=impact_score,
            downstream_impact_reason=impact_reason,
            critical_key_source=critical_source,
        ))
    return points


def _classify_handoff_anomaly(
    s_keys: list[str], r_keys: list[str],
    s_size: int, r_size: int,
    sender_output: Any, receiver_input: Any,
) -> tuple[str, list[str], str]:
    """Classify a handoff anomaly: loss, bloat, compression, truncation, or ok.

    Returns:
        (anomaly_type, lost_keys, truncation_detail)
    """
    lost = [k for k in s_keys if k not in r_keys] if s_keys and r_keys else []
    delta = r_size - s_size

    if lost:
        return "loss", lost, ""
    if delta > s_size * 2 and s_size > 0:
        return "bloat", [], ""
    if delta < -s_size * 0.5 and s_size > 100:
        return "compression", [], ""

    is_trunc, trunc_desc = _detect_truncation(sender_output, receiver_input)
    if is_trunc:
        return "truncation", [], trunc_desc
    return "ok", [], ""


def _trace_inferred_handoffs(
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> list[ContextFlowPoint]:
    """Infer context flow from sequential agent spans under the same parent.

    Used when no explicit HANDOFF spans exist. Compares sender output
    to receiver input to detect loss, bloat, compression, truncation.
    """
    import json as _json

    points = []
    for _pid, children in children_map.items():
        agents = sorted(
            [c for c in children if c.span_type == SpanType.AGENT],
            key=lambda s: s.started_at or "",
        )
        for i in range(len(agents) - 1):
            sender, receiver = agents[i], agents[i + 1]
            s_out = sender.output_data or {}
            r_in = receiver.input_data or {}
            s_keys = list(s_out.keys()) if isinstance(s_out, dict) else []
            r_keys = list(r_in.keys()) if isinstance(r_in, dict) else []
            if not _is_likely_handoff(s_keys, r_keys, r_in, sibling_count=len(agents)):
                continue
            s_size = len(_json.dumps(s_out, default=str).encode())
            r_size = len(_json.dumps(r_in, default=str).encode())
            anomaly, lost, trunc_desc = _classify_handoff_anomaly(
                s_keys, r_keys, s_size, r_size, s_out, r_in,
            )
            transforms = _detect_transformations(s_out, r_in, s_keys, r_keys)
            sent_units, recv_units, critical_sent, critical_lost, reference_sent, reference_lost, semantic_score, semantic_reason = _semantic_retention(
                s_keys,
                r_keys,
                s_size,
                r_size,
                anomaly,
                lost,
                transforms,
                s_out,
                r_in,
            )
            impact_score = None
            impact_reason = ""
            if _should_measure_downstream_impact(anomaly, critical_lost, semantic_score):
                impact_score, impact_reason = _downstream_impact(receiver, trace, children_map)
            if impact_reason:
                semantic_reason = f"{semantic_reason}; downstream impact: {impact_reason}" if semantic_reason else f"downstream impact: {impact_reason}"
            # Resolve the provenance of the critical-key decision so the
            # viewer can show users *why* these keys were flagged.
            _, critical_source = _infer_critical_keys_with_provenance(s_out, None)
            points.append(ContextFlowPoint(
                from_agent=sender.name, to_agent=receiver.name,
                keys_sent=s_keys, size_bytes=s_size,
                keys_received=r_keys, size_received_bytes=r_size,
                keys_lost=lost, size_delta_bytes=r_size - s_size,
                anomaly=anomaly,
                truncation_detail=trunc_desc if anomaly == "truncation" else "",
                retention_ratio=r_size / s_size if s_size > 0 else None,
                transformations=transforms,
                info_units_sent=sent_units,
                info_units_received=recv_units,
                critical_keys_sent=critical_sent,
                critical_keys_lost=critical_lost,
                reference_ids_sent=reference_sent,
                reference_ids_lost=reference_lost,
                semantic_retention_score=semantic_score,
                semantic_loss_reason=semantic_reason,
                downstream_impact_score=impact_score,
                downstream_impact_reason=impact_reason,
                critical_key_source=critical_source,
            ))
    return points


def analyze_context_flow(trace: ExecutionTrace) -> ContextFlowReport:
    """Analyze how context flows between agents via handoffs.

    Answers Q2: "Which handoff lost critical information?"
    Detects loss, bloat, compression, and truncation anomalies.

    Args:
        trace: The execution trace to analyze.

    Returns:
        ContextFlowResult with anomalies (loss, bloat, mutation) at handoff points.
    """
    # Learn which keys this particular trace actually relies on before we
    # walk handoffs — otherwise every trace uses the same English-keyword
    # heuristic and misses domain-specific criticals like ``file_list`` or
    # ``navigation_tree`` entirely.
    learned = _learn_critical_keys_from_trace(trace)
    if learned:
        trace.metadata.setdefault("context.learned_critical_keys", sorted(learned))
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    children_map = _build_children_span_map(trace)
    _LEARNED_KEYS_STATE["keys"] = frozenset(learned)
    try:
        points = (
            _trace_explicit_handoffs(handoff_spans, trace, children_map)
            if handoff_spans else _trace_inferred_handoffs(trace, children_map)
        )
    finally:
        _LEARNED_KEYS_STATE.pop("keys", None)

    return ContextFlowReport(
        handoff_count=len(points),
        total_context_bytes=sum(p.size_bytes for p in points),
        points=points,
        anomalies=[p for p in points if p.anomaly != "ok"],
    )


def _learn_critical_keys_from_trace(trace: ExecutionTrace) -> set[str]:
    """Learn trace-specific critical keys from observed span I/O.

    A key is promoted as critical when it is *both*:
      1. produced (appears in span output_data), and
      2. consumed by ≥ 2 downstream spans (appears in later span input_data
         or referenced textually in the input payload).

    This is conservative: trivial keys like ``id`` or ``result`` that
    appear once in passing won't cross the threshold, while
    domain-specific anchors like ``file_list`` in a docs-navigation
    session do.
    """
    produced_at: dict[str, int] = {}
    consumed_at: dict[str, int] = {}
    for idx, span in enumerate(trace.spans):
        for key in _iter_top_level_keys(span.output_data):
            produced_at.setdefault(key, idx)
        input_keys = set(_iter_top_level_keys(span.input_data))
        input_text = _payload_text(span.input_data)
        for key, first_idx in produced_at.items():
            if idx <= first_idx:
                continue
            if key in input_keys or _looks_referenced(key, input_text):
                consumed_at[key] = consumed_at.get(key, 0) + 1
    # Require ≥ 2 downstream consumers so one-off echoes don't pass.
    return {key for key, count in consumed_at.items() if count >= 2}


def _iter_top_level_keys(payload: Any) -> Iterable[str]:
    """Yield user-visible top-level key names from a trace payload."""
    if isinstance(payload, dict):
        for key in payload:
            if isinstance(key, str) and key and not key.startswith("_"):
                yield key


def _payload_text(payload: Any) -> str:
    """Flatten a payload to a searchable lowercase string (bounded)."""
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload[:4096].lower()
    try:
        import json as _json
        return _json.dumps(payload, default=str)[:4096].lower()
    except (TypeError, ValueError):
        return str(payload)[:4096].lower()


def _looks_referenced(key: str, text: str) -> bool:
    """Return True if ``key`` appears as a word/identifier in ``text``."""
    if not text or not key:
        return False
    lowered = key.lower()
    # Require a word-boundary-ish match to avoid spurious substring hits.
    return (
        f'"{lowered}"' in text
        or f"'{lowered}'" in text
        or f" {lowered}" in text
        or text.startswith(lowered)
    )


def analyze_retries(trace: ExecutionTrace) -> dict:
    """Detect retry patterns in a trace.

    Identifies spans that were retried (same name under same parent,
    first failed then succeeded).

    Args:
        trace: The execution trace to analyze.

    Returns:
        RetryAnalysis with per-span retry stats and wasted time estimates.
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

    Args:
        trace: The execution trace to analyze.

    Returns:
        CostAnalysis with per-agent costs, token usage, and cost-per-quality metrics.
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
    quality_signal: float | None = None  # 0-1 explicit quality if available
    quality_evidence: str = ""
    span_id: str = ""
    grounding_issue_count: int = 0
    claim_count: int = 0
    citation_count: int = 0
    unsupported_claim_count: int = 0
    missing_citation_count: int = 0
    unverified_claim_count: int = 0
    removed_claim_count: int = 0
    citation_coverage: float | None = None


@dataclass
class CostYieldPathSummary:
    """Aggregated cost-yield summary for a path through the orchestration."""
    path_kind: str  # critical_path or handoff_chain
    agents: list[str]
    total_cost_usd: float
    total_tokens: int
    avg_yield_score: float
    min_yield_score: float
    aggregate_quality_signal: float | None = None
    contains_failure: bool = False
    waste_score: float = 0.0
    grounding_issue_count: int = 0
    claim_count: int = 0
    citation_count: int = 0
    unsupported_claim_count: int = 0
    missing_citation_count: int = 0
    unverified_claim_count: int = 0
    removed_claim_count: int = 0
    citation_coverage: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path_kind": self.path_kind,
            "agents": self.agents,
            "label": " → ".join(self.agents),
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_tokens": self.total_tokens,
            "avg_yield_score": round(self.avg_yield_score, 1),
            "min_yield_score": round(self.min_yield_score, 1),
            "aggregate_quality_signal": round(self.aggregate_quality_signal, 3) if self.aggregate_quality_signal is not None else None,
            "contains_failure": self.contains_failure,
            "waste_score": round(self.waste_score, 1),
            "grounding_issue_count": self.grounding_issue_count,
            "claim_count": self.claim_count,
            "citation_count": self.citation_count,
            "unsupported_claim_count": self.unsupported_claim_count,
            "missing_citation_count": self.missing_citation_count,
            "unverified_claim_count": self.unverified_claim_count,
            "removed_claim_count": self.removed_claim_count,
            "citation_coverage": round(self.citation_coverage, 3) if self.citation_coverage is not None else None,
        }


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
    path_summaries: list[CostYieldPathSummary] = field(default_factory=list)
    critical_path_summary: CostYieldPathSummary | None = None
    worst_path: str = ""

    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "total_cost_usd": round(self.total_cost_usd, 4),
            "total_tokens": self.total_tokens,
            "highest_cost_agent": self.highest_cost_agent,
            "lowest_yield_agent": self.lowest_yield_agent,
            "best_ratio_agent": self.best_ratio_agent,
            "most_wasteful_agent": self.most_wasteful_agent,
            "waste_score": round(self.waste_score, 1),
            "recommendations": self.recommendations,
            "worst_path": self.worst_path,
            "critical_path_summary": self.critical_path_summary.to_dict() if self.critical_path_summary else None,
            "path_summaries": [p.to_dict() for p in self.path_summaries],
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
                    "quality_signal": round(e.quality_signal, 3) if e.quality_signal is not None else None,
                    "quality_evidence": e.quality_evidence,
                    "grounding_issue_count": e.grounding_issue_count,
                    "claim_count": e.claim_count,
                    "citation_count": e.citation_count,
                    "unsupported_claim_count": e.unsupported_claim_count,
                    "missing_citation_count": e.missing_citation_count,
                    "unverified_claim_count": e.unverified_claim_count,
                    "removed_claim_count": e.removed_claim_count,
                    "citation_coverage": round(e.citation_coverage, 3) if e.citation_coverage is not None else None,
                } for e in self.entries
            ],
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
        lines = [
            "# Cost-Yield Analysis", "",
            f"Total: {self.total_tokens:,} tokens, ${self.total_cost_usd:.4f}", "",
            f"- Highest cost: {self.highest_cost_agent}",
            f"- Lowest yield: {self.lowest_yield_agent}",
            f"- Best ratio:   {self.best_ratio_agent}",
            f"- **Most wasteful: {self.most_wasteful_agent}** (waste score: {self.waste_score:.0f}/100)" if self.most_wasteful_agent else "",
            f"- Worst path:   {self.worst_path}" if self.worst_path else "",
            "",
        ]
        if self.critical_path_summary:
            cp = self.critical_path_summary
            lines.append(
                f"Critical path cost-yield: {' → '.join(cp.agents)} · ${cp.total_cost_usd:.4f} · yield {cp.avg_yield_score:.0f}/100"
            )
            lines.append("")
        if self.recommendations:
            lines.append("## Recommendations")
            lines.append("")
            for rec in self.recommendations:
                lines.append(f"  💡 {rec}")
            lines.append("")
        if self.path_summaries:
            lines.append("## Path Summaries")
            lines.append("")
            for path in sorted(self.path_summaries, key=lambda item: -item.waste_score)[:3]:
                quality = f" · quality {path.aggregate_quality_signal:.0%}" if path.aggregate_quality_signal is not None else ""
                fail = " · failure" if path.contains_failure else ""
                grounding = (
                    f" · grounding issues {path.grounding_issue_count} · citations {path.citation_coverage:.0%}"
                    if path.claim_count and path.citation_coverage is not None else ""
                )
                lines.append(
                    f"- {' → '.join(path.agents)} [{path.path_kind}] — ${path.total_cost_usd:.4f}, yield {path.avg_yield_score:.0f}/100, waste {path.waste_score:.0f}/100{quality}{fail}{grounding}"
                )
            lines.append("")
        lines.extend([
            "## Per-Agent Breakdown", "",
        ])
        for e in sorted(self.entries, key=lambda x: -x.cost_usd):
            cps = f"${e.cost_per_success:.4f}" if e.cost_per_success != float("inf") else "N/A (failed)"
            lines.append(f"**{e.agent}** — {e.tokens:,} tokens, ${e.cost_usd:.4f}")
            lines.append(f"  yield: {e.yield_score:.0f}/100, cost/success: {cps}, {e.duration_ms:.0f}ms")
            if e.quality_signal is not None:
                lines.append(f"  quality signal: {e.quality_signal:.0%} ({e.quality_evidence})")
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
    leaf_names: set[str] | None = None,
) -> tuple[str, float]:
    """Find the agent with highest waste score.

    When ``leaf_names`` is provided, containers (agents with agent
    descendants) are excluded so the verdict points at a real offender
    instead of the parent that simply aggregates everyone's cost.
    """
    if not entries:
        return "", 0.0
    candidates = entries
    if leaf_names:
        leaf = [e for e in entries if e.agent in leaf_names]
        if leaf:
            candidates = leaf
    max_tok = max((e.tokens for e in candidates if e.tokens > 0), default=1)
    scored = [(e, _compute_waste_score(e, max_tok)) for e in candidates]
    scored.sort(key=lambda x: -x[1])
    return scored[0][0].agent, scored[0][1]


def _entry_weight(entry: CostYieldEntry) -> float:
    """Weight an entry by real spend when available, then by token volume."""
    if entry.cost_usd > 0:
        return entry.cost_usd
    if entry.tokens > 0:
        return entry.tokens / 1000
    return 1.0


def _build_handoff_paths(handoffs: list[HandoffInfo]) -> list[list[str]]:
    """Build agent chains from inferred or explicit handoffs."""
    if not handoffs:
        return []
    adjacency: dict[str, list[str]] = {}
    indegree: dict[str, int] = {}
    nodes: set[str] = set()
    for handoff in handoffs:
        adjacency.setdefault(handoff.from_agent, [])
        if handoff.to_agent not in adjacency[handoff.from_agent]:
            adjacency[handoff.from_agent].append(handoff.to_agent)
        indegree[handoff.to_agent] = indegree.get(handoff.to_agent, 0) + 1
        indegree.setdefault(handoff.from_agent, indegree.get(handoff.from_agent, 0))
        nodes.update({handoff.from_agent, handoff.to_agent})
    roots = sorted(node for node in nodes if indegree.get(node, 0) == 0)
    if not roots:
        roots = sorted(nodes)
    paths: list[list[str]] = []

    def _walk(node: str, path: list[str]) -> None:
        next_nodes = adjacency.get(node, [])
        if not next_nodes:
            paths.append(path)
            return
        for child in next_nodes:
            if child in path:
                paths.append(path)
                continue
            _walk(child, path + [child])

    for root in roots:
        _walk(root, [root])
    unique: list[list[str]] = []
    seen: set[tuple[str, ...]] = set()
    for path in paths:
        key = tuple(path)
        if len(path) >= 2 and key not in seen:
            unique.append(path)
            seen.add(key)
    return unique


def _summarize_path_entries(
    agent_names: list[str],
    path_kind: str,
    entries_by_agent: dict[str, list[CostYieldEntry]],
) -> CostYieldPathSummary | None:
    """Aggregate agent-level cost-yield entries into a path-level summary."""
    path_entries: list[CostYieldEntry] = []
    filtered_agents: list[str] = []
    for agent in agent_names:
        matches = entries_by_agent.get(agent, [])
        if not matches:
            continue
        filtered_agents.append(agent)
        path_entries.extend(matches)
    if not path_entries or not filtered_agents:
        return None
    weights = [_entry_weight(entry) for entry in path_entries]
    total_weight = sum(weights) or float(len(path_entries))
    avg_yield = sum(entry.yield_score * weight for entry, weight in zip(path_entries, weights, strict=False)) / total_weight
    quality_entries = [(entry.quality_signal, weight) for entry, weight in zip(path_entries, weights, strict=False) if entry.quality_signal is not None]
    aggregate_quality = None
    if quality_entries:
        quality_weight = sum(weight for _signal, weight in quality_entries) or float(len(quality_entries))
        aggregate_quality = sum(signal * weight for signal, weight in quality_entries if signal is not None) / quality_weight
    claim_count = sum(entry.claim_count for entry in path_entries)
    citation_count = sum(entry.citation_count for entry in path_entries)
    return CostYieldPathSummary(
        path_kind=path_kind,
        agents=filtered_agents,
        total_cost_usd=sum(entry.cost_usd for entry in path_entries),
        total_tokens=sum(entry.tokens for entry in path_entries),
        avg_yield_score=avg_yield,
        min_yield_score=min(entry.yield_score for entry in path_entries),
        aggregate_quality_signal=aggregate_quality,
        contains_failure=any(entry.status == "failed" for entry in path_entries),
        grounding_issue_count=sum(entry.grounding_issue_count for entry in path_entries),
        claim_count=claim_count,
        citation_count=citation_count,
        unsupported_claim_count=sum(entry.unsupported_claim_count for entry in path_entries),
        missing_citation_count=sum(entry.missing_citation_count for entry in path_entries),
        unverified_claim_count=sum(entry.unverified_claim_count for entry in path_entries),
        removed_claim_count=sum(entry.removed_claim_count for entry in path_entries),
        citation_coverage=min(citation_count / claim_count, 1.0) if claim_count > 0 else None,
    )


def _compute_path_summaries(
    trace: ExecutionTrace,
    entries: list[CostYieldEntry],
) -> tuple[list[CostYieldPathSummary], CostYieldPathSummary | None, str]:
    """Summarize cost-yield across critical and handoff-derived paths."""
    if not entries:
        return [], None, ""
    flow = analyze_flow(trace)
    entries_by_agent: dict[str, list[CostYieldEntry]] = {}
    for entry in entries:
        entries_by_agent.setdefault(entry.agent, []).append(entry)

    summaries: list[CostYieldPathSummary] = []
    seen: set[tuple[str, ...]] = set()
    critical_summary = _summarize_path_entries(flow.critical_path, "critical_path", entries_by_agent)
    if critical_summary:
        summaries.append(critical_summary)
        seen.add(tuple(critical_summary.agents))
    for path in _build_handoff_paths(flow.handoffs):
        summary = _summarize_path_entries(path, "handoff_chain", entries_by_agent)
        if not summary:
            continue
        key = tuple(summary.agents)
        if key in seen:
            continue
        summaries.append(summary)
        seen.add(key)
    max_cost = max((summary.total_cost_usd for summary in summaries if summary.total_cost_usd > 0), default=0.0)
    max_tokens = max((summary.total_tokens for summary in summaries if summary.total_tokens > 0), default=0)
    for summary in summaries:
        if max_cost > 0:
            cost_factor = summary.total_cost_usd / max_cost
        else:
            cost_factor = summary.total_tokens / max(max_tokens, 1)
        summary.waste_score = round(cost_factor * ((100 - summary.avg_yield_score) / 100) * 100, 1)
    worst_path = ""
    if summaries:
        worst = max(summaries, key=lambda item: item.waste_score)
        worst_path = " → ".join(worst.agents)
    return summaries, critical_summary, worst_path


def _generate_cost_recommendations(
    entries: list[CostYieldEntry],
    leaf_names: set[str] | None = None,
) -> list[str]:
    """Generate actionable recommendations from cost-yield data.

    Each recommendation targets a specific inefficiency pattern
    with a concrete suggestion for improvement. ``leaf_names`` restricts
    generic "cost-per-success" advice to leaf agents; emitting that advice
    for a whole-session container (where cost-per-success is just
    total_cost/1) produces a tautological "this session cost $X/success"
    line that is not actionable.
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
        elif e.quality_signal is not None and e.quality_signal < 0.5 and e.cost_usd > 0:
            recs.append(
                f"'{e.agent}' reports weak quality signals ({e.quality_signal:.0%}: {e.quality_evidence}). "
                f"Tighten prompts, routing, or validation before spending more budget."
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
            # Only emit generic "consider batching" advice for leaf agents.
            # For a container/root that rolled up every subagent's cost,
            # cost-per-success is tautological and there is nothing to batch.
            if leaf_names is not None and e.agent not in leaf_names:
                continue
            recs.append(
                f"'{e.agent}' costs ${e.cost_per_success:.4f}/success. "
                f"Consider batching or using a smaller model."
            )
    return recs[:5]  # Cap at 5 recommendations


def _normalize_quality_value(value: Any) -> float | None:
    """Normalize common quality-style numeric values to 0-1."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if not isinstance(value, (int, float)):
        return None
    numeric = float(value)
    if numeric < 0:
        return 0.0
    if numeric <= 1.0:
        return numeric
    if numeric <= 100.0:
        return numeric / 100.0
    return 1.0


def _quality_label_signal(value: Any) -> float | None:
    """Map common qualitative labels to a normalized quality score."""
    if not isinstance(value, str):
        return None
    label = value.strip().lower()
    strong = {"pass": 0.95, "passed": 0.95, "success": 0.95, "ok": 0.9,
              "good": 0.85, "high": 0.85, "complete": 0.9, "completed": 0.9,
              "improved": 0.9}
    medium = {"medium": 0.6, "partial": 0.5, "warning": 0.45,
              "degraded": 0.35, "mixed": 0.5}
    weak = {"fail": 0.05, "failed": 0.05, "error": 0.0, "bad": 0.1,
            "poor": 0.1, "low": 0.2, "regressed": 0.1}
    if label in strong:
        return strong[label]
    if label in medium:
        return medium[label]
    return weak.get(label)


def _quality_candidates(data: dict[str, Any]) -> list[tuple[float, float, str]]:
    """Collect weighted explicit quality signals from a structured payload."""
    numeric_weights = {
        "quality": 1.0,
        "score": 0.9,
        "accuracy": 1.0,
        "completeness": 0.85,
        "confidence": 0.6,
        "relevance": 0.75,
        "coverage": 0.7,
        "pass_rate": 1.0,
        "rating": 0.7,
    }
    label_weights = {
        "verdict": 1.0,
        "status": 0.9,
        "quality": 1.0,
        "confidence": 0.5,
    }
    candidates: list[tuple[float, float, str]] = []
    for key, weight in numeric_weights.items():
        value = _normalize_quality_value(data.get(key))
        if value is not None:
            candidates.append((value, weight, key))
    for key, weight in label_weights.items():
        value = _quality_label_signal(data.get(key))
        if value is not None:
            candidates.append((value, weight, key))
    if "success" in data and isinstance(data["success"], bool):
        candidates.append((1.0 if data["success"] else 0.0, 1.0, "success"))
    return candidates


def _rule_pass_signal(data: dict[str, Any]) -> tuple[float, str] | None:
    """Extract a quality signal from EvaluationResult-like pass/fail counts."""
    passed = data.get("passed")
    total = data.get("total")
    if not isinstance(passed, (int, float)) or not isinstance(total, (int, float)):
        return None
    total_value = max(float(total), 1.0)
    pass_rate = max(0.0, min(float(passed) / total_value, 1.0))
    overall = _quality_label_signal(data.get("overall"))
    if overall is None:
        overall = _quality_label_signal(data.get("overall_verdict"))
    if overall is None:
        overall = pass_rate
    signal = (pass_rate * 0.75) + (overall * 0.25)
    return signal, "evaluation_rules"


def _rules_list_signal(data: dict[str, Any]) -> tuple[float, str] | None:
    """Extract a quality signal from a list of rule verdicts."""
    rules = data.get("rules")
    if not isinstance(rules, list) or not rules:
        return None
    passed = 0
    considered = 0
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        verdict = str(rule.get("verdict", "")).lower()
        if verdict in {"pass", "fail"}:
            considered += 1
            if verdict == "pass":
                passed += 1
    if considered == 0:
        return None
    return passed / considered, "rule_verdicts"


def _comparison_signal(data: dict[str, Any]) -> tuple[float, str] | None:
    """Extract a quality signal from replay/comparison-style outputs."""
    verdict = _quality_label_signal(data.get("verdict"))
    regressed = data.get("regressed")
    improved = data.get("improved")
    recommendation = _quality_label_signal(data.get("recommendation"))
    candidates: list[float] = []
    if verdict is not None:
        candidates.append(verdict)
    if isinstance(regressed, (int, float)) and isinstance(improved, (int, float)):
        total = max(float(regressed) + float(improved), 1.0)
        balance = max(0.0, min((float(improved) + 1.0) / (total + 1.0), 1.0))
        candidates.append(balance)
    if recommendation is not None:
        candidates.append(recommendation)
    if not candidates:
        return None
    return sum(candidates) / len(candidates), "comparison_result"


def _count_items(value: Any) -> int:
    """Count list-like or numeric quantities used in grounding heuristics."""
    if isinstance(value, (list, tuple, set, dict)):
        return len(value)
    if isinstance(value, (int, float)):
        return max(int(value), 0)
    return 0


def _grounding_breakdown(data: dict[str, Any]) -> dict[str, int | float | None]:
    """Collect grounding and citation integrity counts from a structured payload."""
    claims = _count_items(data.get("claims"))
    verified = _count_items(data.get("verified_claims"))
    unsupported = _count_items(data.get("unsupported_claims"))
    unverified = _count_items(data.get("unverified_claims"))
    missing_citations = _count_items(data.get("missing_citation_ids"))
    removed_claims = _count_items(data.get("removed_claim_count"))
    citations = _count_items(data.get("citations"))
    claim_count = max(claims, verified + unsupported + unverified + removed_claims)
    citation_coverage = None
    if claim_count > 0:
        citation_coverage = min(citations / claim_count, 1.0)
    return {
        "claim_count": claim_count,
        "citation_count": citations,
        "unsupported_claim_count": unsupported,
        "missing_citation_count": missing_citations,
        "unverified_claim_count": unverified,
        "removed_claim_count": removed_claims,
        "grounding_issue_count": unsupported + missing_citations + unverified + removed_claims,
        "citation_coverage": citation_coverage,
    }


def _grounding_signal(data: dict[str, Any]) -> tuple[float, str] | None:
    """Extract a quality signal from evidence grounding and citation integrity."""
    breakdown = _grounding_breakdown(data)
    claims = int(breakdown["claim_count"] or 0)
    verified = _count_items(data.get("verified_claims"))
    unsupported = int(breakdown["unsupported_claim_count"] or 0) + int(breakdown["unverified_claim_count"] or 0)
    missing_citations = int(breakdown["missing_citation_count"] or 0)
    removed_claims = int(breakdown["removed_claim_count"] or 0)
    citations = int(breakdown["citation_count"] or 0)
    if not any([claims, verified, unsupported, missing_citations, removed_claims, citations]):
        return None
    total_claims = max(claims, verified + unsupported + removed_claims, 1)
    support_ratio = min(citations / max(claims, 1), 1.0) if claims else 1.0
    verified_ratio = min(verified / total_claims, 1.0) if verified else max(0.0, 1.0 - (unsupported / total_claims))
    citation_ratio = 1.0 - min(missing_citations / total_claims, 1.0)
    unsupported_ratio = min((unsupported + removed_claims) / total_claims, 1.0)
    signal = (support_ratio * 0.35) + (verified_ratio * 0.45) + (citation_ratio * 0.2)
    signal = max(0.0, min(signal - (unsupported_ratio * 0.25), 1.0))
    return signal, "grounding_integrity"


def _nested_quality_candidates(data: dict[str, Any]) -> list[tuple[float, float, str]]:
    """Collect quality signals from nested evaluation/replay structures."""
    nested_keys = ["evaluation", "eval", "comparison", "replay", "baseline", "candidate"]
    candidates: list[tuple[float, float, str]] = []
    sources: list[tuple[tuple[float, str] | None, float]] = [
        (_rule_pass_signal(data), 1.0),
        (_rules_list_signal(data), 0.9),
        (_comparison_signal(data), 1.0),
        (_grounding_signal(data), 1.0),
    ]
    for result, weight in sources:
        if result is not None:
            value, source = result
            candidates.append((value, weight, source))
    for key in nested_keys:
        nested = data.get(key)
        if not isinstance(nested, dict):
            continue
        for result, weight in [
            (_rule_pass_signal(nested), 1.0),
            (_rules_list_signal(nested), 0.9),
            (_comparison_signal(nested), 1.0),
            (_grounding_signal(nested), 1.0),
        ]:
            if result is None:
                continue
            value, source = result
            candidates.append((value, weight, f"{key}.{source}"))
    return candidates


def _extract_quality_signal(output_data: Any, metadata: dict[str, Any]) -> tuple[float | None, str]:
    """Extract an explicit quality signal from output or metadata when available."""
    candidates: list[tuple[float, float, str]] = []
    if isinstance(output_data, dict):
        candidates.extend(_quality_candidates(output_data))
        candidates.extend(_nested_quality_candidates(output_data))
    if metadata:
        prefixed = {str(k).split(".")[-1]: v for k, v in metadata.items() if isinstance(k, str)}
        candidates.extend(_quality_candidates(prefixed))
        candidates.extend(_nested_quality_candidates(prefixed))
    if not candidates:
        return None, ""
    weighted_sum = sum(value * weight for value, weight, _source in candidates)
    total_weight = sum(weight for _value, weight, _source in candidates)
    sources = ", ".join(sorted({source for _value, _weight, source in candidates}))
    return weighted_sum / max(total_weight, 1e-9), sources


def _default_yield_score(
    succeeded: bool,
    has_output: bool,
    output_size: int,
    output_data: Any,
    metadata: dict[str, Any],
) -> tuple[float, float | None, str]:
    """Default yield scoring: explicit quality first, size heuristics second."""
    if not succeeded:
        return 0.0, None, ""
    quality_signal, evidence = _extract_quality_signal(output_data, metadata)
    if quality_signal is not None:
        score = 15.0
        if has_output:
            score += 10.0
        score += quality_signal * 70.0
        if output_size > 1000:
            score += 5.0
        return min(score, 100.0), quality_signal, evidence
    score = 0.0
    if succeeded:
        score += 50
    if has_output:
        score += 30
    if output_size > 100:
        score += 10
    if output_size > 1000:
        score += 10
    return score, None, ""


def _compute_agent_costs(
    trace: ExecutionTrace,
    cost_fn: Callable | None,
    yield_fn: Callable | None,
) -> list[CostYieldEntry]:
    """Compute cost and yield entries for each agent span.

    For each agent computes cost (custom or estimated_cost_usd),
    yield score (custom or default), cost-per-success, and token efficiency.

    Cost and tokens are rolled up across the agent's subtree when the agent
    span itself carries none — real runtimes (Claude, LangGraph, …) tend to
    charge cost on the leaf LLM calls, not on the orchestrating agent span.
    Without the roll-up the cost-yield panel reports $0 for every agent and
    destroys the credibility of Q3.
    """
    import json as _json

    children_map = _build_children_span_map(trace)

    def _subtree_cost_tokens(root: Span) -> tuple[float, int]:
        """Sum estimated_cost_usd and token_count across ``root``'s subtree."""
        stack = [root]
        cost = 0.0
        tokens = 0
        visited: set[str] = set()
        while stack:
            span = stack.pop()
            if span.span_id in visited:
                continue
            visited.add(span.span_id)
            cost += float(span.estimated_cost_usd or 0.0)
            tokens += int(span.token_count or 0)
            for child in children_map.get(span.span_id, []):
                if child.span_id not in visited:
                    stack.append(child)
        return cost, tokens

    entries = []
    for s in trace.agent_spans:
        direct_cost = (cost_fn(s) if cost_fn else s.estimated_cost_usd) or 0.0
        direct_tokens = s.token_count or 0
        if direct_cost > 0 or direct_tokens > 0 or cost_fn:
            cost = direct_cost
            tokens = direct_tokens
        else:
            # Agent span carries no cost itself (the common Claude case).
            # Roll up from descendants so Q3 numbers match reality.
            cost, tokens = _subtree_cost_tokens(s)
        dur = s.duration_ms or 0.0
        succeeded = s.status == SpanStatus.COMPLETED
        has_output = s.output_data is not None
        output_size = _measure_output_size(s.output_data, _json)
        grounding = _grounding_breakdown(s.output_data) if isinstance(s.output_data, dict) else _grounding_breakdown({})
        quality_signal = None
        quality_evidence = ""
        if yield_fn:
            yield_score = yield_fn(s)
        else:
            yield_score, quality_signal, quality_evidence = _default_yield_score(
                succeeded,
                has_output,
                output_size,
                s.output_data,
                s.metadata,
            )
        cost_per_success = cost if succeeded and cost > 0 else (float("inf") if not succeeded else 0.0)
        entries.append(CostYieldEntry(
            agent=s.name, tokens=tokens, cost_usd=cost,
            status=s.status.value, duration_ms=dur,
            has_output=has_output, output_size_bytes=output_size,
            cost_per_success=cost_per_success,
            tokens_per_ms=tokens / max(dur, 1),
            yield_score=yield_score,
            quality_signal=quality_signal,
            quality_evidence=quality_evidence,
            span_id=s.span_id,
            grounding_issue_count=int(grounding["grounding_issue_count"] or 0),
            claim_count=int(grounding["claim_count"] or 0),
            citation_count=int(grounding["citation_count"] or 0),
            unsupported_claim_count=int(grounding["unsupported_claim_count"] or 0),
            missing_citation_count=int(grounding["missing_citation_count"] or 0),
            unverified_claim_count=int(grounding["unverified_claim_count"] or 0),
            removed_claim_count=int(grounding["removed_claim_count"] or 0),
            citation_coverage=grounding["citation_coverage"],
        ))
    return entries


def _measure_output_size(output_data: Any, json_mod: Any) -> int:
    """Measure serialized output size in bytes. Returns 0 on failure."""
    if output_data is None:
        return 0
    try:
        return len(json_mod.dumps(output_data, default=str).encode("utf-8"))
    except Exception:
        return 0


def _compute_yield_scores(
    entries: list[CostYieldEntry],
    leaf_names: set[str] | None = None,
) -> dict[str, str]:
    """Compute summary yield scores: highest cost, lowest yield, best ratio agents.

    When ``leaf_names`` is provided, "highest cost" prefers agents that
    are leaves (no child agents). The root container of a deeply-nested
    trace naturally has the highest rolled-up cost, but reporting
    "the whole session is the most expensive agent" is tautological —
    the user wants the leaf that actually burned the tokens.

    Returns dict with keys: highest_cost, lowest_yield, best_ratio.
    """
    if not entries:
        return {"highest_cost": "N/A", "lowest_yield": "N/A", "best_ratio": "N/A"}
    candidates = entries
    if leaf_names:
        leaf_entries = [e for e in entries if e.agent in leaf_names]
        if leaf_entries:
            candidates = leaf_entries
    return {
        "highest_cost": max(candidates, key=lambda e: e.cost_usd).agent,
        "lowest_yield": min(candidates, key=lambda e: e.yield_score).agent,
        "best_ratio": max(candidates, key=lambda e: e.yield_score / max(e.cost_usd, 0.0001)).agent,
    }


def analyze_cost_yield(
    trace: ExecutionTrace,
    cost_fn: Callable | None = None,
    yield_fn: Callable | None = None,
) -> CostYieldReport:
    """Compare cost per agent vs output quality.

    Answers Q4: "Which execution path has the highest cost but worst yield?"

    Args:
        trace: The execution trace to analyze.
        cost_fn: Optional custom cost function (span) -> float.
        yield_fn: Optional custom yield function (span) -> float (0-100).

    Returns:
        CostYieldReport with per-agent breakdown and summary.
    """
    entries = _compute_agent_costs(trace, cost_fn, yield_fn)
    # Identify leaf agents (no agent descendants) so summary metrics
    # don't just report "the root is most expensive" tautologies when
    # cost rolls up.
    agent_ids = {s.span_id for s in trace.agent_spans}
    children_map = _build_children_span_map(trace)
    leaf_names: set[str] = set()
    for s in trace.agent_spans:
        has_agent_descendant = False
        stack = list(children_map.get(s.span_id, []))
        while stack:
            c = stack.pop()
            if c.span_id in agent_ids:
                has_agent_descendant = True
                break
            stack.extend(children_map.get(c.span_id, []))
        if not has_agent_descendant:
            leaf_names.add(s.name)
    scores = _compute_yield_scores(entries, leaf_names=leaf_names)
    wasteful, waste_score = _find_most_wasteful(entries, leaf_names=leaf_names)
    recommendations = _generate_cost_recommendations(entries, leaf_names=leaf_names)
    path_summaries, critical_path_summary, worst_path = _compute_path_summaries(trace, entries)

    # Total cost: when a custom cost_fn is supplied, its entries are the
    # authoritative values — sum the leaf entries (or all entries if no
    # leaves) to avoid double-counting rolled-up costs. When no cost_fn
    # is supplied, sum direct estimated_cost_usd over every span to get
    # the real total without double-counting the roll-up.
    if cost_fn is not None:
        if leaf_names:
            total_cost = sum(e.cost_usd for e in entries if e.agent in leaf_names)
        else:
            total_cost = sum(e.cost_usd for e in entries)
        if leaf_names:
            total_tokens = sum(e.tokens for e in entries if e.agent in leaf_names)
        else:
            total_tokens = sum(e.tokens for e in entries)
    else:
        total_cost = sum(float(s.estimated_cost_usd or 0.0) for s in trace.spans)
        total_tokens = sum(int(s.token_count or 0) for s in trace.spans)

    return CostYieldReport(
        entries=entries,
        total_cost_usd=total_cost,
        total_tokens=total_tokens,
        highest_cost_agent=scores["highest_cost"],
        lowest_yield_agent=scores["lowest_yield"],
        best_ratio_agent=scores["best_ratio"],
        most_wasteful_agent=wasteful,
        waste_score=waste_score,
        recommendations=recommendations,
        path_summaries=path_summaries,
        critical_path_summary=critical_path_summary,
        worst_path=worst_path,
    )



@dataclass
class DecisionRecord:
    """A single orchestration decision and its downstream outcome."""
    coordinator: str
    chosen_agent: str
    alternatives: list[str]
    rationale: str
    criteria: dict
    confidence: float | None
    downstream_status: str  # "completed", "failed", etc.
    downstream_duration_ms: float | None
    led_to_failure: bool  # True if chosen agent (or its children) failed
    led_to_degradation: bool = False
    failure_source: str = ""
    bottleneck_span: str = ""
    context_loss_handoffs: list[str] = field(default_factory=list)
    degradation_signals: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
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
            "led_to_degradation": self.led_to_degradation,
            "failure_source": self.failure_source,
            "bottleneck_span": self.bottleneck_span,
            "context_loss_handoffs": self.context_loss_handoffs,
            "degradation_signals": self.degradation_signals,
        }


@dataclass
class DecisionAnalysis:
    """Analysis of all orchestration decisions in a trace."""
    decisions: list[DecisionRecord]
    total_decisions: int
    decisions_leading_to_failure: int
    decisions_with_degradation: int
    decision_quality_score: float  # 0-1: fraction of decisions with good outcomes
    suggestions: list[dict] = field(default_factory=list)  # optimal agent recommendations

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "total_decisions": self.total_decisions,
            "decisions_leading_to_failure": self.decisions_leading_to_failure,
            "decisions_with_degradation": self.decisions_with_degradation,
            "decision_quality_score": round(self.decision_quality_score, 2),
            "decisions": [d.to_dict() for d in self.decisions],
            "suggestions": self.suggestions,
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
        lines = [
            "# Orchestration Decision Analysis", "",
            f"Total decisions: {self.total_decisions}",
            f"Led to failure: {self.decisions_leading_to_failure}",
            f"Showed degradation: {self.decisions_with_degradation}",
            f"Decision quality: {self.decision_quality_score:.0%}", "",
        ]
        for d in self.decisions:
            icon = "\u2717" if d.led_to_degradation else "\u2713"
            alts = ", ".join(d.alternatives) if d.alternatives else "none"
            lines.append(f"{icon} **{d.coordinator}** chose **{d.chosen_agent}** over [{alts}]")
            if d.rationale:
                lines.append(f"  Rationale: {d.rationale}")
            lines.append(f"  Outcome: {d.downstream_status}"
                         f"{f' ({d.downstream_duration_ms:.0f}ms)' if d.downstream_duration_ms else ''}")
            for signal in d.degradation_signals:
                lines.append(f"  Signal: {signal}")
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
        """Serialize to dictionary."""
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

    Args:
        trace: The execution trace to analyze.

    Returns:
        List of BadDecision records for orchestration choices that repeat failures.
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


def _collect_subtree_ids(
    root_span_id: str,
    children_map: dict[str, list[Span]],
) -> set[str]:
    """Collect a span subtree, including the root span id."""
    subtree_ids = {root_span_id}
    stack = [root_span_id]
    while stack:
        current = stack.pop()
        for child in children_map.get(current, []):
            if child.span_id not in subtree_ids:
                subtree_ids.add(child.span_id)
                stack.append(child.span_id)
    return subtree_ids


def _span_sort_key(span: Span) -> tuple[str, str, str]:
    """Provide a stable ordering key for spans."""
    return (span.started_at or "", span.ended_at or "", span.span_id)


def _resolve_chosen_agent_span(
    ds: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> Span | None:
    """Resolve the agent span selected by a decision within the local subtree."""
    chosen = ds.metadata.get("decision.chosen", "")
    if not chosen:
        return None
    candidates = [
        span for span in trace.agent_spans
        if span.name == chosen
    ]
    if ds.parent_span_id:
        local_ids = _collect_subtree_ids(ds.parent_span_id, children_map)
        local = [span for span in candidates if span.span_id in local_ids]
        if local:
            candidates = local
    candidates.sort(key=_span_sort_key)
    return candidates[0] if candidates else None


def _find_failed_descendant(
    root_span: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> Span | None:
    """Return the earliest failed span inside a chosen agent subtree."""
    subtree_ids = _collect_subtree_ids(root_span.span_id, children_map)
    failures = [
        span for span in trace.spans
        if span.span_id in subtree_ids and span.status == SpanStatus.FAILED
    ]
    failures.sort(key=_span_sort_key)
    return failures[0] if failures else None


def _subtree_agent_names(
    root_span: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
) -> set[str]:
    """Collect agent names within a chosen agent subtree."""
    subtree_ids = _collect_subtree_ids(root_span.span_id, children_map)
    return {
        span.name for span in trace.agent_spans
        if span.span_id in subtree_ids
    }


def _context_losses_for_agents(
    agent_names: set[str],
    context_report: ContextFlowReport,
) -> list[str]:
    """Return handoffs with context degradation inside a chosen subtree."""
    handoffs = []
    for point in context_report.anomalies:
        if point.anomaly not in {"loss", "truncation"}:
            continue
        if point.from_agent in agent_names or point.to_agent in agent_names:
            handoffs.append(f"{point.from_agent} → {point.to_agent}")
    return handoffs


def _decision_degradation_signals(
    failure_source: str,
    bottleneck_span: str,
    context_losses: list[str],
) -> list[str]:
    """Summarize concrete degradation evidence for a decision."""
    signals = []
    if failure_source:
        signals.append(f"Failure propagated to {failure_source}")
    if context_losses:
        signals.append(f"Context loss on {context_losses[0]}")
    if bottleneck_span and signals:
        signals.append(f"Critical path bottleneck at {bottleneck_span}")
    return signals


def _decision_span_to_record(
    ds: Span,
    trace: ExecutionTrace,
    children_map: dict[str, list[Span]],
    bottleneck: BottleneckReport,
    context_report: ContextFlowReport,
) -> DecisionRecord:
    """Convert a decision span into a DecisionRecord with downstream outcome."""
    chosen = ds.metadata.get("decision.chosen", "")
    agent = _resolve_chosen_agent_span(ds, trace, children_map)

    if agent is not None:
        led_to_failure = (
            agent.status == SpanStatus.FAILED
            or _has_descendant_failure(agent.span_id, children_map)
        )
        failure_source = ""
        failed_span = _find_failed_descendant(agent, trace, children_map)
        if failed_span is not None:
            failure_source = failed_span.name
        agent_names = _subtree_agent_names(agent, trace, children_map)
        bottleneck_span = ""
        if bottleneck.bottleneck_span in agent_names or bottleneck.bottleneck_agent in agent_names:
            bottleneck_span = bottleneck.bottleneck_span
        context_losses = _context_losses_for_agents(agent_names, context_report)
        degradation_signals = _decision_degradation_signals(
            failure_source,
            bottleneck_span,
            context_losses,
        )
        downstream_status = agent.status.value
        downstream_dur = agent.duration_ms
    else:
        downstream_status = "unknown"
        downstream_dur = None
        led_to_failure = False
        failure_source = ""
        bottleneck_span = ""
        context_losses = []
        degradation_signals = []

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
        led_to_degradation=bool(degradation_signals),
        failure_source=failure_source,
        bottleneck_span=bottleneck_span,
        context_loss_handoffs=context_losses,
        degradation_signals=degradation_signals,
    )


def _suggest_optimal_agents(
    decisions: list[DecisionRecord],
    trace: ExecutionTrace,
) -> list[dict]:
    """Suggest optimal agent selection based on historical performance in trace.

    Builds a performance profile for each agent seen in decisions,
    then suggests the best alternative when a decision led to failure.

    Returns:
        List of suggestion dicts with 'decision_index', 'current_agent',
        'suggested_agent', and 'reason'.
    """
    profiles = _build_agent_profiles_from_decisions(decisions, trace)
    suggestions: list[dict] = []
    for i, d in enumerate(decisions):
        if not d.led_to_failure:
            continue
        best = _find_best_alternative(d, profiles)
        if best:
            suggestions.append({
                "decision_index": i,
                "current_agent": d.chosen_agent,
                "suggested_agent": best["agent"],
                "reason": best["reason"],
            })
    return suggestions


def _build_agent_profiles_from_decisions(
    decisions: list, trace,
) -> dict[str, dict]:
    """Build performance profiles for agents seen in decisions."""
    from agentguard.core.trace import SpanStatus
    profiles: dict[str, dict] = {}
    for s in trace.agent_spans:
        name = s.name
        if name not in profiles:
            profiles[name] = {
                "total": 0, "succeeded": 0, "total_ms": 0.0,
                "avg_ms": 0.0, "success_rate": 0.0,
            }
        p = profiles[name]
        p["total"] += 1
        if s.status == SpanStatus.COMPLETED:
            p["succeeded"] += 1
        p["total_ms"] += s.duration_ms or 0
    for p in profiles.values():
        p["avg_ms"] = p["total_ms"] / max(p["total"], 1)
        p["success_rate"] = p["succeeded"] / max(p["total"], 1)
    return profiles


def _find_best_alternative(
    decision: DecisionRecord, profiles: dict[str, dict],
) -> dict | None:
    """Find the best alternative agent for a failed decision."""
    candidates = []
    for alt in decision.alternatives:
        if alt in profiles and profiles[alt]["success_rate"] > 0:
            candidates.append((alt, profiles[alt]))
    if not candidates:
        return None
    best_name, best_prof = max(candidates, key=lambda x: x[1]["success_rate"])
    current_prof = profiles.get(decision.chosen_agent, {})
    current_rate = current_prof.get("success_rate", 0)
    return {
        "agent": best_name,
        "reason": (
            f"{best_name} has {best_prof['success_rate']:.0%} success rate "
            f"({best_prof['avg_ms']:.0f}ms avg) vs "
            f"{decision.chosen_agent} at {current_rate:.0%}"
        ),
    }


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

    bottleneck = analyze_bottleneck(trace)
    context_report = analyze_context_flow(trace)

    records = [
        _decision_span_to_record(ds, trace, children_map, bottleneck, context_report)
        for ds in decision_spans
    ]

    total = len(records)
    failures = sum(1 for r in records if r.led_to_failure)
    degradations = sum(1 for r in records if r.led_to_degradation)
    quality = 1.0 if total == 0 else (total - degradations) / total
    suggestions = _suggest_optimal_agents(records, trace)

    return DecisionAnalysis(
        decisions=records,
        total_decisions=total,
        decisions_leading_to_failure=failures,
        decisions_with_degradation=degradations,
        decision_quality_score=quality,
        suggestions=suggestions,
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
        """Serialize to dictionary."""
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
        """Serialize to dictionary."""
        return {
            "total_spans_checked": self.total_spans_checked,
            "anomaly_count": self.anomaly_count,
            "anomalies": [a.to_dict() for a in self.anomalies],
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
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
    baseline: dict[str, float] | None = None,
    reference_traces: list[ExecutionTrace] | None = None,
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

    Args:
        trace: The execution trace to analyze.

    Returns:
        TimingAnalysis with gap detection, overlap analysis, and scheduling insights.
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
        except Exception:
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
    chosen_duration_ms: float | None
    best_alternative: str | None
    best_alt_status: str | None
    best_alt_duration_ms: float | None
    regret_ms: float | None  # chosen_duration - best_alt_duration (positive = regret)
    chosen_failed: bool
    best_alt_failed: bool
    verdict: str  # "optimal", "suboptimal", "catastrophic", "no_alternatives"
    chosen_degraded: bool = False
    best_alt_success_rate: float | None = None
    evidence_source: str = "none"
    evidence_runs: int = 0
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
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
            "chosen_degraded": self.chosen_degraded,
            "best_alt_success_rate": round(self.best_alt_success_rate, 2) if self.best_alt_success_rate is not None else None,
            "evidence_source": self.evidence_source,
            "evidence_runs": self.evidence_runs,
            "rationale": self.rationale,
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
        """Serialize to dictionary."""
        return {
            "total_decisions": self.total_decisions,
            "optimal": self.optimal_count,
            "suboptimal": self.suboptimal_count,
            "catastrophic": self.catastrophic_count,
            "total_regret_ms": round(self.total_regret_ms, 1),
            "results": [r.to_dict() for r in self.results],
        }

    def to_report(self) -> str:
        """Format as human-readable report string."""
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
            if r.evidence_runs:
                lines.append(f"  Evidence: {r.evidence_source}, {r.evidence_runs} observed run(s)")
            if r.regret_ms and r.regret_ms > 0:
                lines.append(f"  Regret: +{r.regret_ms:.0f}ms")
            if r.rationale:
                lines.append(f"  Why: {r.rationale}")
            lines.append("")
        return "\n".join(lines)


def _verdict_icon(verdict: str) -> str:
    """Map verdict to display icon."""
    return {"optimal": "\u2705", "suboptimal": "\u26a0\ufe0f",
            "catastrophic": "\u274c", "no_alternatives": "\u2796"}.get(verdict, "?")


def _build_agent_outcome_profiles(trace: ExecutionTrace) -> dict[str, dict[str, float | int | str]]:
    """Build representative agent profiles from observed runs.

    Counterfactual analysis should compare against representative performance,
    not a single lucky fastest run. Profiles aggregate observed success and
    duration across agent runs in the trace.
    """
    profiles: dict[str, dict[str, float | int | str]] = {}
    for span in trace.agent_spans:
        profile = profiles.setdefault(
            span.name,
            {
                "runs": 0,
                "completed_runs": 0,
                "failed_runs": 0,
                "total_duration_ms": 0.0,
                "completed_duration_ms": 0.0,
                "success_rate": 0.0,
                "avg_duration_ms": 0.0,
                "avg_completed_duration_ms": 0.0,
            },
        )
        profile["runs"] += 1
        profile["total_duration_ms"] += span.duration_ms or 0.0
        if span.status == SpanStatus.COMPLETED:
            profile["completed_runs"] += 1
            profile["completed_duration_ms"] += span.duration_ms or 0.0
        elif span.status == SpanStatus.FAILED:
            profile["failed_runs"] += 1

    for profile in profiles.values():
        runs = int(profile["runs"])
        completed_runs = int(profile["completed_runs"])
        profile["success_rate"] = completed_runs / max(runs, 1)
        profile["avg_duration_ms"] = float(profile["total_duration_ms"]) / max(runs, 1)
        if completed_runs:
            profile["avg_completed_duration_ms"] = (
                float(profile["completed_duration_ms"]) / completed_runs
            )
    return profiles


def _profile_to_candidate(
    agent_name: str,
    profiles: dict[str, dict[str, float | int | str]],
    historical_stats: dict[str, dict] | None = None,
) -> dict[str, Any] | None:
    """Resolve an alternative agent into a comparable candidate profile."""
    if agent_name in profiles:
        profile = profiles[agent_name]
        duration = profile.get("avg_completed_duration_ms") or profile.get("avg_duration_ms")
        return {
            "agent": agent_name,
            "status": "completed" if profile.get("completed_runs", 0) else "failed",
            "duration_ms": duration,
            "failed": profile.get("completed_runs", 0) == 0,
            "success_rate": float(profile.get("success_rate", 0.0)),
            "runs": int(profile.get("runs", 0)),
            "source": "in_trace",
        }
    if historical_stats and agent_name in historical_stats:
        profile = historical_stats[agent_name]
        duration = profile.get("avg_completed_duration_ms") or profile.get("avg_duration_ms")
        success_rate = float(profile.get("success_rate", 0.0))
        return {
            "agent": agent_name,
            "status": "completed" if success_rate >= 0.5 else "failed",
            "duration_ms": duration,
            "failed": success_rate < 0.5,
            "success_rate": success_rate,
            "runs": int(profile.get("runs", 0)),
            "source": "historical",
        }
    return None


def _candidate_key(candidate: dict[str, Any]) -> tuple[int, float, float, int]:
    """Rank alternatives by reliability first, then latency, then evidence depth."""
    duration = float(candidate["duration_ms"]) if candidate["duration_ms"] is not None else float("inf")
    return (
        0 if candidate["failed"] else 1,
        float(candidate["success_rate"]),
        -duration,
        int(candidate["runs"]),
    )


def _meaningful_regret(
    chosen_dur: float | None,
    best_alt_dur: float | None,
) -> bool:
    """Ignore tiny latency differences to avoid noisy suboptimal verdicts."""
    if chosen_dur is None or best_alt_dur is None:
        return False
    delta = chosen_dur - best_alt_dur
    if delta <= 0:
        return False
    return delta >= 50 and delta / max(chosen_dur, 1) >= 0.1


def _counterfactual_rationale(
    chosen_agent: str,
    chosen_degraded: bool,
    best_candidate: dict[str, Any] | None,
    regret: float | None,
) -> str:
    """Generate a concise explanation for the counterfactual verdict."""
    if best_candidate is None:
        return "No alternative agent executed, so no counterfactual comparison is possible."
    parts = [
        f"{best_candidate['agent']} showed {best_candidate['success_rate']:.0%} success over {best_candidate['runs']} run(s)"
    ]
    if best_candidate["duration_ms"] is not None:
        parts.append(f"with {best_candidate['duration_ms']:.0f}ms representative latency")
    if chosen_degraded:
        parts.append(f"while {chosen_agent} showed downstream degradation")
    elif regret is not None and regret > 0:
        parts.append(f"saving about {regret:.0f}ms")
    return "; ".join(parts) + "."


def _evaluate_single_decision(
    decision: DecisionRecord,
    trace: ExecutionTrace,
    historical_stats: dict[str, dict] | None = None,
) -> CounterfactualResult:
    """Compare one decision's chosen agent against its alternatives.

    Uses in-trace performance first. Falls back to historical_stats
    for alternatives that never ran in this trace.
    """
    chosen_dur = decision.downstream_duration_ms
    chosen_failed = decision.led_to_failure
    chosen_status = decision.downstream_status
    chosen_degraded = decision.led_to_degradation
    profiles = _build_agent_outcome_profiles(trace)

    best_candidate: dict[str, Any] | None = None

    for alt_name in decision.alternatives:
        candidate = _profile_to_candidate(alt_name, profiles, historical_stats)
        if candidate is None:
            continue
        if best_candidate is None or _candidate_key(candidate) > _candidate_key(best_candidate):
            best_candidate = candidate

    best_alt = best_candidate["agent"] if best_candidate else None
    best_alt_status = best_candidate["status"] if best_candidate else None
    best_alt_dur = best_candidate["duration_ms"] if best_candidate else None
    best_alt_failed = bool(best_candidate["failed"]) if best_candidate else True
    regret = _compute_regret(chosen_dur, best_alt_dur)
    meaningful_regret = _meaningful_regret(chosen_dur, best_alt_dur)
    verdict = _determine_verdict(
        chosen_failed, chosen_degraded, best_alt, best_alt_failed, meaningful_regret
    )
    rationale = _counterfactual_rationale(
        decision.chosen_agent,
        chosen_degraded,
        best_candidate,
        regret,
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
        chosen_degraded=chosen_degraded,
        best_alt_success_rate=(best_candidate["success_rate"] if best_candidate else None),
        evidence_source=(best_candidate["source"] if best_candidate else "none"),
        evidence_runs=(best_candidate["runs"] if best_candidate else 0),
        rationale=rationale,
        verdict=verdict,
    )


def _compute_regret(
    chosen_dur: float | None, best_alt_dur: float | None
) -> float | None:
    """Compute time regret (positive = chose slower path)."""
    if chosen_dur is not None and best_alt_dur is not None:
        return chosen_dur - best_alt_dur
    return None


def _determine_verdict(
    chosen_failed: bool,
    chosen_degraded: bool,
    best_alt: str | None,
    best_alt_failed: bool,
    meaningful_regret: bool,
) -> str:
    """Classify decision quality."""
    if best_alt is None:
        return "no_alternatives"
    if chosen_failed and not best_alt_failed:
        return "catastrophic"
    if chosen_degraded and not best_alt_failed:
        return "suboptimal"
    if meaningful_regret:
        return "suboptimal"
    return "optimal"


def analyze_counterfactual(trace: ExecutionTrace) -> CounterfactualAnalysis:
    """Compare actual decisions against best alternative paths.

    For each orchestration decision, finds the best alternative that
    actually ran in the trace and compares outcomes. This answers Q5:
    'Was the orchestrator's decision optimal?'

    Limitations: can only compare against alternatives that ran.
    Alternatives that never executed get no counterfactual score.

    Args:
        trace: The execution trace to analyze.

    Returns:
        CounterfactualAnalysis with what-if scenarios and estimated impact.
    """
    da = analyze_decisions(trace)
    historical_stats = _build_agent_outcome_profiles(trace)
    results = [_evaluate_single_decision(d, trace, historical_stats) for d in da.decisions]

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
