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
