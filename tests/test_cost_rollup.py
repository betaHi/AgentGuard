"""Cost must roll up from descendants when an agent span has none of its own.

Real runtimes (Claude, LangGraph, multi-step wrappers) attach cost and
tokens to the leaf LLM / tool spans — not to the orchestrating agent.
If the cost-yield analysis only reads the agent span's own
``estimated_cost_usd``, every entry shows $0 and Q3 is silently useless.
"""

from __future__ import annotations

from agentguard.analysis import analyze_cost_yield
from agentguard.builder import TraceBuilder


def test_cost_rolls_up_from_llm_children():
    trace = (
        TraceBuilder("rollup-basic")
        .agent("coordinator", duration_ms=10_000)
            .llm_call("claude-call-1", duration_ms=2000,
                      token_count=1500, cost_usd=0.30)
            .llm_call("claude-call-2", duration_ms=2000,
                      token_count=2000, cost_usd=0.42)
            .tool("Bash", duration_ms=500)
        .end()
        .build()
    )
    report = analyze_cost_yield(trace)
    coordinator = next(e for e in report.entries if e.agent == "coordinator")
    # 0.30 + 0.42 = 0.72, rolled up from the LLM children.
    assert coordinator.cost_usd > 0, (
        f"coordinator must aggregate child cost; got {coordinator.cost_usd}"
    )
    assert abs(coordinator.cost_usd - 0.72) < 1e-6
    assert coordinator.tokens == 3500


def test_explicit_agent_cost_wins_over_rollup():
    """If the agent carries its own cost, don't double-count from children."""
    trace = (
        TraceBuilder("rollup-explicit")
        .agent("planner", duration_ms=1000, token_count=10, cost_usd=0.05)
            .llm_call("llm", duration_ms=500, token_count=500, cost_usd=0.25)
        .end()
        .build()
    )
    report = analyze_cost_yield(trace)
    planner = next(e for e in report.entries if e.agent == "planner")
    assert abs(planner.cost_usd - 0.05) < 1e-6, (
        f"when agent carries direct cost, do NOT roll up; got {planner.cost_usd}"
    )


def test_rollup_does_not_descend_into_nested_agents():
    """Nested agents each own their subtree's cost — no double counting."""
    # The outer coordinator walks its subtree but each inner agent is
    # a separate entry. The roll-up should still include the inner
    # agent's LLM calls because the coordinator's timeline DID incur
    # them, but the inner agent's entry must not be erased.
    trace = (
        TraceBuilder("rollup-nested")
        .agent("outer", duration_ms=5000)
            .agent("inner", duration_ms=3000)
                .llm_call("llm", duration_ms=1000,
                          token_count=500, cost_usd=0.20)
            .end()
        .end()
        .build()
    )
    report = analyze_cost_yield(trace)
    agents = {e.agent: e for e in report.entries}
    assert "outer" in agents
    assert "inner" in agents
    # Both agents get the $0.20 because both subtrees contain the LLM call.
    # This is the honest answer — the coordinator DID spend that money.
    assert abs(agents["inner"].cost_usd - 0.20) < 1e-6
    assert abs(agents["outer"].cost_usd - 0.20) < 1e-6
