"""Manual trace API — for maximum control and zero intrusion.

When decorators and context managers don't fit your architecture,
use the manual API to explicitly create and manage spans.

Usage:
    from agentguard.sdk.manual import ManualTracer
    
    tracer = ManualTracer(task="my task")
    
    agent_id = tracer.start_agent("my-agent", version="v1")
    tool_id = tracer.start_tool("search", parent=agent_id, input_data={"q": "AI"})
    tracer.end_tool(tool_id, output=results)
    tracer.end_agent(agent_id, output=final_result)
    
    trace = tracer.finish()
"""

from __future__ import annotations

from typing import Any, Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType
from agentguard.sdk.recorder import TraceRecorder


class ManualTracer:
    """Explicit trace construction API.
    
    Use when you need full control over span lifecycle,
    e.g., in event-driven or callback-based architectures.
    """
    
    def __init__(self, task: str = "", trigger: str = "manual", output_dir: str = ".agentguard/traces"):
        self._recorder = TraceRecorder(task=task, trigger=trigger, output_dir=output_dir)
        self._spans: dict[str, Span] = {}
    
    def start_agent(
        self,
        name: str,
        version: str = "latest",
        parent: Optional[str] = None,
        input_data: Any = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Start recording an agent span.
        
        Returns:
            Span ID (use to end the span later).
        """
        span = Span(
            span_type=SpanType.AGENT,
            name=name,
            parent_span_id=parent,
            input_data=input_data,
            metadata={"agent_version": version, **(metadata or {})},
        )
        self._recorder.trace.add_span(span)
        self._spans[span.span_id] = span
        return span.span_id
    
    def start_tool(
        self,
        name: str,
        parent: Optional[str] = None,
        input_data: Any = None,
        metadata: Optional[dict] = None,
    ) -> str:
        """Start recording a tool span.
        
        Returns:
            Span ID.
        """
        span = Span(
            span_type=SpanType.TOOL,
            name=name,
            parent_span_id=parent,
            input_data=input_data,
            metadata=metadata or {},
        )
        self._recorder.trace.add_span(span)
        self._spans[span.span_id] = span
        return span.span_id
    
    def end_agent(self, span_id: str, output: Any = None) -> None:
        """Mark an agent span as completed."""
        span = self._spans.get(span_id)
        if span:
            span.complete(output=output)
    
    def end_tool(self, span_id: str, output: Any = None) -> None:
        """Mark a tool span as completed."""
        span = self._spans.get(span_id)
        if span:
            span.complete(output=output)
    
    def fail_span(self, span_id: str, error: str) -> None:
        """Mark any span as failed."""
        span = self._spans.get(span_id)
        if span:
            span.fail(error=error)
    
    def finish(self) -> ExecutionTrace:
        """Finalize and save the trace."""
        return self._recorder.finish()
    
    @property
    def trace(self) -> ExecutionTrace:
        """Access the current trace."""
        return self._recorder.trace
