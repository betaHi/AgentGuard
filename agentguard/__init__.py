"""AgentGuard — Record, Replay, Evaluate, and Guard your AI Agents.

Integration styles:

    # Style 1: Decorators (sync)
    @record_agent(name="my-agent", version="v1")
    def my_agent(task): ...
    
    # Style 2: Decorators (async)
    @record_agent_async(name="my-agent", version="v1")
    async def my_agent(task): ...
    
    # Style 3: Context managers (sync)
    with AgentTrace(name="my-agent", version="v1") as agent:
        ...
    
    # Style 4: Context managers (async)
    async with AsyncAgentTrace(name="my-agent", version="v1") as agent:
        ...
    
    # Style 5: Spawned processes
    from agentguard.sdk.distributed import inject_trace_context, init_recorder_from_env
"""

__version__ = "0.1.0"

from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.async_decorators import record_agent_async, record_tool_async
from agentguard.sdk.context import AgentTrace, ToolContext, AsyncAgentTrace, AsyncToolContext

__all__ = [
    "record_agent", "record_tool",
    "record_agent_async", "record_tool_async",
    "AgentTrace", "ToolContext",
    "AsyncAgentTrace", "AsyncToolContext",
]
