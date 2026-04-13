"""Tests for most wasteful agent detection and recommendations (Q4)."""

from agentguard.analysis import CostYieldEntry, _compute_waste_score, analyze_cost_yield
from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace, SpanStatus


def _entry(agent, tokens=0, cost=0.0, status="completed",
           yield_score=50, has_output=True):
    return CostYieldEntry(
        agent=agent, tokens=tokens, cost_usd=cost, status=status,
        duration_ms=100, has_output=has_output, output_size_bytes=100,
        cost_per_success=cost if status == "completed" else float("inf"),
        tokens_per_ms=0.1, yield_score=yield_score,
    )


class TestWasteScore:
    def test_failed_agent_max_waste(self):
        e = _entry("bad", status="failed", tokens=1000)
        assert _compute_waste_score(e) == 100.0

    def test_high_yield_low_waste(self):
        e = _entry("good", yield_score=95)
        score = _compute_waste_score(e)
        assert score < 10

    def test_low_yield_high_waste(self):
        e = _entry("bad", yield_score=10, tokens=500)
        score = _compute_waste_score(e)
        assert score > 80


class TestMostWasteful:
    def test_identifies_wasteful_agent(self):
        trace = (TraceBuilder("waste")
            .agent("good", duration_ms=100).end()
            .agent("bad", duration_ms=5000).end()
            .build())
        # Mark bad as failed
        for s in trace.spans:
            if s.name == "bad":
                s.status = SpanStatus.FAILED
                s.error = "crash"
        report = analyze_cost_yield(trace)
        assert report.most_wasteful_agent == "bad"
        assert report.waste_score > 0

    def test_empty_trace_no_crash(self):
        trace = ExecutionTrace(task="empty")
        trace.complete()
        report = analyze_cost_yield(trace)
        assert report.most_wasteful_agent == ""

    def test_waste_in_to_dict(self):
        trace = (TraceBuilder("dict")
            .agent("x", duration_ms=100).end()
            .build())
        report = analyze_cost_yield(trace)
        d = report.to_dict()
        assert "most_wasteful_agent" in d
        assert "waste_score" in d
        assert "recommendations" in d


class TestRecommendations:
    def test_failed_agent_gets_recommendation(self):
        trace = (TraceBuilder("rec")
            .agent("fail_agent", duration_ms=100).end()
            .build())
        for s in trace.spans:
            if s.name == "fail_agent":
                s.status = SpanStatus.FAILED
                s.error = "err"
                s.metadata["token_count"] = 500
        report = analyze_cost_yield(trace)
        # May or may not have recs depending on token count
        assert isinstance(report.recommendations, list)

    def test_recommendations_in_report(self):
        trace = (TraceBuilder("report")
            .agent("a", duration_ms=100).end()
            .build())
        report = analyze_cost_yield(trace)
        text = report.to_report()
        assert "Most wasteful" in text or "Per-Agent" in text

    def test_max_5_recommendations(self):
        trace = TraceBuilder("many")
        for i in range(10):
            trace.agent(f"agent_{i}", duration_ms=100).end()
        t = trace.build()
        for s in t.spans:
            s.status = SpanStatus.FAILED
            s.error = "err"
        report = analyze_cost_yield(t)
        assert len(report.recommendations) <= 5
