"""Tests for SDK trace sampling — record only N% of traces."""

from unittest.mock import patch
import agentguard
from agentguard.sdk.decorators import record_agent, _should_sample
from agentguard.settings import reset_settings


class TestSampling:
    def setup_method(self):
        reset_settings()

    def teardown_method(self):
        reset_settings()

    def test_default_rate_always_samples(self):
        """Default sampling_rate=1.0 always records."""
        for _ in range(20):
            assert _should_sample() is True

    def test_zero_rate_never_samples(self):
        agentguard.configure(sampling_rate=0.0)
        for _ in range(20):
            assert _should_sample() is False

    def test_full_rate_always_samples(self):
        agentguard.configure(sampling_rate=1.0)
        for _ in range(20):
            assert _should_sample() is True

    def test_partial_rate_probabilistic(self):
        """50% sampling should produce roughly half True."""
        agentguard.configure(sampling_rate=0.5)
        results = [_should_sample() for _ in range(1000)]
        true_count = sum(results)
        # Should be roughly 500 ± 100
        assert 300 < true_count < 700, f"Got {true_count}/1000"

    def test_decorated_function_works_when_sampled_out(self):
        """Function returns correctly even when not sampled."""
        agentguard.configure(sampling_rate=0.0)

        @record_agent(name="test")
        def my_fn(x):
            return x * 3

        assert my_fn(7) == 21

    def test_decorated_function_works_when_sampled_in(self):
        agentguard.configure(sampling_rate=1.0)

        @record_agent(name="test")
        def my_fn(x):
            return x + 1

        assert my_fn(10) == 11

    def test_exception_still_raised_when_sampled_out(self):
        agentguard.configure(sampling_rate=0.0)

        @record_agent(name="test")
        def failing():
            raise ValueError("boom")

        import pytest
        with pytest.raises(ValueError, match="boom"):
            failing()

    def test_settings_unavailable_defaults_to_sample(self):
        """If settings module fails, should still record (fail-open)."""
        with patch("agentguard.settings.get_settings",
                   side_effect=RuntimeError("broken")):
            assert _should_sample() is True
