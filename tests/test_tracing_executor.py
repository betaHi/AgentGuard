"""Tests for TracingExecutor — thread pool with trace context propagation."""

import contextlib
import time

from agentguard import record_agent, record_tool
from agentguard.sdk.context import TracingExecutor
from agentguard.sdk.recorder import finish_recording, init_recorder


def test_basic_context_propagation():
    """Spans in worker threads are parented to the submitting span."""
    init_recorder(task="executor test")

    @record_agent(name="coordinator", version="v1")
    def coordinator():
        @record_agent(name="worker", version="v1")
        def worker(item):
            return {"item": item, "done": True}

        with TracingExecutor(max_workers=2) as executor:
            futures = [executor.submit(worker, i) for i in range(3)]
            return [f.result() for f in futures]

    results = coordinator()
    trace = finish_recording()

    assert len(results) == 3
    # Worker spans should exist
    workers = [s for s in trace.spans if s.name == "worker"]
    assert len(workers) == 3
    # Workers should be parented to coordinator
    coord = [s for s in trace.spans if s.name == "coordinator"][0]
    for w in workers:
        assert w.parent_span_id == coord.span_id


def test_tool_spans_in_workers():
    """Tool spans inside workers are correctly parented."""
    init_recorder(task="tool in worker")

    @record_tool(name="process")
    def process(x):
        return x * 2

    @record_agent(name="parallel-agent", version="v1")
    def parallel_agent():
        with TracingExecutor(max_workers=2) as executor:
            futures = [executor.submit(process, i) for i in range(4)]
            return [f.result() for f in futures]

    parallel_agent()
    trace = finish_recording()

    tools = [s for s in trace.spans if s.name == "process"]
    assert len(tools) == 4
    agent = [s for s in trace.spans if s.name == "parallel-agent"][0]
    for t in tools:
        assert t.parent_span_id == agent.span_id


def test_exception_in_worker():
    """Exceptions in workers propagate correctly and span is marked failed."""
    init_recorder(task="exception test")

    @record_agent(name="failing-worker", version="v1")
    def failing_worker():
        raise ValueError("boom")

    with TracingExecutor(max_workers=1) as executor:
        future = executor.submit(failing_worker)
        with contextlib.suppress(ValueError):
            future.result()

    trace = finish_recording()
    failed = [s for s in trace.spans if s.name == "failing-worker"]
    assert len(failed) == 1
    assert failed[0].status.value == "failed"
    assert "boom" in failed[0].error


def test_context_manager():
    """TracingExecutor works as context manager."""
    init_recorder(task="ctx manager")

    with TracingExecutor(max_workers=2) as executor:
        future = executor.submit(lambda: 42)
        assert future.result() == 42

    finish_recording()


def test_empty_submit():
    """Submitting zero tasks works fine."""
    init_recorder(task="empty")
    with TracingExecutor(max_workers=1):
        pass  # no submits
    trace = finish_recording()
    assert trace is not None


def test_concurrent_agents_all_traced():
    """Multiple concurrent agents all appear in trace."""
    init_recorder(task="concurrent")

    @record_agent(name="agent-a", version="v1")
    def agent_a():
        time.sleep(0.01)
        return "a"

    @record_agent(name="agent-b", version="v1")
    def agent_b():
        time.sleep(0.01)
        return "b"

    with TracingExecutor(max_workers=2) as executor:
        fa = executor.submit(agent_a)
        fb = executor.submit(agent_b)
        assert fa.result() == "a"
        assert fb.result() == "b"

    trace = finish_recording()
    names = {s.name for s in trace.agent_spans}
    assert "agent-a" in names
    assert "agent-b" in names
