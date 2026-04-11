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


# --- Bug fix tests ---

def test_distributed_child_writes_separate_file():
    """Child process writes separate file; merge persists and cleans up."""
    import tempfile, os
    from agentguard.sdk.distributed import inject_trace_context, init_recorder_from_env, merge_child_traces
    from agentguard import AgentTrace
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = str(Path(tmpdir) / "traces")
        
        # Parent records a trace
        parent_rec = init_recorder(task="parent-task", output_dir=traces_dir)
        parent_trace_id = parent_rec.trace.trace_id
        env = inject_trace_context(parent_rec, parent_span_id="fake-parent-span")
        parent_trace = finish_recording()
        parent_span_count = len(parent_trace.spans)
        
        # Simulate child by setting env vars
        for k, v in env.items():
            os.environ[k] = v
        os.environ["AGENTGUARD_OUTPUT_DIR"] = traces_dir
        
        child_rec = init_recorder_from_env()
        with AgentTrace(name="child-agent") as agent:
            agent.set_output("child result")
        finish_recording()
        
        # Pre-merge: both files exist
        parent_file = Path(traces_dir) / f"{parent_trace_id}.json"
        child_files = list(Path(traces_dir).glob(f"{parent_trace_id}_child_*.json"))
        assert parent_file.exists(), "Parent trace file should exist"
        assert len(child_files) >= 1, "Child trace file should exist separately"
        
        # Merge with persist=True, cleanup=True (defaults)
        merged = merge_child_traces(parent_trace, traces_dir)
        
        # Verify: merged trace has more spans than original parent
        assert len(merged.spans) > parent_span_count, "Merged trace should include child spans"
        
        # Verify: parent file on disk now contains merged result
        persisted = ExecutionTrace.from_json(parent_file.read_text())
        assert len(persisted.spans) == len(merged.spans), "Persisted file should have merged spans"
        
        # Verify: child files cleaned up
        remaining_child_files = list(Path(traces_dir).glob(f"{parent_trace_id}_child_*.json"))
        assert len(remaining_child_files) == 0, "Child files should be cleaned up after merge"
        
        # Verify: CLI/web can now read the single merged file
        assert len(list(Path(traces_dir).glob("*.json"))) == 1, "Only one trace file should remain"
        
        # Cleanup env
        for k in env:
            os.environ.pop(k, None)


def test_guard_tool_failure_not_escalated_as_agent():
    """Tool failures should not trigger agent consecutive failure escalation."""
    from agentguard.guard import Guard
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        alerts = []
        class CaptureAlert:
            def send(self, message, severity="warning", metadata=None):
                alerts.append({"message": message, "severity": severity})
        
        guard = Guard(traces_dir=str(traces_dir), alert_handlers=[CaptureAlert()], fail_threshold=2)
        
        # Create traces where only TOOLS fail, agents succeed
        for i in range(3):
            trace = ExecutionTrace(task=f"test-{i}")
            agent = Span(name="my-agent", span_type=SpanType.AGENT)
            agent.complete()  # agent succeeds
            tool = Span(name="web_search", span_type=SpanType.TOOL, parent_span_id=agent.span_id)
            tool.fail("timeout")  # tool fails
            trace.add_span(agent)
            trace.add_span(tool)
            trace.fail()
            (traces_dir / f"{trace.trace_id}.json").write_text(trace.to_json())
        
        guard.check_new_traces()
        
        # Should NOT have critical alerts (tool failures shouldn't escalate as agent failures)
        critical = [a for a in alerts if a["severity"] == "critical"]
        assert len(critical) == 0, f"Tool failures should not trigger critical agent alerts, got: {critical}"


def test_html_xss_prevention():
    """HTML report should escape ALL user-controlled fields including error."""
    from agentguard.web.viewer import generate_timeline_html
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        # XSS payloads in every user-controlled field
        trace = ExecutionTrace(task='<script>alert("task-xss")</script>')
        trace.trigger = '<img src=x onerror=alert("trigger")>'
        span = Span(name='<script>alert("name")</script>', span_type=SpanType.AGENT,
                    metadata={"agent_version": '<script>alert("ver")</script>'})
        span.fail(error='<script>document.cookie</script>')
        trace.add_span(span)
        trace.fail()
        (traces_dir / f"{trace.trace_id}.json").write_text(trace.to_json())
        
        output_path = str(Path(tmpdir) / "report.html")
        generate_timeline_html(traces_dir=str(traces_dir), output=output_path)
        
        html_content = Path(output_path).read_text()
        
        # NONE of these raw XSS strings should appear unescaped
        assert '<script>alert("task-xss")' not in html_content, "Task XSS not escaped"
        assert '<script>alert("name")' not in html_content, "Name XSS not escaped"
        assert '<script>document.cookie' not in html_content, "Error XSS not escaped"
        # Trigger: html.escape converts < > " but not =, which is fine
        # The key is that <img> tag can't be created because < > are escaped
        assert '<img src=x onerror' not in html_content, "Trigger XSS: raw img tag not escaped"
        assert '<script>alert("ver")' not in html_content, "Version XSS not escaped"
        
        # Escaped versions SHOULD appear
        assert '&lt;script&gt;' in html_content, "Content should be HTML-escaped"
