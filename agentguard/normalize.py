"""Trace normalization — clean up and standardize traces.

Handles:
- Missing required fields (fill in defaults)
- Inconsistent timestamps (fix ordering)
- Orphan span resolution (re-parent or promote to root)
- Status reconciliation (fix parent status based on children)
- Deduplication (remove duplicate spans)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


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


def normalize_trace(trace: ExecutionTrace) -> NormalizationResult:
    """Normalize a trace by fixing common issues.
    
    This is non-destructive — it creates a new trace with fixes applied.
    """
    changes: list[str] = []
    
    # 1. Fix missing trace fields
    if not trace.started_at:
        if trace.spans:
            earliest = min((s.started_at for s in trace.spans if s.started_at), default=None)
            if earliest:
                trace.started_at = earliest
                changes.append("Set trace.started_at from earliest span")
    
    if not trace.ended_at and trace.status in (SpanStatus.COMPLETED, SpanStatus.FAILED):
        if trace.spans:
            latest = max((s.ended_at for s in trace.spans if s.ended_at), default=None)
            if latest:
                trace.ended_at = latest
                changes.append("Set trace.ended_at from latest span")
    
    # 2. Fix orphan spans (parent_id references non-existent span)
    span_ids = {s.span_id for s in trace.spans}
    for span in trace.spans:
        if span.parent_span_id and span.parent_span_id not in span_ids:
            span.parent_span_id = None
            changes.append(f"Orphan span '{span.name}' promoted to root")
    

    # 2b. Fix inconsistent timestamps (end before start)
    for span in trace.spans:
        if span.started_at and span.ended_at:
            try:
                start_dt = datetime.fromisoformat(span.started_at)
                end_dt = datetime.fromisoformat(span.ended_at)
                if end_dt < start_dt:
                    # Swap them — most likely a serialization error
                    span.started_at, span.ended_at = span.ended_at, span.started_at
                    changes.append(
                        f"Swapped timestamps on span '{span.name}' "
                        f"(end was before start)"
                    )
            except (ValueError, TypeError):
                pass
        elif span.started_at and not span.ended_at and span.status in (
            SpanStatus.COMPLETED, SpanStatus.FAILED
        ):
            # Span is done but has no end time — set to start time
            span.ended_at = span.started_at
            changes.append(f"Set missing ended_at on completed span '{span.name}'")

    # 3. Deduplicate spans (same span_id)
    seen_ids: set[str] = set()
    deduped: list[Span] = []
    for span in trace.spans:
        if span.span_id not in seen_ids:
            seen_ids.add(span.span_id)
            deduped.append(span)
        else:
            changes.append(f"Removed duplicate span '{span.name}' (id: {span.span_id})")
    trace.spans = deduped
    
    # 4. Fix inconsistent statuses
    # If trace is COMPLETED but has unhandled failures, mark as FAILED
    has_unhandled_failure = False
    span_map = {s.span_id: s for s in trace.spans}
    
    for span in trace.spans:
        if span.status == SpanStatus.FAILED and not span.failure_handled:
            # Check if parent succeeded (meaning failure was handled)
            if span.parent_span_id and span.parent_span_id in span_map:
                parent = span_map[span.parent_span_id]
                if parent.status != SpanStatus.COMPLETED:
                    has_unhandled_failure = True
            else:
                # Root span failed = trace failed
                has_unhandled_failure = True
    
    if has_unhandled_failure and trace.status == SpanStatus.COMPLETED:
        trace.status = SpanStatus.FAILED
        changes.append("Trace status changed to FAILED (unhandled failures detected)")
    
    # 5. Fix running spans (trace is complete but span still running)
    if trace.status in (SpanStatus.COMPLETED, SpanStatus.FAILED):
        for span in trace.spans:
            if span.status == SpanStatus.RUNNING:
                span.status = SpanStatus.FAILED
                span.error = span.error or "Span still running when trace completed"
                if not span.ended_at:
                    span.ended_at = trace.ended_at
                changes.append(f"Running span '{span.name}' marked as FAILED")
    
    # 6. Fill missing span trace_id
    for span in trace.spans:
        if not span.trace_id:
            span.trace_id = trace.trace_id
            changes.append(f"Set trace_id on span '{span.name}'")
    
    return NormalizationResult(trace=trace, changes=changes)
