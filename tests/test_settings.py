"""Tests for agentguard.configure() global settings."""

import pytest

import agentguard
from agentguard.sdk.threading import is_auto_trace_threading_enabled
from agentguard.sdk.recorder import finish_recording, init_recorder
from agentguard.settings import Settings, configure, get_settings, reset_settings


class TestConfigure:
    def setup_method(self):
        reset_settings()

    def test_defaults(self):
        s = get_settings()
        assert s.output_dir == ".agentguard/traces"
        assert s.max_trace_size_mb == 10.0
        assert s.sampling_rate == 1.0
        assert s.auto_truncate is False
        assert s.auto_thread_context is False

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

    def test_set_auto_thread_context(self):
        configure(auto_thread_context=True)
        assert get_settings().auto_thread_context is True
        assert is_auto_trace_threading_enabled() is True

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
        assert s.output_dir == ".agentguard/traces"
        assert s.sampling_rate == 1.0
        assert s.auto_thread_context is False
        assert is_auto_trace_threading_enabled() is False

    def test_accessible_from_package(self):
        """configure() is importable from agentguard directly."""
        agentguard.configure(output_dir="./test")
        assert agentguard.get_settings().output_dir == "./test"
        agentguard.reset_settings()

    def test_init_recorder_uses_configured_output_dir(self, tmp_path):
        traces_dir = tmp_path / "product-traces"
        configure(output_dir=str(traces_dir))
        init_recorder(task="configured-output")
        trace = finish_recording()
        assert (traces_dir / f"{trace.trace_id}.json").exists()


class TestSettingsValidation:
    def test_valid_settings(self):
        s = Settings(sampling_rate=0.5, max_trace_size_mb=5.0)
        assert s.validate() == []

    def test_sampling_rate_boundary(self):
        assert Settings(sampling_rate=0.0).validate() == []
        assert Settings(sampling_rate=1.0).validate() == []
        assert len(Settings(sampling_rate=1.01).validate()) > 0
