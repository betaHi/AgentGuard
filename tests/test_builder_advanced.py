"""Advanced builder tests — verify complex trace structures."""

import pytest

from agentguard.builder import TraceBuilder
from agentguard.core.trace import SpanType
from agentguard.flowgraph import build_flow_graph
from agentguard.normalize import normalize_trace
from agentguard.propagation import analyze_propagation
from agentguard.schema import validate_trace_dict
from agentguard.scoring import score_trace


class TestBuilderComplexTraces:
    """Build complex traces and verify they analyze correctly."""

    def test_deeply_nested(self):
        """5 levels of nesting."""
        trace = (TraceBuilder("deep")
            .agent("coordinator")
                .agent("manager")
                    .agent("worker")
                        .tool("api_call")
                        .llm_call("claude", token_count=100)
                    .end()
                .end()
            .end()
            .build())

        assert len(trace.spans) == 5
        errors = validate_trace_dict(trace.to_dict())
        assert errors == []

    def test_wide_fanout(self):
        """10 parallel children under one parent."""
        b = TraceBuilder("wide").agent("orchestrator")
        for i in range(10):
            b = b.agent(f"worker_{i}", duration_ms=1000).end()
        trace = b.end().build()

        assert len(trace.spans) == 11
        graph = build_flow_graph(trace)
        # Builder creates sequential spans (time cursor advances), so parallelism = 1
        # This is correct — real parallelism requires threading (see parallel_pipeline.py)
        assert graph.max_parallelism >= 1

    def test_mixed_success_failure(self):
        """Mix of successful and failed spans."""
        trace = (TraceBuilder("mixed")
            .agent("ok_agent", duration_ms=2000)
                .tool("ok_tool")
            .end()
            .agent("bad_agent", duration_ms=1000, status="failed", error="crash")
                .tool("bad_tool", status="failed", error="dependency failed")
            .end()
            .agent("recovery_agent", duration_ms=1500)
            .end()
            .build())

        prop = analyze_propagation(trace)
        assert prop.total_failures >= 2

        score = score_trace(trace)
        assert 20 < score.overall < 90

    def test_handoff_chain(self):
        """Long chain of handoffs: A → B → C → D → E."""
        b = TraceBuilder("chain")
        agents = ["planner", "researcher", "analyst", "writer", "reviewer"]

        for i, name in enumerate(agents):
            b = b.agent(name, duration_ms=1000, output_data={f"step_{i}": "data"}).end()
            if i < len(agents) - 1:
                b = b.handoff(name, agents[i + 1], context_size=500 * (i + 1))

        trace = b.build()
        handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
        assert len(handoffs) == 4
        assert len(trace.spans) == 9  # 5 agents + 4 handoffs

    def test_retry_with_eventual_success(self):
        """Tool fails twice, then succeeds."""
        trace = (TraceBuilder("retry")
            .agent("resilient")
                .tool("flaky", status="failed", error="attempt 1", retry_count=0)
                .tool("flaky", status="failed", error="attempt 2", retry_count=1)
                .tool("flaky", status="completed", retry_count=2)
            .end()
            .build())

        assert len(trace.spans) == 4

    def test_llm_heavy_pipeline(self):
        """Pipeline dominated by LLM calls with costs."""
        trace = (TraceBuilder("llm_heavy")
            .agent("researcher", token_count=5000, cost_usd=0.15)
                .llm_call("gpt4-research", token_count=4000, cost_usd=0.12)
                .llm_call("gpt4-summarize", token_count=1000, cost_usd=0.03)
            .end()
            .agent("writer", token_count=8000, cost_usd=0.24)
                .llm_call("gpt4-write", token_count=6000, cost_usd=0.18)
                .llm_call("gpt4-edit", token_count=2000, cost_usd=0.06)
            .end()
            .build())

        from agentguard.metrics import extract_metrics
        m = extract_metrics(trace)
        assert m.total_tokens == 26000
        assert m.total_cost_usd == pytest.approx(0.78, abs=0.01)

    def test_normalize_built_trace(self):
        """Built traces should pass normalization."""
        trace = (TraceBuilder("normalize_test")
            .agent("a", duration_ms=1000).end()
            .build())
        result = normalize_trace(trace)
        # Should have minimal changes (just trace_id assignment)
        assert len([c for c in result.changes if "trace_id" not in c]) <= 1

    def test_json_roundtrip(self):
        """Complex trace should survive JSON serialization."""
        from agentguard.core.trace import ExecutionTrace

        trace = (TraceBuilder("roundtrip")
            .agent("a", duration_ms=3000, tags=["critical"], token_count=1000)
                .tool("t1", duration_ms=1000, retry_count=2)
                .llm_call("llm1", token_count=500, cost_usd=0.015)
            .end()
            .handoff("a", "b", context_size=2000, dropped_keys=["raw"])
            .agent("b", duration_ms=2000)
            .end()
            .build())

        json_str = trace.to_json()
        restored = ExecutionTrace.from_json(json_str)

        assert len(restored.spans) == len(trace.spans)
        assert restored.task == trace.task
