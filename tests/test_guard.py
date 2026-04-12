"""Tests for guard mode."""

import json
import tempfile
from pathlib import Path
from agentguard.guard import Guard, StdoutAlert, FileAlert
from agentguard.core.trace import ExecutionTrace, Span, SpanType


def test_guard_detects_failure():
    """Guard detects failed traces and alerts."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        # Create a failed trace
        trace = ExecutionTrace(task="test")
        span = Span(name="agent-1", span_type=SpanType.AGENT)
        span.fail("timeout")
        trace.add_span(span)
        trace.fail()
        (traces_dir / f"{trace.trace_id}.json").write_text(trace.to_json())
        
        alerts = []
        class CaptureAlert:
            def send(self, message, severity="warning", metadata=None):
                alerts.append({"message": message, "severity": severity})
        
        guard = Guard(traces_dir=str(traces_dir), alert_handlers=[CaptureAlert()])
        guard.check_new_traces()
        
        assert len(alerts) > 0
        assert len(alerts) > 0, f"Expected alerts, got none"


def test_guard_consecutive_fails():
    """Guard detects consecutive failures and escalates severity."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        alerts = []
        class CaptureAlert:
            def send(self, message, severity="warning", metadata=None):
                alerts.append({"message": message, "severity": severity})
        
        guard = Guard(traces_dir=str(traces_dir), alert_handlers=[CaptureAlert()], fail_threshold=2)
        
        # Create 2 failed traces
        for i in range(2):
            trace = ExecutionTrace(task=f"test-{i}")
            span = Span(name="flaky-agent", span_type=SpanType.AGENT)
            span.fail("error")
            trace.add_span(span)
            trace.fail()
            (traces_dir / f"{trace.trace_id}.json").write_text(trace.to_json())
        
        guard.check_new_traces()
        
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical_alerts) > 0


def test_file_alert():
    """FileAlert writes to JSONL file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        filepath = Path(tmpdir) / "alerts.jsonl"
        alert = FileAlert(str(filepath))
        alert.send("test alert", severity="warning")
        
        assert filepath.exists()
        data = json.loads(filepath.read_text().strip())
        assert data["message"] == "test alert"


def test_guard_detects_regression():
    """Guard detects when a previously passing agent starts failing (regression)."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()

        alerts = []

        class CaptureAlert:
            def send(self, message, severity="warning", metadata=None):
                alerts.append({"message": message, "severity": severity, "metadata": metadata})

        guard = Guard(
            traces_dir=str(traces_dir),
            alert_handlers=[CaptureAlert()],
            fail_threshold=2,
        )

        # Phase 1: Agent succeeds — no alerts expected
        trace_ok = ExecutionTrace(task="healthy run")
        span_ok = Span(name="data-agent", span_type=SpanType.AGENT)
        span_ok.complete(output={"status": "ok"})
        trace_ok.add_span(span_ok)
        trace_ok.complete()
        (traces_dir / f"{trace_ok.trace_id}.json").write_text(trace_ok.to_json())

        guard.check_new_traces()
        assert len(alerts) == 0, "No alerts expected for passing trace"
        assert guard._consecutive_fails.get("data-agent", 0) == 0

        # Phase 2: Agent starts failing (regression) — warnings expected
        for i in range(2):
            trace_fail = ExecutionTrace(task=f"regression run {i}")
            span_fail = Span(name="data-agent", span_type=SpanType.AGENT)
            span_fail.fail("RuntimeError: upstream API changed response format")
            trace_fail.add_span(span_fail)
            trace_fail.fail()
            (traces_dir / f"{trace_fail.trace_id}.json").write_text(trace_fail.to_json())

        guard.check_new_traces()

        # Should have warning alerts for failures
        warning_alerts = [a for a in alerts if a["severity"] == "warning"]
        assert len(warning_alerts) >= 1, "Expected warning alerts for failed traces"

        # Should escalate to critical after threshold consecutive failures
        critical_alerts = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical_alerts) >= 1, "Expected critical alert after consecutive failures"
        assert "data-agent" in critical_alerts[0]["message"]

        # Phase 3: Agent recovers — counter should reset
        alerts.clear()
        trace_recover = ExecutionTrace(task="recovery run")
        span_recover = Span(name="data-agent", span_type=SpanType.AGENT)
        span_recover.complete(output={"status": "recovered"})
        trace_recover.add_span(span_recover)
        trace_recover.complete()
        (traces_dir / f"{trace_recover.trace_id}.json").write_text(trace_recover.to_json())

        guard.check_new_traces()
        assert guard._consecutive_fails.get("data-agent", 0) == 0, "Counter should reset after recovery"
        assert len(alerts) == 0, "No alerts expected after recovery"


def test_guard_watch_max_iterations():
    """Guard.watch() respects max_iterations and stops."""
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()

        guard = Guard(traces_dir=str(traces_dir), alert_handlers=[])
        # Should complete without hanging
        guard.watch(interval=0, max_iterations=3)
