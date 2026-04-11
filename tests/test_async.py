"""Tests for async decorators and context managers."""

import asyncio
from agentguard.sdk.async_decorators import record_agent_async, record_tool_async
from agentguard.sdk.context import AsyncAgentTrace
from agentguard.sdk.recorder import init_recorder, finish_recording


def test_async_record_agent():
    """@record_agent_async captures async agent execution."""
    init_recorder(task="async-test")
    
    @record_tool_async(name="async-search")
    async def search(q):
        return [f"result for {q}"]
    
    @record_agent_async(name="async-agent", version="v1")
    async def agent(task):
        results = await search(task)
        return {"results": results}
    
    asyncio.run(agent("test query"))
    trace = finish_recording()
    
    assert len(trace.spans) == 2
    assert trace.spans[0].name == "async-agent"
    assert trace.spans[1].name == "async-search"
    assert trace.spans[1].parent_span_id == trace.spans[0].span_id


def test_async_context_manager():
    """AsyncAgentTrace works as async context manager."""
    init_recorder(task="async-ctx-test")
    
    async def run():
        async with AsyncAgentTrace(name="async-cm-agent", version="v2") as agent:
            agent.set_output({"status": "ok"})
    
    asyncio.run(run())
    trace = finish_recording()
    
    assert len(trace.spans) == 1
    assert trace.spans[0].name == "async-cm-agent"
    assert trace.spans[0].status.value == "completed"


def test_async_failure():
    """Async decorators capture exceptions."""
    init_recorder(task="async-fail")
    
    @record_agent_async(name="failing-async")
    async def bad():
        raise ValueError("async boom")
    
    try:
        asyncio.run(bad())
    except ValueError:
        pass
    
    trace = finish_recording()
    assert trace.spans[0].status.value == "failed"
    assert "async boom" in trace.spans[0].error
