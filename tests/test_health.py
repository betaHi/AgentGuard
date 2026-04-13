"""Tests for health report."""

import tempfile
from pathlib import Path

from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.health import generate_health_report


def test_health_report_basic():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()

        # 3 successful traces
        for i in range(3):
            t = ExecutionTrace(task=f"task-{i}")
            s = Span(name="good-agent", span_type=SpanType.AGENT)
            s.complete()
            t.add_span(s)
            t.complete()
            (traces_dir / f"{t.trace_id}.json").write_text(t.to_json())

        # 1 failed trace
        t = ExecutionTrace(task="bad")
        s = Span(name="good-agent", span_type=SpanType.AGENT)
        s.fail("oops")
        t.add_span(s)
        t.fail()
        (traces_dir / f"{t.trace_id}.json").write_text(t.to_json())

        report = generate_health_report(str(traces_dir))
        assert report.total_traces == 4
        assert len(report.agents) == 1
        assert report.agents[0].success_rate == 0.75
        assert report.overall_health == "warning"  # 75% < 0.8 warning threshold


def test_health_critical():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()

        # All failures
        for i in range(5):
            t = ExecutionTrace(task=f"fail-{i}")
            s = Span(name="bad-agent", span_type=SpanType.AGENT)
            s.fail("crash")
            t.add_span(s)
            t.fail()
            (traces_dir / f"{t.trace_id}.json").write_text(t.to_json())

        report = generate_health_report(str(traces_dir))
        assert report.overall_health == "critical"
        assert report.agents[0].status == "critical"


def test_health_report_output():
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()

        t = ExecutionTrace(task="test")
        s = Span(name="agent-x", span_type=SpanType.AGENT)
        s.complete()
        t.add_span(s)
        t.complete()
        (traces_dir / f"{t.trace_id}.json").write_text(t.to_json())

        report = generate_health_report(str(traces_dir))
        text = report.to_report()
        assert "Health Report" in text
        assert "agent-x" in text
