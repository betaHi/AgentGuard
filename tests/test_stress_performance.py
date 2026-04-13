"""Stress test: 1000-span trace, verify analysis completes in <5s.

Generates a large realistic trace and ensures all analysis modules
handle it within acceptable time bounds.
"""

import time
import random

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.analysis import (
    analyze_failures, analyze_bottleneck, analyze_flow,
    analyze_cost_yield, analyze_decisions, analyze_context_flow,
)
from agentguard.propagation import analyze_propagation


def _build_large_trace(n_spans: int = 1000, seed: int = 42) -> ExecutionTrace:
    """Generate a deterministic trace with n_spans spans.

    Structure: 50 top-level agents, each with ~20 child tools.
    10% of spans are failed. Some agents have handoff spans.
    """
    rng = random.Random(seed)
    trace = ExecutionTrace(task="stress test")
    trace.started_at = "2025-01-01T00:00:00+00:00"

    agents = []
    span_count = 0

    # Create top-level agents
    n_agents = min(50, n_spans // 20)
    for i in range(n_agents):
        if span_count >= n_spans:
            break
        agent = _make_agent_span(i, rng)
        trace.add_span(agent)
        agents.append(agent)
        span_count += 1

        # Add child tools
        n_tools = rng.randint(10, 25)
        for j in range(n_tools):
            if span_count >= n_spans:
                break
            tool = _make_tool_span(i, j, agent.span_id, rng)
            trace.add_span(tool)
            span_count += 1

    # Add handoff spans between adjacent agents
    for k in range(len(agents) - 1):
        if span_count >= n_spans:
            break
        handoff = _make_handoff_span(agents[k], agents[k + 1])
        trace.add_span(handoff)
        span_count += 1

    trace.ended_at = "2025-01-01T00:01:00+00:00"
    trace.status = SpanStatus.COMPLETED
    return trace


def _make_agent_span(idx: int, rng: random.Random) -> Span:
    """Create an agent span with random timing."""
    failed = rng.random() < 0.1
    dur_s = rng.uniform(0.1, 2.0)
    return Span(
        name=f"agent_{idx}",
        span_type=SpanType.AGENT,
        started_at=f"2025-01-01T00:00:{idx:02d}+00:00",
        ended_at=f"2025-01-01T00:00:{idx:02d}+00:00",
        status=SpanStatus.FAILED if failed else SpanStatus.COMPLETED,
        error=f"Error in agent_{idx}" if failed else None,
        metadata={"model": f"model-{idx % 5}", "version": "v1"},
    )


def _make_tool_span(
    agent_idx: int, tool_idx: int, parent_id: str, rng: random.Random
) -> Span:
    """Create a tool span parented to an agent."""
    failed = rng.random() < 0.1
    return Span(
        name=f"tool_{agent_idx}_{tool_idx}",
        span_type=SpanType.TOOL,
        parent_span_id=parent_id,
        started_at=f"2025-01-01T00:00:{agent_idx:02d}+00:00",
        ended_at=f"2025-01-01T00:00:{agent_idx:02d}+00:00",
        status=SpanStatus.FAILED if failed else SpanStatus.COMPLETED,
        error=f"Tool error" if failed else None,
    )


def _make_handoff_span(from_agent: Span, to_agent: Span) -> Span:
    """Create a handoff span between two agents."""
    return Span(
        name=f"handoff:{from_agent.name}->{to_agent.name}",
        span_type=SpanType.HANDOFF,
        started_at=from_agent.ended_at,
        ended_at=to_agent.started_at,
        status=SpanStatus.COMPLETED,
        metadata={
            "handoff.from": from_agent.name,
            "handoff.to": to_agent.name,
        },
    )


class TestStressPerformance:
    """All analysis modules must complete on 1000-span trace in <5s each."""

    def setup_method(self):
        self.trace = _build_large_trace(1000)
        assert len(self.trace.spans) >= 900  # at least 900 spans

    def test_span_count(self):
        assert len(self.trace.spans) >= 900

    def test_analyze_failures_under_5s(self):
        start = time.monotonic()
        result = analyze_failures(self.trace)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"analyze_failures took {elapsed:.2f}s"
        assert result.total_failed_spans >= 0

    def test_analyze_bottleneck_under_5s(self):
        start = time.monotonic()
        result = analyze_bottleneck(self.trace)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"analyze_bottleneck took {elapsed:.2f}s"
        assert isinstance(result.bottleneck_span, str)

    def test_analyze_flow_under_5s(self):
        start = time.monotonic()
        result = analyze_flow(self.trace)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"analyze_flow took {elapsed:.2f}s"

    def test_analyze_cost_yield_under_5s(self):
        start = time.monotonic()
        result = analyze_cost_yield(self.trace)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"analyze_cost_yield took {elapsed:.2f}s"

    def test_analyze_propagation_under_5s(self):
        start = time.monotonic()
        result = analyze_propagation(self.trace)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"analyze_propagation took {elapsed:.2f}s"
        assert result.total_failures >= 0

    def test_analyze_context_flow_under_5s(self):
        start = time.monotonic()
        result = analyze_context_flow(self.trace)
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"analyze_context_flow took {elapsed:.2f}s"
