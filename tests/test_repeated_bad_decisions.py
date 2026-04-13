"""Tests for repeated bad decision detection (Q5)."""

import time
from agentguard import record_agent, record_decision
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.analysis import detect_repeated_bad_decisions


class TestRepeatedBadDecisions:
    def test_detects_repeated_failure(self):
        """Agent chosen twice, fails both times → detected."""
        init_recorder(task="repeat", trigger="test")

        @record_agent(name="flaky", version="v1")
        def flaky():
            raise ValueError("always fails")

        @record_agent(name="coord", version="v1")
        def coord():
            for _ in range(3):
                record_decision(
                    coordinator="coord", chosen_agent="flaky",
                    alternatives=["stable"], rationale="bad habit",
                    confidence=0.5,
                )
                try:
                    flaky()
                except ValueError:
                    pass

        coord()
        trace = finish_recording()
        results = detect_repeated_bad_decisions(trace)
        assert len(results) >= 1
        assert results[0].agent == "flaky"
        assert results[0].times_chosen >= 2
        assert results[0].times_failed >= 2
        assert results[0].failure_rate > 0

    def test_no_repeat_if_single_choice(self):
        """Agent chosen once → not flagged even if failed."""
        init_recorder(task="single", trigger="test")

        @record_agent(name="once", version="v1")
        def once():
            raise RuntimeError("fail")

        @record_agent(name="coord", version="v1")
        def coord():
            record_decision(
                coordinator="coord", chosen_agent="once",
                alternatives=[], rationale="only option",
                confidence=1.0,
            )
            try:
                once()
            except RuntimeError:
                pass

        coord()
        trace = finish_recording()
        results = detect_repeated_bad_decisions(trace)
        assert len(results) == 0  # only chosen once

    def test_no_decisions_empty(self):
        """Trace with no decisions → empty list."""
        init_recorder(task="empty", trigger="test")

        @record_agent(name="solo", version="v1")
        def solo():
            return {}

        solo()
        trace = finish_recording()
        results = detect_repeated_bad_decisions(trace)
        assert results == []

    def test_successful_repeats_not_flagged(self):
        """Agent chosen multiple times but always succeeds → not flagged."""
        init_recorder(task="success", trigger="test")

        @record_agent(name="reliable", version="v1")
        def reliable():
            return {"ok": True}

        @record_agent(name="coord", version="v1")
        def coord():
            for _ in range(3):
                record_decision(
                    coordinator="coord", chosen_agent="reliable",
                    alternatives=["other"], rationale="trust",
                    confidence=0.9,
                )
                reliable()

        coord()
        trace = finish_recording()
        results = detect_repeated_bad_decisions(trace)
        assert len(results) == 0

    def test_to_dict_serializable(self):
        """Results are JSON-serializable."""
        import json
        init_recorder(task="dict", trigger="test")

        @record_agent(name="bad", version="v1")
        def bad():
            raise RuntimeError("err")

        @record_agent(name="coord", version="v1")
        def coord():
            for _ in range(2):
                record_decision(
                    coordinator="coord", chosen_agent="bad",
                    alternatives=[], rationale="x", confidence=0.5,
                )
                try:
                    bad()
                except RuntimeError:
                    pass

        coord()
        trace = finish_recording()
        results = detect_repeated_bad_decisions(trace)
        if results:
            d = results[0].to_dict()
            json.dumps(d)  # should not raise
            assert "failure_rate" in d

    def test_sorted_by_failure_rate(self):
        """Results sorted by failure_rate descending."""
        init_recorder(task="sort", trigger="test")

        @record_agent(name="sometimes_bad", version="v1")
        def sometimes_bad(fail=False):
            if fail:
                raise RuntimeError("err")
            return {}

        @record_agent(name="always_bad", version="v1")
        def always_bad():
            raise RuntimeError("err")

        @record_agent(name="coord", version="v1")
        def coord():
            for i in range(3):
                record_decision(
                    coordinator="coord", chosen_agent="sometimes_bad",
                    alternatives=[], rationale="x", confidence=0.5,
                )
                try:
                    sometimes_bad(fail=(i == 0))
                except RuntimeError:
                    pass
            for _ in range(2):
                record_decision(
                    coordinator="coord", chosen_agent="always_bad",
                    alternatives=[], rationale="x", confidence=0.5,
                )
                try:
                    always_bad()
                except RuntimeError:
                    pass

        coord()
        trace = finish_recording()
        results = detect_repeated_bad_decisions(trace)
        if len(results) >= 2:
            assert results[0].failure_rate >= results[1].failure_rate
