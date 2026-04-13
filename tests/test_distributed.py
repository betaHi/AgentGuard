"""Tests for distributed trace propagation."""

import os

from agentguard import AgentTrace
from agentguard.sdk.distributed import ENV_TRACE_ID, init_recorder_from_env, inject_trace_context
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
