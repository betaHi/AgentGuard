"""Failure propagation analysis — causal chains, blast radius, and failure graphs.

Goes beyond simple root-cause detection to model how failures spread
through a multi-agent execution graph, answering:
- What's the full causal chain from root to leaf?
- What's the blast radius (direct + transitive impact)?
- Which spans acted as circuit breakers (caught and contained failures)?
- What would happen if a specific span failed? (hypothetical analysis)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


@dataclass
class CausalLink:
    """A link in a failure's causal chain."""
    from_span_id: str
    from_span_name: str
    to_span_id: str
    to_span_name: str
    relationship: str  # "parent_failure", "dependency_failure", "cascade"
    confidence: float = 1.0  # 0.0–1.0: certainty this link is causal

    def to_dict(self) -> dict:
        return {
            "from_id": self.from_span_id, "from_name": self.from_span_name,
            "to_id": self.to_span_id, "to_name": self.to_span_name,
            "relationship": self.relationship,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class CausalChain:
    """Complete causal chain for a single root cause failure."""
    root_span_id: str
    root_span_name: str
    root_error: str
    links: list[CausalLink] = field(default_factory=list)
    affected_span_ids: list[str] = field(default_factory=list)
    depth: int = 0  # how many levels deep the failure propagated
    contained: bool = False  # was it contained by a circuit breaker
    contained_by: str | None = None  # span_id that contained it
    severity: str = "unknown"  # "recoverable" or "fatal"
    severity_reason: str = ""  # why this classification

    @property
    def chain_confidence(self) -> float:
        """Overall chain confidence — product of all link confidences.

        Returns 1.0 for chains with no links (root cause only).
        Multiply because each weak link reduces total certainty.
        """
        if not self.links:
            return 1.0
        result = 1.0
        for link in self.links:
            result *= link.confidence
        return result

    def to_dict(self) -> dict:
        return {
            "root_span_id": self.root_span_id,
            "root_span_name": self.root_span_name,
            "root_error": self.root_error,
            "links": [l.to_dict() for l in self.links],
            "affected_count": len(self.affected_span_ids),
            "depth": self.depth,
            "contained": self.contained,
            "contained_by": self.contained_by,
            "chain_confidence": round(self.chain_confidence, 3),
            "severity": self.severity,
            "severity_reason": self.severity_reason,
        }


@dataclass
class PropagationAnalysis:
    """Full failure propagation analysis for a trace."""
    causal_chains: list[CausalChain]
    circuit_breakers: list[dict]  # spans that contained failures
    total_failures: int
    total_affected: int  # unique spans affected by any failure chain
    max_depth: int  # deepest failure chain
    containment_rate: float  # fraction of root causes that were contained

    def to_dict(self) -> dict:
        return {
            "causal_chains": [c.to_dict() for c in self.causal_chains],
            "circuit_breakers": self.circuit_breakers,
            "total_failures": self.total_failures,
            "total_affected": self.total_affected,
            "max_depth": self.max_depth,
            "containment_rate": round(self.containment_rate, 2),
        }

    def to_report(self) -> str:
        lines = [
            "# Failure Propagation Analysis",
            "",
            f"- **Root causes:** {len(self.causal_chains)}",
            f"- **Total affected spans:** {self.total_affected}",
            f"- **Max propagation depth:** {self.max_depth}",
            f"- **Containment rate:** {self.containment_rate:.0%}",
            "",
        ]
        for chain in self.causal_chains:
            icon = "🟡" if chain.contained else "🔴"
            lines.append(f"{icon} **{chain.root_span_name}**: {chain.root_error}")
            conf_pct = chain.chain_confidence * 100
            lines.append(f"   Depth: {chain.depth}, Affected: {len(chain.affected_span_ids)}, Chain confidence: {conf_pct:.0f}%")
            if chain.contained:
                lines.append(f"   🛡️ Contained by: {chain.contained_by}")
            for link in chain.links:
                conf_str = f" [{link.confidence:.0%}]" if link.confidence < 1.0 else ""
                lines.append(f"   → {link.from_span_name} ──({link.relationship})──▶ {link.to_span_name}{conf_str}")

        if self.circuit_breakers:
            lines.append("")
            lines.append("## Circuit Breakers")
            for cb in self.circuit_breakers:
                lines.append(f"🛡️ **{cb['name']}** contained {cb['contained_count']} failures")

        return "\n".join(lines)


def _compute_link_confidence(
    parent: Span, child: Span, span_map: dict[str, Span]
) -> float:
    """Compute causal confidence for a failure propagation link.

    Heuristics (each factor multiplies the base confidence of 1.0):
    - Same error type/message: high confidence (1.0)
    - Different error types: lower confidence (0.7)
    - Timing: child failed shortly after parent → higher confidence
    - Direct parent-child: higher than siblings (0.9 vs 0.6)

    Why heuristics: without explicit causal annotations, we infer
    causation from correlation. This is inherently uncertain.
    """
    confidence = 1.0

    # Error type similarity
    p_err = (parent.error or "").split(":")[0].strip()
    c_err = (child.error or "").split(":")[0].strip()
    if p_err and c_err:
        if p_err == c_err:
            confidence *= 1.0  # same error type = strong signal
        elif p_err in c_err or c_err in p_err:
            confidence *= 0.85  # partial match
        else:
            confidence *= 0.7  # different errors

    # Relationship type
    if child.parent_span_id == parent.span_id:
        confidence *= 0.95  # direct parent → very likely causal
    else:
        confidence *= 0.6  # sibling or distant = weaker causation

    # Timing proximity (child should fail after or near parent)
    if parent.ended_at and child.started_at:
        try:
            from datetime import datetime
            p_end = datetime.fromisoformat(str(parent.ended_at))
            c_start = datetime.fromisoformat(str(child.started_at))
            gap_ms = (c_start - p_end).total_seconds() * 1000
            if gap_ms < 0:
                # Child started before parent ended — concurrent, weaker
                confidence *= 0.8
            elif gap_ms > 5000:
                # Large gap — less likely causal
                confidence *= 0.6
        except (ValueError, TypeError):
            pass  # can't parse timestamps, skip timing factor

    return min(confidence, 1.0)


def _classify_severity(
    chain: CausalChain, trace,
) -> tuple[str, str]:
    """Classify a causal chain as recoverable or fatal.

    Recoverable: contained by circuit breaker, or trace still succeeded.
    Fatal: propagated to root and trace failed, or affected >50% of spans.
    """
    from agentguard.core.trace import SpanStatus
    trace_failed = trace.status == SpanStatus.FAILED
    affected_ratio = len(chain.affected_span_ids) / max(len(trace.spans), 1)
    if chain.contained:
        return "recoverable", f"Contained by {chain.contained_by}"
    if not trace_failed and chain.depth <= 1:
        return "recoverable", "Shallow failure, trace succeeded"
    if trace_failed and chain.depth >= 2:
        return "fatal", f"Propagated {chain.depth} levels deep, trace failed"
    if affected_ratio > 0.5:
        return "fatal", f"Affected {affected_ratio:.0%} of spans"
    if trace_failed:
        return "fatal", "Trace failed"
    return "recoverable", "Trace succeeded despite failure"


def _check_containment(
    span_id: str, chain: CausalChain,
    parent_map: dict[str, str], span_map: dict[str, Any],
    failed_ids: set[str], cb_counts: dict[str, int],
) -> None:
    """Check if a failed span's parent contained the failure (circuit breaker)."""
    pid = parent_map.get(span_id)
    if pid and pid in span_map:
        parent = span_map[pid]
        if parent.status == SpanStatus.COMPLETED and span_id in failed_ids and not chain.contained:
            chain.contained = True
            chain.contained_by = parent.name
            cb_counts[pid] = cb_counts.get(pid, 0) + 1


def _trace_causal_chain(
    rc_id: str,
    span_map: dict[str, Any],
    children_map: dict[str, list[str]],
    parent_map: dict[str, str],
    failed_ids: set[str],
) -> tuple[CausalChain, set[str], dict[str, int]]:
    """Trace a single causal chain from a root cause failure.

    BFS through children to find all affected descendants.
    Detects circuit breakers (parents that contain failures).

    Returns:
        (chain, affected_ids, circuit_breaker_counts)
    """
    rc_span = span_map[rc_id]
    chain = CausalChain(
        root_span_id=rc_id, root_span_name=rc_span.name,
        root_error=rc_span.error or "unknown",
    )
    affected: set[str] = {rc_id}
    cb_counts: dict[str, int] = {}
    queue = [(rc_id, 0)]
    visited = {rc_id}
    max_depth = 0
    while queue:
        current_id, depth = queue.pop(0)
        current = span_map.get(current_id)
        if not current:
            continue
        for child_id in children_map.get(current_id, []):
            if child_id in visited:
                continue
            visited.add(child_id)
            child = span_map.get(child_id)
            if not child or child.span_id not in failed_ids:
                continue
            conf = _compute_link_confidence(current, child, span_map)
            chain.links.append(CausalLink(
                from_span_id=current_id, from_span_name=current.name,
                to_span_id=child_id, to_span_name=child.name,
                relationship="cascade", confidence=conf,
            ))
            chain.affected_span_ids.append(child_id)
            affected.add(child_id)
            max_depth = max(max_depth, depth + 1)
            queue.append((child_id, depth + 1))
        _check_containment(current_id, chain, parent_map, span_map, failed_ids, cb_counts)
    chain.depth = max_depth
    return chain, affected, cb_counts


def _build_circuit_breakers(
    cb_counts: dict[str, int],
    span_map: dict[str, Any],
) -> list[dict]:
    """Build circuit breaker report from aggregated counts."""
    breakers = []
    for cb_id, count in sorted(cb_counts.items(), key=lambda x: -x[1]):
        cb = span_map.get(cb_id)
        if cb:
            breakers.append({"span_id": cb_id, "name": cb.name, "contained_count": count})
    return breakers


def analyze_propagation(trace: ExecutionTrace) -> PropagationAnalysis:
    """Analyze how failures propagate through the span tree.

    Builds causal chains, identifies circuit breakers, computes containment.
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}
    parent_map: dict[str, str] = {}
    for s in trace.spans:
        if s.parent_span_id:
            parent_map[s.span_id] = s.parent_span_id
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

    failed_ids = {s.span_id for s in trace.spans if s.status == SpanStatus.FAILED}
    if not failed_ids:
        return PropagationAnalysis(
            causal_chains=[], circuit_breakers=[],
            total_failures=0, total_affected=0, max_depth=0, containment_rate=1.0,
        )

    root_causes = [sid for sid in failed_ids
                   if parent_map.get(sid) is None or parent_map.get(sid) not in failed_ids]

    all_affected: set[str] = set()
    chains: list[CausalChain] = []
    all_cb: dict[str, int] = {}
    for rc_id in root_causes:
        chain, affected, cb = _trace_causal_chain(
            rc_id, span_map, children_map, parent_map, failed_ids)
        chains.append(chain)
        all_affected.update(affected)
        for k, v in cb.items():
            all_cb[k] = all_cb.get(k, 0) + v

    for chain in chains:
        chain.severity, chain.severity_reason = _classify_severity(chain, trace)

    return PropagationAnalysis(
        causal_chains=chains,
        circuit_breakers=_build_circuit_breakers(all_cb, span_map),
        total_failures=len(failed_ids),
        total_affected=len(all_affected),
        max_depth=max((c.depth for c in chains), default=0),
        containment_rate=sum(1 for c in chains if c.contained) / max(len(chains), 1),
    )


def hypothetical_failure(trace: ExecutionTrace, span_id: str) -> dict:
    """What-if analysis: what would happen if a specific span failed?

    Given a trace and a span ID, simulate what would happen if that span
    failed. Returns the hypothetical blast radius.

    Args:
        trace: The execution trace.
        span_id: The span to hypothetically fail.

    Returns:
        Dict with: affected_spans, blast_radius, critical (whether it's on critical path)
    """
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[str]] = {}

    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s.span_id)

    target = span_map.get(span_id)
    if not target:
        return {"error": f"Span {span_id} not found", "affected_spans": [], "blast_radius": 0}

    # Find all downstream spans (transitive children)
    affected = []
    queue = [span_id]
    visited = {span_id}

    while queue:
        current = queue.pop(0)
        for child_id in children_map.get(current, []):
            if child_id not in visited:
                visited.add(child_id)
                child = span_map.get(child_id)
                if child:
                    affected.append({
                        "span_id": child_id,
                        "name": child.name,
                        "type": child.span_type.value,
                    })
                    queue.append(child_id)

    # Check if span is on the critical path (longest path from root)
    # Simple heuristic: if it's an agent span with children, it's likely critical
    is_critical = target.span_type == SpanType.AGENT and bool(children_map.get(span_id))

    return {
        "target_span": target.name,
        "target_type": target.span_type.value,
        "affected_spans": affected,
        "blast_radius": len(affected),
        "critical": is_critical,
    }


def _build_handoff_chains(handoff_spans: list) -> list[list[dict]]:
    """Group time-sorted handoff spans into connected chains.

    Two handoffs are in the same chain if the first's 'to' agent
    matches the second's 'from' agent.
    """
    chains: list[list[dict]] = []
    current: list[dict] = []
    for h in handoff_spans:
        entry = {
            "from": h.handoff_from or "",
            "to": h.handoff_to or "",
            "context_size_bytes": h.context_size_bytes or 0,
            "utilization": h.metadata.get("handoff.utilization", 1.0),
            "dropped_keys": h.context_dropped_keys or [],
        }
        if current and current[-1]["to"] == entry["from"]:
            current.append(entry)
        else:
            if current:
                chains.append(current)
            current = [entry]
    if current:
        chains.append(current)
    return chains


def _analyze_chain_degradation(
    chains: list[list[dict]],
) -> tuple[list[dict], dict | None]:
    """Compute per-chain reports and find the critical handoff (most loss).

    Returns:
        (chain_reports, critical_handoff)
    """
    reports = []
    max_loss = 0
    critical = None
    for chain in chains:
        if not chain:
            continue
        agents = [chain[0]["from"]] + [h["to"] for h in chain]
        dropped = [k for h in chain for k in h["dropped_keys"]]
        avg_util = sum(h["utilization"] for h in chain) / len(chain)
        reports.append({
            "agents": agents, "length": len(chain),
            "start_size_bytes": chain[0]["context_size_bytes"],
            "end_size_bytes": chain[-1]["context_size_bytes"],
            "total_keys_dropped": len(dropped),
            "dropped_keys": dropped,
            "avg_utilization": round(avg_util, 2),
        })
        for h in chain:
            loss = len(h["dropped_keys"])
            if loss > max_loss:
                max_loss = loss
                critical = {"from": h["from"], "to": h["to"], "keys_dropped": h["dropped_keys"]}
    return reports, critical


def analyze_handoff_chains(trace: ExecutionTrace) -> dict:
    """Analyze sequences of handoffs to detect degradation patterns.

    Identifies context degradation over chains, handoff frequency,
    and critical handoff points where most context is lost.
    """
    handoff_spans = sorted(
        [s for s in trace.spans if s.span_type == SpanType.HANDOFF],
        key=lambda s: s.started_at or "",
    )
    if not handoff_spans:
        return {"chains": [], "total_handoffs": 0, "degradation_score": 0.0, "critical_handoff": None}

    chains = _build_handoff_chains(handoff_spans)
    reports, critical = _analyze_chain_degradation(chains)

    total_dropped = sum(len(h.context_dropped_keys or []) for h in handoff_spans)
    total_sent = sum(len(h.metadata.get("handoff.context_keys", [])) for h in handoff_spans)

    return {
        "chains": reports,
        "total_handoffs": len(handoff_spans),
        "degradation_score": round(total_dropped / max(total_sent, 1), 2),
        "critical_handoff": critical,
    }


def compute_context_integrity(trace: ExecutionTrace) -> dict:
    """Compute an overall context integrity score for the trace.

    Combines multiple signals:
    - Handoff utilization (are receivers using the context?)
    - Context loss detection (are keys being dropped?)
    - Failure containment (do circuit breakers work?)

    Returns:
        Dict with: integrity_score (0-1), components, recommendations
    """
    # Component 1: Handoff utilization
    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    utilizations = [s.metadata.get("handoff.utilization", 1.0) for s in handoff_spans]
    avg_utilization = sum(utilizations) / max(len(utilizations), 1)

    # Component 2: Context loss
    total_dropped = sum(len(s.context_dropped_keys or []) for s in handoff_spans)
    total_keys = sum(len(s.metadata.get("handoff.context_keys", [])) for s in handoff_spans)
    loss_rate = total_dropped / max(total_keys, 1)
    loss_score = 1.0 - loss_rate

    # Component 3: Failure resilience
    from agentguard.propagation import analyze_propagation
    prop = analyze_propagation(trace)
    resilience = prop.containment_rate

    # Weighted score
    integrity = (avg_utilization * 0.4) + (loss_score * 0.4) + (resilience * 0.2)

    recommendations = []
    if avg_utilization < 0.7:
        recommendations.append("Low context utilization — receivers are ignoring sent data. Review what context is being passed.")
    if loss_rate > 0.3:
        recommendations.append(f"High context loss rate ({loss_rate:.0%}) — critical keys may be dropped during handoffs.")
    if resilience < 0.5 and prop.total_failures > 0:
        recommendations.append("Low failure containment — add error handling or circuit breakers to agents.")
    if not handoff_spans:
        recommendations.append("No explicit handoffs recorded — use record_handoff() to track context flow.")

    return {
        "integrity_score": round(integrity, 2),
        "components": {
            "handoff_utilization": round(avg_utilization, 2),
            "context_preservation": round(loss_score, 2),
            "failure_resilience": round(resilience, 2),
        },
        "recommendations": recommendations,
        "total_handoffs": len(handoff_spans),
        "total_keys_dropped": total_dropped,
    }
