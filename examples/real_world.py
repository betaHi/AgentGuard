"""Real-world example: Research agent pipeline with evaluation.

Demonstrates:
1. Multi-agent workflow recording
2. Rule-based evaluation
3. Replay baseline + comparison
4. HTML report generation
"""

import time
import random
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.eval.rules import evaluate_rules
from agentguard.core.eval_schema import EvaluationResult
from agentguard.replay import ReplayEngine
from agentguard.web.viewer import generate_timeline_html


# --- Define tools ---

@record_tool(name="search_api")
def search_api(query: str) -> list[dict]:
    """Simulates a search API call."""
    time.sleep(random.uniform(0.05, 0.15))
    count = random.randint(3, 8)
    return [
        {
            "title": f"Article {i}: {query}",
            "url": f"https://news.example.com/{query.replace(' ', '-')}/{i}",
            "date": "2026-04-11",
            "source": random.choice(["TechCrunch", "Arxiv", "HackerNews"]),
        }
        for i in range(count)
    ]

@record_tool(name="llm_summarize")
def llm_summarize(articles: list) -> str:
    """Simulates LLM summarization."""
    time.sleep(random.uniform(0.1, 0.2))
    return f"Analysis of {len(articles)} articles: key trends include increasing adoption of multi-agent systems, growing focus on agent reliability, and emergence of new evaluation frameworks."


# --- Define agents ---

@record_agent(name="researcher", version="v1.3")
def researcher(topic: str) -> dict:
    """Research agent: searches and collects information."""
    articles = search_api(f"{topic} latest developments")
    trending = search_api(f"{topic} GitHub trending")
    return {
        "articles": articles + trending,
        "topic": topic,
        "source_count": 2,
    }

@record_agent(name="analyst", version="v2.0")
def analyst(data: dict) -> dict:
    """Analysis agent: synthesizes research findings."""
    summary = llm_summarize(data["articles"])
    return {
        "summary": summary,
        "article_count": len(data["articles"]),
        "quality_score": random.uniform(0.7, 0.95),
    }

@record_agent(name="pipeline-coordinator", version="v1.0")
def run_pipeline(task: str) -> dict:
    """Pipeline coordinator: orchestrates the research workflow."""
    research = researcher(task)
    analysis = analyst(research)
    return {
        "task": task,
        "articles": research["articles"],
        "analysis": analysis["summary"],
        "quality": analysis["quality_score"],
    }


def main():
    print("=" * 60)
    print("  AgentGuard Real-World Example")
    print("=" * 60)
    
    # 1. Record execution
    print("\n1. Recording agent execution...")
    init_recorder(task="AI Research Pipeline", trigger="manual")
    result = run_pipeline("AI Agent Observability")
    trace = finish_recording()
    print(f"   ✅ Trace saved ({len(trace.spans)} spans, {trace.duration_ms:.0f}ms)")
    
    # 2. Evaluate
    print("\n2. Evaluating output quality...")
    rules = [
        {"type": "min_count", "target": "articles", "value": 5, "name": "min-articles"},
        {"type": "each_has", "target": "articles", "fields": ["title", "url", "date"], "name": "required-fields"},
        {"type": "no_duplicates", "target": "articles", "field": "url", "name": "unique-urls"},
        {"type": "contains", "target": "analysis", "keywords": ["agent", "trend"], "mode": "any", "name": "has-keywords"},
        {"type": "range", "target": "quality", "min_val": 0.5, "max_val": 1.0, "name": "quality-range"},
    ]
    
    eval_results = evaluate_rules(result, rules)
    passed = sum(1 for r in eval_results if r.verdict.value == "pass")
    print(f"   ✅ {passed}/{len(eval_results)} rules passed")
    for r in eval_results:
        icon = "✓" if r.verdict.value == "pass" else "✗"
        print(f"      {icon} {r.name}: {r.verdict.value}")
    
    # 3. Save as replay baseline
    print("\n3. Saving replay baseline...")
    engine = ReplayEngine()
    engine.save_baseline(
        name="ai-research-pipeline",
        input_data={"task": "AI Agent Observability"},
        output_data=result,
        rules=rules,
    )
    print("   ✅ Baseline saved")
    
    # 4. Generate web report
    print("\n4. Generating web report...")
    report = generate_timeline_html()
    print(f"   ✅ Report: {report}")
    
    print("\n" + "=" * 60)
    print("  Done! View trace with:")
    print(f"  agentguard show .agentguard/traces/{trace.trace_id}.json")
    print("=" * 60)


if __name__ == "__main__":
    main()
