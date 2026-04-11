"""Trace export utilities.

Export AgentGuard traces to various formats:
- JSON (native)
- JSONL (for streaming/logging)
- OTel-compatible format (for integration with observability platforms)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span


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
    
    return {
        "total_spans": len(spans),
        "agent_count": len(trace.agent_spans),
        "tool_count": len(trace.tool_spans),
        "total_duration_ms": trace.duration_ms,
        "avg_span_duration_ms": sum(durations) / len(durations) if durations else 0,
        "max_span_duration_ms": max(durations) if durations else 0,
        "error_count": len(errors),
        "error_rate": len(errors) / len(spans) if spans else 0,
        "deepest_nesting": max_depth,
        "slowest_span": {"name": slowest.name, "duration_ms": slowest.duration_ms},
    }
