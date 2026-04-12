"""Context manager API — low-intrusion alternative to decorators.

Usage:
    with AgentTrace(name="my-agent", version="v1") as trace:
        with trace.tool("web_search") as tool:
            results = do_search(query)
            tool.set_output(results)
        trace.set_output({"results": results})
"""

from __future__ import annotations

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
