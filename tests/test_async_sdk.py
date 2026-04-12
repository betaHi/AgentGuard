"""Tests for async SDK integration styles."""

import pytest
import asyncio
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.core.trace import SpanType, SpanStatus


class TestAsyncDecorators:
    def test_async_agent(self):
        from agentguard import record_agent_async
        init_recorder(task="async_agent_test")
        
        @record_agent_async(name="async_worker")
        async def worker():
            await asyncio.sleep(0.01)
            return {"result": "async done"}
        
        result = asyncio.run(worker())
        trace = finish_recording()
        
        assert result == {"result": "async done"}
        agents = [s for s in trace.spans if s.span_type == SpanType.AGENT]
        assert len(agents) == 1
        assert agents[0].name == "async_worker"

    def test_async_tool(self):
        from agentguard.sdk.async_decorators import record_tool_async
        init_recorder(task="async_tool_test")
        
        @record_tool_async(name="async_fetch")
        async def fetch(url):
            await asyncio.sleep(0.01)
            return {"data": url}
        
        result = asyncio.run(fetch("https://test.com"))
        trace = finish_recording()
        
        tools = [s for s in trace.spans if s.span_type == SpanType.TOOL]
        assert len(tools) == 1

    def test_async_error(self):
        from agentguard import record_agent_async
        init_recorder(task="async_error_test")
        
        @record_agent_async(name="async_fail")
        async def fail():
            await asyncio.sleep(0.01)
            raise RuntimeError("async boom")
        
        with pytest.raises(RuntimeError):
            asyncio.run(fail())
        
        trace = finish_recording()
        agent = trace.spans[0]
        assert agent.status == SpanStatus.FAILED
        assert "async boom" in agent.error


class TestAsyncContextManagers:
    def test_async_agent_context(self):
        from agentguard import AsyncAgentTrace
        init_recorder(task="async_ctx_test")
        
        async def run():
            async with AsyncAgentTrace(name="async_ctx") as agent:
                await asyncio.sleep(0.01)
                agent.set_output({"done": True})
        
        asyncio.run(run())
        trace = finish_recording()
        assert len(trace.spans) >= 1
