"""Tests for cost-yield analysis."""

from agentguard.analysis import CostYieldReport, analyze_cost_yield
from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace


def _make_trace_with_costs():
    """Build a trace with varied cost/quality profiles."""
    return (TraceBuilder("cost-yield test")
        .agent("cheap-good", duration_ms=1000, token_count=500, cost_usd=0.01)
        .end()
        .agent("expensive-good", duration_ms=3000, token_count=5000, cost_usd=0.15)
        .end()
        .agent("expensive-bad", duration_ms=5000, token_count=8000, cost_usd=0.25,
               status="failed", error="out of tokens")
        .end()
        .build())


def test_basic_cost_yield():
    """Analyze a trace with agents of different cost/quality."""
    trace = _make_trace_with_costs()
    report = analyze_cost_yield(trace)

    assert isinstance(report, CostYieldReport)
    assert len(report.entries) == 3
    assert report.total_tokens == 500 + 5000 + 8000
    assert abs(report.total_cost_usd - 0.41) < 0.001
    assert report.highest_cost_agent == "expensive-bad"
    assert report.lowest_yield_agent == "expensive-bad"  # failed = 0 yield


def test_yield_score_components():
    """Yield score reflects completion, output presence, and output size."""
    trace = TraceBuilder("yield scoring")
    # Agent that completes with large output
    trace = (TraceBuilder("yield scoring")
        .agent("rich", duration_ms=100, token_count=100, cost_usd=0.01,
               output_data={"data": "x" * 2000})
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    # completed(50) + has_output(30) + >100B(10) + >1000B(10) = 100
    assert entry.yield_score == 100.0


def test_yield_score_no_output():
    """Completed agent without output gets partial yield."""
    trace = (TraceBuilder("no output")
        .agent("bare", duration_ms=100, token_count=0, cost_usd=0)
        .end()
        .build())
    report = analyze_cost_yield(trace)
    # completed(50) only, no output
    assert report.entries[0].yield_score == 50.0


def test_failed_agent_zero_yield():
    """Failed agent gets zero yield score."""
    trace = (TraceBuilder("failed")
        .agent("broken", duration_ms=100, token_count=1000, cost_usd=0.05,
               status="failed", error="crash")
        .end()
        .build())
    report = analyze_cost_yield(trace)
    assert report.entries[0].yield_score == 0.0
    assert report.entries[0].cost_per_success == float("inf")


def test_empty_trace():
    """Empty trace returns safe defaults."""
    trace = ExecutionTrace(task="empty")
    report = analyze_cost_yield(trace)
    assert len(report.entries) == 0
    assert report.total_cost_usd == 0.0
    assert report.total_tokens == 0
    assert report.highest_cost_agent == "N/A"
    assert report.lowest_yield_agent == "N/A"
    assert report.best_ratio_agent == "N/A"


def test_zero_cost_agents():
    """Agents with zero cost don't cause division errors."""
    trace = (TraceBuilder("free agents")
        .agent("free", duration_ms=100, token_count=0, cost_usd=0)
        .end()
        .build())
    report = analyze_cost_yield(trace)
    assert report.entries[0].cost_per_success == 0.0
    assert report.entries[0].tokens_per_ms == 0.0


def test_to_dict_serializable():
    """to_dict output must be JSON-serializable."""
    import json
    trace = _make_trace_with_costs()
    report = analyze_cost_yield(trace)
    d = report.to_dict()
    serialized = json.dumps(d)
    assert "expensive-bad" in serialized
    # inf should be "N/A", not Infinity
    assert "Infinity" not in serialized


def test_to_report_readable():
    """to_report produces human-readable markdown."""
    trace = _make_trace_with_costs()
    report = analyze_cost_yield(trace)
    text = report.to_report()
    assert "# Cost-Yield Analysis" in text
    assert "expensive-bad" in text
    assert "N/A (failed)" in text


def test_best_ratio_prefers_high_yield_low_cost():
    """Best ratio agent should be the one with highest yield per dollar."""
    trace = (TraceBuilder("ratio test")
        .agent("cheap-good", duration_ms=100, token_count=100, cost_usd=0.001,
               output_data={"result": "x" * 500})
        .end()
        .agent("expensive-ok", duration_ms=100, token_count=5000, cost_usd=1.0,
               output_data={"result": "y"})
        .end()
        .build())
    report = analyze_cost_yield(trace)
    assert report.best_ratio_agent == "cheap-good"
