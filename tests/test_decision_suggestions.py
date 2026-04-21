"""Tests for Q5 optimal agent selection suggestions."""

from agentguard.analysis import analyze_decisions
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


def _decision_trace(
    task: str,
    chosen_name: str,
    chosen_status: SpanStatus,
    alternatives: list[str],
) -> ExecutionTrace:
    """Build a minimal trace with one real orchestration decision span."""
    trace = ExecutionTrace(task=task)
    coordinator = Span(name="coordinator", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
    decision = Span(
        name=f"coordinator → {chosen_name} (decision)",
        span_type=SpanType.HANDOFF,
        parent_span_id=coordinator.span_id,
        status=SpanStatus.COMPLETED,
        metadata={
            "decision.type": "orchestration",
            "decision.coordinator": "coordinator",
            "decision.chosen": chosen_name,
            "decision.alternatives": alternatives,
        },
    )
    chosen = Span(
        name=chosen_name,
        span_type=SpanType.AGENT,
        parent_span_id=coordinator.span_id,
        status=chosen_status,
        error="always fails" if chosen_status == SpanStatus.FAILED else None,
    )
    spans = [coordinator, decision, chosen]
    for alternative in alternatives:
        spans.append(
            Span(
                name=alternative,
                span_type=SpanType.AGENT,
                parent_span_id=coordinator.span_id,
                status=SpanStatus.COMPLETED,
            )
        )
    for span in spans:
        trace.add_span(span)
    trace.complete()
    return trace


def _trace_with_bad_decision():
    """Coordinator picks failing agent when a good alternative exists."""
    return _decision_trace(
        task="bad decision",
        chosen_name="bad_agent",
        chosen_status=SpanStatus.FAILED,
        alternatives=["good_agent"],
    )


def _trace_all_succeed():
    """All decisions lead to success — no suggestions needed."""
    return _decision_trace(
        task="all good",
        chosen_name="worker_a",
        chosen_status=SpanStatus.COMPLETED,
        alternatives=["worker_b"],
    )


def _trace_no_alternatives():
    """Failed decision but no alternatives recorded."""
    return _decision_trace(
        task="no alts",
        chosen_name="only_agent",
        chosen_status=SpanStatus.FAILED,
        alternatives=[],
    )


class TestDecisionSuggestions:
    def test_suggests_better_agent(self):
        r = analyze_decisions(_trace_with_bad_decision())
        assert len(r.suggestions) == 1
        assert r.suggestions[0]["current_agent"] == "bad_agent"
        assert r.suggestions[0]["suggested_agent"] == "good_agent"

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
