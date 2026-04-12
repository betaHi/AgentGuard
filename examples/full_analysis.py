"""Full analysis example using TraceBuilder — showcases ALL analysis modules.

This creates a realistic multi-agent pipeline trace using the fluent builder,
then runs every analysis module to demonstrate the complete toolkit.
"""

from agentguard.builder import TraceBuilder
from agentguard.scoring import score_trace
from agentguard.metrics import extract_metrics
from agentguard.timeline import build_timeline
from agentguard.flowgraph import build_flow_graph
from agentguard.propagation import analyze_propagation, compute_context_integrity
from agentguard.context_flow import analyze_context_flow_deep
from agentguard.correlation import analyze_correlations
from agentguard.annotations import auto_annotate
from agentguard.filter import filter_spans, by_type, by_status, is_slow
from agentguard.core.trace import SpanType, SpanStatus


def main():
    # Build a realistic trace
    trace = (TraceBuilder("Blog post: AI agent observability trends")
        .agent("researcher", duration_ms=8000, 
               output_data={"articles": ["a1", "a2", "a3"], "raw": "x" * 3000, "meta": {"src": "web"}},
               token_count=2000, cost_usd=0.06)
            .tool("web_search", duration_ms=3000)
            .tool("arxiv_fetch", duration_ms=2000)
            .llm_call("claude-summarize", duration_ms=2500, token_count=1500, cost_usd=0.04)
        .end()
        .handoff("researcher", "analyst", context_size=3500, dropped_keys=["raw"])
        .agent("analyst", duration_ms=6000,
               input_data={"articles": ["a1", "a2", "a3"], "meta": {"src": "web"}},
               output_data={"insights": ["i1", "i2"], "analysis": "deep analysis..."},
               token_count=3000, cost_usd=0.09)
            .llm_call("claude-analyze", duration_ms=4000, token_count=2500, cost_usd=0.08)
        .end()
        .handoff("analyst", "writer", context_size=1500)
        .agent("writer", duration_ms=10000,
               input_data={"insights": ["i1", "i2"]},
               output_data={"draft": "# Blog Post\n..."},
               token_count=5000, cost_usd=0.15)
            .llm_call("claude-write", duration_ms=8000, token_count=4000, cost_usd=0.12)
            .tool("grammar_check", duration_ms=1000)
        .end()
        .agent("reviewer", duration_ms=4000, 
               status="failed", error="Review service timeout",
               token_count=1000, cost_usd=0.03)
            .tool("style_check", duration_ms=500, status="failed", error="Connection refused", retry_count=3)
        .end()
        .build())
    
    print("=" * 70)
    print("🛡️ AgentGuard Full Analysis — Built with TraceBuilder")
    print("=" * 70)
    print(f"Task: {trace.task}")
    print(f"Spans: {len(trace.spans)} | Status: {trace.status.value}")
    
    # 1. Score
    print("\n" + "=" * 70)
    score = score_trace(trace)
    print(score.to_report())
    
    # 2. Metrics
    print("\n" + "=" * 70)
    print("📊 METRICS")
    m = extract_metrics(trace)
    print(f"  Agents: {m.agent_count} | Tools: {m.tool_count} | Handoffs: {m.handoff_count}")
    print(f"  Duration p50: {m.overall_duration.p50_ms:.0f}ms | p90: {m.overall_duration.p90_ms:.0f}ms")
    print(f"  Success rate: {m.success_rate:.0%} | Error rate: {m.error_rate:.0%}")
    print(f"  Tokens: {m.total_tokens:,} | Cost: ${m.total_cost_usd:.2f}")
    
    # 3. Timeline
    print("\n" + "=" * 70)
    tl = build_timeline(trace)
    print(tl.to_text(max_events=15))
    
    # 4. Flow Graph
    print("\n" + "=" * 70)
    graph = build_flow_graph(trace)
    print(graph.to_report())
    
    # 5. Failure Propagation
    print("\n" + "=" * 70)
    prop = analyze_propagation(trace)
    print(prop.to_report())
    
    # 6. Context Flow
    print("\n" + "=" * 70)
    ctx = analyze_context_flow_deep(trace)
    print(ctx.to_report())
    
    # 7. Correlations
    print("\n" + "=" * 70)
    corr = analyze_correlations(trace)
    print(corr.to_report())
    
    # 8. Auto-annotate
    print("\n" + "=" * 70)
    print("📝 AUTO-ANNOTATIONS")
    store = auto_annotate(trace)
    summary = store.summary()
    print(f"  {summary['total']} annotations across {summary['spans_annotated']} spans")
    print(f"  By severity: {summary['by_severity']}")
    
    # 9. Filtering
    print("\n" + "=" * 70)
    print("🔍 FILTERED VIEWS")
    slow = filter_spans(trace, is_slow(5000))
    print(f"  Slow spans (>5s): {[s.name for s in slow]}")
    failed = filter_spans(trace, by_status(SpanStatus.FAILED))
    print(f"  Failed spans: {[s.name for s in failed]}")
    agents = filter_spans(trace, by_type(SpanType.AGENT))
    print(f"  Agents: {[s.name for s in agents]}")
    
    # 10. Context Integrity
    print("\n" + "=" * 70)
    integrity = compute_context_integrity(trace)
    print(f"🛡️ CONTEXT INTEGRITY: {integrity['integrity_score']}/1.00")
    for k, v in integrity["components"].items():
        print(f"  {k}: {v}")
    
    print("\n✅ All 10 analysis modules demonstrated!")


if __name__ == "__main__":
    main()
