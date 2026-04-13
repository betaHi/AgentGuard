"""Deep trace analysis demo — showcases all new trace semantics.

This example creates a realistic multi-agent content pipeline and
demonstrates:
1. Handoff context tracking (record_handoff + mark_context_used)
2. Failure propagation analysis (causal chains, circuit breakers)
3. Flow graph (phases, parallelism, critical path, Mermaid)
4. Context flow (compression, truncation, bandwidth)
5. Span correlation (fingerprints, patterns)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import json
from agentguard import (
    record_handoff, mark_context_used, detect_context_loss,
    analyze_propagation, hypothetical_failure,
    build_flow_graph, analyze_context_flow_deep,
)
from agentguard.sdk.recorder import init_recorder, finish_recording, get_recorder
from agentguard.sdk.decorators import record_agent, record_tool
from agentguard.correlation import analyze_correlations
from agentguard.propagation import analyze_handoff_chains, compute_context_integrity


def main():
    """Run a simulated multi-agent content pipeline with deep analysis."""
    
    print("=" * 60)
    print("🛡️ AgentGuard — Deep Trace Analysis Demo")
    print("=" * 60)
    
    # Initialize recorder
    recorder = init_recorder(task="Content Pipeline: Write blog post about AI agents")
    
    # === Phase 1: Research ===
    @record_agent(name="researcher")
    def research(topic):
        return {
            "articles": [f"Article about {topic} #{i}" for i in range(5)],
            "sources": ["arxiv", "github", "twitter"],
            "raw_data": "x" * 2000,  # large raw data
            "metadata": {"query": topic, "timestamp": "2026-04-12"},
        }
    
    @record_tool(name="web_search")
    def web_search(query):
        return {"results": [f"Result for {query}"]}
    
    research_output = research("AI agents")
    
    # === Handoff 1: researcher → analyst (drops raw_data) ===
    h1 = record_handoff(
        from_agent="researcher",
        to_agent="analyst",
        context=research_output,
        summary="5 articles about AI agents with sources and metadata",
    )
    
    # Analyst only uses articles and sources (drops raw_data and metadata)
    mark_context_used(h1, used_keys=["articles", "sources"])
    
    # === Phase 2: Analysis (simulated) ===
    @record_agent(name="analyst")
    def analyze(articles, sources):
        return {
            "key_points": ["Point 1: agents are evolving", "Point 2: observability matters"],
            "analysis": "Detailed analysis of multi-agent systems...",
        }
    
    analysis_output = analyze(
        articles=research_output["articles"],
        sources=research_output["sources"],
    )
    
    # === Handoff 2: analyst → writer ===
    h2 = record_handoff(
        from_agent="analyst",
        to_agent="writer",
        context=analysis_output,
        summary="Key points and analysis for blog post",
    )
    mark_context_used(h2, used_keys=["key_points", "analysis"])
    
    # === Phase 3: Writing ===
    @record_agent(name="writer")
    def write(key_points, analysis):
        return {"draft": "# AI Agents in 2026\n\nAgents are evolving..."}
    
    draft = write(
        key_points=analysis_output["key_points"],
        analysis=analysis_output["analysis"],
    )
    
    # === Finish recording ===
    trace = finish_recording()
    
    print(f"\n📊 Trace: {trace.trace_id}")
    print(f"   Spans: {len(trace.spans)}")
    print(f"   Duration: {trace.duration_ms:.0f}ms")
    
    # === Analysis 1: Handoff Chains ===
    print("\n" + "=" * 60)
    print("🔗 Handoff Chain Analysis")
    print("=" * 60)
    
    chains = analyze_handoff_chains(trace)
    print(f"Total handoffs: {chains['total_handoffs']}")
    print(f"Degradation score: {chains['degradation_score']}")
    if chains["critical_handoff"]:
        ch = chains["critical_handoff"]
        print(f"Critical handoff: {ch['from']} → {ch['to']} (dropped: {ch['keys_dropped']})")
    
    # === Analysis 2: Context Integrity ===
    print("\n" + "=" * 60)
    print("🛡️ Context Integrity Score")
    print("=" * 60)
    
    integrity = compute_context_integrity(trace)
    print(f"Integrity score: {integrity['integrity_score']}")
    for key, val in integrity["components"].items():
        print(f"  {key}: {val}")
    for rec in integrity["recommendations"]:
        print(f"  ⚠️ {rec}")
    
    # === Analysis 3: Flow Graph ===
    print("\n" + "=" * 60)
    print("📊 Flow Graph")
    print("=" * 60)
    
    graph = build_flow_graph(trace)
    print(graph.to_report())
    
    print("\n📊 Mermaid Diagram:")
    print(graph.to_mermaid())
    
    # === Analysis 4: Context Flow ===
    print("\n" + "=" * 60)
    print("📦 Context Flow")
    print("=" * 60)
    
    ctx_flow = analyze_context_flow_deep(trace)
    print(ctx_flow.to_report())
    
    # === Analysis 5: Correlations ===
    print("\n" + "=" * 60)
    print("🔍 Span Correlations")
    print("=" * 60)
    
    correlations = analyze_correlations(trace)
    print(correlations.to_report())
    
    # === Analysis 6: Failure Propagation (hypothetical) ===
    print("\n" + "=" * 60)
    print("💥 Hypothetical Failure Analysis")
    print("=" * 60)
    
    for span in trace.spans[:3]:
        hyp = hypothetical_failure(trace, span.span_id)
        print(f"If '{hyp.get('target_span', '?')}' failed → blast radius: {hyp['blast_radius']}")
    
    print("\n✅ Demo complete!")


if __name__ == "__main__":
    main()
