"""Production-ready usage example.

Shows how to use AgentGuard in a real application:
1. Instrument your agents (minimal code changes)
2. Run your pipeline
3. Analyze and act on results
4. Set up monitoring (SLA + alerts)

This is the "copy and adapt" example.
"""

import sys, os, time, random, threading
random.seed(42)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ══════════════════════════════════════
# Step 1: Import and instrument
# ══════════════════════════════════════
from agentguard import (
    record_agent, record_tool, record_handoff, mark_context_used,
    score_trace, extract_metrics, build_flow_graph,
    analyze_propagation, analyze_context_flow_deep,
    SLAChecker, AlertEngine, rule_trace_failed, rule_score_below,
    TraceBuilder, summarize_trace, summarize_brief,
)
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.store import TraceStore
from agentguard.web.viewer import generate_report_from_trace


# ── Your existing tools (add @record_tool) ──
@record_tool(name="llm_call")
def call_llm(prompt: str, model: str = "claude-3-sonnet") -> str:
    time.sleep(random.uniform(0.1, 0.3))
    return f"LLM response to: {prompt[:30]}..."

@record_tool(name="web_search")
def search_web(query: str) -> list:
    time.sleep(random.uniform(0.1, 0.2))
    return [{"title": f"Result for {query}", "url": "https://..."}]

@record_tool(name="db_query")
def query_db(sql: str) -> list:
    time.sleep(random.uniform(0.05, 0.1))
    return [{"id": 1, "data": "row"}]


# ── Your existing agents (add @record_agent) ──
@record_agent(name="researcher", version="v2.1")
def research(topic: str) -> dict:
    web_results = search_web(topic)
    analysis = call_llm(f"Analyze: {topic}")
    return {"results": web_results, "analysis": analysis}

@record_agent(name="writer", version="v1.3")
def write(research_data: dict) -> str:
    return call_llm(f"Write report based on: {research_data['analysis']}")


# ══════════════════════════════════════
# Step 2: Run your pipeline
# ══════════════════════════════════════
def run_pipeline(topic: str) -> dict:
    """Your pipeline, now fully instrumented."""
    
    # Start recording
    recorder = init_recorder(task=f"Research: {topic}")
    
    # Run agents
    data = research(topic)
    
    # Record handoff (the key insight: track what flows between agents)
    h = record_handoff("researcher", "writer", context=data,
                       summary=f"Research on {topic}")
    mark_context_used(h, used_keys=["analysis"])  # writer only uses analysis
    
    report = write(data)
    
    # Finish recording
    trace = finish_recording()
    
    return {"report": report, "trace": trace}


# ══════════════════════════════════════
# Step 3: Analyze
# ══════════════════════════════════════
def analyze(trace):
    """Post-pipeline analysis."""
    
    # Quick summary
    print(summarize_brief(trace))
    
    # Detailed score
    score = score_trace(trace)
    print(f"\nScore: {score.overall:.0f}/100 ({score.grade})")
    for c in score.components:
        print(f"  {c.name}: {c.score:.0f}/100")
    
    # Metrics
    m = extract_metrics(trace)
    print(f"\nMetrics: {m.agent_count} agents, {m.tool_count} tools, "
          f"{m.total_tokens} tokens, ${m.total_cost_usd:.2f}")
    
    # Flow graph
    graph = build_flow_graph(trace)
    print(f"\nFlow: {graph.max_parallelism}x parallelism, "
          f"{graph.sequential_fraction:.0%} sequential")
    
    # Failure check
    prop = analyze_propagation(trace)
    if prop.total_failures > 0:
        print(f"\n⚠️ Failures: {prop.total_failures} "
              f"(containment: {prop.containment_rate:.0%})")
    
    # Natural language summary
    print(f"\n📝 {summarize_trace(trace)}")
    
    return score


# ══════════════════════════════════════
# Step 4: Monitor (SLA + Alerts)
# ══════════════════════════════════════
def setup_monitoring():
    """Set up SLA checks and alert rules."""
    
    # Define SLA
    sla = (SLAChecker()
        .max_duration_ms(5000)
        .min_success_rate(0.95)
        .min_score(70)
        .max_cost_usd(1.0))
    
    # Define alerts
    alerts = AlertEngine()
    alerts.add_rule(rule_trace_failed(severity="critical"))
    alerts.add_rule(rule_score_below(60, severity="error"))
    alerts.add_rule(rule_score_below(80, severity="warning"))
    
    return sla, alerts


# ══════════════════════════════════════
# Main
# ══════════════════════════════════════
if __name__ == "__main__":
    print("🛡️ AgentGuard — Production Usage Example")
    print("=" * 50)
    
    # Run pipeline
    result = run_pipeline("AI agent observability trends 2026")
    trace = result["trace"]
    
    # Analyze
    print("\n📊 Analysis")
    print("-" * 40)
    score = analyze(trace)
    
    # Monitor
    print("\n🔔 Monitoring")
    print("-" * 40)
    sla, alert_engine = setup_monitoring()
    
    sla_result = sla.check(trace)
    print(f"SLA: {'✅ PASS' if sla_result.passed else '❌ FAIL'}")
    for v in sla_result.violations:
        print(f"  ⚠️ {v.message}")
    
    alerts = alert_engine.evaluate(trace)
    if alerts:
        for a in alerts:
            print(f"  🔔 [{a.severity}] {a.message}")
    else:
        print("  No alerts triggered")
    
    # Save and generate HTML report
    store = TraceStore()
    store.save(trace)
    html = generate_report_from_trace(trace)
    print(f"\n🌐 Report: {html}")
    print(f"📦 Trace saved: {trace.trace_id}")
