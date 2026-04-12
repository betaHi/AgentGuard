"""Enhanced trace export — CSV, TSV, and flat table formats.

Export traces as tabular data for analysis in spreadsheets,
pandas, or data warehouses.
"""

from __future__ import annotations

from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span


def trace_to_csv(trace: ExecutionTrace, delimiter: str = ",") -> str:
    """Export trace spans as CSV.
    
    Each row is a span with flattened fields.
    """
    headers = [
        "trace_id", "span_id", "parent_span_id", "span_type", "name",
        "status", "started_at", "ended_at", "duration_ms",
        "error", "retry_count", "token_count", "cost_usd",
        "handoff_from", "handoff_to", "context_size_bytes",
    ]
    
    lines = [delimiter.join(headers)]
    
    for s in trace.spans:
        row = [
            trace.trace_id,
            s.span_id,
            s.parent_span_id or "",
            s.span_type.value,
            _escape_csv(s.name, delimiter),
            s.status.value,
            s.started_at or "",
            s.ended_at or "",
            f"{s.duration_ms:.1f}" if s.duration_ms else "",
            _escape_csv(s.error or "", delimiter),
            str(s.retry_count),
            str(s.token_count or ""),
            f"{s.estimated_cost_usd:.4f}" if s.estimated_cost_usd else "",
            s.handoff_from or "",
            s.handoff_to or "",
            str(s.context_size_bytes or ""),
        ]
        lines.append(delimiter.join(row))
    
    return "\n".join(lines)


def traces_to_csv(traces: list[ExecutionTrace], delimiter: str = ",") -> str:
    """Export multiple traces as a single CSV."""
    if not traces:
        return ""
    
    # Use first trace for headers
    result = trace_to_csv(traces[0], delimiter)
    
    for trace in traces[1:]:
        csv = trace_to_csv(trace, delimiter)
        # Skip header row
        lines = csv.split("\n")[1:]
        result += "\n" + "\n".join(lines)
    
    return result


def trace_to_table(trace: ExecutionTrace) -> list[dict]:
    """Export trace as a list of flat dictionaries (ready for pandas)."""
    rows = []
    for s in trace.spans:
        rows.append({
            "trace_id": trace.trace_id,
            "task": trace.task,
            "span_id": s.span_id,
            "parent_span_id": s.parent_span_id,
            "span_type": s.span_type.value,
            "name": s.name,
            "status": s.status.value,
            "started_at": s.started_at,
            "ended_at": s.ended_at,
            "duration_ms": s.duration_ms,
            "error": s.error,
            "retry_count": s.retry_count,
            "token_count": s.token_count,
            "cost_usd": s.estimated_cost_usd,
            "handoff_from": s.handoff_from,
            "handoff_to": s.handoff_to,
            "context_size_bytes": s.context_size_bytes,
            "tags": ",".join(s.tags) if s.tags else "",
        })
    return rows


def _escape_csv(value: str, delimiter: str) -> str:
    """Escape a value for CSV output."""
    if delimiter in value or '"' in value or "\n" in value:
        return '"' + value.replace('"', '""') + '"'
    return value
