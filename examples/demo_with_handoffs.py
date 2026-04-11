"""Demo: Multi-agent pipeline with explicit handoff tracking."""

import time
import random
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck


@record_tool(name="web_search")
def search(query: str) -> list[dict]:
    time.sleep(random.uniform(0.1, 0.3))
    return [{"title": f"Result: {query}", "url": f"https://example.com/{i}"} for i in range(random.randint(3, 7))]

@record_tool(name="summarize")
def summarize(data: list) -> str:
    time.sleep(random.uniform(0.1, 0.2))
    return f"Summary of {len(data)} items with key insights"

@record_agent(name="researcher", version="v1.3")
def researcher(topic: str) -> dict:
    articles = search(f"{topic} latest")
    return {"articles": articles, "topic": topic}

@record_agent(name="analyst", version="v2.0")
def analyst(research_data: dict) -> dict:
    analysis = summarize(research_data["articles"])
    return {"analysis": analysis, "source_count": len(research_data["articles"])}

@record_agent(name="coordinator", version="v1.0")
def coordinator(task: str) -> dict:
    # Phase 1: Research
    research = researcher(task)
    
    # Explicit handoff: researcher → analyst
    record_handoff(
        from_agent="researcher",
        to_agent="analyst",
        context=research,
        summary=f"Passing {len(research['articles'])} articles about {task}",
    )
    
    # Phase 2: Analysis
    analysis = analyst(research)
    
    return {"task": task, "research": research, "analysis": analysis}


def main():
    print("=" * 60)
    print("  AgentGuard — Handoff Tracking Demo")
    print("=" * 60)
    
    recorder = init_recorder(task="Research Pipeline with Handoffs", trigger="manual")
    result = coordinator("AI Agent Observability")
    trace = finish_recording()
    
    print(f"\n✅ Trace: {len(trace.spans)} spans, {trace.duration_ms:.0f}ms")
    
    # Run diagnostics
    print("\n--- Failure Analysis ---")
    fa = analyze_failures(trace)
    print(f"Resilience: {fa.resilience_score:.0%}")
    
    print("\n--- Bottleneck Analysis ---")
    bn = analyze_bottleneck(trace)
    print(f"Bottleneck: {bn.bottleneck_span} ({bn.bottleneck_pct:.0f}%)")
    print(f"Critical path: {' → '.join(bn.critical_path)}")
    
    print("\n--- Flow Analysis ---")
    fl = analyze_flow(trace)
    for h in fl.handoffs:
        print(f"Handoff: {h.from_agent} → {h.to_agent} ({h.context_size_bytes}B)")
    
    # Show handoff spans in trace
    handoff_spans = [s for s in trace.spans if s.span_type.value == "handoff"]
    if handoff_spans:
        print(f"\n--- Explicit Handoffs: {len(handoff_spans)} ---")
        for h in handoff_spans:
            print(f"  🔀 {h.name} ({h.context_size_bytes}B)")


if __name__ == "__main__":
    main()
