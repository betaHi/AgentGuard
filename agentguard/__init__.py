"""AgentGuard — Record, Replay, Evaluate, and Guard your AI Agents.

Three integration styles, pick what fits:

    # Style 1: Decorators (minimal code change)
    @record_agent(name="my-agent", version="v1")
    def my_agent(task): ...
    
    # Style 2: Context managers (zero decoration)
    with AgentTrace(name="my-agent", version="v1") as agent:
        ...
    
    # Style 3: Spawned processes (multi-process agents)
    from agentguard.sdk.distributed import inject_trace_context, init_recorder_from_env
"""

__version__ = "0.1.0"

from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.context import AgentTrace, ToolContext

__all__ = ["record_agent", "record_tool", "AgentTrace", "ToolContext"]
