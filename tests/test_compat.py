"""Tests for trace compatibility."""

import pytest
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus
from agentguard.compat import (
    get_schema_version, needs_migration, migrate,
    check_compatibility, CURRENT_SCHEMA_VERSION,
)


class TestCompat:
    def test_current_version(self):
        trace = ExecutionTrace(task="test")
        trace.add_span(Span(name="a", status=SpanStatus.COMPLETED))
        data = trace.to_dict()
        data["schema_version"] = CURRENT_SCHEMA_VERSION
        assert not needs_migration(data)

    def test_old_version_needs_migration(self):
        data = {"trace_id": "x", "status": "completed", "spans": [],
                "schema_version": "0.1.0"}
        assert needs_migration(data)

    def test_no_version_is_old(self):
        data = {"trace_id": "x", "status": "completed", "spans": []}
        assert get_schema_version(data) == "0.1.0"

    def test_migrate_adds_fields(self):
        data = {
            "trace_id": "x", "status": "completed",
            "spans": [{"span_id": "s1", "span_type": "agent", "name": "a", "status": "completed"}],
        }
        migrated = migrate(data)
        assert migrated["schema_version"] == CURRENT_SCHEMA_VERSION
        assert migrated["spans"][0].get("context_received") is None  # default

    def test_check_compatible(self):
        data = {
            "trace_id": "x", "status": "completed",
            "schema_version": CURRENT_SCHEMA_VERSION,
            "spans": [{"span_id": "s1", "span_type": "agent", "name": "a", "status": "completed"}],
        }
        result = check_compatibility(data)
        assert result["compatible"]

    def test_check_unknown_type(self):
        data = {
            "trace_id": "x", "status": "completed",
            "spans": [{"span_id": "s1", "span_type": "unknown", "name": "a", "status": "completed"}],
        }
        result = check_compatibility(data)
        assert len(result["issues"]) >= 1
