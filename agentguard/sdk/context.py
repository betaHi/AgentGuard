"""Context manager API — low-intrusion alternative to decorators.

Usage:
    with AgentTrace(name="my-agent", version="v1") as trace:
        with trace.tool("web_search") as tool:
            results = do_search(query)
            tool.set_output(results)
        trace.set_output({"results": results})
"""

from __future__ import annotations

import asyncio

from typing import Any, Optional
from agentguard.core.trace import Span, SpanType
from agentguard.sdk.recorder import get_recorder


class ToolContext:
    """Context manager for recording a single tool call as a trace span.

    Creates a TOOL span on entry and completes/fails it on exit. Nest
    inside an ``AgentTrace`` to establish parent-child relationships.

    Args:
        name: Tool name (e.g., ``"web_search"``, ``"db_query"``).
        input_data: Input passed to the tool. Must be JSON-serializable.
        metadata: Additional key-value metadata for the span.

    Example::

        with AgentTrace(name="agent") as agent:
            with agent.tool("search", input_data={"q": "AI"}) as t:
                results = search("AI")
                t.set_output(results)
    """
    
    def __init__(self, name: str, input_data: Any = None, metadata: Optional[dict] = None):
        self.name = name
        self._input = input_data
        self._metadata = metadata or {}
        self._span: Optional[Span] = None
    
    def __enter__(self) -> ToolContext:
        recorder = get_recorder()
        self._span = Span(
            span_type=SpanType.TOOL,
            name=self.name,
            parent_span_id=recorder.current_span_id,
            input_data=self._input,
            metadata=self._metadata,
        )
        recorder.push_span(self._span)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        recorder = get_recorder()
        if self._span:
            if exc_type:
                self._span.fail(f"{exc_type.__name__}: {exc_val}")
            else:
                self._span.complete()
            recorder.pop_span(self._span)
        return False
    
    def set_output(self, output: Any) -> None:
        """Store the tool's output data on the span.

        Args:
            output: Result data. Must be JSON-serializable.
        """
        if self._span:
            self._span.output_data = output


class AgentTrace:
    """Context manager for recording an agent execution.
    
    Low-intrusion alternative to @record_agent decorator.
    
    Example:
        recorder = init_recorder(task="my task")
        with AgentTrace(name="researcher", version="v1") as agent:
            with agent.tool("search", input_data={"q": "AI"}) as t:
                results = search("AI")
                t.set_output(results)
            agent.set_output({"results": results})
        trace = finish_recording()
    """
    
    def __init__(self, name: str, version: str = "latest", metadata: Optional[dict] = None):
        """Initialize an agent trace context.

        Args:
            name: Agent name (e.g., ``"researcher"``).
            version: Agent version string (e.g., ``"v2.1"``).
            metadata: Additional key-value metadata for the span.
        """
        self.name = name
        self.version = version
        self._metadata = {"agent_version": version, **(metadata or {})}
        self._span: Optional[Span] = None
    
    def __enter__(self) -> AgentTrace:
        recorder = get_recorder()
        self._span = Span(
            span_type=SpanType.AGENT,
            name=self.name,
            parent_span_id=recorder.current_span_id,
            metadata=self._metadata,
        )
        recorder.push_span(self._span)
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        recorder = get_recorder()
        if self._span:
            if exc_type:
                self._span.fail(f"{exc_type.__name__}: {exc_val}")
            else:
                self._span.complete()
            recorder.pop_span(self._span)
        return False
    
    def set_output(self, output: Any) -> None:
        """Store the agent's output data on the span.

        Args:
            output: Result data. Must be JSON-serializable.
        """
        if self._span:
            self._span.output_data = output
    
    def tool(self, name: str, input_data: Any = None, metadata: Optional[dict] = None) -> ToolContext:
        """Create a nested tool context within this agent.

        The returned ``ToolContext`` will have this agent's span as its parent.

        Args:
            name: Tool name.
            input_data: Input to the tool. Must be JSON-serializable.
            metadata: Additional key-value metadata.

        Returns:
            A ``ToolContext`` to use as a context manager.
        """
        return ToolContext(name=name, input_data=input_data, metadata=metadata)


class AsyncAgentTrace:
    """Async context manager for recording agent execution.

    Async equivalent of ``AgentTrace``. Use with ``async with`` for agents
    that perform async I/O.

    Args:
        name: Agent name.
        version: Agent version string.
        metadata: Additional key-value metadata.

    Example::

        async with AsyncAgentTrace(name="my-agent", version="v1") as agent:
            async with agent.tool("search") as t:
                results = await search(query)
                t.set_output(results)
            agent.set_output(results)
    """
    
    def __init__(self, name: str, version: str = "latest", metadata: Optional[dict] = None):
        self.name = name
        self.version = version
        self._metadata = {"agent_version": version, **(metadata or {})}
        self._span: Optional[Span] = None
    
    async def __aenter__(self) -> AsyncAgentTrace:
        recorder = get_recorder()
        self._span = Span(
            span_type=SpanType.AGENT,
            name=self.name,
            parent_span_id=recorder.current_span_id,
            metadata=self._metadata,
        )
        recorder.push_span(self._span)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        recorder = get_recorder()
        if self._span:
            if exc_type:
                self._span.fail(f"{exc_type.__name__}: {exc_val}")
            else:
                self._span.complete()
            recorder.pop_span(self._span)
        return False
    
    def set_output(self, output: Any) -> None:
        """Store the agent's output data on the span.

        Args:
            output: Result data. Must be JSON-serializable.
        """
        if self._span:
            self._span.output_data = output
    
    def tool(self, name: str, input_data: Any = None, metadata: Optional[dict] = None) -> AsyncToolContext:
        """Create a nested async tool context within this agent.

        Args:
            name: Tool name.
            input_data: Input to the tool.
            metadata: Additional key-value metadata.

        Returns:
            An ``AsyncToolContext`` to use with ``async with``.
        """
        return AsyncToolContext(name=name, input_data=input_data, metadata=metadata)


class AsyncToolContext:
    """Async context manager for recording tool calls.

    Async equivalent of ``ToolContext``. Creates a TOOL span on async
    entry and completes/fails it on async exit.

    Args:
        name: Tool name.
        input_data: Input to the tool. Must be JSON-serializable.
        metadata: Additional key-value metadata.
    """
    
    def __init__(self, name: str, input_data: Any = None, metadata: Optional[dict] = None):
        self.name = name
        self._input = input_data
        self._metadata = metadata or {}
        self._span: Optional[Span] = None
    
    async def __aenter__(self) -> AsyncToolContext:
        recorder = get_recorder()
        self._span = Span(
            span_type=SpanType.TOOL,
            name=self.name,
            parent_span_id=recorder.current_span_id,
            input_data=self._input,
            metadata=self._metadata,
        )
        recorder.push_span(self._span)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        recorder = get_recorder()
        if self._span:
            if exc_type:
                self._span.fail(f"{exc_type.__name__}: {exc_val}")
            else:
                self._span.complete()
            recorder.pop_span(self._span)
        return False
    
    def set_output(self, output: Any) -> None:
        """Store the tool's output data on the span.

        Args:
            output: Result data. Must be JSON-serializable.
        """
        if self._span:
            self._span.output_data = output


class TracingExecutor:
    """ThreadPoolExecutor wrapper that propagates trace context to workers.

    Without this, spans created in worker threads become orphans because
    the thread-local span stack is empty. TracingExecutor captures the
    parent context at submit time and restores it in each worker before
    the callable runs.

    Uses only stdlib (concurrent.futures) — zero external dependencies.

    Example::

        from agentguard.sdk.context import TracingExecutor

        with TracingExecutor(max_workers=4) as executor:
            futures = [
                executor.submit(my_agent, task)
                for task in tasks
            ]
            results = [f.result() for f in futures]
    """

    def __init__(self, max_workers: Optional[int] = None) -> None:
        from concurrent.futures import ThreadPoolExecutor
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Submit a callable with trace context propagation.

        Captures the current span stack and restores it in the worker
        thread before calling fn.

        Args:
            fn: Callable to execute in the thread pool.
            *args: Positional arguments for fn.
            **kwargs: Keyword arguments for fn.

        Returns:
            A Future representing the pending result.
        """
        recorder = get_recorder()
        parent_context = recorder.capture_context()

        def _wrapped() -> Any:
            recorder.restore_context(parent_context)
            return fn(*args, **kwargs)

        return self._executor.submit(_wrapped)

    def map(self, fn: Any, *iterables: Any, timeout: Optional[float] = None) -> Any:
        """Map fn over iterables with trace context propagation.

        Each invocation receives the parent trace context so spans
        are correctly parented.

        Args:
            fn: Callable to map.
            *iterables: Input iterables.
            timeout: Max seconds to wait for results.

        Returns:
            Iterator of results.
        """
        recorder = get_recorder()
        parent_context = recorder.capture_context()

        def _make_wrapped(item_args: tuple) -> Any:
            recorder.restore_context(parent_context)
            return fn(*item_args)

        # Zip iterables into tuples for _make_wrapped
        zipped = zip(*iterables)
        return self._executor.map(_make_wrapped, zipped, timeout=timeout)

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the executor."""
        self._executor.shutdown(wait=wait)

    def __enter__(self) -> "TracingExecutor":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown(wait=True)



class TracingProcessExecutor:
    """ProcessPoolExecutor wrapper that propagates trace context across processes.

    Unlike TracingExecutor (threads), processes don't share memory.
    This wrapper:
    1. Captures parent context (span IDs) at submit time
    2. Runs the callable in a worker process with a local recorder
    3. Collects child spans from the worker and merges them into
       the parent recorder

    Limitations:
    - fn and args must be picklable (stdlib ProcessPoolExecutor requirement)
    - Spans created in workers are merged after completion, not in real-time
    - Worker-side recorder is independent; cross-process span nesting
      is reconstructed via parent_span_id

    Uses only stdlib (concurrent.futures, multiprocessing) — zero external deps.

    Example::

        from agentguard.sdk.context import TracingProcessExecutor

        with TracingProcessExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(cpu_bound_agent, data)
                for data in chunks
            ]
            results = [f.result() for f in futures]
    """

    def __init__(self, max_workers: Optional[int] = None) -> None:
        from concurrent.futures import ProcessPoolExecutor
        self._executor = ProcessPoolExecutor(max_workers=max_workers)

    def submit(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        """Submit a callable with trace context propagation.

        Captures parent span ID so worker spans are correctly parented.
        Wraps the result to include worker spans for merging.

        Args:
            fn: Picklable callable to execute in the process pool.
            *args: Positional arguments for fn.
            **kwargs: Keyword arguments for fn.

        Returns:
            A Future whose result is the fn return value.
            Worker spans are automatically merged on result retrieval.
        """
        recorder = get_recorder()
        parent_context = recorder.capture_context()
        task_name = recorder.trace.task if recorder.trace else ""

        future = self._executor.submit(
            _process_worker, fn, args, kwargs, parent_context, task_name
        )
        return _MergingFuture(future, recorder)

    def shutdown(self, wait: bool = True) -> None:
        """Shut down the executor."""
        self._executor.shutdown(wait=wait)

    def __enter__(self) -> "TracingProcessExecutor":
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.shutdown(wait=True)


class _MergingFuture:
    """Future wrapper that merges worker spans into parent on result().

    This is transparent to the caller — they get the actual return
    value, and spans are silently merged into the parent trace.
    """

    def __init__(self, future: Any, recorder: Any) -> None:
        self._future = future
        self._recorder = recorder

    def result(self, timeout: Optional[float] = None) -> Any:
        """Get the result and merge worker spans."""
        worker_result = self._future.result(timeout=timeout)
        _merge_worker_spans(self._recorder, worker_result)
        return worker_result["return_value"]

    def done(self) -> bool:
        return self._future.done()

    def cancel(self) -> bool:
        return self._future.cancel()

    def exception(self, timeout: Optional[float] = None) -> Any:
        return self._future.exception(timeout=timeout)


def _process_worker(
    fn: Any,
    args: tuple,
    kwargs: dict,
    parent_context: tuple[str, ...],
    task_name: str,
) -> dict:
    """Run fn in a worker process with a local recorder.

    Creates a fresh recorder, restores parent context,
    runs the function, and returns both the result and
    any spans created for merging back.

    This function must be module-level (picklable).
    """
    from agentguard.sdk.recorder import init_recorder, finish_recording

    init_recorder(task=task_name or "worker", trigger="process_pool")
    recorder = get_recorder()
    recorder.restore_context(parent_context)

    error = None
    return_value = None
    try:
        return_value = fn(*args, **kwargs)
    except Exception as e:
        error = str(e)

    trace = finish_recording()
    span_dicts = [_span_to_dict(s) for s in trace.spans]

    return {
        "return_value": return_value,
        "error": error,
        "spans": span_dicts,
    }


def _span_to_dict(span: Any) -> dict:
    """Serialize a span to a picklable dict for cross-process transfer."""
    return {
        "span_id": span.span_id,
        "name": span.name,
        "span_type": span.span_type.value if span.span_type else "agent",
        "parent_span_id": span.parent_span_id,
        "started_at": span.started_at,
        "ended_at": span.ended_at,
        "status": span.status.value if span.status else "completed",
        "error": span.error,
        "metadata": dict(span.metadata) if span.metadata else {},
        "input_data": span.input_data,
        "output_data": span.output_data,
    }


def _merge_worker_spans(recorder: Any, worker_result: dict) -> None:
    """Merge spans from a worker process into the parent recorder.

    Reconstructs Span objects from serialized dicts and adds them
    to the active trace. Preserves parent_span_id for correct nesting.
    """
    from agentguard.core.trace import Span, SpanType, SpanStatus

    if not recorder.trace:
        return

    for sd in worker_result.get("spans", []):
        span = Span(
            span_id=sd["span_id"],
            name=sd["name"],
            span_type=SpanType(sd["span_type"]),
            parent_span_id=sd.get("parent_span_id"),
            started_at=sd.get("started_at"),
            ended_at=sd.get("ended_at"),
            status=SpanStatus(sd["status"]),
            error=sd.get("error"),
            metadata=sd.get("metadata", {}),
            input_data=sd.get("input_data"),
            output_data=sd.get("output_data"),
        )
        recorder.trace.add_span(span)

    if worker_result.get("error"):
        raise RuntimeError(f"Worker failed: {worker_result['error']}")


def traced_task(
    coro: Any,
    name: Optional[str] = None,
) -> "asyncio.Task[Any]":
    """Create an asyncio task with trace context propagation.

    Wraps ``asyncio.create_task()`` to capture the current span stack
    and restore it inside the task coroutine, so spans created in the
    task are correctly parented.

    Without this, ``asyncio.create_task(my_agent())`` loses the parent
    span context because the task runs in a fresh coroutine frame.

    Args:
        coro: The coroutine to schedule as a task.
        name: Optional task name (passed to ``asyncio.create_task``).

    Returns:
        An ``asyncio.Task`` with trace context propagated.

    Example::

        async def pipeline():
            task_a = traced_task(agent_a(), name="agent-a")
            task_b = traced_task(agent_b(), name="agent-b")
            return await asyncio.gather(task_a, task_b)
    """
    recorder = get_recorder()
    parent_context = recorder.capture_context()

    async def _wrapped() -> Any:
        recorder.restore_context(parent_context)
        return await coro

    kwargs: dict[str, Any] = {}
    if name is not None:
        kwargs["name"] = name
    return asyncio.create_task(_wrapped(), **kwargs)
