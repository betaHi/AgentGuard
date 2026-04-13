"""Trace importer — import traces from external formats.

Supports importing from:
- OpenTelemetry JSON export
- Langfuse-style spans
- Generic JSON (best-effort)
"""

from __future__ import annotations

from datetime import UTC

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


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


def _flatten_otel_spans(data: dict) -> list[dict]:
    """Flatten OTel resourceSpans → scopeSpans → spans into a flat list."""
    all_spans = []
    for rs in data.get("resourceSpans", []):
        for ss in rs.get("scopeSpans", []):
            all_spans.extend(ss.get("spans", []))
    return all_spans or data.get("spans", [])


def _parse_otel_attrs(raw_attrs: list | dict) -> dict:
    """Convert OTel attribute list to flat dict."""
    if isinstance(raw_attrs, dict):
        return raw_attrs
    attrs = {}
    for attr in raw_attrs:
        key = attr.get("key", "")
        value = attr.get("value", {})
        if isinstance(value, dict):
            attrs[key] = (value.get("stringValue") or value.get("intValue") or
                         value.get("doubleValue") or value.get("boolValue", ""))
        else:
            attrs[key] = value
    return attrs


def _otel_ns_to_iso(ns: int) -> str:
    """Convert OTel nanosecond Unix timestamp to ISO 8601 string."""
    if not ns:
        return ""
    from datetime import datetime
    return datetime.fromtimestamp(ns / 1e9, tz=UTC).isoformat()


def _convert_otel_span(otel_span: dict) -> Span:
    """Convert a single OTel span dict to an AgentGuard Span."""
    attrs = _parse_otel_attrs(otel_span.get("attributes", []))
    otel_span["_parsed_attributes"] = attrs

    status = _guess_status(otel_span)
    error_msg = None
    if status == SpanStatus.FAILED:
        error_msg = otel_span.get("status", {}).get("message", "Unknown error")

    return Span(
        span_id=otel_span.get("spanId", "")[:12],
        parent_span_id=otel_span.get("parentSpanId", "")[:12] or None,
        span_type=_guess_span_type(otel_span),
        name=otel_span.get("name", "unnamed"),
        status=status,
        started_at=_otel_ns_to_iso(otel_span.get("startTimeUnixNano", 0)),
        ended_at=_otel_ns_to_iso(otel_span.get("endTimeUnixNano", 0)),
        error=error_msg,
        metadata=attrs,
    )


def import_otel(data: dict) -> ExecutionTrace:
    """Import from OpenTelemetry JSON export format (resourceSpans envelope)."""
    trace = ExecutionTrace(task="Imported from OpenTelemetry")
    all_spans = _flatten_otel_spans(data)

    if all_spans:
        trace.trace_id = all_spans[0].get("traceId", trace.trace_id)[:16]

    for otel_span in all_spans:
        trace.add_span(_convert_otel_span(otel_span))

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
