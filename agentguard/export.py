"""Trace export utilities.

Export AgentGuard traces to various formats:
- JSON (native)
- JSONL (for streaming/logging)
- OTel-compatible format (for integration with observability platforms)
"""



from __future__ import annotations

import json
from pathlib import Path

from agentguard.core.trace import ExecutionTrace

__all__ = ['export_jsonl', 'export_otel_spans', 'export_otel', 'trace_statistics']


def export_jsonl(trace: ExecutionTrace, filepath: str) -> None:
    """Export trace as JSONL (one span per line).

    Useful for log aggregation systems (ELK, Loki, etc.)
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        # Write trace header
        f.write(json.dumps({
            "type": "trace",
            "trace_id": trace.trace_id,
            "task": trace.task,
            "trigger": trace.trigger,
            "status": trace.status.value,
            "started_at": trace.started_at,
            "ended_at": trace.ended_at,
            "duration_ms": trace.duration_ms,
        }, ensure_ascii=False) + "\n")
        # Write each span
        for span in trace.spans:
            f.write(json.dumps({
                "type": "span",
                "trace_id": trace.trace_id,
                "span_id": span.span_id,
                "parent_span_id": span.parent_span_id,
                "span_type": span.span_type.value,
                "name": span.name,
                "status": span.status.value,
                "started_at": span.started_at,
                "ended_at": span.ended_at,
                "duration_ms": span.duration_ms,
                "error": span.error,
                "metadata": span.metadata,
            }, ensure_ascii=False) + "\n")


def export_otel_spans(trace: ExecutionTrace) -> list[dict]:
    """Convert trace to OTel-compatible span format.

    Follows OpenTelemetry GenAI semantic conventions where applicable.
    Output can be sent to any OTel-compatible collector.

    Returns:
        List of span dicts in OTel format.
    """
    otel_spans = []

    for span in trace.spans:
        attributes = {
            "agentguard.trace_id": trace.trace_id,
            "agentguard.task": trace.task,
        }

        # Map to OTel GenAI conventions
        if span.span_type.value == "agent":
            attributes["gen_ai.operation.name"] = "invoke_agent"
            attributes["gen_ai.agent.name"] = span.name
            if "agent_version" in span.metadata:
                attributes["gen_ai.agent.version"] = span.metadata["agent_version"]
        elif span.span_type.value == "tool":
            attributes["gen_ai.operation.name"] = "execute_tool"
            attributes["gen_ai.tool.name"] = span.name
        elif span.span_type.value == "llm_call":
            attributes["gen_ai.operation.name"] = "chat"
            if "model" in span.metadata:
                attributes["gen_ai.request.model"] = span.metadata["model"]

        # Add custom metadata
        for k, v in span.metadata.items():
            if k not in ("agent_version",):
                attributes[f"agentguard.{k}"] = v

        otel_span = {
            "traceId": trace.trace_id.replace("-", "")[:32].ljust(32, "0"),
            "spanId": span.span_id.replace("-", "")[:16].ljust(16, "0"),
            "parentSpanId": (span.parent_span_id or "").replace("-", "")[:16].ljust(16, "0") if span.parent_span_id else "",
            "operationName": f"{span.span_type.value}:{span.name}",
            "startTime": span.started_at,
            "endTime": span.ended_at,
            "duration_ms": span.duration_ms,
            "status": {
                "code": "OK" if span.status.value == "completed" else "ERROR",
                "message": span.error or "",
            },
            "attributes": attributes,
        }

        otel_spans.append(otel_span)

    return otel_spans



def export_otel(trace: ExecutionTrace, filepath: str | None = None) -> dict:
    """Export trace to OpenTelemetry JSON format (resourceSpans envelope).

    Produces the standard OTel JSON structure that can be imported back
    via ``importer.import_otel()`` or sent to any OTel-compatible collector.

    Uses nanosecond Unix timestamps and attribute list format per the
    OTel specification.

    Args:
        trace: The execution trace to export.
        filepath: Optional file path to write JSON output.

    Returns:
        Dict in OTel ``resourceSpans`` format.
    """
    from datetime import datetime

    def _iso_to_unix_nano(iso: str | None) -> int:
        if not iso:
            return 0
        try:
            dt = datetime.fromisoformat(iso)
            return int(dt.timestamp() * 1e9)
        except (ValueError, TypeError):
            return 0

    def _attrs_to_otel(attributes: dict) -> list[dict]:
        """Convert flat dict to OTel attribute list format."""
        result = []
        for k, v in attributes.items():
            if isinstance(v, bool):
                result.append({"key": k, "value": {"boolValue": v}})
            elif isinstance(v, int):
                result.append({"key": k, "value": {"intValue": str(v)}})
            elif isinstance(v, float):
                result.append({"key": k, "value": {"doubleValue": v}})
            elif isinstance(v, list):
                str_vals = [{"stringValue": str(item)} for item in v]
                result.append({"key": k, "value": {"arrayValue": {"values": str_vals}}})
            else:
                result.append({"key": k, "value": {"stringValue": str(v)}})
        return result

    otel_spans = []
    trace_id_hex = trace.trace_id.replace("-", "")[:32].ljust(32, "0")

    for span in trace.spans:
        attributes = {
            "agentguard.span_type": span.span_type.value,
            "agentguard.task": trace.task,
        }

        if span.span_type.value == "agent":
            attributes["gen_ai.operation.name"] = "invoke_agent"
            attributes["gen_ai.agent.name"] = span.name
            ver = span.metadata.get("agent_version")
            if ver:
                attributes["gen_ai.agent.version"] = ver
        elif span.span_type.value == "tool":
            attributes["gen_ai.operation.name"] = "execute_tool"
            attributes["gen_ai.tool.name"] = span.name
        elif span.span_type.value == "llm_call":
            attributes["gen_ai.operation.name"] = "chat"
            model = span.metadata.get("model")
            if model:
                attributes["gen_ai.request.model"] = model
        elif span.span_type.value == "handoff":
            attributes["agentguard.handoff.from"] = span.handoff_from or ""
            attributes["agentguard.handoff.to"] = span.handoff_to or ""
            if span.context_size_bytes is not None:
                attributes["agentguard.handoff.context_size_bytes"] = span.context_size_bytes

        if span.error:
            attributes["error.message"] = span.error

        for k, v in span.metadata.items():
            if k not in ("agent_version", "model"):
                attr_key = f"agentguard.{k}" if not k.startswith("agentguard.") else k
                attributes[attr_key] = v

        span_id_hex = span.span_id.replace("-", "")[:16].ljust(16, "0")
        parent_hex = ""
        if span.parent_span_id:
            parent_hex = span.parent_span_id.replace("-", "")[:16].ljust(16, "0")

        status_code = 1 if span.status.value == "completed" else 2  # 1=Ok, 2=Error

        otel_span = {
            "traceId": trace_id_hex,
            "spanId": span_id_hex,
            "parentSpanId": parent_hex,
            "name": f"{span.span_type.value}:{span.name}",
            "kind": "INTERNAL",
            "startTimeUnixNano": _iso_to_unix_nano(span.started_at),
            "endTimeUnixNano": _iso_to_unix_nano(span.ended_at),
            "attributes": _attrs_to_otel(attributes),
            "status": {
                "code": status_code,
                "message": span.error or "",
            },
        }
        otel_spans.append(otel_span)

    result = {
        "resourceSpans": [{
            "resource": {
                "attributes": _attrs_to_otel({
                    "service.name": "agentguard",
                    "agentguard.trace_id": trace.trace_id,
                    "agentguard.task": trace.task,
                    "agentguard.trigger": trace.trigger,
                }),
            },
            "scopeSpans": [{
                "scope": {"name": "agentguard", "version": "0.1.0"},
                "spans": otel_spans,
            }],
        }],
    }

    if filepath:
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    return result


def trace_statistics(trace: ExecutionTrace) -> dict:
    """Compute statistics for a trace.

    Returns dict with:
    - total_spans, agent_count, tool_count
    - total_duration_ms, avg_span_duration_ms
    - error_count, error_rate
    - deepest_nesting (max depth of span tree)
    - slowest_span (name + duration)
    """
    spans = trace.spans
    if not spans:
        return {"total_spans": 0}

    durations = [s.duration_ms for s in spans if s.duration_ms is not None]
    errors = [s for s in spans if s.status.value == "failed"]

    # Calculate nesting depth
    depth_map = {}
    for s in spans:
        if s.parent_span_id is None:
            depth_map[s.span_id] = 0
        else:
            parent_depth = depth_map.get(s.parent_span_id, 0)
            depth_map[s.span_id] = parent_depth + 1

    max_depth = max(depth_map.values()) if depth_map else 0

    # Find slowest span
    slowest = max(spans, key=lambda s: s.duration_ms or 0)

    # Percentiles
    sorted_dur = sorted(durations)
    p50 = sorted_dur[len(sorted_dur) // 2] if sorted_dur else 0
    p95 = sorted_dur[int(len(sorted_dur) * 0.95)] if sorted_dur else 0
    p99 = sorted_dur[int(len(sorted_dur) * 0.99)] if sorted_dur else 0

    return {
        "total_spans": len(spans),
        "agent_count": len(trace.agent_spans),
        "tool_count": len(trace.tool_spans),
        "total_duration_ms": trace.duration_ms,
        "avg_span_duration_ms": sum(durations) / len(durations) if durations else 0,
        "p50_duration_ms": p50,
        "p95_duration_ms": p95,
        "p99_duration_ms": p99,
        "max_span_duration_ms": max(durations) if durations else 0,
        "error_count": len(errors),
        "error_rate": len(errors) / len(spans) if spans else 0,
        "deepest_nesting": max_depth,
        "slowest_span": {"name": slowest.name, "duration_ms": slowest.duration_ms},
        "total_tokens": sum(s.token_count or 0 for s in spans),
        "total_cost_usd": sum(s.estimated_cost_usd or 0 for s in spans),
    }
