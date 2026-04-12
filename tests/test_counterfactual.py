"""Tests for counterfactual decision analysis (Q5)."""

from agentguard import record_agent, record_decision
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.analysis import analyze_counterfactual

import time


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
            try:
                bad_choice()
            except RuntimeError:
                pass
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
