"""Example: Parallel Multi-Agent Pipeline.

A realistic content research pipeline where multiple agents work in PARALLEL:

  coordinator
  ├── [PARALLEL] web_researcher      — searches web sources
  ├── [PARALLEL] academic_researcher — searches arxiv/papers
  ├── [PARALLEL] social_researcher   — searches twitter/reddit
  │
  ├── [SEQUENTIAL] merger            — combines results from all 3
  ├── [SEQUENTIAL] analyst           — analyzes merged data
  └── [SEQUENTIAL] writer            — writes final report

The first 3 researchers run simultaneously (simulated with threading),
then results are merged and processed sequentially.

This demonstrates:
- True parallel agent execution with timing overlap
- Handoffs from multiple sources to one merger
- Context flow through parallel branches
- Failure in one branch while others succeed
"""

import time
import random
import sys
import os

random.seed(42)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import TraceThread, record_agent, record_tool, record_handoff, mark_context_used
from agentguard.sdk.recorder import init_recorder, finish_recording, get_recorder
from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck
from agentguard.flowgraph import build_flow_graph
from agentguard.propagation import analyze_propagation
from agentguard.context_flow import analyze_context_flow_deep
from agentguard.scoring import score_trace
from agentguard.ascii_viz import gantt_chart, status_summary
from agentguard.web.viewer import generate_timeline_html


# ──────────────────────────────────────────
# Tools
# ──────────────────────────────────────────

@record_tool(name="web_search")
def web_search(query: str) -> list:
    time.sleep(random.uniform(0.2, 0.4))
    return [{"title": f"Web: {query} result {i}", "url": f"https://example.com/{i}"} for i in range(3)]

@record_tool(name="arxiv_search")
def arxiv_search(query: str) -> list:
    time.sleep(random.uniform(0.3, 0.5))
    return [{"title": f"Paper: {query} #{i}", "arxiv_id": f"2026.{1000+i}"} for i in range(2)]

@record_tool(name="social_search")
def social_search(query: str) -> list:
    time.sleep(random.uniform(0.1, 0.3))
    # Simulate occasional failure
    if random.random() < 0.3:
        raise ConnectionError("Social API rate limited")
    return [{"text": f"Tweet about {query}", "likes": random.randint(10, 1000)}]

@record_tool(name="llm_summarize")
def llm_summarize(data: dict) -> str:
    time.sleep(random.uniform(0.2, 0.4))
    return f"Summary of {len(data)} items"

@record_tool(name="llm_analyze")
def llm_analyze(text: str) -> dict:
    time.sleep(random.uniform(0.3, 0.5))
    return {"insights": ["Key trend: AI agents", "Growing adoption"], "confidence": 0.85}

@record_tool(name="llm_write")
def llm_write(analysis: dict, sources: list) -> str:
    time.sleep(random.uniform(0.4, 0.6))
    return f"# Research Report\n\nBased on {len(sources)} sources...\n\n## Key Insights\n..."


# ──────────────────────────────────────────
# Agents
# ──────────────────────────────────────────

@record_agent(name="web_researcher", version="v1.0")
def web_researcher(topic: str) -> dict:
    """Research from web sources."""
    results = web_search(topic)
    summary = llm_summarize({"web_results": results})
    return {"source": "web", "results": results, "summary": summary, "count": len(results)}

@record_agent(name="academic_researcher", version="v1.0")
def academic_researcher(topic: str) -> dict:
    """Research from academic papers."""
    papers = arxiv_search(topic)
    summary = llm_summarize({"papers": papers})
    return {"source": "academic", "results": papers, "summary": summary, "count": len(papers)}

@record_agent(name="social_researcher", version="v1.0")
def social_researcher(topic: str) -> dict:
    """Research from social media (may fail due to rate limits)."""
    try:
        posts = social_search(topic)
        return {"source": "social", "results": posts, "summary": f"{len(posts)} posts", "count": len(posts)}
    except ConnectionError as e:
        # Graceful degradation — return partial results
        return {"source": "social", "results": [], "summary": "Rate limited", "count": 0, "error": str(e)}

@record_agent(name="merger", version="v1.0")
def merge_results(web_data: dict, academic_data: dict, social_data: dict) -> dict:
    """Merge results from all research branches."""
    all_results = []
    all_results.extend(web_data.get("results", []))
    all_results.extend(academic_data.get("results", []))
    all_results.extend(social_data.get("results", []))
    
    return {
        "total_sources": 3,
        "total_results": len(all_results),
        "results": all_results,
        "summaries": {
            "web": web_data.get("summary", ""),
            "academic": academic_data.get("summary", ""),
            "social": social_data.get("summary", ""),
        },
    }

@record_agent(name="analyst", version="v2.0")
def analyze(merged: dict) -> dict:
    """Analyze merged research data."""
    analysis = llm_analyze(str(merged["summaries"]))
    return {
        "analysis": analysis,
        "source_count": merged["total_sources"],
        "result_count": merged["total_results"],
    }

@record_agent(name="writer", version="v1.0")
def write_report(analysis_data: dict, sources: list) -> str:
    """Write the final research report."""
    return llm_write(analysis_data["analysis"], sources)


@record_agent(name="parallel-coordinator", version="v1.0")
def orchestrate_pipeline(topic: str) -> dict:
    """Coordinate the full parallel research workflow under one root span."""
    # ── Phase 1: PARALLEL research ──
    # Run 3 researchers concurrently using trace-aware threads
    results = {}
    errors = {}

    def run_researcher(name, fn, *args):
        try:
            results[name] = fn(*args)
        except Exception as e:
            errors[name] = str(e)
            results[name] = {"source": name, "results": [], "error": str(e)}

    threads = [
        TraceThread(target=run_researcher, args=("web", web_researcher, topic)),
        TraceThread(target=run_researcher, args=("academic", academic_researcher, topic)),
        TraceThread(target=run_researcher, args=("social", social_researcher, topic)),
    ]

    print("\n📡 Phase 1: Parallel Research")
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    web_data = results.get("web", {})
    academic_data = results.get("academic", {})
    social_data = results.get("social", {})

    print(f"   Web: {web_data.get('count', 0)} results")
    print(f"   Academic: {academic_data.get('count', 0)} results")
    print(f"   Social: {social_data.get('count', 0)} results")
    if errors:
        print(f"   ⚠ Errors: {errors}")

    # ── Handoffs: all researchers → merger ──
    h1 = record_handoff("web_researcher", "merger", context=web_data, summary=f"{web_data.get('count', 0)} web results")
    h2 = record_handoff("academic_researcher", "merger", context=academic_data, summary=f"{academic_data.get('count', 0)} papers")
    h3 = record_handoff("social_researcher", "merger", context=social_data, summary=f"{social_data.get('count', 0)} social posts")

    # Track what merger actually uses
    mark_context_used(h1, used_keys=["results", "summary"])
    mark_context_used(h2, used_keys=["results", "summary"])
    mark_context_used(h3, used_keys=["results", "summary"])

    # ── Phase 2: Sequential processing ──
    print("\n🔄 Phase 2: Merge & Analyze")
    merged = merge_results(web_data, academic_data, social_data)
    print(f"   Merged: {merged['total_results']} total results")

    h4 = record_handoff("merger", "analyst", context=merged, summary=f"{merged['total_results']} merged results")
    mark_context_used(h4, used_keys=["summaries", "total_results"])

    analysis = analyze(merged)
    print(f"   Analysis: {analysis['analysis']['insights']}")

    h5 = record_handoff("analyst", "writer", context=analysis, summary="Analysis with insights")
    mark_context_used(h5, used_keys=["analysis"])

    # ── Phase 3: Write report ──
    print("\n✍️ Phase 3: Write Report")
    report = write_report(analysis, merged["results"])
    print(f"   Report: {len(report)} chars")

    return {
        "report": report,
        "merged": merged,
        "analysis": analysis,
    }


# ──────────────────────────────────────────
# Pipeline
# ──────────────────────────────────────────

def run_pipeline(topic: str = "Multi-agent AI systems"):
    """Run the parallel research pipeline."""
    
    print(f"🔬 Starting parallel research pipeline: '{topic}'")
    print("=" * 60)
    
    recorder = init_recorder(task=f"Parallel Research: {topic}")
    result = orchestrate_pipeline(topic)
    
    # ── Finish and analyze ──
    trace = finish_recording()
    
    print("\n" + "=" * 60)
    print("📊 Analysis")
    print("=" * 60)
    
    # Score
    score = score_trace(trace)
    print(f"\n🎯 Score: {score.overall:.0f}/100 ({score.grade})")
    
    # Status
    print(f"\n{status_summary(trace)}")
    
    # Gantt chart
    print(f"\n{gantt_chart(trace)}")
    
    # Flow graph
    graph = build_flow_graph(trace)
    print(f"\n{graph.to_report()}")
    print(f"\n📊 Mermaid:\n{graph.to_mermaid()}")
    
    # Propagation
    prop = analyze_propagation(trace)
    if prop.total_failures > 0:
        print(f"\n{prop.to_report()}")
    
    # Context flow
    ctx = analyze_context_flow_deep(trace)
    print(f"\n{ctx.to_report()}")
    
    # Generate HTML report
    from agentguard.store import TraceStore
    store = TraceStore()
    store.save(trace)
    html_path = generate_timeline_html()
    print(f"\n🌐 HTML report: {html_path}")
    
    return trace


if __name__ == "__main__":
    trace = run_pipeline()
