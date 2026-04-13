"""Tests for context manager API."""

from agentguard.sdk.context import AgentTrace
from agentguard.sdk.recorder import finish_recording, init_recorder


def test_agent_trace_context_manager():
    """AgentTrace context manager records agent span."""
    init_recorder(task="ctx-test")

    with AgentTrace(name="my-agent", version="v2") as agent:
        agent.set_output({"result": "ok"})

    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "my-agent"
    assert trace.spans[0].status.value == "completed"


def test_nested_context_managers():
    """Nested agent + tool context managers create proper hierarchy."""
    init_recorder(task="nested-ctx")

    with AgentTrace(name="researcher", version="v1") as agent:
        with agent.tool("search", input_data={"q": "AI"}) as t:
            t.set_output(["result1", "result2"])
        with agent.tool("summarize") as t:
            t.set_output("summary text")
        agent.set_output({"summary": "done"})

    trace = finish_recording()
    assert len(trace.spans) == 3
    assert trace.spans[0].name == "researcher"
    assert trace.spans[1].name == "search"
    assert trace.spans[1].parent_span_id == trace.spans[0].span_id
    assert trace.spans[2].name == "summarize"


def test_context_manager_failure():
    """Context manager captures exceptions."""
    init_recorder(task="fail-ctx")

    try:
        with AgentTrace(name="bad-agent"):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    trace = finish_recording()
    assert trace.spans[0].status.value == "failed"
    assert "RuntimeError: boom" in trace.spans[0].error
