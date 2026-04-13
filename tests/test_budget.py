"""Tests for context budget tracking."""

from agentguard.budget import analyze_budget
from agentguard.builder import TraceBuilder


class TestBudget:
    def test_basic(self):
        trace = (TraceBuilder("budget_test")
            .agent("a", token_count=1000, cost_usd=0.03).end()
            .agent("b", token_count=2000, cost_usd=0.06).end()
            .build())

        report = analyze_budget(trace, budgets={"a": 5000, "b": 3000})
        assert report.total_tokens == 3000
        assert report.over_budget_count == 0

    def test_over_budget(self):
        trace = (TraceBuilder("over_budget")
            .agent("heavy", token_count=10000).end()
            .build())

        report = analyze_budget(trace, budgets={"heavy": 5000})
        assert report.over_budget_count == 1
        heavy = next(a for a in report.agents if a.agent_name == "heavy")
        assert heavy.over_budget
        assert heavy.utilization == 2.0

    def test_default_budget(self):
        trace = (TraceBuilder("default")
            .agent("a", token_count=1000).end()
            .build())

        report = analyze_budget(trace, default_budget=2000)
        a = report.agents[0]
        assert a.budget_tokens == 2000
        assert a.utilization == 0.5

    def test_with_llm_calls(self):
        trace = (TraceBuilder("llm_budget")
            .agent("researcher", token_count=500)
                .llm_call("claude", token_count=3000)
            .end()
            .build())

        report = analyze_budget(trace, budgets={"researcher": 5000})
        researcher = next(a for a in report.agents if a.agent_name == "researcher")
        assert researcher.used_tokens >= 3000  # includes LLM call tokens

    def test_report(self):
        trace = (TraceBuilder("report")
            .agent("a", token_count=1000).end()
            .build())
        report = analyze_budget(trace, budgets={"a": 2000})
        text = report.to_report()
        assert "Budget" in text

    def test_to_dict(self):
        trace = (TraceBuilder("dict")
            .agent("a", token_count=100).end()
            .build())
        report = analyze_budget(trace)
        d = report.to_dict()
        assert "total_tokens" in d
