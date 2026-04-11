"""Distributed trace propagation for multi-process agent systems.

When agents are spawned as separate processes (subprocess, multiprocessing, etc.),
trace context must be propagated explicitly. This module provides utilities for that.

Architecture:
    - Parent process creates the main trace and writes to {trace_id}.json
    - Each child process writes to {trace_id}_child_{pid}.json
    - After all children complete, call merge_child_traces() to combine
    
Usage:
    # Parent process
    recorder = init_recorder(task="my task")
    parent_span = recorder.trace.spans[0]  # get the parent agent span
    env = inject_trace_context(parent_span_id=parent_span.span_id)
    subprocess.run(["python", "child_agent.py"], env={**os.environ, **env})
    trace = finish_recording()
    # Merge child traces into parent
    merged = merge_child_traces(trace)
    
    # Child process (child_agent.py)
    recorder = init_recorder_from_env()  # separate file, linked by trace_id
    with AgentTrace(name="child-agent") as agent:
        ...
    finish_recording()
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span
from agentguard.sdk.recorder import TraceRecorder, init_recorder, get_recorder

# Environment variable names for trace propagation
ENV_TRACE_ID = "AGENTGUARD_TRACE_ID"
ENV_PARENT_SPAN_ID = "AGENTGUARD_PARENT_SPAN_ID"
ENV_TASK = "AGENTGUARD_TASK"
ENV_TRIGGER = "AGENTGUARD_TRIGGER"
ENV_OUTPUT_DIR = "AGENTGUARD_OUTPUT_DIR"


def inject_trace_context(
    recorder: Optional[TraceRecorder] = None,
    parent_span_id: Optional[str] = None,
) -> dict[str, str]:
    """Extract current trace context as environment variables.
    
    Pass these to subprocess.run() or multiprocessing to propagate
    the trace across process boundaries.
    
    Args:
        recorder: TraceRecorder to extract context from. Uses global if None.
        parent_span_id: Explicit parent span ID for child spans to nest under.
                       If None, uses the current span on the recorder's stack.
    
    Returns:
        Dict of environment variables to set in the child process.
    
    Example:
        # In parent, after starting an agent span:
        env = inject_trace_context(parent_span_id=agent_span_id)
        subprocess.run(["python", "agent.py"], env={**os.environ, **env})
    """
    rec = recorder or get_recorder()
    return {
        ENV_TRACE_ID: rec.trace.trace_id,
        ENV_PARENT_SPAN_ID: parent_span_id or rec.current_span_id or "",
        ENV_TASK: rec.trace.task,
        ENV_TRIGGER: rec.trace.trigger,
        ENV_OUTPUT_DIR: str(rec.output_dir),
    }


def init_recorder_from_env() -> TraceRecorder:
    """Initialize a recorder from environment variables set by parent process.
    
    The child recorder writes to a separate file ({trace_id}_child_{pid}.json)
    to avoid overwriting the parent trace. Use merge_child_traces() after
    all children complete to combine everything.
    
    Returns:
        TraceRecorder connected to the parent trace context.
    """
    trace_id = os.environ.get(ENV_TRACE_ID, "")
    parent_span_id = os.environ.get(ENV_PARENT_SPAN_ID, "")
    task = os.environ.get(ENV_TASK, "")
    trigger = os.environ.get(ENV_TRIGGER, "manual")
    output_dir = os.environ.get(ENV_OUTPUT_DIR, ".agentguard/traces")
    
    recorder = init_recorder(task=task, trigger=trigger, output_dir=output_dir)
    
    # Use same trace_id as parent for correlation
    if trace_id:
        recorder.trace.trace_id = trace_id
    
    # Set parent span ID so child spans nest correctly
    # We push it onto the stack so new spans get this as parent
    if parent_span_id:
        recorder._local.span_stack = [parent_span_id]
    
    # Override the output filename to avoid overwriting parent
    pid = os.getpid()
    recorder._child_suffix = f"_child_{pid}"
    
    return recorder


def merge_child_traces(
    parent_trace: ExecutionTrace,
    traces_dir: str = ".agentguard/traces",
) -> ExecutionTrace:
    """Merge child process traces into the parent trace.
    
    Finds all {trace_id}_child_*.json files and incorporates their spans
    into the parent trace, preserving parent_span_id linkage.
    
    Args:
        parent_trace: The parent ExecutionTrace to merge into.
        traces_dir: Directory containing trace files.
    
    Returns:
        Merged ExecutionTrace with all child spans included.
    """
    dir_path = Path(traces_dir)
    if not dir_path.exists():
        return parent_trace
    
    # Find child trace files
    pattern = f"{parent_trace.trace_id}_child_*.json"
    child_files = list(dir_path.glob(pattern))
    
    for child_file in child_files:
        try:
            child_data = json.loads(child_file.read_text(encoding="utf-8"))
            child_trace = ExecutionTrace.from_dict(child_data)
            
            # Add child spans to parent, preserving their parent_span_id
            for span in child_trace.spans:
                span.trace_id = parent_trace.trace_id
                parent_trace.spans.append(span)
            
            # Optionally remove the child file after merging
            # child_file.unlink()
        except Exception:
            pass  # Skip malformed child traces
    
    return parent_trace


def extract_trace_id() -> Optional[str]:
    """Get the current trace ID from environment (if propagated by parent)."""
    return os.environ.get(ENV_TRACE_ID)
