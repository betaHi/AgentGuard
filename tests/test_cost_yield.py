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


def test_explicit_quality_signal_beats_output_size_heuristic():
    """A large output with poor explicit quality should not look high-yield."""
    trace = (TraceBuilder("quality signal")
        .agent(
            "large-but-bad",
            duration_ms=1000,
            token_count=2000,
            cost_usd=0.08,
            output_data={"summary": "x" * 3000, "quality": 0.2},
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    assert entry.quality_signal == 0.2
    assert entry.yield_score < 60


def test_quality_verdict_affects_default_yield():
    """Qualitative verdicts should lower default yield without a custom fn."""
    trace = (TraceBuilder("verdict signal")
        .agent(
            "regressed-agent",
            duration_ms=1000,
            token_count=1000,
            cost_usd=0.05,
            output_data={"result": "x" * 500, "verdict": "regressed"},
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    assert entry.quality_signal is not None
    assert entry.quality_signal <= 0.1
    assert entry.yield_score < 50


def test_quality_signal_serialized_and_reported():
    """Structured output should expose quality evidence for Q4 diagnostics."""
    trace = (TraceBuilder("quality evidence")
        .agent(
            "scored",
            duration_ms=100,
            token_count=100,
            cost_usd=0.01,
            output_data={"quality": 0.8, "confidence": 0.6},
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    payload = report.to_dict()["agents"][0]
    assert payload["quality_signal"] is not None
    assert "quality" in payload["quality_evidence"]
    assert "quality signal" in report.to_report().lower()


def test_evaluation_result_shape_affects_default_yield():
    """Evaluation-style pass/fail summaries should influence default yield."""
    trace = (TraceBuilder("eval quality")
        .agent(
            "evaluated-agent",
            duration_ms=200,
            token_count=300,
            cost_usd=0.02,
            output_data={
                "overall": "fail",
                "passed": 1,
                "failed": 2,
                "total": 3,
                "rules": [
                    {"name": "enough", "verdict": "pass"},
                    {"name": "fresh", "verdict": "fail"},
                    {"name": "complete", "verdict": "fail"},
                ],
            },
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    assert entry.quality_signal is not None
    assert entry.quality_signal < 0.4
    assert "evaluation_rules" in entry.quality_evidence or "rule_verdicts" in entry.quality_evidence
    assert entry.yield_score < 50


def test_replay_comparison_shape_affects_default_yield():
    """Replay/comparison-style regressions should lower default yield."""
    trace = (TraceBuilder("replay quality")
        .agent(
            "candidate-agent",
            duration_ms=300,
            token_count=400,
            cost_usd=0.03,
            output_data={
                "verdict": "regressed",
                "comparison": {
                    "improved": 0,
                    "regressed": 2,
                    "recommendation": "review_before_deploy",
                },
            },
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    assert entry.quality_signal is not None
    assert entry.quality_signal < 0.35
    assert "comparison_result" in entry.quality_evidence
    assert entry.yield_score < 45


def test_grounding_signal_affects_default_yield():
    """Unsupported claims and missing citations should lower default yield."""
    trace = (TraceBuilder("grounding quality")
        .agent(
            "fact-checker",
            duration_ms=400,
            token_count=800,
            cost_usd=0.04,
            output_data={
                "claims": ["c1", "c2", "c3"],
                "citations": ["doc-1", "doc-2"],
                "unsupported_claims": ["c3"],
                "missing_citation_ids": ["doc-3"],
                "verdict": "needs_revision",
            },
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    assert entry.quality_signal is not None
    assert entry.quality_signal < 0.6
    assert "grounding_integrity" in entry.quality_evidence
    assert entry.yield_score < 70


def test_unverified_claims_lower_default_yield():
    """Draft outputs with unverified claims should not look fully high-yield."""
    trace = (TraceBuilder("unverified claims")
        .agent(
            "generator",
            duration_ms=1200,
            token_count=1600,
            cost_usd=0.07,
            output_data={
                "claims": ["c1", "c2", "c3"],
                "citations": ["doc-1", "doc-2"],
                "unverified_claims": ["c3"],
            },
        )
        .end()
        .build())
    report = analyze_cost_yield(trace)
    entry = report.entries[0]
    assert entry.quality_signal is not None
    assert entry.quality_signal < 0.75
    assert "grounding_integrity" in entry.quality_evidence


def test_path_summaries_include_grounding_breakdown():
    """Path summaries should aggregate claim grounding signals, not just yield."""
    trace = (TraceBuilder("path grounding")
        .agent("coordinator", duration_ms=5000)
            .agent(
                "generator",
                duration_ms=1200,
                token_count=1200,
                cost_usd=0.05,
                output_data={
                    "claims": ["c1", "c2", "c3"],
                    "citations": ["doc-1", "doc-2"],
                    "unverified_claims": ["c3"],
                },
            )
            .end()
            .handoff("generator", "fact-checker", context_size=200)
            .agent(
                "fact-checker",
                duration_ms=800,
                token_count=900,
                cost_usd=0.04,
                output_data={
                    "verified_claims": ["c1", "c2"],
                    "unsupported_claims": ["c3"],
                    "missing_citation_ids": ["doc-3"],
                },
            )
            .end()
        .end()
        .build())
    report = analyze_cost_yield(trace)
    path = max(report.path_summaries, key=lambda item: item.grounding_issue_count)
    assert path.grounding_issue_count >= 2
    assert path.citation_coverage is not None
    assert path.to_dict()["grounding_issue_count"] >= 2


    def test_path_summaries_identify_worst_chain():
        """Q4 should expose the most wasteful handoff chain, not only single agents."""
        trace = (TraceBuilder("path summary")
         .agent("coordinator", duration_ms=7000)
             .agent("good-start", duration_ms=500, token_count=100, cost_usd=0.005,
                 output_data={"summary": "ok", "quality": 0.9})
             .end()
             .handoff("good-start", "good-finish", context_size=100)
             .agent("good-finish", duration_ms=500, token_count=150, cost_usd=0.007,
                 output_data={"summary": "good", "quality": 0.95})
             .end()
             .agent("bad-start", duration_ms=1000, token_count=2000, cost_usd=0.08,
                 output_data={"summary": "x" * 1200, "quality": 0.25})
             .end()
             .handoff("bad-start", "bad-finish", context_size=600)
             .agent("bad-finish", duration_ms=1000, token_count=2500, cost_usd=0.09,
                 output_data={"verdict": "regressed", "comparison": {"improved": 0, "regressed": 2}})
             .end()
         .end()
         .build())
        report = analyze_cost_yield(trace)
        assert report.path_summaries
        assert report.worst_path == "bad-start → bad-finish"
        labels = {" → ".join(path.agents) for path in report.path_summaries}
        assert "bad-start → bad-finish" in labels
        worst = max(report.path_summaries, key=lambda path: path.waste_score)
        assert worst.avg_yield_score < 50


    def test_critical_path_summary_exposed():
        """Cost-yield should expose a critical-path summary for Q4 diagnostics."""
        trace = (TraceBuilder("critical path summary")
         .agent("pipeline", duration_ms=4000)
             .agent("researcher", duration_ms=1500, token_count=500, cost_usd=0.03,
                 output_data={"quality": 0.8, "summary": "research"})
             .end()
             .agent("writer", duration_ms=1200, token_count=700, cost_usd=0.04,
                 input_data={"summary": "research"},
                 output_data={"quality": 0.7, "summary": "draft"})
             .end()
         .end()
         .build())
        report = analyze_cost_yield(trace)
        assert report.critical_path_summary is not None
        assert report.critical_path_summary.total_cost_usd > 0
        assert report.to_dict()["critical_path_summary"] is not None
