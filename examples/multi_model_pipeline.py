"""Example: Multi-Model Pipeline — GPT-4, Claude, and local model cost comparison.

Demonstrates AgentGuard's cost-yield analysis across different LLM providers.
Each agent uses a different model with distinct cost/speed/quality profiles.

Pipeline:
  coordinator
  ├── planner (GPT-4)        — expensive, fast planning
  ├── researcher (Claude)    — mid-cost, thorough research
  ├── local-summarizer       — free, fast, lower quality
  └── reviewer (GPT-4)       — expensive quality gate

Run: python examples/multi_model_pipeline.py
"""

import time
import random
import sys
import os

random.seed(42)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard import record_agent, record_tool, record_handoff
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.analysis import analyze_cost_yield, analyze_bottleneck


# ── Tools (simulated LLM calls with model-specific costs) ──

@record_tool(name="gpt4_call")
def gpt4_call(prompt: str) -> dict:
    """Simulate GPT-4 API call — fast but expensive."""
    time.sleep(random.uniform(0.1, 0.2))
    tokens = random.randint(800, 1200)
    return {"response": f"GPT-4 response to: {prompt[:30]}", "tokens": tokens}


@record_tool(name="claude_call")
def claude_call(prompt: str) -> dict:
    """Simulate Claude API call — balanced cost and quality."""
    time.sleep(random.uniform(0.15, 0.3))
    tokens = random.randint(1000, 1500)
    return {"response": f"Claude response to: {prompt[:30]}", "tokens": tokens}


@record_tool(name="local_llm_call")
def local_llm_call(prompt: str) -> dict:
    """Simulate local model — free but slower and lower quality."""
    time.sleep(random.uniform(0.05, 0.1))
    tokens = random.randint(400, 600)
    return {"response": f"Local response to: {prompt[:30]}", "tokens": tokens}


# ── Agents ──

@record_agent(name="planner", version="v1.0", metadata={"model": "gpt-4"})
def planner(task: str) -> dict:
    """Plan with GPT-4 — fast, structured output."""
    result = gpt4_call(f"Plan implementation of: {task}")
    return {
        "plan": ["Step 1: Research", "Step 2: Implement", "Step 3: Review"],
        "tokens_used": result["tokens"],
        "cost_usd": result["tokens"] * 0.00003,  # GPT-4 pricing
    }


@record_agent(name="researcher", version="v2.0", metadata={"model": "claude-3"})
def researcher(plan: dict) -> dict:
    """Research with Claude — thorough, mid-cost."""
    result = claude_call(f"Research for: {plan['plan'][0]}")
    return {
        "findings": [f"Finding {i}" for i in range(5)],
        "sources": 5,
        "tokens_used": result["tokens"],
        "cost_usd": result["tokens"] * 0.000015,  # Claude pricing
    }


@record_agent(name="local-summarizer", version="v1.0", metadata={"model": "llama-3-8b"})
def local_summarizer(research: dict) -> dict:
    """Summarize with local model — free, fast, lower quality."""
    result = local_llm_call(f"Summarize {research['sources']} sources")
    return {
        "summary": "Brief summary of findings",
        "tokens_used": result["tokens"],
        "cost_usd": 0.0,  # Local model = free
    }


@record_agent(name="reviewer", version="v1.0", metadata={"model": "gpt-4"})
def reviewer(summary: dict) -> dict:
    """Review with GPT-4 — expensive quality gate."""
    result = gpt4_call(f"Review quality of: {summary['summary'][:50]}")
    approved = random.random() > 0.1  # 90% approval rate with seed(42)
    return {
        "approved": approved,
        "feedback": "Looks good" if approved else "Needs revision",
        "tokens_used": result["tokens"],
        "cost_usd": result["tokens"] * 0.00003,
    }


@record_agent(name="coordinator", version="v1.0")
def coordinator(task: str) -> dict:
    """Orchestrate multi-model pipeline."""
    plan = planner(task)
    record_handoff("planner", "researcher", context=plan, summary="3-step plan")

    research = researcher(plan)
    record_handoff("researcher", "local-summarizer", context=research,
                   summary=f"{research['sources']} sources")

    summary = local_summarizer(research)
    record_handoff("local-summarizer", "reviewer", context=summary,
                   summary="Summary for review")

    review = reviewer(summary)

    total_cost = plan["cost_usd"] + research["cost_usd"] + summary["cost_usd"] + review["cost_usd"]
    return {
        "status": "approved" if review["approved"] else "needs_revision",
        "total_cost_usd": round(total_cost, 4),
    }


# ── Main ──

def main():
    print("=" * 60)
    print("  Multi-Model Pipeline: Cost Comparison")
    print("=" * 60)

    init_recorder(task="Multi-Model Cost Comparison", trigger="manual")
    result = coordinator("Add user authentication with OAuth2")
    trace = finish_recording()

    print(f"\n  Result: {result['status']}")
    print(f"  Total cost: ${result['total_cost_usd']:.4f}")
    print(f"  Spans: {len(trace.spans)}")

    # Cost-yield analysis
    cy = analyze_cost_yield(trace)
    print(f"\n  Cost-Yield Analysis:")
    print(f"  Highest cost:  {cy.highest_cost_agent}")
    print(f"  Lowest yield:  {cy.lowest_yield_agent}")
    print(f"  Best ratio:    {cy.best_ratio_agent}")

    for e in sorted(cy.entries, key=lambda x: -x.cost_usd):
        model = ""
        for s in trace.agent_spans:
            if s.name == e.agent:
                model = s.metadata.get("model", "")
                break
        cost_str = f"${e.cost_usd:.4f}" if e.cost_usd > 0 else "free"
        print(f"    {e.agent:20} ({model:12}) yield:{e.yield_score:.0f}/100  cost:{cost_str}")

    # Bottleneck
    bn = analyze_bottleneck(trace)
    print(f"\n  Bottleneck: {bn.bottleneck_span} ({bn.bottleneck_pct:.0f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
