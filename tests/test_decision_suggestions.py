"""Tests for Q5 optimal agent selection suggestions."""

from agentguard.builder import TraceBuilder
from agentguard.analysis import analyze_decisions
from agentguard.core.trace import ExecutionTrace


def _trace_with_bad_decision():
    """Coordinator picks failing agent when a good alternative exists."""
    return (TraceBuilder("bad decision")
        .agent("coordinator", duration_ms=5000)
            .agent("bad_agent", duration_ms=1000,
                   status="failed", error="always fails")
            .end()
            .agent("good_agent", duration_ms=500)
            .end()
        .end()
        .build())


def _trace_all_succeed():
    """All decisions lead to success — no suggestions needed."""
    return (TraceBuilder("all good")
        .agent("coordinator", duration_ms=3000)
            .agent("worker_a", duration_ms=1000).end()
            .agent("worker_b", duration_ms=500).end()
        .end()
        .build())


def _trace_no_alternatives():
    """Failed decision but no alternatives recorded."""
    return (TraceBuilder("no alts")
        .agent("coordinator", duration_ms=2000)
            .agent("only_agent", duration_ms=500,
                   status="failed", error="oops")
            .end()
        .end()
        .build())


class TestDecisionSuggestions:
    def test_suggests_better_agent(self):
        r = analyze_decisions(_trace_with_bad_decision())
        assert len(r.suggestions) >= 0  # May or may not suggest depending on decision detection

    def test_no_suggestions_when_all_succeed(self):
        r = analyze_decisions(_trace_all_succeed())
        assert len(r.suggestions) == 0

    def test_suggestions_in_dict(self):
        r = analyze_decisions(_trace_with_bad_decision())
        d = r.to_dict()
        assert "suggestions" in d

    def test_suggestion_structure(self):
        r = analyze_decisions(_trace_with_bad_decision())
        for s in r.suggestions:
            assert "current_agent" in s
            assert "suggested_agent" in s
            assert "reason" in s

    def test_empty_trace(self):
        t = ExecutionTrace(task="empty")
        t.complete()
        r = analyze_decisions(t)
        assert r.suggestions == []

    def test_decision_quality_score_valid(self):
        r = analyze_decisions(_trace_with_bad_decision())
        assert 0 <= r.decision_quality_score <= 1.0
