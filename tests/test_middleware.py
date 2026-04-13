"""Tests for middleware utilities."""

from agentguard.sdk.middleware import patch_method, wrap_agent, wrap_tool
from agentguard.sdk.recorder import finish_recording, init_recorder


def test_wrap_agent():
    """wrap_agent wraps a plain function."""
    init_recorder(task="wrap-test")

    def my_fn(x):
        return x * 2

    traced = wrap_agent(my_fn, name="wrapped-agent", version="v1")
    result = traced(5)
    assert result == 10

    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "wrapped-agent"


def test_wrap_tool():
    """wrap_tool wraps a plain function."""
    init_recorder(task="wrap-tool-test")

    def search(q):
        return [q]

    traced = wrap_tool(search, name="search")
    result = traced("AI")
    assert result == ["AI"]

    trace = finish_recording()
    assert trace.spans[0].span_type.value == "tool"


def test_patch_method():
    """patch_method instruments a class method."""
    init_recorder(task="patch-test")

    class MyAgent:
        def run(self, task):
            return f"done: {task}"

    patch_method(MyAgent, "run", agent_name="patched-agent")

    agent = MyAgent()
    result = agent.run("test")
    assert result == "done: test"

    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "patched-agent"
