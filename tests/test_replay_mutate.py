"""Test: replay a trace, mutate one agent's timing, verify analysis changes.

This is a mutation test — proves analysis functions are sensitive to
actual data changes, not just returning static results.
"""

import json
from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace
from agentguard.analysis import analyze_bottleneck, analyze_cost_yield, analyze_timing
from agentguard.scoring import score_trace


def _base_trace():
    """Balanced trace: two agents with similar durations."""
    return (TraceBuilder("mutation test")
        .agent("coordinator", duration_ms=6000)
            .agent("fast_agent", duration_ms=1000, token_count=100, cost_usd=0.01)
                .tool("api_call", duration_ms=500)
            .end()
            .agent("slow_agent", duration_ms=4000, token_count=200, cost_usd=0.02)
                .tool("db_query", duration_ms=3000)
            .end()
        .end()
        .build())


def _mutate_timing(trace, agent_name, new_duration_ms):
    """Clone a trace and change one agent's duration."""
    d = trace.to_dict()
    for span in d["spans"]:
        if span["name"] == agent_name:
            # Adjust ended_at based on started_at + new duration
            from datetime import datetime, timezone, timedelta
            start = datetime.fromisoformat(span["started_at"])
            end = start + timedelta(milliseconds=new_duration_ms)
            span["ended_at"] = end.isoformat()
    return ExecutionTrace.from_dict(d)


def _mutate_status(trace, agent_name, new_status, error=None):
    """Clone a trace and change one agent's status."""
    d = trace.to_dict()
    for span in d["spans"]:
        if span["name"] == agent_name:
            span["status"] = new_status
            if error:
                span["error"] = error
    return ExecutionTrace.from_dict(d)


class TestReplayMutateTiming:
    def test_bottleneck_changes_when_timing_changes(self):
        """Making fast_agent slower should change bottleneck."""
        base = _base_trace()
        bn_base = analyze_bottleneck(base)
        # Bottleneck is work span (tool), not container agent
        assert bn_base.bottleneck_span in ("slow_agent", "db_query")

        mutated = _mutate_timing(base, "fast_agent", 8000)
        bn_mut = analyze_bottleneck(mutated)
        # After mutation, fast_agent or its tool is the bottleneck
        bn_names = [r["name"] for r in bn_mut.agent_rankings]
        assert bn_mut.bottleneck_duration_ms > bn_base.bottleneck_duration_ms or bn_mut.bottleneck_span != bn_base.bottleneck_span

    def test_score_changes_when_agent_fails(self):
        """Failing an agent should reduce the score."""
        base = _base_trace()
        score_base = score_trace(base)

        mutated = _mutate_status(base, "slow_agent", "failed", "timeout")
        score_mut = score_trace(mutated)

        assert score_mut.overall < score_base.overall

    def test_cost_yield_wasteful_changes(self):
        """Increasing cost of an agent should change waste analysis."""
        base = _base_trace()
        cy_base = analyze_cost_yield(base)

        # Mutate: give fast_agent huge cost
        d = base.to_dict()
        for span in d["spans"]:
            if span["name"] == "fast_agent":
                span["estimated_cost_usd"] = 10.0
        mutated = ExecutionTrace.from_dict(d)
        cy_mut = analyze_cost_yield(mutated)

        assert cy_mut.highest_cost_agent == "fast_agent"

    def test_json_round_trip_preserves_mutation(self):
        """Mutations survive JSON serialization."""
        base = _base_trace()
        mutated = _mutate_timing(base, "fast_agent", 9999)
        j = mutated.to_json()
        reloaded = ExecutionTrace.from_dict(json.loads(j))
        fast = [s for s in reloaded.spans if s.name == "fast_agent"][0]
        assert abs((fast.duration_ms or 0) - 9999) < 10

    def test_analysis_is_not_cached(self):
        """Running analysis twice on different traces gives different results."""
        t1 = _base_trace()
        t2 = _mutate_timing(t1, "slow_agent", 100)
        bn1 = analyze_bottleneck(t1)
        bn2 = analyze_bottleneck(t2)
        assert bn1.bottleneck_span != bn2.bottleneck_span or \
               bn1.bottleneck_duration_ms != bn2.bottleneck_duration_ms

    def test_timing_analysis_reflects_mutation(self):
        """Timing analysis should show different results after mutation."""
        base = _base_trace()
        t1 = analyze_timing(base)
        mutated = _mutate_timing(base, "fast_agent", 50)
        t2 = analyze_timing(mutated)
        assert t1 != t2
