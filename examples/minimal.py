import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

"""Minimal AgentGuard example — instrument two agents in 10 lines."""
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import finish_recording, init_recorder


@record_tool(name="search")
def search(q): return ["result1", "result2"]

@record_agent(name="researcher", version="v1")
def researcher(topic): return search(topic)

init_recorder(task="Minimal Example")
researcher("AI agents")
trace = finish_recording()
print(f"✅ Trace {trace.trace_id}: {len(trace.spans)} spans, {trace.duration_ms:.0f}ms")
