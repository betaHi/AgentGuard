"""Top-of-report 3-bullet executive summary."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.web.viewer import trace_to_html_string, _executive_summary_bullets


def _span(sid, name, parent, *, cost=0.0, dur=1000, out=None):
    start = datetime(2024, 1, 1, tzinfo=timezone.utc).isoformat()
    end = datetime(2024, 1, 1, 0, 0, int(dur / 1000), tzinfo=timezone.utc).isoformat()
    return Span(
        span_id=sid, trace_id="t", name=name, parent_span_id=parent,
        span_type=SpanType.AGENT, status=SpanStatus.COMPLETED,
        started_at=start, ended_at=end,
        estimated_cost_usd=cost,
        output_data=out,
    )


def _trace_with_signals() -> ExecutionTrace:
    trace = ExecutionTrace(trace_id="t", task="demo", trigger="unit-test")
    trace.metadata["claude.stop_reason"] = "max_tokens"
    trace.metadata["claude.deliverables_count"] = 0
    trace.add_span(_span("root", "root", None, dur=10000))
    trace.add_span(_span("a1", "expensive-agent", "root", cost=12.50, dur=5000))
    trace.add_span(_span("a2", "cheap-agent", "root", cost=0.10, dur=500))
    trace.complete()
    return trace


def test_executive_summary_renders_top_of_report():
    trace = _trace_with_signals()
    html = trace_to_html_string(trace)
    assert 'class="exec-summary"' in html
    assert "Top 3 takeaways" in html
    # The max_tokens stop reason must surface as a headline bullet.
    assert "Did not finish cleanly" in html


def test_executive_summary_limits_to_three_bullets():
    bullets = _executive_summary_bullets(_trace_with_signals())
    assert len(bullets) <= 3


def test_clean_trace_may_produce_fewer_bullets():
    trace = ExecutionTrace(trace_id="t", task="tiny", trigger="unit-test")
    trace.add_span(_span("root", "root", None, dur=100))
    trace.complete()
    # No failures / no costs / no handoffs — bullets may be empty, but must
    # not raise and must not inject a broken summary block.
    html = trace_to_html_string(trace)
    assert "<html" in html.lower() or "<!doctype" in html.lower()


def test_summary_appears_before_diagnostic_grid():
    trace = _trace_with_signals()
    html = trace_to_html_string(trace)
    i_summary = html.find("exec-summary")
    i_grid = html.find("Orchestration Diagnostics")
    assert i_summary != -1 and i_grid != -1
    assert i_summary < i_grid, "executive summary must precede the diagnostics grid"
