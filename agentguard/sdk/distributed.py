"""Distributed trace propagation for multi-process agent systems.

When agents are spawned as separate processes (subprocess, multiprocessing, etc.),
trace context must be propagated explicitly. This module provides utilities for that.

Architecture:
    - Parent process creates the main trace and writes to {trace_id}.json
    - Each child process writes to {trace_id}_child_{pid}.json
    - After all children complete, call merge_child_traces() to combine
      into a single file and optionally clean up child files.

Usage:
    # Parent process
    recorder = init_recorder(task="my task")
    env = inject_trace_context(parent_span_id="some-span-id")
    subprocess.run(["python", "child.py"], env={**os.environ, **env})
    trace = finish_recording()
    merged = merge_child_traces(trace)  # merges, persists, cleans up

    # Child process (child.py)
    recorder = init_recorder_from_env()
    with AgentTrace(name="child-agent") as agent:
        ...
    finish_recording()
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path

from agentguard.core.trace import ExecutionTrace
from agentguard.sdk.recorder import TraceRecorder, get_recorder, init_recorder

ENV_TRACE_ID = "AGENTGUARD_TRACE_ID"
ENV_PARENT_SPAN_ID = "AGENTGUARD_PARENT_SPAN_ID"
ENV_TASK = "AGENTGUARD_TASK"
ENV_TRIGGER = "AGENTGUARD_TRIGGER"
ENV_OUTPUT_DIR = "AGENTGUARD_OUTPUT_DIR"


def inject_trace_context(
    recorder: TraceRecorder | None = None,
    parent_span_id: str | None = None,
) -> dict[str, str]:
    """Extract current trace context as environment variables.

    Args:
        recorder: TraceRecorder to extract context from. Uses global if None.
        parent_span_id: Explicit parent span ID for child spans to nest under.

    Returns:
        Dict of environment variables to set in the child process.
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

    Child writes to a separate file ({trace_id}_child_{pid}.json).
    Use merge_child_traces() in the parent after all children complete.

    Returns:
        TraceRecorder connected to the parent trace context.
    """
    trace_id = os.environ.get(ENV_TRACE_ID, "")
    parent_span_id = os.environ.get(ENV_PARENT_SPAN_ID, "")
    task = os.environ.get(ENV_TASK, "")
    trigger = os.environ.get(ENV_TRIGGER, "manual")
    output_dir = os.environ.get(ENV_OUTPUT_DIR, ".agentguard/traces")

    recorder = init_recorder(task=task, trigger=trigger, output_dir=output_dir)

    if trace_id:
        recorder.trace.trace_id = trace_id

    if parent_span_id:
        recorder._local.span_stack = [parent_span_id]

    pid = os.getpid()
    recorder._child_suffix = f"_child_{pid}"

    return recorder


def merge_child_traces(
    parent_trace: ExecutionTrace,
    traces_dir: str = ".agentguard/traces",
    cleanup: bool = True,
    persist: bool = True,
) -> ExecutionTrace:
    """Merge child process traces into the parent trace.

    Finds all {trace_id}_child_*.json files, incorporates their spans
    into the parent trace, optionally persists the merged result to disk,
    and optionally removes child files.

    Args:
        parent_trace: The parent ExecutionTrace to merge into.
        traces_dir: Directory containing trace files.
        cleanup: If True, delete child trace files after merging.
        persist: If True, overwrite the parent trace file with merged result.

    Returns:
        Merged ExecutionTrace with all child spans included.
    """
    dir_path = Path(traces_dir)
    if not dir_path.exists():
        return parent_trace

    pattern = f"{parent_trace.trace_id}_child_*.json"
    child_files = list(dir_path.glob(pattern))

    if not child_files:
        return parent_trace

    for child_file in child_files:
        try:
            child_data = json.loads(child_file.read_text(encoding="utf-8"))
            child_trace = ExecutionTrace.from_dict(child_data)

            for span in child_trace.spans:
                span.trace_id = parent_trace.trace_id
                parent_trace.spans.append(span)
        except Exception:
            pass

    # Persist merged trace to the parent file
    if persist:
        parent_file = dir_path / f"{parent_trace.trace_id}.json"
        parent_file.write_text(parent_trace.to_json(), encoding="utf-8")

    # Clean up child files
    if cleanup:
        for child_file in child_files:
            with contextlib.suppress(Exception):
                child_file.unlink()

    return parent_trace


def extract_trace_id() -> str | None:
    """Get the current trace ID from environment (if propagated by parent)."""
    return os.environ.get(ENV_TRACE_ID)
