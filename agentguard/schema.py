"""Trace schema validation — validate trace JSON against the schema.

Provides:
- JSON Schema definition for ExecutionTrace
- Validation functions with detailed error messages
- Schema versioning for forward compatibility
"""

from __future__ import annotations

from typing import Any

SCHEMA_VERSION = "0.1.0"

SPAN_SCHEMA = {
    "type": "object",
    "required": ["span_id", "span_type", "name", "status"],
    "properties": {
        "span_id": {"type": "string", "minLength": 1},
        "trace_id": {"type": "string"},
        "parent_span_id": {"type": ["string", "null"]},
        "span_type": {"type": "string", "enum": ["agent", "tool", "llm_call", "handoff"]},
        "name": {"type": "string"},
        "status": {"type": "string", "enum": ["running", "completed", "failed", "timeout"]},
        "started_at": {"type": ["string", "null"]},
        "ended_at": {"type": ["string", "null"]},
        "input_data": {},
        "output_data": {},
        "error": {"type": ["string", "null"]},
        "metadata": {"type": "object"},
        "handoff_from": {"type": ["string", "null"]},
        "handoff_to": {"type": ["string", "null"]},
        "context_passed": {"type": ["object", "null"]},
        "context_size_bytes": {"type": ["integer", "null"]},
        "context_received": {"type": ["object", "null"]},
        "context_used_keys": {"type": ["array", "null"]},
        "context_dropped_keys": {"type": ["array", "null"]},
        "retry_count": {"type": "integer", "minimum": 0},
        "retry_of": {"type": ["string", "null"]},
        "tags": {"type": "array", "items": {"type": "string"}},
        "token_count": {"type": ["integer", "null"]},
        "estimated_cost_usd": {"type": ["number", "null"]},
        "caused_by": {"type": ["string", "null"]},
        "failure_handled": {"type": "boolean"},
    },
}

TRACE_SCHEMA = {
    "type": "object",
    "required": ["trace_id", "status", "spans"],
    "properties": {
        "trace_id": {"type": "string", "minLength": 1},
        "task": {"type": "string"},
        "trigger": {"type": "string"},
        "started_at": {"type": ["string", "null"]},
        "ended_at": {"type": ["string", "null"]},
        "status": {"type": "string", "enum": ["running", "completed", "failed", "timeout"]},
        "duration_ms": {"type": ["number", "null"]},
        "spans": {"type": "array", "items": SPAN_SCHEMA},
        "metadata": {"type": "object"},
    },
}


def validate_trace_dict(data: dict) -> list[str]:
    """Validate a trace dictionary against the schema.
    
    Returns a list of error messages (empty if valid).
    Uses manual validation (no jsonschema dependency).
    """
    errors = []
    
    # Required fields
    for field in ["trace_id", "status", "spans"]:
        if field not in data:
            errors.append(f"Missing required field: {field}")
    
    if errors:
        return errors
    
    # Type checks
    if not isinstance(data["trace_id"], str) or not data["trace_id"]:
        errors.append("trace_id must be a non-empty string")
    
    valid_statuses = {"running", "completed", "failed", "timeout"}
    if data.get("status") not in valid_statuses:
        errors.append(f"Invalid status: {data.get('status')} (must be one of {valid_statuses})")
    
    if not isinstance(data.get("spans", []), list):
        errors.append("spans must be an array")
        return errors
    
    # Validate each span
    valid_types = {"agent", "tool", "llm_call", "handoff"}
    span_ids = set()
    
    for i, span in enumerate(data["spans"]):
        prefix = f"spans[{i}]"
        
        if not isinstance(span, dict):
            errors.append(f"{prefix}: must be an object")
            continue
        
        # Required span fields
        for field in ["span_id", "span_type", "name", "status"]:
            if field not in span:
                errors.append(f"{prefix}: missing required field '{field}'")
        
        if "span_id" in span:
            if span["span_id"] in span_ids:
                errors.append(f"{prefix}: duplicate span_id '{span['span_id']}'")
            span_ids.add(span["span_id"])
        
        if "span_type" in span and span["span_type"] not in valid_types:
            errors.append(f"{prefix}: invalid span_type '{span['span_type']}'")
        
        if "status" in span and span["status"] not in valid_statuses:
            errors.append(f"{prefix}: invalid status '{span['status']}'")
        
        # Parent reference check
        if span.get("parent_span_id") and span["parent_span_id"] not in span_ids:
            # Might be forward reference — check after all spans
            pass
    
    # Second pass: check parent references
    for i, span in enumerate(data["spans"]):
        parent_id = span.get("parent_span_id")
        if parent_id and parent_id not in span_ids:
            errors.append(f"spans[{i}]: parent_span_id '{parent_id}' references non-existent span")
    
    return errors


def validate_trace_json(json_str: str) -> list[str]:
    """Validate a trace JSON string."""
    import json
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        return [f"Invalid JSON: {e}"]
    return validate_trace_dict(data)


def get_schema() -> dict:
    """Get the trace JSON schema."""
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "AgentGuard ExecutionTrace",
        "version": SCHEMA_VERSION,
        **TRACE_SCHEMA,
    }
