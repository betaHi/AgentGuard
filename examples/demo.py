"""Demo: Multi-agent research workflow with AgentGuard tracing.

Shows how to instrument a multi-agent system with minimal code changes.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


import random
import time

from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import finish_recording, init_recorder

# --- Tools (add @record_tool, that's it) ---

@record_tool(name="web_search")
def web_search(query: str) -> list[dict]:
    """Search the web for relevant articles."""
    time.sleep(random.uniform(0.1, 0.3))
    return [
        {"title": f"Article about {query}", "url": f"https://example.com/{i}", "date": "2026-04-11"}
        for i in range(random.randint(3, 7))
    ]

@record_tool(name="github_api")
def github_api(query: str) -> list[dict]:
    """Search GitHub for trending repos."""
    time.sleep(random.uniform(0.1, 0.2))
    return [
        {"repo": "org/project-a", "stars": 12500},
        {"repo": "org/project-b", "stars": 8300},
    ]

@record_tool(name="summarize")
def summarize(articles: list) -> str:
    """Summarize a list of articles using LLM."""
    time.sleep(random.uniform(0.2, 0.4))
    return f"Summary of {len(articles)} items: key findings include..."


# --- Agents (add @record_agent, that's it) ---

@record_agent(name="news-collector", version="v1.3", metadata={"role": "research"})
def collect_news(topic: str) -> dict:
    """Collect news from multiple sources."""
    articles = web_search(f"{topic} latest news")
    trending = github_api(topic)
    summary = summarize(articles + trending)
    return {"articles": articles, "trending": trending, "summary": summary}

@record_agent(name="analyst", version="v2.0", metadata={"role": "analysis"})
def analyze(topic: str) -> dict:
    """Analyze trends in a topic area."""
    data = web_search(f"{topic} trends analysis")
    return {"analysis": summarize(data), "source_count": len(data)}

@record_agent(name="coordinator", version="v1.0", metadata={"role": "orchestrator"})
def run_research(task: str) -> dict:
    """Coordinate multiple agents to complete a research task."""
    news = collect_news(task)
    analysis = analyze(task)
    return {"task": task, "news": news, "analysis": analysis}


if __name__ == "__main__":
    # Start recording
    recorder = init_recorder(task="AI Agent Research Report", trigger="manual")

    # Run the workflow
    result = run_research("AI Agent Observability")

    # Save trace
    trace = finish_recording()
    print(f"\n✅ Trace saved: .agentguard/traces/{trace.trace_id}.json")
    print(f"   Agents: {len(trace.agent_spans)}, Tools: {len(trace.tool_spans)}, Duration: {trace.duration_ms:.0f}ms")
    print("\n📊 View trace:")
    print(f"   python -m agentguard.cli.main show .agentguard/traces/{trace.trace_id}.json")

    # Generate web report
    from agentguard.web.viewer import generate_timeline_html
    report = generate_timeline_html()
    print(f"\n🌐 Web report: {report}")
