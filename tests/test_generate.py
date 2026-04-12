"""Tests for trace generator."""

import pytest
from agentguard.generate import generate_trace, generate_batch


class TestGenerateTrace:
    def test_basic(self):
        trace = generate_trace(seed=42)
        assert len(trace.spans) > 0
        assert trace.task == "synthetic_pipeline"

    def test_custom_agents(self):
        trace = generate_trace(agents=5, seed=42)
        agent_spans = [s for s in trace.spans if s.span_type.value == "agent"]
        assert len(agent_spans) == 5

    def test_no_failures(self):
        trace = generate_trace(failure_rate=0, seed=42)
        failed = [s for s in trace.spans if s.status.value == "failed"]
        assert len(failed) == 0

    def test_all_failures(self):
        trace = generate_trace(failure_rate=1.0, seed=42)
        agents = [s for s in trace.spans if s.span_type.value == "agent"]
        assert all(s.status.value == "failed" for s in agents)

    def test_no_handoffs(self):
        trace = generate_trace(handoffs=False, seed=42)
        handoffs = [s for s in trace.spans if s.span_type.value == "handoff"]
        assert len(handoffs) == 0

    def test_reproducible(self):
        t1 = generate_trace(seed=123)
        t2 = generate_trace(seed=123)
        assert len(t1.spans) == len(t2.spans)

    def test_with_costs(self):
        trace = generate_trace(include_costs=True, seed=42)
        has_tokens = any(s.token_count and s.token_count > 0 for s in trace.spans)
        assert has_tokens


class TestGenerateBatch:
    def test_batch(self):
        traces = generate_batch(count=5, seed=42)
        assert len(traces) == 5

    def test_batch_different(self):
        traces = generate_batch(count=3, agents=2, seed=42)
        # Different seeds should produce different traces
        tasks = {t.task for t in traces}
        assert len(tasks) == 3
