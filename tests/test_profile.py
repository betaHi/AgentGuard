"""Tests for agent profiling."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.profile import build_agent_profiles


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _make_traces():
    traces = []
    for i in range(3):
        t = ExecutionTrace(task=f"run_{i}", started_at=_ts(i * 20), ended_at=_ts(i * 20 + 10))
        t.add_span(Span(name="researcher", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                       started_at=_ts(i * 20), ended_at=_ts(i * 20 + 5),
                       token_count=1000, estimated_cost_usd=0.03))
        t.add_span(Span(name="h1", span_type=SpanType.HANDOFF, status=SpanStatus.COMPLETED,
                       handoff_from="researcher", handoff_to="writer"))
        t.add_span(Span(name="writer", span_type=SpanType.AGENT,
                       status=SpanStatus.COMPLETED if i < 2 else SpanStatus.FAILED,
                       error="timeout" if i >= 2 else None,
                       started_at=_ts(i * 20 + 5), ended_at=_ts(i * 20 + 10),
                       token_count=2000, estimated_cost_usd=0.06))
        traces.append(t)
    return traces


class TestAgentProfiles:
    def test_basic(self):
        profiles = build_agent_profiles(_make_traces())
        assert "researcher" in profiles
        assert "writer" in profiles

    def test_invocation_count(self):
        profiles = build_agent_profiles(_make_traces())
        assert profiles["researcher"].total_invocations == 3
        assert profiles["writer"].total_invocations == 3

    def test_success_rate(self):
        profiles = build_agent_profiles(_make_traces())
        assert profiles["researcher"].success_rate == 1.0
        assert profiles["writer"].success_rate == pytest.approx(2/3, abs=0.01)

    def test_errors_tracked(self):
        profiles = build_agent_profiles(_make_traces())
        assert len(profiles["writer"].errors) == 1
        assert "timeout" in profiles["writer"].errors[0]

    def test_handoff_tracking(self):
        profiles = build_agent_profiles(_make_traces())
        assert "writer" in profiles["researcher"].handoff_to
        assert profiles["researcher"].handoff_to["writer"] == 3

    def test_tokens_cost(self):
        profiles = build_agent_profiles(_make_traces())
        assert profiles["researcher"].total_tokens == 3000
        assert profiles["writer"].total_cost_usd == pytest.approx(0.18, abs=0.01)

    def test_report(self):
        profiles = build_agent_profiles(_make_traces())
        report = profiles["researcher"].to_report()
        assert "researcher" in report
        assert "Invocations" in report

    def test_to_dict(self):
        profiles = build_agent_profiles(_make_traces())
        d = profiles["researcher"].to_dict()
        assert "success_rate" in d
        assert "handoff_to" in d

    def test_empty(self):
        profiles = build_agent_profiles([])
        assert profiles == {}
