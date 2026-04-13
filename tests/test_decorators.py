"""Tests for SDK decorators."""

import contextlib

from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.recorder import finish_recording, init_recorder


def test_record_agent_basic():
    """@record_agent captures agent execution."""
    init_recorder(task="test")

    @record_agent(name="test-agent", version="v1")
    def my_agent(x: int) -> int:
        return x * 2

    result = my_agent(5)
    assert result == 10

    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "test-agent"
    assert trace.spans[0].status.value == "completed"
    assert trace.spans[0].metadata["agent_version"] == "v1"


def test_record_tool_basic():
    """@record_tool captures tool execution."""
    init_recorder(task="test")

    @record_tool(name="calculator")
    def add(a: int, b: int) -> int:
        return a + b

    result = add(3, 4)
    assert result == 7

    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "calculator"
    assert trace.spans[0].span_type.value == "tool"


def test_nested_agent_tool():
    """Nested agent → tool calls create parent-child spans."""
    init_recorder(task="nested-test")

    @record_tool(name="search")
    def search(query: str) -> list:
        return ["result1", "result2"]

    @record_agent(name="researcher", version="v1")
    def research(topic: str) -> dict:
        results = search(topic)
        return {"topic": topic, "results": results}

    output = research("AI agents")
    assert output["results"] == ["result1", "result2"]

    trace = finish_recording()
    assert len(trace.spans) == 2

    agent_span = trace.spans[0]
    tool_span = trace.spans[1]
    assert agent_span.name == "researcher"
    assert tool_span.name == "search"
    assert tool_span.parent_span_id == agent_span.span_id


def test_record_agent_failure():
    """@record_agent captures failures."""
    init_recorder(task="fail-test")

    @record_agent(name="failing-agent", version="v1")
    def bad_agent() -> None:
        raise ValueError("oops")

    with contextlib.suppress(ValueError):
        bad_agent()

    trace = finish_recording()
    assert trace.spans[0].status.value == "failed"
    assert "ValueError: oops" in trace.spans[0].error
