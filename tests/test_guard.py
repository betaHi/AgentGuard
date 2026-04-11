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
        assert any("failed" in a["message"].lower() for a in alerts)


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
