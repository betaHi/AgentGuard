"""AgentGuard — Record, Replay, Evaluate, and Guard your AI Agents.

Quick Start:
    from agentguard import record_agent, record_tool, AgentTrace
    from agentguard.sdk.recorder import init_recorder, finish_recording
    
    # Option 1: Decorators
    @record_agent(name="my-agent", version="v1")
    def my_agent(task): ...
    
    # Option 2: Context managers (less intrusive)
    with AgentTrace(name="my-agent", version="v1") as agent:
        with agent.tool("search") as t:
            results = search(query)
            t.set_output(results)
"""

__version__ = "0.1.0"

from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.context import AgentTrace, ToolContext

__all__ = ["record_agent", "record_tool", "AgentTrace", "ToolContext"]
