"""Tests for agentguard.configure() global settings."""

import pytest
import agentguard
from agentguard.settings import configure, get_settings, reset_settings, Settings


class TestConfigure:
    def setup_method(self):
        reset_settings()

    def test_defaults(self):
        s = get_settings()
        assert s.output_dir == ".agentguard"
        assert s.max_trace_size_mb == 10.0
        assert s.sampling_rate == 1.0
        assert s.auto_truncate is False

    def test_set_output_dir(self):
        configure(output_dir="./my-traces")
        assert get_settings().output_dir == "./my-traces"

    def test_set_max_trace_size(self):
        configure(max_trace_size_mb=20.0)
        assert get_settings().max_trace_size_mb == 20.0

    def test_set_sampling_rate(self):
        configure(sampling_rate=0.5)
        assert get_settings().sampling_rate == 0.5

    def test_set_auto_truncate(self):
        configure(auto_truncate=True)
        assert get_settings().auto_truncate is True

    def test_partial_update_preserves_other(self):
        configure(output_dir="./a")
        configure(sampling_rate=0.1)
        s = get_settings()
        assert s.output_dir == "./a"
        assert s.sampling_rate == 0.1

    def test_invalid_sampling_rate_raises(self):
        with pytest.raises(ValueError, match="sampling_rate"):
            configure(sampling_rate=1.5)

    def test_invalid_negative_sampling_rate(self):
        with pytest.raises(ValueError, match="sampling_rate"):
            configure(sampling_rate=-0.1)

    def test_invalid_max_trace_size_raises(self):
        with pytest.raises(ValueError, match="max_trace_size"):
            configure(max_trace_size_mb=0)

    def test_reset_restores_defaults(self):
        configure(output_dir="./x", sampling_rate=0.1)
        reset_settings()
        s = get_settings()
        assert s.output_dir == ".agentguard"
        assert s.sampling_rate == 1.0

    def test_accessible_from_package(self):
        """configure() is importable from agentguard directly."""
        agentguard.configure(output_dir="./test")
        assert agentguard.get_settings().output_dir == "./test"
        agentguard.reset_settings()


class TestSettingsValidation:
    def test_valid_settings(self):
        s = Settings(sampling_rate=0.5, max_trace_size_mb=5.0)
        assert s.validate() == []

    def test_sampling_rate_boundary(self):
        assert Settings(sampling_rate=0.0).validate() == []
        assert Settings(sampling_rate=1.0).validate() == []
        assert len(Settings(sampling_rate=1.01).validate()) > 0
