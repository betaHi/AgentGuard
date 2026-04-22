"""Tests for ``--expected-artifact`` downgrade on diagnose-claude-session."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentguard.cli.main import _apply_expected_artifacts
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _trace() -> ExecutionTrace:
    trace = ExecutionTrace(trace_id="t", task="demo", trigger="unit-test")
    trace.metadata["claude.stop_reason"] = "end_turn"
    trace.metadata["claude.completion_signal"] = 1.0
    root = Span(
        span_id="s", trace_id="t", name="root",
        span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        ended_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc).isoformat(),
        metadata={"claude.stop_reason": "end_turn", "claude.quality": 1.0},
    )
    trace.add_span(root)
    return trace


def test_missing_artifact_downgrades_completion_signal(tmp_path):
    trace = _trace()
    _apply_expected_artifacts(trace, [str(tmp_path / "not-there.md")])
    assert trace.metadata["claude.completion_signal"] == 0.0
    assert trace.metadata["claude.stop_reason"] == "missing_expected_artifacts"
    assert trace.spans[0].metadata["claude.quality"] == 0.0
    assert trace.metadata["expected_artifacts.missing"] == [
        str(tmp_path / "not-there.md")
    ]


def test_existing_artifact_preserves_signal(tmp_path):
    artifact = tmp_path / "out.md"
    artifact.write_text("done", encoding="utf-8")
    trace = _trace()
    _apply_expected_artifacts(trace, [str(artifact)])
    assert trace.metadata["claude.completion_signal"] == 1.0
    assert trace.metadata["claude.stop_reason"] == "end_turn"
    assert trace.metadata["expected_artifacts.missing"] == []


def test_no_paths_is_noop():
    trace = _trace()
    _apply_expected_artifacts(trace, [])
    assert "expected_artifacts.checked" not in trace.metadata
    assert trace.metadata["claude.completion_signal"] == 1.0
