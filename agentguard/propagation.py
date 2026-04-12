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
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


@dataclass
class CausalLink:
    """A link in a failure's causal chain."""
    from_span_id: str
    from_span_name: str
    to_span_id: str
    to_span_name: str
    relationship: str  # "parent_failure", "dependency_failure", "cascade"
    
    def to_dict(self) -> dict:
        return {
            "from_id": self.from_span_id, "from_name": self.from_span_name,
            "to_id": self.to_span_id, "to_name": self.to_span_name,
            "relationship": self.relationship,
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
    contained_by: Optional[str] = None  # span_id that contained it
    
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
            lines.append(f"   Depth: {chain.depth}, Affected: {len(chain.affected_span_ids)}")
            if chain.contained:
                lines.append(f"   🛡️ Contained by: {chain.contained_by}")
            for link in chain.links:
                lines.append(f"   → {link.from_span_name} ──({link.relationship})──▶ {link.to_span_name}")
        
        if self.circuit_breakers:
            lines.append("")
            lines.append("## Circuit Breakers")
            for cb in self.circuit_breakers:
                lines.append(f"🛡️ **{cb['name']}** contained {cb['contained_count']} failures")
        
        return "\n".join(lines)


def analyze_propagation(trace: ExecutionTrace) -> PropagationAnalysis:
    """Analyze how failures propagate through the span tree.
    
    Builds full causal chains from each root cause to all affected spans,
    identifies circuit breakers (spans that catch and contain failures),
    and computes containment metrics.
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
    
    # Find root cause failures: failed spans whose parent didn't fail
    root_causes = []
    for sid in failed_ids:
        parent_id = parent_map.get(sid)
        if parent_id is None or parent_id not in failed_ids:
            root_causes.append(sid)
    
    # For each root cause, trace the full propagation chain
    all_affected: set[str] = set()
    chains: list[CausalChain] = []
    circuit_breaker_counts: dict[str, int] = {}
    
    for rc_id in root_causes:
        rc_span = span_map[rc_id]
        chain = CausalChain(
            root_span_id=rc_id,
            root_span_name=rc_span.name,
            root_error=rc_span.error or "unknown",
        )
        
        # BFS to find all affected descendants
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
                if not child:
                    continue
                
                if child.span_id in failed_ids:
                    # Failure propagated to this child
                    chain.links.append(CausalLink(
                        from_span_id=current_id,
                        from_span_name=current.name,
                        to_span_id=child_id,
                        to_span_name=child.name,
                        relationship="cascade",
                    ))
                    chain.affected_span_ids.append(child_id)
                    all_affected.add(child_id)
                    max_depth = max(max_depth, depth + 1)
                    queue.append((child_id, depth + 1))
                elif current_id in failed_ids:
                    # Parent failed but this child succeeded — circuit breaker pattern
                    # (child handled the failure or was independent)
                    pass
            
            # Check if parent contained this failure
            parent_id = parent_map.get(current_id)
            if parent_id and parent_id in span_map:
                parent = span_map[parent_id]
                if parent.status == SpanStatus.COMPLETED and current_id in failed_ids:
                    # Parent succeeded despite child failure = containment
                    if not chain.contained:
                        chain.contained = True
                        chain.contained_by = parent.name
                        circuit_breaker_counts[parent_id] = circuit_breaker_counts.get(parent_id, 0) + 1
        
        chain.depth = max_depth
        all_affected.add(rc_id)
        chains.append(chain)
    
    # Build circuit breaker report
    circuit_breakers = []
    for cb_id, count in sorted(circuit_breaker_counts.items(), key=lambda x: -x[1]):
        cb = span_map.get(cb_id)
        if cb:
            circuit_breakers.append({
                "span_id": cb_id,
                "name": cb.name,
                "contained_count": count,
            })
    
    contained_count = sum(1 for c in chains if c.contained)
    
    return PropagationAnalysis(
        causal_chains=chains,
        circuit_breakers=circuit_breakers,
        total_failures=len(failed_ids),
        total_affected=len(all_affected),
        max_depth=max((c.depth for c in chains), default=0),
        containment_rate=contained_count / max(len(chains), 1),
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
