"""Tests for traced_task — asyncio task with trace context propagation."""

import asyncio
import contextlib

import pytest

from agentguard.sdk.async_decorators import record_agent_async, record_tool_async
from agentguard.sdk.context import traced_task
from agentguard.sdk.recorder import finish_recording, init_recorder


@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def test_basic_async_context_propagation():
    """Spans in traced tasks are parented to the caller."""
    async def run():
        init_recorder(task="async ctx test")

        @record_agent_async(name="coordinator", version="v1")
        async def coordinator():
            @record_agent_async(name="worker", version="v1")
            async def worker(item):
                return {"item": item}

            tasks = [traced_task(worker(i)) for i in range(3)]
            return await asyncio.gather(*tasks)

        results = await coordinator()
        trace = finish_recording()
        return results, trace

    results, trace = asyncio.run(run())
    assert len(results) == 3
    workers = [s for s in trace.spans if s.name == "worker"]
    assert len(workers) == 3
    coord = [s for s in trace.spans if s.name == "coordinator"][0]
    for w in workers:
        assert w.parent_span_id == coord.span_id


def test_tool_spans_in_tasks():
    """Tool spans inside traced tasks are correctly parented."""
    async def run():
        init_recorder(task="tool in task")

        @record_tool_async(name="fetch")
        async def fetch(url):
            return f"data from {url}"

        @record_agent_async(name="fetcher", version="v1")
        async def fetcher():
            tasks = [traced_task(fetch(f"url-{i}")) for i in range(2)]
            return await asyncio.gather(*tasks)

        await fetcher()
        return finish_recording()

    trace = asyncio.run(run())
    tools = [s for s in trace.spans if s.name == "fetch"]
    assert len(tools) == 2
    agent = [s for s in trace.spans if s.name == "fetcher"][0]
    for t in tools:
        assert t.parent_span_id == agent.span_id


def test_exception_in_task():
    """Exceptions in traced tasks propagate and span is marked failed."""
    async def run():
        init_recorder(task="exception")

        @record_agent_async(name="boom", version="v1")
        async def boom():
            raise ValueError("async boom")

        task = traced_task(boom())
        with contextlib.suppress(ValueError):
            await task
        return finish_recording()

    trace = asyncio.run(run())
    failed = [s for s in trace.spans if s.name == "boom"]
    assert len(failed) == 1
    assert failed[0].status.value == "failed"
    assert "boom" in failed[0].error


def test_named_task():
    """traced_task passes name to asyncio.create_task."""
    async def run():
        init_recorder(task="named")

        async def noop():
            return 42

        task = traced_task(noop(), name="my-task")
        result = await task
        finish_recording()
        return result, task.get_name()

    result, name = asyncio.run(run())
    assert result == 42
    assert name == "my-task"


def test_concurrent_tasks_all_traced():
    """Multiple concurrent traced tasks all appear in trace."""
    async def run():
        init_recorder(task="concurrent")

        @record_agent_async(name="agent-x", version="v1")
        async def agent_x():
            await asyncio.sleep(0.01)
            return "x"

        @record_agent_async(name="agent-y", version="v1")
        async def agent_y():
            await asyncio.sleep(0.01)
            return "y"

        tx = traced_task(agent_x())
        ty = traced_task(agent_y())
        await asyncio.gather(tx, ty)
        return finish_recording()

    trace = asyncio.run(run())
    names = {s.name for s in trace.agent_spans}
    assert "agent-x" in names
    assert "agent-y" in names
