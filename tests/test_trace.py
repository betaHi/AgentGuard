"""Tests for execution trace data models."""

import json
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def test_span_creation():
    """Span can be created with defaults."""
    span = Span(name="test-agent", span_type=SpanType.AGENT)
    assert span.name == "test-agent"
    assert span.span_type == SpanType.AGENT
    assert span.status == SpanStatus.RUNNING
    assert span.span_id  # auto-generated


def test_span_complete():
    """Span can be marked as completed."""
    span = Span(name="test")
    span.complete(output={"result": "ok"})
    assert span.status == SpanStatus.COMPLETED
    assert span.ended_at is not None
    assert span.output_data == {"result": "ok"}


def test_span_fail():
    """Span can be marked as failed."""
    span = Span(name="test")
    span.fail(error="something broke")
    assert span.status == SpanStatus.FAILED
    assert span.error == "something broke"


def test_trace_creation():
    """Trace can be created and spans added."""
    trace = ExecutionTrace(task="test-task", trigger="manual")
    agent_span = Span(name="agent-1", span_type=SpanType.AGENT)
    tool_span = Span(name="search", span_type=SpanType.TOOL, parent_span_id=agent_span.span_id)
    
    trace.add_span(agent_span)
    trace.add_span(tool_span)
    
    assert len(trace.spans) == 2
    assert trace.spans[0].trace_id == trace.trace_id
    assert trace.spans[1].trace_id == trace.trace_id


def test_trace_serialization():
    """Trace can be serialized to JSON and back."""
    trace = ExecutionTrace(task="test-task")
    span = Span(name="agent-1", span_type=SpanType.AGENT)
    span.complete(output="done")
    trace.add_span(span)
    trace.complete()
    
    # Serialize
    json_str = trace.to_json()
    data = json.loads(json_str)
    assert data["task"] == "test-task"
    assert len(data["spans"]) == 1
    
    # Deserialize
    trace2 = ExecutionTrace.from_json(json_str)
    assert trace2.task == "test-task"
    assert len(trace2.spans) == 1
    assert trace2.spans[0].name == "agent-1"


def test_trace_build_tree():
    """Trace can assemble spans into a tree."""
    trace = ExecutionTrace(task="multi-agent")
    
    root = Span(name="orchestrator", span_type=SpanType.AGENT)
    child1 = Span(name="agent-a", span_type=SpanType.AGENT, parent_span_id=root.span_id)
    child2 = Span(name="agent-b", span_type=SpanType.AGENT, parent_span_id=root.span_id)
    tool = Span(name="search", span_type=SpanType.TOOL, parent_span_id=child1.span_id)
    
    trace.add_span(root)
    trace.add_span(child1)
    trace.add_span(child2)
    trace.add_span(tool)
    
    roots = trace.build_tree()
    assert len(roots) == 1
    assert roots[0].name == "orchestrator"
    assert len(roots[0].children) == 2
    assert len(roots[0].children[0].children) == 1  # agent-a has search tool


def test_trace_agent_and_tool_spans():
    """Trace can filter spans by type."""
    trace = ExecutionTrace()
    trace.add_span(Span(name="a1", span_type=SpanType.AGENT))
    trace.add_span(Span(name="t1", span_type=SpanType.TOOL))
    trace.add_span(Span(name="a2", span_type=SpanType.AGENT))
    
    assert len(trace.agent_spans) == 2
    assert len(trace.tool_spans) == 1
