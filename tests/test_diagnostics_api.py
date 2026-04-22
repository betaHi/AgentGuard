"""Smoke test for the curated ``agentguard.diagnostics`` public API."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentguard import diagnostics
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _trivial_trace() -> ExecutionTrace:
    trace = ExecutionTrace(trace_id="t1", task="demo", trigger="unit-test")
    root = Span(
        span_id="s1",
        trace_id="t1",
        name="root",
        span_type=SpanType.AGENT,
        status=SpanStatus.COMPLETED,
        started_at=datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat(),
        ended_at=datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc).isoformat(),
    )
    trace.add_span(root)
    trace.complete()
    return trace


def test_public_surface_exports_are_callable():
    """All re-exported callables must actually be callable (no broken imports)."""
    for name in (
        "score_trace",
        "analyze_failures", "analyze_flow", "analyze_bottleneck",
        "analyze_context_flow", "analyze_cost", "analyze_cost_yield",
        "analyze_decisions", "analyze_counterfactual", "analyze_timing",
        "import_claude_session", "list_claude_sessions",
        "diagnose", "render_html_report",
    ):
        assert callable(getattr(diagnostics, name)), name


def test_diagnose_returns_composite_report():
    trace = _trivial_trace()
    report = diagnostics.diagnose(trace)
    assert isinstance(report, diagnostics.DiagnosticReport)
    assert report.trace is trace
    assert report.score is not None
    assert report.failures is not None
    assert report.bottleneck is not None
    assert report.context_flow is not None
    assert report.cost_yield is not None
    assert report.decisions is not None


def test_diagnose_report_to_dict_is_json_friendly():
    import json
    trace = _trivial_trace()
    report = diagnostics.diagnose(trace)
    payload = report.to_dict()
    assert payload["trace_id"] == "t1"
    # Must round-trip through json without errors.
    json.dumps(payload, default=str)


def test_render_html_report_returns_string():
    html = diagnostics.render_html_report(_trivial_trace())
    assert "<html" in html.lower() or "<!doctype" in html.lower()


def test_render_html_report_writes_to_path(tmp_path):
    out = tmp_path / "report.html"
    result = diagnostics.render_html_report(_trivial_trace(), output_path=str(out))
    assert result == str(out)
    assert out.exists()
    assert out.stat().st_size > 0


def test_all_listed_names_are_exported():
    for name in diagnostics.__all__:
        assert hasattr(diagnostics, name), name
