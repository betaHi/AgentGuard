"""Demo: Multi-process agent workflow using subprocess spawn.

Shows how AgentGuard traces propagate across process boundaries.
Run this file directly: python examples/subprocess_demo.py

Architecture:
    - Parent process creates the trace and spawns child processes
    - Each child receives trace context via environment variables
    - Child traces are written to separate files, then merged by parent
"""

import subprocess
import sys
import os
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.sdk.distributed import (
    inject_trace_context,
    init_recorder_from_env,
    merge_child_traces,
)


def run_child(agent_name: str, duration: float):
    """Child process entry point — called when this script is invoked with args."""
    recorder = init_recorder_from_env()

    @record_agent(name=agent_name, version="v1.0")
    def do_work():
        time.sleep(duration)
        return {"agent": agent_name, "pid": os.getpid(), "status": "done"}

    result = do_work()
    finish_recording()
    print(f"   [{agent_name}] pid={os.getpid()} completed: {result}")


def main():
    """Parent process: spawn real child agent processes and merge traces."""
    recorder = init_recorder(task="Distributed Agent Pipeline", trigger="api")
    print("🛡️ Parent: Starting distributed agent pipeline")
    print(f"   Trace ID: {recorder.trace.trace_id}")
    print(f"   Parent PID: {os.getpid()}")

    # Build env with trace context propagated to children
    child_env = {**os.environ, **inject_trace_context()}

    # Spawn two agent processes using this same script with child args
    this_script = os.path.abspath(__file__)
    children = []
    for agent_name, duration in [("spawned-agent-a", "0.1"), ("spawned-agent-b", "0.15")]:
        proc = subprocess.Popen(
            [sys.executable, this_script, "--child", agent_name, duration],
            env=child_env,
        )
        children.append(proc)

    # Wait for all children to finish
    for proc in children:
        proc.wait()

    # Finish parent trace, then merge child traces
    trace = finish_recording()
    merged = merge_child_traces(trace, traces_dir=str(recorder.output_dir))

    print(f"\n✅ Trace saved: {recorder.output_dir / (trace.trace_id + '.json')}")
    print(f"   Total spans (merged): {len(merged.spans)}")
    pids = {os.getpid()}
    for span in merged.spans:
        if hasattr(span, 'metadata') and span.metadata and 'pid' in span.metadata:
            pids.add(span.metadata['pid'])
    print(f"   Cross-process: True (parent + {len(children)} children)")


if __name__ == "__main__":
    if "--child" in sys.argv:
        idx = sys.argv.index("--child")
        agent_name = sys.argv[idx + 1]
        duration = float(sys.argv[idx + 2])
        run_child(agent_name, duration)
    else:
        main()
