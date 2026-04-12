"""Tests for distributed trace propagation."""

import pytest
import os
from agentguard.sdk.distributed import inject_trace_context, extract_trace_id
from agentguard.sdk.recorder import init_recorder, finish_recording


class TestDistributedTraces:
    def test_inject_context(self):
        """inject_trace_context should return env vars with trace info."""
        recorder = init_recorder(task="distributed_test")
        env = inject_trace_context()
        assert "AGENTGUARD_TRACE_ID" in env
        assert env["AGENTGUARD_TRACE_ID"] == recorder.trace.trace_id
        finish_recording()

    def test_extract_trace_id_from_env(self):
        """extract_trace_id should read from environment."""
        os.environ["AGENTGUARD_TRACE_ID"] = "test-trace-123"
        try:
            tid = extract_trace_id()
            assert tid == "test-trace-123"
        finally:
            del os.environ["AGENTGUARD_TRACE_ID"]
    
    def test_extract_trace_id_missing(self):
        """extract_trace_id should return None when not set."""
        os.environ.pop("AGENTGUARD_TRACE_ID", None)
        tid = extract_trace_id()
        assert tid is None
