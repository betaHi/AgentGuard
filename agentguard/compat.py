"""Trace compatibility — check and migrate traces between schema versions.

As the trace schema evolves, this module ensures:
- Old traces can be read by new code
- New fields get sensible defaults
- Schema version is tracked
"""

from __future__ import annotations

from typing import Any

CURRENT_SCHEMA_VERSION = "0.2.0"

# Migration functions: version -> version
_MIGRATIONS = {}


def _migrate_0_1_to_0_2(data: dict) -> dict:
    """Migrate from schema 0.1 to 0.2 (add new handoff fields)."""
    for span in data.get("spans", []):
        # Add new fields with defaults
        span.setdefault("context_received", None)
        span.setdefault("context_used_keys", None)
        span.setdefault("context_dropped_keys", None)
    data.setdefault("schema_version", "0.2.0")
    return data

_MIGRATIONS[("0.1.0", "0.2.0")] = _migrate_0_1_to_0_2


def get_schema_version(data: dict) -> str:
    """Get the schema version of a trace dict."""
    return data.get("schema_version", "0.1.0")


def needs_migration(data: dict) -> bool:
    """Check if a trace needs migration to current schema."""
    return get_schema_version(data) != CURRENT_SCHEMA_VERSION


def migrate(data: dict) -> dict:
    """Migrate a trace dict to the current schema version.
    
    Applies all necessary migrations in sequence.
    """
    version = get_schema_version(data)
    
    if version == CURRENT_SCHEMA_VERSION:
        return data
    
    # Apply migrations in order
    migration_path = [
        ("0.1.0", "0.2.0"),
    ]
    
    for from_ver, to_ver in migration_path:
        if version == from_ver:
            fn = _MIGRATIONS.get((from_ver, to_ver))
            if fn:
                data = fn(data)
                version = to_ver
    
    data["schema_version"] = CURRENT_SCHEMA_VERSION
    return data


def check_compatibility(data: dict) -> dict:
    """Check trace compatibility and return a report."""
    version = get_schema_version(data)
    current = CURRENT_SCHEMA_VERSION
    
    issues = []
    
    # Check for unknown span types
    valid_types = {"agent", "tool", "llm_call", "handoff"}
    for span in data.get("spans", []):
        if span.get("span_type") not in valid_types:
            issues.append(f"Unknown span type: {span.get('span_type')}")
    
    # Check for missing required fields
    for i, span in enumerate(data.get("spans", [])):
        if "span_id" not in span:
            issues.append(f"spans[{i}]: missing span_id")
        if "name" not in span:
            issues.append(f"spans[{i}]: missing name")
    
    return {
        "schema_version": version,
        "current_version": current,
        "compatible": version == current or len(issues) == 0,
        "needs_migration": version != current,
        "issues": issues,
    }
