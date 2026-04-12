"""Trace timeline — event-based chronological view of execution.

Converts a trace's span tree into a flat, time-ordered event stream:
- Each span generates START and END events
- Handoffs generate HANDOFF events
- Failures generate FAILURE events
- Context changes generate CONTEXT events

Useful for:
- Understanding exact execution order
- Debugging timing issues
- Building timeline visualizations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


class EventType(str, Enum):
    SPAN_START = "span_start"
    SPAN_END = "span_end"
    FAILURE = "failure"
    HANDOFF = "handoff"
    RETRY = "retry"
    CONTEXT_CHANGE = "context_change"


@dataclass
class TimelineEvent:
    """A single event on the timeline."""
    timestamp: str
    event_type: EventType
    span_id: str
    span_name: str
    span_type: str
    details: dict = field(default_factory=dict)
    
    @property
    def time(self) -> Optional[datetime]:
        try:
            return datetime.fromisoformat(self.timestamp)
        except (ValueError, TypeError):
            return None
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "event_type": self.event_type.value,
            "span_id": self.span_id,
            "span_name": self.span_name,
            "span_type": self.span_type,
            "details": self.details,
        }


@dataclass
class Timeline:
    """Ordered list of events from a trace."""
    events: list[TimelineEvent]
    trace_id: str
    duration_ms: Optional[float]
    
    def to_dict(self) -> dict:
        return {
            "trace_id": self.trace_id,
            "duration_ms": self.duration_ms,
            "event_count": len(self.events),
            "events": [e.to_dict() for e in self.events],
        }
    
    def to_text(self, max_events: int = 50) -> str:
        """Human-readable timeline."""
        lines = [
            f"# Timeline: {self.trace_id}",
            f"Duration: {self.duration_ms:.0f}ms" if self.duration_ms else "Duration: unknown",
            "",
        ]
        
        icons = {
            EventType.SPAN_START: "▶️",
            EventType.SPAN_END: "⏹️",
            EventType.FAILURE: "💥",
            EventType.HANDOFF: "🔀",
            EventType.RETRY: "🔄",
            EventType.CONTEXT_CHANGE: "📦",
        }
        
        for event in self.events[:max_events]:
            icon = icons.get(event.event_type, "📎")
            ts_short = event.timestamp.split("T")[1][:12] if "T" in event.timestamp else event.timestamp[:12]
            detail_str = ""
            if event.details:
                if "error" in event.details:
                    detail_str = f" — {event.details['error']}"
                elif "duration_ms" in event.details:
                    detail_str = f" — {event.details['duration_ms']:.0f}ms"
                elif "from" in event.details and "to" in event.details:
                    detail_str = f" — {event.details['from']} → {event.details['to']}"
            
            lines.append(f"{ts_short} {icon} [{event.span_type}] {event.span_name}{detail_str}")
        
        if len(self.events) > max_events:
            lines.append(f"... and {len(self.events) - max_events} more events")
        
        return "\n".join(lines)
    
    def filter_by_type(self, event_type: EventType) -> list[TimelineEvent]:
        """Get events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def filter_by_span(self, span_name: str) -> list[TimelineEvent]:
        """Get all events for a specific span."""
        return [e for e in self.events if e.span_name == span_name]


def build_timeline(trace: ExecutionTrace) -> Timeline:
    """Build a chronological timeline from a trace.
    
    Converts the span tree into a flat, time-ordered event stream.
    """
    events: list[TimelineEvent] = []
    
    for span in trace.spans:
        # Start event
        if span.started_at:
            events.append(TimelineEvent(
                timestamp=span.started_at,
                event_type=EventType.SPAN_START,
                span_id=span.span_id,
                span_name=span.name,
                span_type=span.span_type.value,
                details={"input_keys": list((span.input_data or {}).keys()) if isinstance(span.input_data, dict) else []},
            ))
        
        # End event
        if span.ended_at:
            details: dict = {}
            if span.duration_ms:
                details["duration_ms"] = span.duration_ms
            if span.status == SpanStatus.COMPLETED:
                details["output_keys"] = list((span.output_data or {}).keys()) if isinstance(span.output_data, dict) else []
            
            events.append(TimelineEvent(
                timestamp=span.ended_at,
                event_type=EventType.SPAN_END,
                span_id=span.span_id,
                span_name=span.name,
                span_type=span.span_type.value,
                details=details,
            ))
        
        # Failure event
        if span.status == SpanStatus.FAILED and span.error:
            events.append(TimelineEvent(
                timestamp=span.ended_at or span.started_at or "",
                event_type=EventType.FAILURE,
                span_id=span.span_id,
                span_name=span.name,
                span_type=span.span_type.value,
                details={"error": span.error, "handled": span.failure_handled},
            ))
        
        # Handoff event
        if span.span_type == SpanType.HANDOFF:
            events.append(TimelineEvent(
                timestamp=span.started_at or "",
                event_type=EventType.HANDOFF,
                span_id=span.span_id,
                span_name=span.name,
                span_type="handoff",
                details={
                    "from": span.handoff_from or "",
                    "to": span.handoff_to or "",
                    "context_size_bytes": span.context_size_bytes or 0,
                },
            ))
        
        # Retry event
        if span.retry_count > 0:
            events.append(TimelineEvent(
                timestamp=span.started_at or "",
                event_type=EventType.RETRY,
                span_id=span.span_id,
                span_name=span.name,
                span_type=span.span_type.value,
                details={"retry_count": span.retry_count, "retry_of": span.retry_of},
            ))
    
    # Sort by timestamp
    events.sort(key=lambda e: e.timestamp)
    
    return Timeline(
        events=events,
        trace_id=trace.trace_id,
        duration_ms=trace.duration_ms,
    )
