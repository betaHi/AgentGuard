"""Tests for distributed trace propagation."""

import os
from pathlib import Path

from agentguard import AgentTrace
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.sdk.distributed import ENV_TRACE_ID, init_recorder_from_env, inject_trace_context
from agentguard.sdk.distributed import merge_child_traces
from agentguard.sdk.recorder import finish_recording, init_recorder


def test_inject_trace_context():
    """inject_trace_context returns proper env vars."""
    recorder = init_recorder(task="parent-task", trigger="api")
    env = inject_trace_context(recorder)

    assert ENV_TRACE_ID in env
    assert env[ENV_TRACE_ID] == recorder.trace.trace_id
    finish_recording()


def test_init_from_env():
    """init_recorder_from_env picks up parent trace context."""
    # Simulate parent
    parent = init_recorder(task="parent-task")
    env = inject_trace_context(parent)
    parent_trace_id = parent.trace.trace_id
    finish_recording()

    # Simulate child (set env vars)
    for k, v in env.items():
        os.environ[k] = v

    child = init_recorder_from_env()
    assert child.trace.trace_id == parent_trace_id
    assert child.trace.task == "parent-task"

    with AgentTrace(name="child-agent") as agent:
        agent.set_output({"result": "ok"})

    trace = finish_recording()
    assert trace.trace_id == parent_trace_id

    # Cleanup env
    for k in env:
        os.environ.pop(k, None)


def test_merge_child_traces_is_idempotent(tmp_path):
    """Repeated merge calls should not duplicate child spans."""
    parent_trace = ExecutionTrace(task="parent")
    parent_span = Span(name="parent-agent", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
    parent_trace.add_span(parent_span)
    parent_trace.complete()

    child_trace = ExecutionTrace(trace_id=parent_trace.trace_id, task="child")
    child_span = Span(
        name="child-agent",
        span_type=SpanType.AGENT,
        status=SpanStatus.COMPLETED,
        parent_span_id=parent_span.span_id,
    )
    child_trace.add_span(child_span)
    child_trace.complete()

    child_file = Path(tmp_path) / f"{parent_trace.trace_id}_child_123.json"
    child_file.write_text(child_trace.to_json(), encoding="utf-8")

    merged_once = merge_child_traces(parent_trace, traces_dir=str(tmp_path), cleanup=False, persist=False)
    merged_twice = merge_child_traces(parent_trace, traces_dir=str(tmp_path), cleanup=False, persist=False)

    child_spans = [span for span in merged_twice.spans if span.name == "child-agent"]
    assert merged_once is merged_twice
    assert len(child_spans) == 1


def test_merge_child_traces_persists_and_cleans_up(tmp_path):
    """Merging child traces should persist parent output and remove child files."""
    parent_trace = ExecutionTrace(task="parent")
    parent_span = Span(name="parent-agent", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
    parent_trace.add_span(parent_span)
    parent_trace.complete()

    child_trace = ExecutionTrace(trace_id=parent_trace.trace_id, task="child")
    child_trace.add_span(
        Span(
            name="child-agent",
            span_type=SpanType.AGENT,
            status=SpanStatus.COMPLETED,
            parent_span_id=parent_span.span_id,
        )
    )
    child_trace.complete()

    child_file = Path(tmp_path) / f"{parent_trace.trace_id}_child_456.json"
    child_file.write_text(child_trace.to_json(), encoding="utf-8")

    merged = merge_child_traces(parent_trace, traces_dir=str(tmp_path), cleanup=True, persist=True)
    parent_file = Path(tmp_path) / f"{parent_trace.trace_id}.json"

    assert parent_file.exists()
    assert not child_file.exists()
    assert any(span.name == "child-agent" for span in merged.spans)
