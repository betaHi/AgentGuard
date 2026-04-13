"""Trace normalization — clean up and standardize traces.

Handles:
- Missing required fields (fill in defaults)
- Inconsistent timestamps (fix ordering)
- Orphan span resolution (re-parent or promote to root)
- Status reconciliation (fix parent status based on children)
- Deduplication (remove duplicate spans)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus


@dataclass
class NormalizationResult:
    """Result of normalizing a trace."""
    trace: ExecutionTrace
    changes: list[str]

    @property
    def changed(self) -> bool:
        return len(self.changes) > 0

    def to_dict(self) -> dict:
        return {
            "changed": self.changed,
            "change_count": len(self.changes),
            "changes": self.changes,
        }


def _fix_trace_fields(trace: ExecutionTrace, changes: list[str]) -> None:
    """Fix missing trace-level timestamps from span boundaries."""
    if not trace.started_at and trace.spans:
        earliest = min((s.started_at for s in trace.spans if s.started_at), default=None)
        if earliest:
            trace.started_at = earliest
            changes.append("Set trace.started_at from earliest span")
    if not trace.ended_at and trace.status in (SpanStatus.COMPLETED, SpanStatus.FAILED) and trace.spans:
        latest = max((s.ended_at for s in trace.spans if s.ended_at), default=None)
        if latest:
            trace.ended_at = latest
            changes.append("Set trace.ended_at from latest span")


def _fix_orphans(trace: ExecutionTrace, changes: list[str]) -> None:
    """Promote orphan spans (parent_id references non-existent span) to root."""
    span_ids = {s.span_id for s in trace.spans}
    for span in trace.spans:
        if span.parent_span_id and span.parent_span_id not in span_ids:
            span.parent_span_id = None
            changes.append(f"Orphan span '{span.name}' promoted to root")


def _fix_timestamps(trace: ExecutionTrace, changes: list[str]) -> None:
    """Fix inconsistent timestamps: swap if end < start, fill missing end."""
    for span in trace.spans:
        if span.started_at and span.ended_at:
            try:
                start_dt = datetime.fromisoformat(span.started_at)
                end_dt = datetime.fromisoformat(span.ended_at)
                if end_dt < start_dt:
                    span.started_at, span.ended_at = span.ended_at, span.started_at
                    changes.append(f"Swapped timestamps on span '{span.name}' (end was before start)")
            except (ValueError, TypeError):
                pass
        elif span.started_at and not span.ended_at and span.status in (
            SpanStatus.COMPLETED, SpanStatus.FAILED,
        ):
            span.ended_at = span.started_at
            changes.append(f"Set missing ended_at on completed span '{span.name}'")


def _dedup_spans(trace: ExecutionTrace, changes: list[str]) -> None:
    """Remove duplicate spans (same span_id), keeping first occurrence."""
    seen: set[str] = set()
    deduped: list[Span] = []
    for span in trace.spans:
        if span.span_id not in seen:
            seen.add(span.span_id)
            deduped.append(span)
        else:
            changes.append(f"Removed duplicate span '{span.name}' (id: {span.span_id})")
    trace.spans = deduped


def _fix_statuses(trace: ExecutionTrace, changes: list[str]) -> None:
    """Fix inconsistent statuses and running spans in completed traces."""
    span_map = {s.span_id: s for s in trace.spans}
    has_unhandled = False
    for span in trace.spans:
        if span.status == SpanStatus.FAILED and not span.failure_handled:
            if span.parent_span_id and span.parent_span_id in span_map:
                if span_map[span.parent_span_id].status != SpanStatus.COMPLETED:
                    has_unhandled = True
            else:
                has_unhandled = True
    if has_unhandled and trace.status == SpanStatus.COMPLETED:
        trace.status = SpanStatus.FAILED
        changes.append("Trace status changed to FAILED (unhandled failures detected)")
    if trace.status in (SpanStatus.COMPLETED, SpanStatus.FAILED):
        for span in trace.spans:
            if span.status == SpanStatus.RUNNING:
                span.status = SpanStatus.FAILED
                span.error = span.error or "Span still running when trace completed"
                if not span.ended_at:
                    span.ended_at = trace.ended_at
                changes.append(f"Running span '{span.name}' marked as FAILED")


def normalize_trace(trace: ExecutionTrace) -> NormalizationResult:
    """Normalize a trace by fixing common issues.

    Non-destructive pipeline: fixes timestamps, orphans, duplicates, statuses.
    """
    changes: list[str] = []
    _fix_trace_fields(trace, changes)
    _fix_orphans(trace, changes)
    _fix_timestamps(trace, changes)
    _dedup_spans(trace, changes)
    _fix_statuses(trace, changes)
    for span in trace.spans:
        if not span.trace_id:
            span.trace_id = trace.trace_id
            changes.append(f"Set trace_id on span '{span.name}'")
    return NormalizationResult(trace=trace, changes=changes)
