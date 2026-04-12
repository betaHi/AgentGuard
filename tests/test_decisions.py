"""Tests for orchestration decision tracking and analysis."""

import json
from agentguard import record_agent, record_decision
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.analysis import analyze_decisions, DecisionRecord, DecisionAnalysis
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def _run_pipeline_with_decisions():
    """Build a trace where a coordinator makes routing decisions."""
    init_recorder(task="decision test")

    @record_agent(name="coordinator", version="v1")
    def coordinator():
        # Decision 1: choose fast-model over slow-model
        record_decision(
            coordinator="coordinator",
            chosen_agent="fast-model",
            alternatives=["slow-model", "cheap-model"],
            rationale="Latency-sensitive request, chose fast-model",
            criteria={"priority": "speed", "budget_ok": True},
            confidence=0.85,
        )

        @record_agent(name="fast-model", version="v1")
        def fast_model():
            return {"result": "done"}

        return fast_model()

    coordinator()
    return finish_recording()


def test_record_decision_creates_span():
    """record_decision creates a HANDOFF span with decision metadata."""
    trace = _run_pipeline_with_decisions()
    decision_spans = [
        s for s in trace.spans
        if s.metadata.get("decision.type") == "orchestration"
    ]
    assert len(decision_spans) == 1
    ds = decision_spans[0]
    assert ds.span_type == SpanType.HANDOFF
    assert ds.metadata["decision.chosen"] == "fast-model"
    assert ds.metadata["decision.alternatives"] == ["slow-model", "cheap-model"]
    assert ds.metadata["decision.rationale"] == "Latency-sensitive request, chose fast-model"
    assert ds.metadata["decision.confidence"] == 0.85
    assert ds.metadata["decision.criteria"]["priority"] == "speed"
    assert ds.status == SpanStatus.COMPLETED


def test_analyze_decisions_success():
    """analyze_decisions identifies successful decisions."""
    trace = _run_pipeline_with_decisions()
    analysis = analyze_decisions(trace)
    assert analysis.total_decisions == 1
    assert analysis.decisions_leading_to_failure == 0
    assert analysis.decision_quality_score == 1.0
    d = analysis.decisions[0]
    assert d.chosen_agent == "fast-model"
    assert d.downstream_status == "completed"
    assert not d.led_to_failure


def test_analyze_decisions_with_failure():
    """Decisions leading to failed agents are flagged."""
    init_recorder(task="bad decision")

    @record_agent(name="router", version="v1")
    def router():
        record_decision(
            coordinator="router",
            chosen_agent="buggy-agent",
            alternatives=["stable-agent"],
            rationale="Chose buggy-agent for new feature support",
        )

        @record_agent(name="buggy-agent", version="v1")
        def buggy():
            raise RuntimeError("crash")

        try:
            buggy()
        except RuntimeError:
            pass

    router()
    trace = finish_recording()
    analysis = analyze_decisions(trace)
    assert analysis.total_decisions == 1
    assert analysis.decisions_leading_to_failure == 1
    assert analysis.decision_quality_score == 0.0
    assert analysis.decisions[0].led_to_failure


def test_empty_trace_no_decisions():
    """Empty trace returns zero decisions gracefully."""
    trace = ExecutionTrace(task="empty")
    analysis = analyze_decisions(trace)
    assert analysis.total_decisions == 0
    assert analysis.decisions_leading_to_failure == 0
    assert analysis.decision_quality_score == 1.0  # no decisions = no bad ones


def test_decision_no_alternatives():
    """Decision with no alternatives is valid."""
    init_recorder(task="single choice")

    record_decision(
        coordinator="router",
        chosen_agent="only-option",
        alternatives=[],
        rationale="No alternatives available",
    )

    @record_agent(name="only-option", version="v1")
    def only():
        return "ok"

    only()
    trace = finish_recording()
    analysis = analyze_decisions(trace)
    assert analysis.total_decisions == 1
    assert analysis.decisions[0].alternatives == []


def test_decision_no_rationale():
    """Decision without rationale still works."""
    init_recorder(task="no reason")
    record_decision(coordinator="r", chosen_agent="a")

    @record_agent(name="a", version="v1")
    def a():
        return "ok"

    a()
    trace = finish_recording()
    analysis = analyze_decisions(trace)
    assert analysis.decisions[0].rationale == ""


def test_multiple_decisions():
    """Multiple decisions in one trace are all tracked."""
    init_recorder(task="multi")
    for name in ["agent-a", "agent-b", "agent-c"]:
        record_decision(coordinator="router", chosen_agent=name,
                        alternatives=["other"], rationale=f"chose {name}")

        @record_agent(name=name, version="v1")
        def agent_fn():
            return "ok"
        agent_fn()

    trace = finish_recording()
    analysis = analyze_decisions(trace)
    assert analysis.total_decisions == 3


def test_to_dict_serializable():
    """to_dict output is JSON-serializable."""
    trace = _run_pipeline_with_decisions()
    analysis = analyze_decisions(trace)
    d = analysis.to_dict()
    serialized = json.dumps(d)
    assert "fast-model" in serialized
    assert "decision_quality_score" in serialized


def test_to_report_readable():
    """to_report produces human-readable output."""
    trace = _run_pipeline_with_decisions()
    analysis = analyze_decisions(trace)
    report = analysis.to_report()
    assert "Orchestration Decision" in report
    assert "fast-model" in report
    assert "Latency-sensitive" in report
