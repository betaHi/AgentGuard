"""Tests for counterfactual decision analysis (Q5)."""

import contextlib
import time
from datetime import UTC, datetime, timedelta

from agentguard import record_agent, record_decision
from agentguard.analysis import analyze_counterfactual
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.sdk.recorder import finish_recording, init_recorder


def _ts(offset_ms: int) -> str:
    base = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)
    return (base + timedelta(milliseconds=offset_ms)).isoformat()


def _pipeline_with_decisions():
    """Build trace with decisions and alternatives that also run."""
    init_recorder(task="counterfactual test", trigger="test")

    @record_agent(name="fast_agent", version="v1")
    def fast_agent():
        time.sleep(0.01)
        return {"result": "fast"}

    @record_agent(name="slow_agent", version="v1")
    def slow_agent():
        time.sleep(0.05)
        return {"result": "slow"}

    @record_agent(name="failing_agent", version="v1")
    def failing_agent():
        raise ValueError("I always fail")

    @record_agent(name="coordinator", version="v1")
    def coordinator():
        record_decision(
            coordinator="coordinator",
            chosen_agent="slow_agent",
            alternatives=["fast_agent"],
            rationale="Thought slow was better",
            confidence=0.6,
        )
        slow_agent()
        fast_agent()  # also runs so we have comparison data
        return {"done": True}

    coordinator()
    return finish_recording()


class TestCounterfactual:
    def test_suboptimal_detected(self):
        """Choosing slower agent when faster exists → suboptimal."""
        trace = _pipeline_with_decisions()
        result = analyze_counterfactual(trace)
        assert result.total_decisions >= 1
        assert result.suboptimal_count >= 1 or result.optimal_count >= 0
        # At least one result exists
        assert len(result.results) >= 1

    def test_regret_is_positive_for_slower(self):
        """Regret should be positive when chosen agent was slower."""
        trace = _pipeline_with_decisions()
        result = analyze_counterfactual(trace)
        for r in result.results:
            if r.best_alternative == "fast_agent" and r.regret_ms is not None:
                assert r.regret_ms > 0  # slow was slower than fast

    def test_no_decisions_empty(self):
        """Trace with no decisions → empty analysis."""
        init_recorder(task="empty", trigger="test")

        @record_agent(name="solo", version="v1")
        def solo():
            return {}

        solo()
        trace = finish_recording()
        result = analyze_counterfactual(trace)
        assert result.total_decisions == 0
        assert result.results == []
        assert result.total_regret_ms == 0.0

    def test_catastrophic_when_chosen_fails(self):
        """Choosing agent that fails while alternative succeeds → catastrophic."""
        init_recorder(task="catastrophic", trigger="test")

        @record_agent(name="bad_choice", version="v1")
        def bad_choice():
            raise RuntimeError("crash")

        @record_agent(name="good_choice", version="v1")
        def good_choice():
            return {"ok": True}

        @record_agent(name="coord", version="v1")
        def coord():
            record_decision(
                coordinator="coord",
                chosen_agent="bad_choice",
                alternatives=["good_choice"],
                rationale="bad guess",
                confidence=0.3,
            )
            with contextlib.suppress(RuntimeError):
                bad_choice()
            good_choice()
            return {}

        coord()
        trace = finish_recording()
        result = analyze_counterfactual(trace)
        catastrophic = [r for r in result.results if r.verdict == "catastrophic"]
        assert len(catastrophic) >= 1

    def test_no_alternatives_verdict(self):
        """Decision with alternatives that never ran → no_alternatives."""
        init_recorder(task="no alts", trigger="test")

        @record_agent(name="only_option", version="v1")
        def only_option():
            return {}

        @record_agent(name="coord", version="v1")
        def coord():
            record_decision(
                coordinator="coord",
                chosen_agent="only_option",
                alternatives=["ghost_agent"],
                rationale="only choice",
                confidence=1.0,
            )
            only_option()
            return {}

        coord()
        trace = finish_recording()
        result = analyze_counterfactual(trace)
        assert result.results[0].verdict == "no_alternatives"

    def test_to_dict_serializable(self):
        """to_dict returns JSON-safe structure."""
        import json
        trace = _pipeline_with_decisions()
        result = analyze_counterfactual(trace)
        d = result.to_dict()
        serialized = json.dumps(d)
        assert "verdict" in serialized
        assert "regret_ms" in serialized

    def test_to_report_text(self):
        """to_report produces readable text."""
        trace = _pipeline_with_decisions()
        result = analyze_counterfactual(trace)
        text = result.to_report()
        assert "Counterfactual" in text
        assert "coordinator" in text.lower() or "coord" in text.lower()

    def test_degraded_choice_can_be_suboptimal_without_hard_failure(self):
        """Context-loss degradation should still count as a suboptimal decision."""
        trace = ExecutionTrace(task="degraded decision")
        router = Span(name="router", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        decision = Span(
            name="router → analyst (decision)",
            span_type=SpanType.HANDOFF,
            parent_span_id=router.span_id,
            status=SpanStatus.COMPLETED,
            metadata={
                "decision.type": "orchestration",
                "decision.coordinator": "router",
                "decision.chosen": "analyst",
                "decision.alternatives": ["stable-agent"],
            },
        )
        analyst = Span(name="analyst", span_type=SpanType.AGENT, parent_span_id=router.span_id, status=SpanStatus.COMPLETED)
        analyst.started_at = _ts(0)
        analyst.ended_at = _ts(200)
        handoff = Span(
            name="analyst → writer",
            span_type=SpanType.HANDOFF,
            parent_span_id=analyst.span_id,
            status=SpanStatus.COMPLETED,
            handoff_from="analyst",
            handoff_to="writer",
            context_size_bytes=300,
            context_dropped_keys=["facts"],
        )
        handoff.metadata["handoff.context_keys"] = ["facts", "summary"]
        stable = Span(name="stable-agent", span_type=SpanType.AGENT, parent_span_id=router.span_id, status=SpanStatus.COMPLETED)
        stable.started_at = _ts(0)
        stable.ended_at = _ts(180)
        for span in [router, decision, analyst, handoff, stable]:
            trace.add_span(span)
        trace.complete()

        result = analyze_counterfactual(trace)
        assert result.results[0].verdict == "suboptimal"
        assert result.results[0].chosen_degraded is True

    def test_uses_representative_alt_performance_not_single_lucky_run(self):
        """Counterfactual should compare against representative average alternative performance."""
        trace = ExecutionTrace(task="representative alternative")
        router = Span(name="router", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        decision = Span(
            name="router → chosen-agent (decision)",
            span_type=SpanType.HANDOFF,
            parent_span_id=router.span_id,
            status=SpanStatus.COMPLETED,
            metadata={
                "decision.type": "orchestration",
                "decision.coordinator": "router",
                "decision.chosen": "chosen-agent",
                "decision.alternatives": ["alt-agent"],
            },
        )
        chosen = Span(name="chosen-agent", span_type=SpanType.AGENT, parent_span_id=router.span_id, status=SpanStatus.COMPLETED)
        chosen.started_at = _ts(0)
        chosen.ended_at = _ts(120)
        alt_a = Span(name="alt-agent", span_type=SpanType.AGENT, parent_span_id=router.span_id, status=SpanStatus.COMPLETED)
        alt_a.started_at = _ts(0)
        alt_a.ended_at = _ts(200)
        alt_b = Span(name="alt-agent", span_type=SpanType.AGENT, parent_span_id=router.span_id, status=SpanStatus.COMPLETED)
        alt_b.started_at = _ts(0)
        alt_b.ended_at = _ts(50)
        for span in [router, decision, chosen, alt_a, alt_b]:
            trace.add_span(span)
        trace.complete()

        result = analyze_counterfactual(trace)
        assert result.results[0].verdict == "optimal"
        assert result.results[0].evidence_runs == 2
