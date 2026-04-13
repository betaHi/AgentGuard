"""Tests for span duration anomaly detection."""

import json

from agentguard.analysis import _compute_baseline, detect_duration_anomalies
from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace


def _baseline():
    return {"researcher": 100.0, "writer": 200.0, "search": 50.0}


def test_no_anomaly_within_threshold():
    """Spans within 3x baseline are not flagged."""
    trace = (TraceBuilder("normal")
        .agent("researcher", duration_ms=250).end()  # 2.5x = under 3x
        .agent("writer", duration_ms=400).end()       # 2x
        .build())
    report = detect_duration_anomalies(trace, baseline=_baseline())
    assert report.anomaly_count == 0


def test_warning_at_3x():
    """Span at 3x+ baseline is flagged as warning."""
    trace = (TraceBuilder("slow")
        .agent("researcher", duration_ms=350).end()  # 3.5x
        .agent("writer", duration_ms=200).end()       # 1x
        .build())
    report = detect_duration_anomalies(trace, baseline=_baseline())
    assert report.anomaly_count == 1
    assert report.anomalies[0].span_name == "researcher"
    assert report.anomalies[0].severity == "warning"
    assert report.anomalies[0].ratio >= 3.0


def test_critical_at_10x():
    """Span at 10x+ baseline is flagged as critical."""
    trace = (TraceBuilder("very slow")
        .agent("researcher", duration_ms=1200).end()  # 12x
        .build())
    report = detect_duration_anomalies(trace, baseline=_baseline())
    assert report.anomaly_count == 1
    assert report.anomalies[0].severity == "critical"


def test_custom_threshold():
    """Custom threshold works."""
    trace = (TraceBuilder("custom")
        .agent("researcher", duration_ms=220).end()  # 2.2x
        .build())
    report = detect_duration_anomalies(trace, baseline=_baseline(), threshold=2.0)
    assert report.anomaly_count == 1


def test_no_baseline_no_flags():
    """Spans without baseline data are skipped."""
    trace = (TraceBuilder("unknown")
        .agent("new-agent", duration_ms=9999).end()
        .build())
    report = detect_duration_anomalies(trace, baseline=_baseline())
    assert report.anomaly_count == 0
    assert report.total_spans_checked == 0


def test_empty_trace():
    """Empty trace returns clean report."""
    trace = ExecutionTrace(task="empty")
    report = detect_duration_anomalies(trace, baseline=_baseline())
    assert report.anomaly_count == 0
    assert report.total_spans_checked == 0


def test_compute_baseline_from_traces():
    """Baseline computed from reference traces."""
    refs = [
        TraceBuilder("ref1").agent("a", duration_ms=100).end().build(),
        TraceBuilder("ref2").agent("a", duration_ms=200).end().build(),
    ]
    baseline = _compute_baseline(refs)
    assert abs(baseline["a"] - 150.0) < 0.1


def test_reference_traces_parameter():
    """detect_duration_anomalies computes baseline from reference_traces."""
    refs = [
        TraceBuilder("ref").agent("a", duration_ms=100).end().build(),
    ]
    trace = TraceBuilder("current").agent("a", duration_ms=500).end().build()
    report = detect_duration_anomalies(trace, reference_traces=refs)
    assert report.anomaly_count == 1
    assert report.anomalies[0].ratio >= 3.0


def test_to_dict_serializable():
    """Report is JSON-serializable."""
    trace = TraceBuilder("slow").agent("researcher", duration_ms=500).end().build()
    report = detect_duration_anomalies(trace, baseline=_baseline())
    serialized = json.dumps(report.to_dict())
    assert "researcher" in serialized


def test_to_report_readable():
    """Report text is human-readable."""
    trace = TraceBuilder("slow").agent("researcher", duration_ms=500).end().build()
    report = detect_duration_anomalies(trace, baseline=_baseline())
    text = report.to_report()
    assert "researcher" in text
    assert "baseline" in text


def test_tool_spans_detected():
    """Tool spans are also checked against baseline."""
    trace = (TraceBuilder("tools")
        .agent("researcher", duration_ms=100)
            .tool("search", duration_ms=200)  # 4x baseline
        .end()
        .build())
    report = detect_duration_anomalies(trace, baseline=_baseline())
    assert any(a.span_name == "search" for a in report.anomalies)
