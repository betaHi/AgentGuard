"""Tests for manual trace API."""

import tempfile
from pathlib import Path

from agentguard.sdk.manual import ManualTracer


def test_manual_tracer_basic():
    """ManualTracer creates proper trace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = ManualTracer(task="manual-test", output_dir=str(Path(tmpdir) / "traces"))

        a = tracer.start_agent("my-agent", version="v1")
        t = tracer.start_tool("search", parent=a, input_data={"q": "test"})
        tracer.end_tool(t, output=["result"])
        tracer.end_agent(a, output={"done": True})

        trace = tracer.finish()
        assert len(trace.spans) == 2
        assert trace.spans[0].name == "my-agent"
        assert trace.spans[1].parent_span_id == trace.spans[0].span_id


def test_manual_tracer_failure():
    """ManualTracer handles failures."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tracer = ManualTracer(task="fail-test", output_dir=str(Path(tmpdir) / "traces"))

        a = tracer.start_agent("agent")
        tracer.fail_span(a, "something broke")

        trace = tracer.finish()
        assert trace.spans[0].status.value == "failed"
        assert trace.spans[0].error == "something broke"
