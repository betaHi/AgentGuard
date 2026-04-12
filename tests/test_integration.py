"""Integration tests — simulate a real user's end-to-end workflow.

These tests verify that a user can:
1. Instrument their existing code with minimal changes
2. Record multi-agent traces
3. Analyze the traces (failures, bottlenecks, handoffs)
4. Evaluate output quality
5. Compare versions
6. Export to different formats
7. Generate reports

Each test is self-contained and tests a complete user journey.
"""

import asyncio
import json
import tempfile
import time
from pathlib import Path

from agentguard import (
    record_agent, record_tool,
    record_agent_async, record_tool_async,
    AgentTrace, ToolContext,
    AsyncAgentTrace,
    record_handoff,
)
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.sdk.manual import ManualTracer
from agentguard.sdk.middleware import wrap_agent, wrap_tool
from agentguard.sdk.distributed import inject_trace_context, init_recorder_from_env, merge_child_traces
from agentguard.eval.rules import evaluate_rules
from agentguard.eval.compare import compare_traces, compare_evals
from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck, analyze_context_flow
from agentguard.diff import diff_traces
from agentguard.export import export_jsonl, export_otel_spans, trace_statistics
from agentguard.replay import ReplayEngine
from agentguard.guard import Guard
from agentguard.health import generate_health_report
from agentguard.query import TraceStore
from agentguard.web.viewer import generate_timeline_html
from agentguard.core.trace import ExecutionTrace, SpanType


# ──────────────────────────────────────────────────────
# Test 1: User instruments existing code with decorators
# ──────────────────────────────────────────────────────

def test_e2e_decorator_workflow():
    """User adds @record_agent/@record_tool to existing functions."""
    
    # User's existing code — just add decorators, nothing else changes
    @record_tool(name="fetch_data")
    def fetch_data(query: str) -> list:
        return [{"id": 1, "title": query}, {"id": 2, "title": f"More {query}"}]

    @record_tool(name="process")
    def process(data: list) -> dict:
        return {"count": len(data), "processed": True}

    @record_agent(name="data-agent", version="v1.0")
    def data_agent(task: str) -> dict:
        raw = fetch_data(task)
        result = process(raw)
        return {"task": task, "result": result, "items": raw}

    @record_agent(name="coordinator", version="v2.0")
    def coordinator(task: str) -> dict:
        return data_agent(task)

    # User starts recording
    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = init_recorder(task="Integration Test", trigger="test", output_dir=f"{tmpdir}/traces")
        
        # User runs their code — NO CHANGES to business logic
        result = coordinator("AI news")
        
        # User finishes recording
        trace = finish_recording()
        
        # Verify: trace was captured correctly
        assert trace.task == "Integration Test"
        assert len(trace.spans) == 4  # coordinator + data-agent + 2 tools
        assert len(trace.agent_spans) == 2
        assert len(trace.tool_spans) == 2
        
        # Verify: parent-child nesting is correct
        coord_span = trace.spans[0]
        agent_span = trace.spans[1]
        assert agent_span.parent_span_id == coord_span.span_id
        
        # Verify: output was captured
        assert trace.spans[0].output_data is not None
        
        # Verify: trace was saved to disk
        trace_files = list(Path(f"{tmpdir}/traces").glob("*.json"))
        assert len(trace_files) == 1
        
        # Verify: trace can be loaded back
        loaded = ExecutionTrace.from_json(trace_files[0].read_text())
        assert loaded.trace_id == trace.trace_id
        assert len(loaded.spans) == 4


# ──────────────────────────────────────────────────────
# Test 2: User uses context managers (no decorators)
# ──────────────────────────────────────────────────────

def test_e2e_context_manager_workflow():
    """User wraps existing code with context managers — zero decoration."""
    
    # User's existing functions — completely untouched
    def my_search(query):
        return [f"result for {query}"]
    
    def my_process(data):
        return {"processed": data}

    with tempfile.TemporaryDirectory() as tmpdir:
        recorder = init_recorder(task="CM Test", output_dir=f"{tmpdir}/traces")
        
        with AgentTrace(name="my-agent", version="v1") as agent:
            with agent.tool("search") as t:
                results = my_search("AI")
                t.set_output(results)
            with agent.tool("process") as t:
                processed = my_process(results)
                t.set_output(processed)
            agent.set_output(processed)
        
        trace = finish_recording()
        assert len(trace.spans) == 3  # agent + 2 tools
        assert trace.spans[0].status.value == "completed"


# ──────────────────────────────────────────────────────
# Test 3: User instruments async code
# ──────────────────────────────────────────────────────

def test_e2e_async_workflow():
    """User instruments async agent code."""
    
    @record_tool_async(name="async_fetch")
    async def fetch(url):
        await asyncio.sleep(0.01)
        return {"data": url}

    @record_agent_async(name="async-agent", version="v1")
    async def agent(task):
        r = await fetch(f"https://api.example.com/{task}")
        return r

    recorder = init_recorder(task="Async Test")
    asyncio.run(agent("search"))
    trace = finish_recording()
    
    assert len(trace.spans) == 2
    assert trace.spans[0].name == "async-agent"
    assert trace.spans[1].parent_span_id == trace.spans[0].span_id


# ──────────────────────────────────────────────────────
# Test 4: User wraps third-party code with middleware
# ──────────────────────────────────────────────────────

def test_e2e_middleware_workflow():
    """User wraps third-party library functions without modifying them."""
    
    # Simulating a third-party class the user can't modify
    class ThirdPartyAgent:
        def run(self, task):
            return f"Result: {task}"
    
    def third_party_tool(query):
        return [query, query]

    recorder = init_recorder(task="Middleware Test")
    
    traced_tool = wrap_tool(third_party_tool, name="external-search")
    traced_agent = wrap_agent(ThirdPartyAgent().run, name="external-agent", version="v3")
    
    results = traced_tool("AI")
    output = traced_agent("summarize")
    
    trace = finish_recording()
    assert len(trace.spans) == 2
    assert output == "Result: summarize"  # original behavior preserved


# ──────────────────────────────────────────────────────
# Test 5: User records handoffs explicitly
# ──────────────────────────────────────────────────────

def test_e2e_handoff_workflow():
    """User tracks context transfer between agents."""
    
    @record_agent(name="producer", version="v1")
    def producer():
        return {"articles": [1, 2, 3], "query": "AI"}

    @record_agent(name="consumer", version="v1")
    def consumer(data):
        return {"processed": len(data["articles"])}

    recorder = init_recorder(task="Handoff Test")
    
    data = producer()
    
    handoff = record_handoff(
        from_agent="producer", to_agent="consumer",
        context=data, summary="3 articles about AI",
    )
    
    result = consumer(data)
    trace = finish_recording()
    
    # Verify handoff span exists
    handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    assert len(handoffs) == 1
    assert handoffs[0].handoff_from == "producer"
    assert handoffs[0].context_size_bytes > 0


# ──────────────────────────────────────────────────────
# Test 6: User runs analysis on captured trace
# ──────────────────────────────────────────────────────

def test_e2e_analysis_workflow():
    """User captures a trace with failures and runs full diagnostics."""
    
    @record_tool(name="api_call")
    def api_call():
        raise ConnectionError("API timeout")
    
    @record_tool(name="fallback_cache")
    def fallback():
        return {"cached": True}

    @record_agent(name="resilient-agent", version="v1")
    def resilient():
        try:
            return api_call()
        except:
            return fallback()

    @record_agent(name="fragile-agent", version="v1")
    def fragile():
        return api_call()  # will crash

    @record_agent(name="orchestrator", version="v1")
    def orchestrator():
        r = resilient()
        try:
            f = fragile()
        except:
            f = {"error": "failed"}
        return {"resilient": r, "fragile": f}

    recorder = init_recorder(task="Analysis Test")
    orchestrator()
    trace = finish_recording()
    
    # Run all analysis functions
    failures = analyze_failures(trace)
    flow = analyze_flow(trace)
    bottleneck = analyze_bottleneck(trace)
    context = analyze_context_flow(trace)
    
    # Verify failure analysis
    assert failures.total_failed_spans >= 2
    assert failures.handled_count >= 1  # resilient agent caught the error
    assert failures.unhandled_count >= 1  # fragile agent didn't
    assert 0 < failures.resilience_score < 1
    
    # Verify flow analysis
    assert flow.agent_count >= 3
    
    # Verify bottleneck
    assert bottleneck.bottleneck_span != ""
    
    # Verify reports generate without error
    assert "Failure" in failures.to_report()
    assert "Bottleneck" in bottleneck.to_report()


# ──────────────────────────────────────────────────────
# Test 7: User evaluates agent output quality
# ──────────────────────────────────────────────────────

def test_e2e_evaluation_workflow():
    """User defines rules and evaluates agent output."""
    
    agent_output = {
        "articles": [
            {"title": "AI News 1", "url": "https://a.com", "date": "2026-04-11"},
            {"title": "AI News 2", "url": "https://b.com", "date": "2026-04-10"},
            {"title": "AI News 3", "url": "https://c.com", "date": "2026-04-11"},
        ],
        "summary": "Key trends: AI agents, observability, multi-agent systems",
    }
    
    rules = [
        {"type": "min_count", "target": "articles", "value": 3, "name": "enough-articles"},
        {"type": "each_has", "target": "articles", "fields": ["title", "url", "date"], "name": "complete-fields"},
        {"type": "no_duplicates", "target": "articles", "field": "url", "name": "no-duplicate-urls"},
        {"type": "contains", "target": "summary", "keywords": ["agent", "trend"], "mode": "any", "name": "relevant-summary"},
        {"type": "recency", "target": "articles.date", "within_days": 3, "name": "recent-articles"},
    ]
    
    results = evaluate_rules(agent_output, rules)
    
    assert len(results) == 5
    passed = sum(1 for r in results if r.verdict.value == "pass")
    assert passed >= 4  # at least 4 of 5 should pass


# ──────────────────────────────────────────────────────
# Test 8: User compares two trace versions
# ──────────────────────────────────────────────────────

def test_e2e_diff_workflow():
    """User compares traces from two different agent versions."""
    
    @record_agent(name="agent", version="v1")
    def v1_agent():
        return {"count": 3}

    @record_agent(name="agent", version="v2")
    def v2_agent():
        raise ValueError("bug in v2")

    # Record v1
    init_recorder(task="V1 run")
    v1_agent()
    trace_v1 = finish_recording()
    
    # Record v2
    init_recorder(task="V2 run")
    try: v2_agent()
    except: pass
    trace_v2 = finish_recording()
    
    # Diff
    diff = diff_traces(trace_v1, trace_v2)
    assert diff.has_changes
    assert len(diff.regressions) >= 1  # v2 regressed (new failure)


# ──────────────────────────────────────────────────────
# Test 9: User exports traces to different formats
# ──────────────────────────────────────────────────────

def test_e2e_export_workflow():
    """User exports traces to JSONL and OTel formats."""
    
    @record_agent(name="export-agent", version="v1")
    def agent():
        return {"data": [1, 2, 3]}

    init_recorder(task="Export Test")
    agent()
    trace = finish_recording()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # JSONL export
        jsonl_path = f"{tmpdir}/trace.jsonl"
        export_jsonl(trace, jsonl_path)
        lines = Path(jsonl_path).read_text().strip().split("\n")
        assert len(lines) >= 2  # header + at least 1 span
        
        # OTel export
        otel_spans = export_otel_spans(trace)
        assert len(otel_spans) >= 1
        assert "gen_ai.operation.name" in otel_spans[0]["attributes"]
        
        # Statistics
        stats = trace_statistics(trace)
        assert stats["total_spans"] >= 1
        assert stats["agent_count"] >= 1


# ──────────────────────────────────────────────────────
# Test 10: User sets up replay baselines and regression testing
# ──────────────────────────────────────────────────────

def test_e2e_replay_workflow():
    """User saves a baseline and checks future runs against it."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        engine = ReplayEngine(baselines_dir=f"{tmpdir}/baselines")
        
        # Save baseline from a good run
        good_output = {"articles": [1, 2, 3, 4, 5], "quality": 0.9}
        engine.save_baseline(
            "daily-report", input_data={"topic": "AI"},
            output_data=good_output,
            rules=[{"type": "min_count", "target": "articles", "value": 5}],
        )
        
        # Simulate a degraded run
        bad_output = {"articles": [1, 2], "quality": 0.4}
        result = engine.compare("daily-report", bad_output)
        
        assert result.verdict == "regressed"


# ──────────────────────────────────────────────────────
# Test 11: User generates health report across multiple traces
# ──────────────────────────────────────────────────────

def test_e2e_health_report():
    """User checks agent health across historical traces."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        # Simulate 5 historical runs
        for i in range(5):
            @record_agent(name="daily-agent", version="v1")
            def agent():
                if i == 4:  # last run fails
                    raise RuntimeError("crash")
                return {"ok": True}
            
            rec = init_recorder(task=f"run-{i}", output_dir=str(traces_dir))
            try: agent()
            except: pass
            finish_recording()
        
        # Generate health report
        report = generate_health_report(str(traces_dir))
        assert report.total_traces == 5
        assert len(report.agents) >= 1
        assert "Health Report" in report.to_report()


# ──────────────────────────────────────────────────────
# Test 12: User generates web report
# ──────────────────────────────────────────────────────

def test_e2e_web_report():
    """User generates an HTML report from traces."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        
        @record_agent(name="web-agent", version="v1")
        def agent():
            return {"result": "ok"}
        
        rec = init_recorder(task="Web Report Test", output_dir=str(traces_dir))
        agent()
        finish_recording()
        
        output = generate_timeline_html(str(traces_dir), f"{tmpdir}/report.html")
        html = Path(output).read_text()
        assert "AgentGuard" in html
        assert "web-agent" in html


# ──────────────────────────────────────────────────────
# Test 13: User queries traces with TraceStore
# ──────────────────────────────────────────────────────

def test_e2e_query_workflow():
    """User filters and queries traces."""
    
    with tempfile.TemporaryDirectory() as tmpdir:
        traces_dir = Path(tmpdir) / "traces"
        traces_dir.mkdir()
        
        # Create varied traces
        for task, trigger, should_fail in [
            ("Daily Report", "cron", False),
            ("Ad-hoc Query", "manual", False),
            ("Broken Pipeline", "cron", True),
        ]:
            @record_agent(name="test-agent", version="v1")
            def agent():
                if should_fail:
                    raise RuntimeError("fail")
                return {"ok": True}
            
            rec = init_recorder(task=task, trigger=trigger, output_dir=str(traces_dir))
            try: agent()
            except: pass
            finish_recording()
        
        store = TraceStore(str(traces_dir))
        
        # Filter by trigger
        cron_traces = store.filter(trigger="cron")
        assert len(cron_traces) == 2
        
        # Filter by status
        failed = store.filter(status="failed")
        assert len(failed) == 1
        
        # Agent stats
        stats = store.agent_stats()
        assert "test-agent" in stats


# ──────────────────────────────────────────────────────
# Test 14: User runs self-reflection and evolution
# ──────────────────────────────────────────────────────

def test_e2e_evolve_workflow():
    """User records traces, then runs self-reflection to get improvement suggestions."""
    
    @record_tool(name="flaky_api")
    def flaky_api():
        raise ConnectionError("timeout")
    
    @record_tool(name="backup")
    def backup():
        return {"ok": True}

    @record_agent(name="agent-with-fallback", version="v1")
    def agent_fb():
        try: return flaky_api()
        except: return backup()

    @record_agent(name="agent-fragile", version="v1")
    def agent_fr():
        return flaky_api()

    @record_agent(name="coord", version="v1")
    def coord():
        a = agent_fb()
        try: b = agent_fr()
        except: b = {"error": True}
        return {"a": a, "b": b}

    with tempfile.TemporaryDirectory() as tmpdir:
        from agentguard.evolve import EvolutionEngine
        engine = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        
        # Run 3 times, learn each time
        for _ in range(3):
            rec = init_recorder(task="Evolve Test", output_dir=f"{tmpdir}/traces")
            coord()
            trace = finish_recording()
            reflection = engine.learn(trace)
            assert len(reflection.lessons) >= 1
        
        # Should have accumulated knowledge
        assert engine.kb.trace_count == 3
        
        # Should have suggestions
        suggestions = engine.suggest(min_confidence=0.5)
        assert len(suggestions) >= 1
        
        # Should detect trends
        trends = engine.detect_trends()
        assert len(trends) >= 1
        
        # Knowledge persists
        engine2 = EvolutionEngine(knowledge_dir=f"{tmpdir}/kb")
        assert engine2.kb.trace_count == 3


# ──────────────────────────────────────────────────────
# Test 15: README Quick Start works exactly as documented
# ──────────────────────────────────────────────────────

def test_readme_quick_start():
    """The exact code from README Quick Start section works."""
    
    # === From README: Option 1: Decorators ===
    from agentguard import record_agent, record_tool
    from agentguard.sdk.recorder import init_recorder, finish_recording
    
    @record_tool(name="web_search")
    def search(query: str) -> list:
        return [{"title": f"Result: {query}", "url": "https://example.com"}]

    @record_agent(name="researcher", version="v1.3")
    def research(topic: str) -> dict:
        results = search(topic)
        return {"results": results}

    with tempfile.TemporaryDirectory() as tmpdir:
        init_recorder(task="Daily Report", trigger="cron", output_dir=f"{tmpdir}/traces")
        research("AI agents")
        trace = finish_recording()
        
        # Verify it actually worked
        assert trace.task == "Daily Report"
        assert len(trace.spans) == 2
        assert trace.spans[0].name == "researcher"
        assert trace.spans[1].name == "web_search"
        
        # Trace file exists
        files = list(Path(f"{tmpdir}/traces").glob("*.json"))
        assert len(files) == 1
        
        # Can be loaded back
        loaded = ExecutionTrace.from_json(files[0].read_text())
        assert loaded.trace_id == trace.trace_id


# ──────────────────────────────────────────────────────
# Test 16: Full coding pipeline e2e with evolve
# ──────────────────────────────────────────────────────

def test_coding_pipeline_full_cycle():
    """The coding pipeline example runs and produces valid trace + analysis + evolve."""
    import subprocess, sys
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Run the actual example
        result = subprocess.run(
            [sys.executable, "examples/coding_pipeline.py"],
            capture_output=True, text=True,
            env={**__import__('os').environ, "PYTHONPATH": "/tmp/AgentGuard"},
            cwd="/tmp/AgentGuard",
            timeout=30,
        )
        
        assert result.returncode == 0, f"Pipeline failed: {result.stderr}"
        assert "Result:" in result.stdout
        assert "Self-Reflection" in result.stdout
