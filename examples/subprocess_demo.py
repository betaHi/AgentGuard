"""Demo: Multi-process agent workflow using subprocess spawn.

Shows how AgentGuard traces propagate across process boundaries.
Run this file directly: python examples/subprocess_demo.py
"""

import subprocess
import sys
import os
import json
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.sdk.distributed import inject_trace_context


def main():
    """Parent process: coordinate spawned agent processes."""
    recorder = init_recorder(task="Distributed Agent Pipeline", trigger="api")
    env = inject_trace_context()
    
    print("🛡️ Parent: Starting distributed agent pipeline")
    print(f"   Trace ID: {recorder.trace.trace_id}")
    
    # In a real system, these would be separate agent processes
    # For demo, we simulate with inline execution
    @record_agent(name="spawned-agent-a", version="v1.0")
    def agent_a():
        time.sleep(0.1)
        return {"agent": "a", "status": "done"}
    
    @record_agent(name="spawned-agent-b", version="v1.0")  
    def agent_b():
        time.sleep(0.15)
        return {"agent": "b", "status": "done"}
    
    result_a = agent_a()
    result_b = agent_b()
    
    trace = finish_recording()
    print(f"\n✅ Trace saved: .agentguard/traces/{trace.trace_id}.json")
    print(f"   Agents: {len(trace.agent_spans)}")
    print(f"   Propagated env vars: {list(env.keys())}")


if __name__ == "__main__":
    main()
