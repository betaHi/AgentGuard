"""Trace diff — compare two execution traces to identify changes.

When you change an agent version, prompt, or configuration, use trace diff
to see exactly what changed in the execution topology.

Usage:
    from agentguard.diff import diff_traces
    result = diff_traces(trace_a, trace_b)
    print(result.to_report())
"""



from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus

__all__ = ['SpanDiff', 'TraceDiff', 'diff_traces']


@dataclass
class SpanDiff:
    """Difference between corresponding spans in two traces."""
    name: str
    span_type: str
    field: str
    value_a: Any
    value_b: Any
    verdict: str = "neutral"  # improved, regressed, changed, added, removed

    def to_dict(self) -> dict:
        return {
            "name": self.name, "type": self.span_type, "field": self.field,
            "before": self.value_a, "after": self.value_b, "verdict": self.verdict,
        }


@dataclass
class TraceDiff:
    """Complete diff between two execution traces."""
    trace_a_id: str
    trace_b_id: str
    diffs: list[SpanDiff] = field(default_factory=list)
    spans_added: list[str] = field(default_factory=list)
    spans_removed: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return len(self.diffs) > 0 or len(self.spans_added) > 0 or len(self.spans_removed) > 0

    @property
    def regressions(self) -> list[SpanDiff]:
        return [d for d in self.diffs if d.verdict == "regressed"]

    @property
    def improvements(self) -> list[SpanDiff]:
        return [d for d in self.diffs if d.verdict == "improved"]

    def to_dict(self) -> dict:
        return {
            "trace_a": self.trace_a_id, "trace_b": self.trace_b_id,
            "changes": len(self.diffs), "regressions": len(self.regressions),
            "improvements": len(self.improvements),
            "added": self.spans_added, "removed": self.spans_removed,
            "diffs": [d.to_dict() for d in self.diffs],
        }

    def to_report(self) -> str:
        lines = [
            "# Trace Diff Report",
            "",
            f"- **Trace A:** {self.trace_a_id}",
            f"- **Trace B:** {self.trace_b_id}",
            f"- **Changes:** {len(self.diffs)}",
            f"- **Improvements:** {len(self.improvements)}",
            f"- **Regressions:** {len(self.regressions)}",
            "",
        ]
        
        if self.spans_added:
            lines.append("## Spans Added")
            for s in self.spans_added:
                lines.append(f"  + {s}")
            lines.append("")
        
        if self.spans_removed:
            lines.append("## Spans Removed")
            for s in self.spans_removed:
                lines.append(f"  - {s}")
            lines.append("")
        
        if self.diffs:
            lines.append("## Changes")
            for d in self.diffs:
                icon = "📈" if d.verdict == "improved" else "📉" if d.verdict == "regressed" else "🔄"
                lines.append(f"  {icon} **{d.name}** ({d.span_type}) — {d.field}: {d.value_a} → {d.value_b}")
        
        return "\n".join(lines)


def diff_traces(trace_a: ExecutionTrace, trace_b: ExecutionTrace) -> TraceDiff:
    """Compare two execution traces and identify differences.
    
    Matches spans by (name, span_type) and compares:
    - status (pass/fail)
    - duration
    - error presence
    - child count
    
    Args:
        trace_a: First trace (baseline).
        trace_b: Second trace (candidate).
    
    Returns:
        TraceDiff with all identified differences.
    """
    result = TraceDiff(trace_a_id=trace_a.trace_id, trace_b_id=trace_b.trace_id)
    
    # Index spans by (name, type) for matching
    def index_spans(trace: ExecutionTrace) -> dict[tuple, Span]:
        idx: dict[tuple, Span] = {}
        for s in trace.spans:
            key = (s.name, s.span_type.value)
            if key not in idx:  # keep first occurrence
                idx[key] = s
        return idx
    
    idx_a = index_spans(trace_a)
    idx_b = index_spans(trace_b)
    
    keys_a = set(idx_a.keys())
    keys_b = set(idx_b.keys())
    
    # Spans added/removed
    for key in keys_b - keys_a:
        result.spans_added.append(f"{key[0]} ({key[1]})")
    for key in keys_a - keys_b:
        result.spans_removed.append(f"{key[0]} ({key[1]})")
    
    # Compare matching spans
    for key in keys_a & keys_b:
        sa = idx_a[key]
        sb = idx_b[key]
        name, stype = key
        
        # Status change
        if sa.status != sb.status:
            if sb.status == SpanStatus.COMPLETED and sa.status == SpanStatus.FAILED:
                verdict = "improved"
            elif sb.status == SpanStatus.FAILED and sa.status == SpanStatus.COMPLETED:
                verdict = "regressed"
            else:
                verdict = "changed"
            result.diffs.append(SpanDiff(
                name=name, span_type=stype, field="status",
                value_a=sa.status.value, value_b=sb.status.value, verdict=verdict,
            ))
        
        # Duration change (significant = >20% change)
        dur_a = sa.duration_ms or 0
        dur_b = sb.duration_ms or 0
        if dur_a > 0 and abs(dur_b - dur_a) / dur_a > 0.2:
            verdict = "improved" if dur_b < dur_a else "regressed"
            result.diffs.append(SpanDiff(
                name=name, span_type=stype, field="duration_ms",
                value_a=round(dur_a), value_b=round(dur_b), verdict=verdict,
            ))
        
        # Error appeared/disappeared
        if sa.error and not sb.error:
            result.diffs.append(SpanDiff(
                name=name, span_type=stype, field="error",
                value_a=sa.error, value_b=None, verdict="improved",
            ))
        elif not sa.error and sb.error:
            result.diffs.append(SpanDiff(
                name=name, span_type=stype, field="error",
                value_a=None, value_b=sb.error, verdict="regressed",
            ))
    
    return result


def diff_flow_graphs(trace_a: ExecutionTrace, trace_b: ExecutionTrace) -> dict:
    """Compare flow graphs of two traces.
    
    Identifies:
    - Changes in parallelism
    - New or removed dependencies
    - Critical path shifts
    - Phase structure changes
    """
    from agentguard.flowgraph import build_flow_graph
    
    graph_a = build_flow_graph(trace_a)
    graph_b = build_flow_graph(trace_b)
    
    changes = []
    
    # Parallelism change
    if graph_a.max_parallelism != graph_b.max_parallelism:
        changes.append({
            "type": "parallelism",
            "field": "max_parallelism",
            "before": graph_a.max_parallelism,
            "after": graph_b.max_parallelism,
        })
    
    # Sequential fraction change
    delta = abs(graph_a.sequential_fraction - graph_b.sequential_fraction)
    if delta > 0.1:
        changes.append({
            "type": "execution_mode",
            "field": "sequential_fraction",
            "before": graph_a.sequential_fraction,
            "after": graph_b.sequential_fraction,
        })
    
    # Critical path change
    if graph_a.critical_path != graph_b.critical_path:
        changes.append({
            "type": "critical_path",
            "before": graph_a.critical_path,
            "after": graph_b.critical_path,
            "duration_before_ms": graph_a.critical_path_ms,
            "duration_after_ms": graph_b.critical_path_ms,
        })
    
    # Phase count change
    if len(graph_a.phases) != len(graph_b.phases):
        changes.append({
            "type": "phase_count",
            "before": len(graph_a.phases),
            "after": len(graph_b.phases),
        })
    
    # Node differences
    names_a = {n.name for n in graph_a.nodes}
    names_b = {n.name for n in graph_b.nodes}
    added_nodes = names_b - names_a
    removed_nodes = names_a - names_b
    
    if added_nodes:
        changes.append({"type": "nodes_added", "names": list(added_nodes)})
    if removed_nodes:
        changes.append({"type": "nodes_removed", "names": list(removed_nodes)})
    
    return {
        "changes": changes,
        "graph_a": {"nodes": len(graph_a.nodes), "edges": len(graph_a.edges), "phases": len(graph_a.phases)},
        "graph_b": {"nodes": len(graph_b.nodes), "edges": len(graph_b.edges), "phases": len(graph_b.phases)},
    }


def diff_context_flow(trace_a: ExecutionTrace, trace_b: ExecutionTrace) -> dict:
    """Compare context flow between two traces.
    
    Identifies:
    - Changes in compression ratio
    - New truncation/expansion events
    - Bottleneck shifts
    """
    from agentguard.context_flow import analyze_context_flow_deep
    
    flow_a = analyze_context_flow_deep(trace_a)
    flow_b = analyze_context_flow_deep(trace_b)
    
    changes = []
    
    # Compression ratio change
    if abs(flow_a.compression_ratio - flow_b.compression_ratio) > 0.1:
        changes.append({
            "type": "compression_ratio",
            "before": flow_a.compression_ratio,
            "after": flow_b.compression_ratio,
        })
    
    # Truncation event count change
    if flow_a.truncation_events != flow_b.truncation_events:
        changes.append({
            "type": "truncation_events",
            "before": flow_a.truncation_events,
            "after": flow_b.truncation_events,
        })
    
    # Bottleneck shift
    if flow_a.bottleneck_agent != flow_b.bottleneck_agent:
        changes.append({
            "type": "bottleneck_shift",
            "before": flow_a.bottleneck_agent,
            "after": flow_b.bottleneck_agent,
        })
    
    # Total data volume change
    bytes_delta = flow_b.total_bytes_in - flow_a.total_bytes_in
    if abs(bytes_delta) > 100:
        changes.append({
            "type": "data_volume",
            "before_bytes": flow_a.total_bytes_in,
            "after_bytes": flow_b.total_bytes_in,
            "delta_bytes": bytes_delta,
        })
    
    return {
        "changes": changes,
        "flow_a": flow_a.to_dict(),
        "flow_b": flow_b.to_dict(),
    }
