"""Distributed trace propagation for multi-process agent systems.

When agents are spawned as separate processes (subprocess, multiprocessing, etc.),
trace context must be propagated explicitly. This module provides utilities for that.

Usage:
    # Parent process
    recorder = init_recorder(task="my task")
    env = inject_trace_context()  # returns dict with AGENTGUARD_TRACE_ID etc.
    subprocess.run(["python", "child_agent.py"], env={**os.environ, **env})
    
    # Child process (child_agent.py)
    recorder = init_recorder_from_env()  # picks up trace context from env
    with AgentTrace(name="child-agent") as agent:
        ...
    finish_recording()
"""

from __future__ import annotations

import os
from typing import Optional

from agentguard.sdk.recorder import TraceRecorder, init_recorder, get_recorder

# Environment variable names for trace propagation
ENV_TRACE_ID = "AGENTGUARD_TRACE_ID"
ENV_PARENT_SPAN_ID = "AGENTGUARD_PARENT_SPAN_ID"
ENV_TASK = "AGENTGUARD_TASK"
ENV_TRIGGER = "AGENTGUARD_TRIGGER"
ENV_OUTPUT_DIR = "AGENTGUARD_OUTPUT_DIR"


def inject_trace_context(recorder: Optional[TraceRecorder] = None) -> dict[str, str]:
    """Extract current trace context as environment variables.
    
    Pass these to subprocess.run() or multiprocessing to propagate
    the trace across process boundaries.
    
    Args:
        recorder: TraceRecorder to extract context from. Uses global if None.
    
    Returns:
        Dict of environment variables to set in the child process.
    
    Example:
        env = inject_trace_context()
        subprocess.run(["python", "agent.py"], env={**os.environ, **env})
    """
    rec = recorder or get_recorder()
    return {
        ENV_TRACE_ID: rec.trace.trace_id,
        ENV_PARENT_SPAN_ID: rec.current_span_id or "",
        ENV_TASK: rec.trace.task,
        ENV_TRIGGER: rec.trace.trigger,
        ENV_OUTPUT_DIR: str(rec.output_dir),
    }


def init_recorder_from_env() -> TraceRecorder:
    """Initialize a recorder from environment variables set by parent process.
    
    Call this at the start of a spawned agent process to join 
    the parent's trace.
    
    Returns:
        TraceRecorder connected to the parent trace.
    
    Example:
        # In child_agent.py
        recorder = init_recorder_from_env()
        with AgentTrace(name="child-agent") as agent:
            ...
        finish_recording()
    """
    trace_id = os.environ.get(ENV_TRACE_ID, "")
    parent_span_id = os.environ.get(ENV_PARENT_SPAN_ID, "")
    task = os.environ.get(ENV_TASK, "")
    trigger = os.environ.get(ENV_TRIGGER, "manual")
    output_dir = os.environ.get(ENV_OUTPUT_DIR, ".agentguard/traces")
    
    recorder = init_recorder(task=task, trigger=trigger, output_dir=output_dir)
    
    # Override trace_id to match parent
    if trace_id:
        recorder.trace.trace_id = trace_id
    
    # Set parent span for proper nesting
    if parent_span_id:
        recorder._span_stack.append(parent_span_id)
    
    return recorder


def extract_trace_id() -> Optional[str]:
    """Get the current trace ID from environment (if propagated by parent).
    
    Returns:
        Trace ID string, or None if not in a propagated context.
    """
    return os.environ.get(ENV_TRACE_ID)
