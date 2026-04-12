"""Trace importer — import traces from external formats.

Supports importing from:
- OpenTelemetry JSON export
- Langfuse-style spans
- Generic JSON (best-effort)
"""

from __future__ import annotations

from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def _guess_span_type(data: dict) -> SpanType:
    """Guess span type from attributes."""
    name = data.get("name", "").lower()
    kind = data.get("kind", "").lower()
    attrs = data.get("_parsed_attributes", {})
    
    if "llm" in name or "completion" in name or "chat" in name:
        return SpanType.LLM_CALL
    if "tool" in name or kind == "tool":
        return SpanType.TOOL
    if "handoff" in name:
        return SpanType.HANDOFF
    if attrs.get("agentguard.span_type"):
        try:
            return SpanType(attrs["agentguard.span_type"])
        except ValueError:
            pass
    return SpanType.AGENT


def _guess_status(data: dict) -> SpanStatus:
    """Guess status from OTel status code."""
    status = data.get("status", {})
    code = status.get("code", status.get("status_code", ""))
    
    if isinstance(code, int):
        return SpanStatus.FAILED if code == 2 else SpanStatus.COMPLETED
    
    code_str = str(code).upper()
    if code_str in ("ERROR", "2", "FAILED"):
        return SpanStatus.FAILED
    if code_str in ("UNSET", "OK", "0", "1", "COMPLETED"):
        return SpanStatus.COMPLETED
    
    # Check for error attribute
    if data.get("status", {}).get("message") or data.get("error"):
        return SpanStatus.FAILED
    
    return SpanStatus.COMPLETED


def import_otel(data: dict) -> ExecutionTrace:
    """Import from OpenTelemetry JSON export format.
    
    Expects OTel format:
    {
        "resourceSpans": [{
            "scopeSpans": [{
                "spans": [{ traceId, spanId, parentSpanId, name, ... }]
            }]
        }]
    }
    """
    trace = ExecutionTrace(task="Imported from OpenTelemetry")
    
    # Flatten all spans
    all_spans = []
    for rs in data.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            all_spans.extend(ss.get("spans", []))
    
    if not all_spans:
        # Try flat span list
        all_spans = data.get("spans", [])
    
    # Set trace ID from first span
    if all_spans:
        trace.trace_id = all_spans[0].get("traceId", trace.trace_id)[:16]
    
    for otel_span in all_spans:
        span_id = otel_span.get("spanId", "")[:12]
        parent_id = otel_span.get("parentSpanId", "")[:12] or None
        
        # Convert timestamps (OTel uses nanoseconds)
        start_ns = otel_span.get("startTimeUnixNano", 0)
        end_ns = otel_span.get("endTimeUnixNano", 0)
        
        from datetime import datetime, timezone
        started_at = ""
        ended_at = ""
        if start_ns:
            started_at = datetime.fromtimestamp(start_ns / 1e9, tz=timezone.utc).isoformat()
        if end_ns:
            ended_at = datetime.fromtimestamp(end_ns / 1e9, tz=timezone.utc).isoformat()
        
        # Extract attributes (OTel uses list format, we convert to dict)
        attrs = {}
        raw_attrs = otel_span.get("attributes", [])
        if isinstance(raw_attrs, dict):
            attrs = raw_attrs
        else:
            for attr in raw_attrs:
                key = attr.get("key", "")
                value = attr.get("value", {})
                if isinstance(value, dict):
                    attrs[key] = (value.get("stringValue") or value.get("intValue") or 
                                 value.get("doubleValue") or value.get("boolValue", ""))
                else:
                    attrs[key] = value
        
        error_msg = None
        status = _guess_status(otel_span)
        if status == SpanStatus.FAILED:
            error_msg = otel_span.get("status", {}).get("message", "Unknown error")
        
        # Store parsed attrs for type guessing
        otel_span["_parsed_attributes"] = attrs
        
        span = Span(
            span_id=span_id,
            parent_span_id=parent_id,
            span_type=_guess_span_type(otel_span),
            name=otel_span.get("name", "unnamed"),
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            error=error_msg,
            metadata=attrs,
        )
        trace.add_span(span)
    
    # Set trace times
    if trace.spans:
        starts = [s.started_at for s in trace.spans if s.started_at]
        ends = [s.ended_at for s in trace.spans if s.ended_at]
        if starts:
            trace.started_at = min(starts)
        if ends:
            trace.ended_at = max(ends)
    
    return trace


def import_generic(data: dict) -> ExecutionTrace:
    """Best-effort import from any JSON format.
    
    Tries to detect the format and import accordingly.
    """
    # Check for AgentGuard native format
    if "trace_id" in data and "spans" in data:
        return ExecutionTrace.from_dict(data)
    
    # Check for OTel format
    if "resourceSpans" in data:
        return import_otel(data)
    
    # Check for flat span list
    if "spans" in data:
        return import_otel({"resourceSpans": [{"scopeSpans": [{"spans": data["spans"]}]}]})
    
    raise ValueError("Unrecognized trace format. Supported: AgentGuard JSON, OpenTelemetry JSON.")
