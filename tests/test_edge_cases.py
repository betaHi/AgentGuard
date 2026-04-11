"""Edge case tests for robustness."""

import json
import tempfile
from pathlib import Path
from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.eval.rules import evaluate_rules, _resolve_path
from agentguard.export import trace_statistics


# --- Empty/minimal traces ---

def test_empty_trace():
    """Empty trace serializes and deserializes correctly."""
    trace = ExecutionTrace(task="empty")
    trace.complete()
    json_str = trace.to_json()
    restored = ExecutionTrace.from_json(json_str)
    assert restored.task == "empty"
    assert len(restored.spans) == 0


def test_single_span_trace():
    """Single-span trace works."""
    trace = ExecutionTrace(task="single")
    span = Span(name="solo", span_type=SpanType.AGENT)
    span.complete(output="done")
    trace.add_span(span)
    trace.complete()
    
    tree = trace.build_tree()
    assert len(tree) == 1
    assert tree[0].name == "solo"


# --- Deep nesting ---

def test_deep_nesting():
    """Deeply nested spans build tree correctly."""
    trace = ExecutionTrace(task="deep")
    spans = []
    for i in range(10):
        parent_id = spans[-1].span_id if spans else None
        s = Span(name=f"level-{i}", span_type=SpanType.AGENT, parent_span_id=parent_id)
        s.complete()
        trace.add_span(s)
        spans.append(s)
    trace.complete()
    
    tree = trace.build_tree()
    assert len(tree) == 1  # one root
    
    stats = trace_statistics(trace)
    assert stats["deepest_nesting"] == 9


# --- Concurrent/overlapping spans ---

def test_many_parallel_agents():
    """Multiple agents at same level work."""
    init_recorder(task="parallel")
    
    @record_agent(name="agent-a")
    def a(): return "a"
    
    @record_agent(name="agent-b")
    def b(): return "b"
    
    @record_agent(name="agent-c")
    def c(): return "c"
    
    a(); b(); c()
    trace = finish_recording()
    assert len(trace.spans) == 3
    assert all(s.parent_span_id is None for s in trace.spans)


# --- Special characters in data ---

def test_unicode_in_output():
    """Unicode data serializes correctly."""
    init_recorder(task="unicode")
    
    @record_agent(name="i18n-agent")
    def agent():
        return {"text": "Hello 世界 🌍 مرحبا"}
    
    agent()
    trace = finish_recording()
    json_str = trace.to_json()
    assert "世界" in json_str
    assert "🌍" in json_str


def test_large_output():
    """Large outputs don't crash serialization."""
    init_recorder(task="large")
    
    @record_agent(name="big-agent")
    def agent():
        return {"data": list(range(10000))}
    
    agent()
    trace = finish_recording()
    assert len(trace.spans) == 1
    assert trace.spans[0].status.value == "completed"


def test_none_output():
    """None output is handled gracefully."""
    init_recorder(task="none")
    
    @record_agent(name="null-agent")
    def agent():
        return None
    
    result = agent()
    assert result is None
    trace = finish_recording()
    assert trace.spans[0].status.value == "completed"


# --- Eval edge cases ---

def test_eval_empty_data():
    """Evaluation on empty data doesn't crash."""
    results = evaluate_rules({}, [
        {"type": "min_count", "target": "articles", "value": 5},
    ])
    assert len(results) == 1
    assert results[0].verdict.value == "fail"


def test_eval_nested_path():
    """Deep path resolution works."""
    data = {"a": {"b": {"c": [1, 2, 3]}}}
    assert _resolve_path(data, "a.b.c") == [1, 2, 3]


def test_eval_missing_path():
    """Missing path returns None."""
    assert _resolve_path({"a": 1}, "b.c") is None


def test_eval_unknown_rule():
    """Unknown rule type returns error verdict."""
    results = evaluate_rules({}, [{"type": "nonexistent_rule"}])
    assert results[0].verdict.value == "error"


# --- Trace file I/O ---

def test_trace_file_roundtrip():
    """Trace survives write → read roundtrip."""
    trace = ExecutionTrace(task="roundtrip-test")
    a = Span(name="agent", span_type=SpanType.AGENT, metadata={"key": "value"})
    t = Span(name="tool", span_type=SpanType.TOOL, parent_span_id=a.span_id, 
             input_data={"q": "test"}, metadata={"timeout": 30})
    a.complete(output={"result": [1, 2, 3]})
    t.complete(output="ok")
    trace.add_span(a)
    trace.add_span(t)
    trace.complete()
    
    with tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False) as f:
        f.write(trace.to_json())
        filepath = f.name
    
    loaded = ExecutionTrace.from_json(Path(filepath).read_text())
    assert loaded.trace_id == trace.trace_id
    assert len(loaded.spans) == 2
    assert loaded.spans[0].metadata == {"key": "value"}
    assert loaded.spans[1].input_data == {"q": "test"}
