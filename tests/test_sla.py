"""Tests for SLA checker."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.sla import SLAChecker


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _fast_good_trace():
    t = ExecutionTrace(task="fast", started_at=_ts(0), ended_at=_ts(2), status=SpanStatus.COMPLETED)
    t.add_span(Span(name="a", status=SpanStatus.COMPLETED, started_at=_ts(0), ended_at=_ts(2)))
    return t


def _slow_bad_trace():
    t = ExecutionTrace(task="slow", started_at=_ts(0), ended_at=_ts(60), status=SpanStatus.FAILED)
    t.add_span(Span(name="a", status=SpanStatus.FAILED, error="timeout",
                   started_at=_ts(0), ended_at=_ts(60), estimated_cost_usd=5.0))
    return t


class TestSLAChecker:
    def test_all_pass(self):
        sla = SLAChecker().max_duration_ms(10000).min_success_rate(0.9)
        result = sla.check(_fast_good_trace())
        assert result.passed
        assert len(result.violations) == 0

    def test_duration_violation(self):
        sla = SLAChecker().max_duration_ms(5000)
        result = sla.check(_slow_bad_trace())
        assert not result.passed
        assert any("duration" in v.constraint for v in result.violations)

    def test_success_rate_violation(self):
        sla = SLAChecker().min_success_rate(0.99)
        result = sla.check(_slow_bad_trace())
        assert not result.passed

    def test_cost_violation(self):
        sla = SLAChecker().max_cost_usd(1.0)
        result = sla.check(_slow_bad_trace())
        assert not result.passed

    def test_score_violation(self):
        sla = SLAChecker().min_score(80)
        result = sla.check(_slow_bad_trace())
        assert not result.passed

    def test_chaining(self):
        sla = (SLAChecker()
            .max_duration_ms(10000)
            .min_success_rate(0.9)
            .max_cost_usd(10.0)
            .min_score(50))
        result = sla.check(_fast_good_trace())
        assert result.checks_run == 4

    def test_batch(self):
        sla = SLAChecker().min_success_rate(0.9)
        result = sla.check_batch([_fast_good_trace(), _slow_bad_trace()])
        assert result["traces_checked"] == 2
        assert result["traces_passed"] == 1

    def test_report(self):
        sla = SLAChecker().max_duration_ms(1000)
        result = sla.check(_slow_bad_trace())
        report = result.to_report()
        assert "FAILED" in report

    def test_to_dict(self):
        sla = SLAChecker().max_duration_ms(5000)
        result = sla.check(_fast_good_trace())
        d = result.to_dict()
        assert "passed" in d
        assert "violations" in d
