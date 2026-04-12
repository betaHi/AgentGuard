"""Comprehensive SDK tests — verify all 7 integration styles work correctly."""

import pytest
import asyncio
from agentguard.sdk.recorder import init_recorder, finish_recording, get_recorder
from agentguard.core.trace import SpanType, SpanStatus


class TestDecoratorStyle:
    """Style 1: Sync decorators."""
    
    def test_agent_decorator(self):
        from agentguard import record_agent
        init_recorder(task="decorator_test")
        
        @record_agent(name="test_agent", version="v1.0")
        def my_agent(x):
            return x * 2
        
        result = my_agent(5)
        trace = finish_recording()
        
        assert result == 10
        agents = [s for s in trace.spans if s.span_type == SpanType.AGENT]
        assert len(agents) == 1
        assert agents[0].name == "test_agent"
        assert agents[0].status == SpanStatus.COMPLETED
    
    def test_tool_decorator(self):
        from agentguard import record_tool
        init_recorder(task="tool_test")
        
        @record_tool(name="my_tool")
        def fetch(url):
            return {"data": url}
        
        result = fetch("https://example.com")
        trace = finish_recording()
        
        assert result == {"data": "https://example.com"}
        tools = [s for s in trace.spans if s.span_type == SpanType.TOOL]
        assert len(tools) == 1

    def test_nested_agent_tool(self):
        from agentguard import record_agent, record_tool
        init_recorder(task="nested_test")
        
        @record_tool(name="search")
        def search(q):
            return [q]
        
        @record_agent(name="researcher")
        def research(topic):
            results = search(topic)
            return {"results": results}
        
        result = research("AI")
        trace = finish_recording()
        
        assert len(trace.spans) >= 2
        # Tool should be child of agent
        agent = next(s for s in trace.spans if s.name == "researcher")
        tool = next(s for s in trace.spans if s.name == "search")
        assert tool.parent_span_id == agent.span_id

    def test_error_in_agent(self):
        from agentguard import record_agent
        init_recorder(task="error_test")
        
        @record_agent(name="failing")
        def fail():
            raise ValueError("test error")
        
        with pytest.raises(ValueError):
            fail()
        
        trace = finish_recording()
        agent = trace.spans[0]
        assert agent.status == SpanStatus.FAILED
        assert "test error" in agent.error


class TestContextManagerStyle:
    """Style 3: Context managers."""
    
    def test_agent_context(self):
        from agentguard import AgentTrace
        init_recorder(task="ctx_test")
        
        with AgentTrace(name="ctx_agent", version="v2") as agent:
            agent.set_output({"result": "done"})
        
        trace = finish_recording()
        assert len(trace.spans) >= 1
        assert trace.spans[0].name == "ctx_agent"
    
    def test_tool_context(self):
        from agentguard import ToolContext
        init_recorder(task="tool_ctx_test")
        
        with ToolContext(name="ctx_tool") as tool:
            tool.set_output({"data": "fetched"})
        
        trace = finish_recording()
        tools = [s for s in trace.spans if s.span_type == SpanType.TOOL]
        assert len(tools) >= 1


class TestHandoffStyle:
    """Style 6: Explicit handoff recording."""
    
    def test_handoff(self):
        from agentguard import record_handoff, mark_context_used
        init_recorder(task="handoff_test")
        
        ctx = {"articles": [1, 2], "metadata": "info"}
        h = record_handoff("sender", "receiver", context=ctx, summary="2 articles")
        result = mark_context_used(h, used_keys=["articles"])
        
        trace = finish_recording()
        handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
        assert len(handoffs) == 1
        assert handoffs[0].handoff_from == "sender"
        assert handoffs[0].handoff_to == "receiver"
        assert result["utilization_ratio"] == 0.5  # 1 of 2 keys used
