"""Demo: Multi-agent news collection workflow with AgentGuard tracing."""

import time
import random
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording


@record_tool(name="web_search")
def web_search(query: str) -> list[dict]:
    """Simulate web search."""
    time.sleep(random.uniform(0.1, 0.3))
    return [
        {"title": f"Result {i} for '{query}'", "url": f"https://example.com/{i}"}
        for i in range(random.randint(3, 7))
    ]


@record_tool(name="github_trending")
def github_trending() -> list[dict]:
    """Simulate GitHub trending check."""
    time.sleep(random.uniform(0.1, 0.2))
    return [
        {"repo": "EvoScientist/EvoScientist", "stars": 2725},
        {"repo": "karpathy/autoresearch", "stars": 70177},
    ]


@record_tool(name="summarize")
def summarize(articles: list) -> str:
    """Simulate LLM summarization."""
    time.sleep(random.uniform(0.2, 0.4))
    return f"Summary of {len(articles)} articles"


@record_agent(name="北极虾 ❄️", version="v1.3", metadata={"role": "news-collector"})
def beiji_news_collector(topic: str) -> dict:
    """北极虾: Collect AI news from multiple sources."""
    results = web_search(f"{topic} latest news 2026")
    trending = github_trending()
    summary = summarize(results + trending)
    return {"articles": results, "trending": trending, "summary": summary}


@record_agent(name="皮皮虾 👊", version="v2.0", metadata={"role": "tech-analyst"})
def pipi_tech_analyst(topic: str) -> dict:
    """皮皮虾: Analyze tech trends."""
    results = web_search(f"{topic} technical analysis")
    analysis = summarize(results)
    return {"analysis": analysis, "sources": len(results)}


@record_agent(name="基围小小虾 🦐", version="v1.0", metadata={"role": "orchestrator"})
def orchestrator(task: str) -> dict:
    """基围小小虾: Orchestrate multi-agent workflow."""
    news = beiji_news_collector(task)
    analysis = pipi_tech_analyst(task)
    return {
        "task": task,
        "news": news,
        "analysis": analysis,
        "status": "completed",
    }


if __name__ == "__main__":
    # Initialize recording
    recorder = init_recorder(task="AI Agent Daily Report", trigger="cron")
    
    # Run the multi-agent workflow
    result = orchestrator("AI Agent 可观测性")
    
    # Finish and save trace
    trace = finish_recording()
    
    print(f"\n✅ Trace saved: .agentguard/traces/{trace.trace_id}.json")
    print(f"   Spans: {len(trace.spans)}, Duration: {trace.duration_ms:.0f}ms")
    print(f"\nView with: python -m agentguard.cli.main show .agentguard/traces/{trace.trace_id}.json")
