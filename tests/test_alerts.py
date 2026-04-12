"""Tests for alert rules engine."""

import pytest
from datetime import datetime, timezone, timedelta
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.alerts import (
    AlertEngine, Alert,
    rule_score_below, rule_error_rate_above,
    rule_duration_above, rule_cost_above, rule_trace_failed,
)


def _ts(offset_s: float = 0) -> str:
    base = datetime(2026, 4, 12, 0, 0, 0, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset_s)).isoformat()


def _good_trace():
    t = ExecutionTrace(task="good", started_at=_ts(0), ended_at=_ts(3), status=SpanStatus.COMPLETED)
    t.add_span(Span(name="a", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
                   started_at=_ts(0), ended_at=_ts(3)))
    return t


def _bad_trace():
    t = ExecutionTrace(task="bad", started_at=_ts(0), ended_at=_ts(10), status=SpanStatus.FAILED)
    t.add_span(Span(name="a", status=SpanStatus.FAILED, error="crash",
                   started_at=_ts(0), ended_at=_ts(10),
                   estimated_cost_usd=5.0))
    return t


class TestAlertRules:
    def test_score_below(self):
        rule = rule_score_below(90)
        alert = rule(_bad_trace())
        assert alert is not None
        assert alert.severity == "warning"

    def test_score_above_threshold(self):
        rule = rule_score_below(10)
        alert = rule(_good_trace())
        assert alert is None

    def test_error_rate(self):
        rule = rule_error_rate_above(0.1)
        alert = rule(_bad_trace())
        assert alert is not None

    def test_duration(self):
        rule = rule_duration_above(5000)
        alert = rule(_bad_trace())  # 10s
        assert alert is not None

    def test_cost(self):
        rule = rule_cost_above(1.0)
        alert = rule(_bad_trace())  # $5
        assert alert is not None

    def test_trace_failed(self):
        rule = rule_trace_failed()
        assert rule(_bad_trace()) is not None
        assert rule(_good_trace()) is None


class TestAlertEngine:
    def test_evaluate(self):
        engine = AlertEngine()
        engine.add_rule(rule_trace_failed())
        engine.add_rule(rule_score_below(90))
        
        alerts = engine.evaluate(_bad_trace())
        assert len(alerts) >= 1

    def test_no_alerts(self):
        engine = AlertEngine()
        engine.add_rule(rule_trace_failed())
        
        alerts = engine.evaluate(_good_trace())
        assert len(alerts) == 0

    def test_batch(self):
        engine = AlertEngine()
        engine.add_rule(rule_trace_failed())
        
        alerts = engine.evaluate_batch([_good_trace(), _bad_trace(), _good_trace()])
        assert len(alerts) == 1

    def test_alert_dict(self):
        rule = rule_trace_failed()
        alert = rule(_bad_trace())
        d = alert.to_dict()
        assert "rule" in d
        assert "severity" in d
