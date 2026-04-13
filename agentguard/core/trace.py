"""Execution trace data models.

An ExecutionTrace captures the complete record of a multi-agent task execution,
including all agent invocations, tool calls, and their relationships.
"""

from __future__ import annotations

import json
import logging

_trace_logger = logging.getLogger(__name__)
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


class SpanStatus(str, Enum):
    """Status of a span execution.

    Values:
        RUNNING: Span is currently executing.
        COMPLETED: Span finished successfully.
        FAILED: Span encountered an unrecoverable error.
        TIMEOUT: Span exceeded its time limit.
    """
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


class SpanType(str, Enum):
    """Type of span in the trace.

    Values:
        AGENT: An autonomous agent performing a task.
        TOOL: A tool invocation (search, API call, etc.).
        LLM_CALL: A direct LLM API call.
        HANDOFF: A context transfer between agents.
    """
    AGENT = "agent"
    TOOL = "tool"
    LLM_CALL = "llm_call"
    HANDOFF = "handoff"


@dataclass
class Span:
    """A single unit of work within a trace.
    
    Spans form a tree structure via parent_span_id, allowing representation
    of nested agent → tool → llm_call hierarchies.
    
    Schema Stability:
        - Fields marked [stable] are part of the public contract and will not
          change without a major version bump.
        - Fields marked [experimental] may change in minor versions.
    
    Attributes (stable):
        span_id: Unique identifier for this span.
        trace_id: ID of the parent trace.
        parent_span_id: ID of the parent span (None for root spans).
        span_type: Type of work (agent, tool, llm_call, handoff).
        name: Human-readable name (e.g., agent name, tool name).
        status: Execution status.
        started_at: When execution started.
        ended_at: When execution ended (None if still running).
        input_data: Input to this span (serializable).
        output_data: Output from this span (serializable).
        error: Error message if failed.
        metadata: Additional key-value metadata.
        children: Child spans (populated during trace assembly).
    """
    span_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    trace_id: str = ""
    parent_span_id: Optional[str] = None
    span_type: SpanType = SpanType.AGENT
    name: str = ""
    status: SpanStatus = SpanStatus.RUNNING
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: Optional[str] = None
    input_data: Optional[Any] = None
    output_data: Optional[Any] = None
    error: Optional[str] = None
    metadata: dict[str, Any] = field(default_factory=dict)
    children: list[Span] = field(default_factory=list)
    
    # Handoff tracking [experimental]: populated when span_type is HANDOFF
    handoff_from: Optional[str] = None      # agent_id that initiated the handoff
    handoff_to: Optional[str] = None        # agent_id that received the handoff
    context_passed: Optional[dict] = None   # keys/summary of context passed
    context_size_bytes: Optional[int] = None  # size of context at handoff point
    context_received: Optional[dict] = None   # what the receiver actually got
    context_used_keys: Optional[list] = None  # which context keys the receiver used
    context_dropped_keys: Optional[list] = None  # keys that were sent but not used
    
    # Retry tracking [experimental]
    retry_count: int = 0               # number of retries before this span succeeded/failed
    retry_of: Optional[str] = None     # span_id of the original attempt (if this is a retry)
    tags: list[str] = field(default_factory=list)  # user-defined labels for filtering
    
    # Cost tracking [experimental]
    token_count: Optional[int] = None        # tokens consumed by this span
    estimated_cost_usd: Optional[float] = None  # estimated cost in USD
    
    # Failure propagation tracking [experimental]
    caused_by: Optional[str] = None         # span_id of the root cause failure
    failure_handled: bool = False           # True if error was caught (try/except)

    @property
    def duration_ms(self) -> Optional[float]:
        """Calculate duration in milliseconds.

        Returns:
            Duration in ms, or None if the span has not ended yet.
        """
        if self.ended_at and self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.ended_at)
            return (end - start).total_seconds() * 1000
        return None

    def complete(self, output: Any = None) -> None:
        """Mark this span as completed.

        Sets status to COMPLETED, records the end timestamp, and
        optionally stores the output data.

        Args:
            output: Result data to store. Must be JSON-serializable.
        """
        self.status = SpanStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc).isoformat()
        if output is not None:
            self.output_data = output

    def fail(self, error: str) -> None:
        """Mark this span as failed.

        Sets status to FAILED and records the end timestamp.

        Args:
            error: Human-readable error message describing the failure.
        """
        self.status = SpanStatus.FAILED
        self.ended_at = datetime.now(timezone.utc).isoformat()
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dictionary.

        Enum fields are converted to their string values. Empty children
        lists are omitted for cleaner output.

        Returns:
            Dict suitable for JSON serialization.
        """
        d = asdict(self)
        d["span_type"] = self.span_type.value
        d["status"] = self.status.value
        if not d["children"]:
            del d["children"]
        if d.get("duration_ms") is None and self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d


@dataclass
class ExecutionTrace:
    """Complete record of a multi-agent task execution.
    
    An ExecutionTrace is the top-level container that holds all spans
    from a single task execution, potentially involving multiple agents.
    
    Attributes:
        trace_id: Unique identifier for this trace.
        task: Human-readable task description.
        trigger: How this trace was initiated (manual, cron, api, event).
        started_at: When the trace started.
        ended_at: When the trace ended.
        status: Overall trace status.
        spans: All spans in this trace (flat list, tree via parent_span_id).
        metadata: Additional trace-level metadata.
    """
    trace_id: str = field(default_factory=lambda: str(uuid.uuid4())[:16])
    task: str = ""
    trigger: str = "manual"
    started_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    ended_at: Optional[str] = None
    status: SpanStatus = SpanStatus.RUNNING
    spans: list[Span] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_span(self, span: Span) -> None:
        """Add a span to this trace.

        The span's trace_id is automatically set to this trace's ID.

        Args:
            span: The Span to add.
        """
        span.trace_id = self.trace_id
        self.spans.append(span)

    def complete(self) -> None:
        """Mark this trace as completed.

        Sets status to COMPLETED and records the end timestamp.
        """
        self.status = SpanStatus.COMPLETED
        self.ended_at = datetime.now(timezone.utc).isoformat()

    def fail(self, error: str = "") -> None:
        """Mark this trace as failed.

        Sets status to FAILED and records the end timestamp.

        Args:
            error: Optional error message describing the failure cause.
        """
        self.status = SpanStatus.FAILED
        self.ended_at = datetime.now(timezone.utc).isoformat()

    @property
    def duration_ms(self) -> Optional[float]:
        """Total trace duration in milliseconds.

        Returns:
            Duration in ms, or None if the trace has not ended yet.
        """
        if self.ended_at and self.started_at:
            start = datetime.fromisoformat(self.started_at)
            end = datetime.fromisoformat(self.ended_at)
            return (end - start).total_seconds() * 1000
        return None

    @property
    def agent_spans(self) -> list[Span]:
        """Get all agent-type spans.

        Returns:
            List of spans where span_type is SpanType.AGENT.
        """
        return [s for s in self.spans if s.span_type == SpanType.AGENT]

    @property
    def tool_spans(self) -> list[Span]:
        """Get all tool-type spans.

        Returns:
            List of spans where span_type is SpanType.TOOL.
        """
        return [s for s in self.spans if s.span_type == SpanType.TOOL]

    def build_tree(self) -> list[Span]:
        """Assemble spans into a tree structure based on parent_span_id.

        Populates each span's ``children`` list by matching parent_span_id
        references. Spans without a valid parent become root nodes.

        Returns:
            List of root-level spans, each with children populated recursively.

        Note:
            This mutates the spans' ``children`` fields in place. Call once
            per trace; repeated calls reset children first.
        """
        span_map = {s.span_id: s for s in self.spans}
        roots = []
        for span in self.spans:
            span.children = []
        for span in self.spans:
            if span.parent_span_id and span.parent_span_id in span_map:
                span_map[span.parent_span_id].children.append(span)
            else:
                roots.append(span)
        return roots

    def to_dict(self) -> dict[str, Any]:
        """Serialize the entire trace to a plain dictionary.

        Returns:
            Dict with trace metadata and all spans, suitable for JSON output.
        """
        return {
            "trace_id": self.trace_id,
            "task": self.task,
            "trigger": self.trigger,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "spans": [s.to_dict() for s in self.spans],
            "metadata": self.metadata,
        }

    def to_json(self, indent: int = 2, truncate: bool = False) -> str:
        """Serialize the trace to a JSON string.

        Args:
            indent: Number of spaces for JSON indentation.
            truncate: If True, truncate oversized span data fields.

        Returns:
            Pretty-printed JSON string. Warns if trace exceeds 10 MB.
        """
        from agentguard.core.limits import check_trace_size, truncate_trace
        d = self.to_dict()
        check_trace_size(d)
        if truncate:
            d = truncate_trace(d)
        return json.dumps(d, indent=indent, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExecutionTrace:
        """Deserialize an ExecutionTrace from a plain dictionary.

        Args:
            data: Dict as produced by ``to_dict()``, typically loaded from JSON.

        Returns:
            Reconstructed ExecutionTrace with all spans.
        """
        trace = cls(
            trace_id=data["trace_id"],
            task=data.get("task", ""),
            trigger=data.get("trigger", "manual"),
            started_at=data["started_at"],
            ended_at=data.get("ended_at"),
            status=SpanStatus(data.get("status", "running")),
            metadata=data.get("metadata", {}),
        )
        for span_data in data.get("spans", []):
            span = Span(
                span_id=span_data["span_id"],
                trace_id=span_data.get("trace_id", trace.trace_id),
                parent_span_id=span_data.get("parent_span_id"),
                span_type=SpanType(span_data.get("span_type", "agent")),
                name=span_data.get("name", ""),
                status=SpanStatus(span_data.get("status", "running")),
                started_at=span_data.get("started_at", ""),
                ended_at=span_data.get("ended_at"),
                input_data=span_data.get("input_data"),
                output_data=span_data.get("output_data"),
                error=span_data.get("error"),
                metadata=span_data.get("metadata", {}),
                handoff_from=span_data.get("handoff_from"),
                handoff_to=span_data.get("handoff_to"),
                context_passed=span_data.get("context_passed"),
                context_size_bytes=span_data.get("context_size_bytes"),
                context_received=span_data.get("context_received"),
                context_used_keys=span_data.get("context_used_keys"),
                context_dropped_keys=span_data.get("context_dropped_keys"),
                caused_by=span_data.get("caused_by"),
                failure_handled=span_data.get("failure_handled", False),
                retry_count=span_data.get("retry_count", 0),
                retry_of=span_data.get("retry_of"),
                tags=span_data.get("tags", []),
                token_count=span_data.get("token_count"),
                estimated_cost_usd=span_data.get("estimated_cost_usd"),
            )
            trace.spans.append(span)
        return trace

    @classmethod
    def from_json(cls, json_str: str) -> ExecutionTrace:
        """Deserialize an ExecutionTrace from a JSON string.

        Args:
            json_str: JSON string as produced by ``to_json()``.

        Returns:
            Reconstructed ExecutionTrace with all spans.
        """
        return cls.from_dict(json.loads(json_str))
