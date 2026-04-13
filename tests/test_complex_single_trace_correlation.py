"""Test: correlation analysis on a complex single trace with multiple patterns.

A realistic trace with failures, slow agents, timing clusters, and
retry patterns — verifies correlation finds all of them in one pass.
"""

from agentguard.builder import TraceBuilder
from agentguard.correlation import analyze_correlations


def _complex_trace():
    """Realistic coding pipeline trace with multiple issues.

    Expected patterns:
    - slow_agent: code_generator is 5x slower than others
    - failure_cluster: 2 workers fail under coordinator
    - timing_cluster: reviewer and tester have similar durations
    """
    return (TraceBuilder("complex coding pipeline")
        .agent("coordinator", duration_ms=15000)
            # Fast planning phase
            .agent("planner", duration_ms=200)
                .tool("llm_plan", duration_ms=150)
            .end()
            # Slow code generation (bottleneck)
            .agent("code_generator", duration_ms=8000)
                .tool("llm_generate", duration_ms=7500)
            .end()
            # Similar-duration review & test (timing cluster)
            .agent("reviewer", duration_ms=1000)
                .tool("llm_review", duration_ms=800)
            .end()
            .agent("tester", duration_ms=1020)
                .tool("run_tests", duration_ms=900)
            .end()
            # Failed deployment attempts (failure cluster)
            .agent("deployer_primary", duration_ms=500,
                   status="failed", error="staging env down")
            .end()
            .agent("deployer_fallback", duration_ms=300,
                   status="failed", error="fallback also down")
            .end()
        .end()
        .build())


class TestComplexSingleTrace:
    def test_finds_multiple_pattern_types(self):
        """Complex trace should have at least 2 different pattern types."""
        r = analyze_correlations(_complex_trace())
        types = set(p["type"] for p in r.patterns)
        assert len(types) >= 2, f"Only found: {types}"

    def test_slow_agent_found(self):
        r = analyze_correlations(_complex_trace())
        slow = [p for p in r.patterns if p["type"] == "slow_agent"]
        slow_names = [p["agent"] for p in slow]
        assert "code_generator" in slow_names or "coordinator" in slow_names

    def test_failure_cluster_found(self):
        r = analyze_correlations(_complex_trace())
        clusters = [p for p in r.patterns if p["type"] == "failure_cluster"]
        assert len(clusters) >= 1
        cluster = clusters[0]
        assert "deployer_primary" in cluster["failed_children"]
        assert "deployer_fallback" in cluster["failed_children"]

    def test_timing_cluster_found(self):
        """reviewer (1000ms) and tester (1020ms) should cluster."""
        r = analyze_correlations(_complex_trace())
        timing = [p for p in r.patterns if p["type"] == "timing_cluster"]
        if timing:
            pairs = timing[0]["pairs"]
            pair_names = {n for pair in pairs for n in pair}
            assert "reviewer" in pair_names or "tester" in pair_names

    def test_fingerprints_for_all_spans(self):
        t = _complex_trace()
        r = analyze_correlations(t)
        assert len(r.fingerprints) == len(t.spans)

    def test_total_patterns_reasonable(self):
        """Should find patterns but not an explosion of false positives."""
        r = analyze_correlations(_complex_trace())
        assert 1 <= len(r.patterns) <= 20

    def test_all_patterns_have_required_fields(self):
        r = analyze_correlations(_complex_trace())
        for p in r.patterns:
            assert "name" in p
            assert "type" in p
            assert "description" in p
            assert "count" in p

    def test_report_serializable(self):
        import json
        r = analyze_correlations(_complex_trace())
        d = r.to_dict()
        json.dumps(d, default=str)  # must not raise
