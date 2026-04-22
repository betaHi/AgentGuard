"""Ground-truth diagnostic accuracy bench.

This bench pins down the analyzers' answers on a handful of crafted
scenarios with known-correct verdicts. It is the anti-regression
baseline the product direction review asks for: if a future refactor
quietly changes the answer our analyzers give on these scenarios, CI
catches it.

Each scenario mirrors one of the five diagnostic questions. The
fixtures are intentionally tiny so the failure message, not the setup,
tells you what broke.
"""

from __future__ import annotations

import pytest

from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace
from agentguard.diagnostics import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost_yield,
    analyze_failures,
    diagnose,
)


# ---------------------------------------------------------------------------
# Q1 — bottleneck identification
# ---------------------------------------------------------------------------

def _slow_worker_trace() -> ExecutionTrace:
    """One agent is 10× slower than its siblings; it must be the bottleneck."""
    return (
        TraceBuilder("bench-bottleneck")
        .agent("coordinator", duration_ms=11_000)
            .agent("fast-a", duration_ms=500)
                .tool("fetch", duration_ms=50)
            .end()
            .agent("slow-worker", duration_ms=10_000)
                .tool("llm-call", duration_ms=9_500)
            .end()
            .agent("fast-b", duration_ms=500)
            .end()
        .end()
        .build()
    )


def test_bottleneck_finds_slow_worker_on_critical_path():
    trace = _slow_worker_trace()
    report = analyze_bottleneck(trace)

    critical_names = report.critical_path  # list[str] of span names
    assert "slow-worker" in critical_names, (
        f"slow-worker must be on the critical path; got {critical_names}"
    )
    # fast-a / fast-b are 20× faster, they must not be flagged as bottleneck.
    assert "fast-a" not in critical_names
    assert "fast-b" not in critical_names


# ---------------------------------------------------------------------------
# Q2 — handoff lost information
# ---------------------------------------------------------------------------

def _lossy_handoff_trace() -> ExecutionTrace:
    """Sender emits a critical ``doc_ids`` key; receiver input drops it."""
    # planner and researcher must be siblings under a shared coordinator
    # for inferred handoffs to fire.
    trace = (
        TraceBuilder("bench-handoff-loss")
        .agent("coordinator", duration_ms=500)
            .agent("planner", duration_ms=100,
                   output_data={
                       "task": "research",
                       "doc_ids": ["d1", "d2", "d3"],
                       "citations": ["c1", "c2"],
                       "requirements": ["deadline", "tone"],
                   })
            .end()
            .agent("researcher", duration_ms=200,
                   input_data={"task": "research"})  # every critical key dropped
                .tool("search", duration_ms=100)
            .end()
        .end()
        .build()
    )
    return trace


def test_handoff_loss_reports_missing_critical_keys():
    trace = _lossy_handoff_trace()
    flow = analyze_context_flow(trace)

    assert flow.points, "must detect at least one handoff"
    any_lost = any(p.keys_lost for p in flow.points)
    assert any_lost, (
        f"expected at least one handoff with keys_lost, "
        f"got: {[p.to_dict() for p in flow.points]}"
    )


# ---------------------------------------------------------------------------
# Q3 — cost/yield on a wasteful path
# ---------------------------------------------------------------------------

def _wasteful_trace() -> ExecutionTrace:
    """One agent spends most of the tokens but returns ``{}``."""
    trace = (
        TraceBuilder("bench-cost-yield")
        .agent("coordinator", duration_ms=5_000)
            .agent("cheap-success", duration_ms=500,
                   token_count=500, cost_usd=0.01,
                   output_data={"answer": "finished the job", "confidence": 0.9})
            .end()
            .agent("expensive-empty", duration_ms=4_000,
                   token_count=50_000, cost_usd=2.00,
                   output_data={})
            .end()
        .end()
        .build()
    )
    return trace


def test_wasteful_agent_ranks_worst_on_cost_yield():
    trace = _wasteful_trace()
    report = analyze_cost_yield(trace)

    by_agent = {e.agent: e for e in report.entries}
    assert "expensive-empty" in by_agent
    assert "cheap-success" in by_agent

    # The wasteful agent must cost more AND yield less than the success.
    assert by_agent["expensive-empty"].cost_usd > by_agent["cheap-success"].cost_usd
    assert by_agent["expensive-empty"].yield_score < by_agent["cheap-success"].yield_score


# ---------------------------------------------------------------------------
# Q4/Q5 — integrated diagnose() composite
# ---------------------------------------------------------------------------

def _failing_pipeline_trace() -> ExecutionTrace:
    """A failure at the tool level that propagates to its parent agent."""
    return (
        TraceBuilder("bench-failure-cascade")
        .agent("root", duration_ms=2_000)
            .agent("worker-ok", duration_ms=500)
            .end()
            .agent("worker-bad", duration_ms=1_200, status="failed",
                   error="downstream propagation")
                .tool("flaky-api", duration_ms=1_000, status="failed",
                      error="HTTP 500 from upstream")
            .end()
        .end()
        .build()
    )


def test_diagnose_flags_the_failed_tool_and_its_parent():
    trace = _failing_pipeline_trace()
    report = diagnose(trace)

    assert report.failures is not None
    failed_names = {rc.span_name for rc in report.failures.root_causes}
    # Either the tool itself or its parent agent (the propagated failure)
    # must surface as a root cause — the analyzer picks the originating
    # span, which depending on heuristics can be either. The contract is
    # that the failure is NOT silently dropped.
    assert failed_names & {"flaky-api", "worker-bad"}, (
        f"at least one failing span must surface as a root cause; got {failed_names}"
    )
    # Score must reflect the failure, not come back at 100.
    assert report.score.overall < 100


def test_diagnose_bench_is_deterministic():
    """Running diagnose() twice on the same trace yields equal totals."""
    trace = _failing_pipeline_trace()
    a = diagnose(trace)
    b = diagnose(trace)
    assert a.score.overall == b.score.overall
    assert len(a.failures.root_causes) == len(b.failures.root_causes)
