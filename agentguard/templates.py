"""Trace templates — predefined pipeline patterns.

Provides ready-to-use templates for common multi-agent patterns:
- Research pipeline (collect → analyze → write)
- Code review pipeline (code → review → fix)
- Support pipeline (classify → route → respond)
- ETL pipeline (extract → transform → load)
"""

from __future__ import annotations

from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace


def research_pipeline(
    topic: str = "AI agents",
    include_failures: bool = False,
) -> ExecutionTrace:
    """Generate a research pipeline trace."""
    builder = (TraceBuilder(f"Research: {topic}")
        .agent("researcher", duration_ms=8000,
               output_data={"articles": ["a1", "a2", "a3"], "sources": ["web", "arxiv"]},
               token_count=2000, cost_usd=0.06)
            .tool("web_search", duration_ms=3000)
            .tool("arxiv_fetch", duration_ms=2000)
            .llm_call("claude-extract", duration_ms=2500, token_count=1500, cost_usd=0.04)
        .end()
        .handoff("researcher", "analyst", context_size=3000)
        .agent("analyst", duration_ms=6000,
               input_data={"articles": ["a1", "a2", "a3"]},
               output_data={"insights": ["i1", "i2"], "analysis": "detailed"},
               token_count=3000, cost_usd=0.09)
            .llm_call("claude-analyze", duration_ms=4000, token_count=2500, cost_usd=0.08)
        .end()
        .handoff("analyst", "writer", context_size=1500)
        .agent("writer", duration_ms=10000,
               input_data={"insights": ["i1", "i2"]},
               output_data={"draft": "# Blog Post"},
               token_count=5000, cost_usd=0.15)
            .llm_call("claude-write", duration_ms=8000, token_count=4000, cost_usd=0.12)
        .end())

    if include_failures:
        builder = builder.agent("reviewer", duration_ms=3000, status="failed", error="timeout").end()

    return builder.build()


def code_review_pipeline(
    pr_title: str = "Fix auth bug",
) -> ExecutionTrace:
    """Generate a code review pipeline trace."""
    return (TraceBuilder(f"Code Review: {pr_title}")
        .agent("code_analyzer", duration_ms=5000,
               output_data={"files_changed": 3, "complexity": "medium"},
               token_count=3000, cost_usd=0.09)
            .tool("git_diff", duration_ms=500)
            .tool("lint_check", duration_ms=1000)
            .llm_call("claude-analyze", duration_ms=3000, token_count=2500, cost_usd=0.08)
        .end()
        .handoff("code_analyzer", "reviewer", context_size=5000)
        .agent("reviewer", duration_ms=8000,
               input_data={"files_changed": 3},
               output_data={"comments": ["fix naming", "add test"], "approve": False},
               token_count=4000, cost_usd=0.12)
            .llm_call("claude-review", duration_ms=6000, token_count=3500, cost_usd=0.10)
        .end()
        .handoff("reviewer", "fixer", context_size=2000)
        .agent("fixer", duration_ms=6000,
               input_data={"comments": ["fix naming", "add test"]},
               output_data={"files_fixed": 2, "tests_added": 1},
               token_count=5000, cost_usd=0.15)
            .tool("code_edit", duration_ms=2000)
            .tool("test_run", duration_ms=3000)
        .end()
        .build())


def support_pipeline() -> ExecutionTrace:
    """Generate a customer support pipeline trace."""
    return (TraceBuilder("Customer Support: Billing issue")
        .agent("classifier", duration_ms=2000,
               input_data={"message": "I was charged twice"},
               output_data={"category": "billing", "priority": "high", "sentiment": "negative"},
               token_count=500, cost_usd=0.015)
            .llm_call("claude-classify", duration_ms=1500, token_count=400, cost_usd=0.012)
        .end()
        .handoff("classifier", "resolver", context_size=500)
        .agent("resolver", duration_ms=5000,
               input_data={"category": "billing", "priority": "high"},
               output_data={"resolution": "refund_issued", "amount": 29.99},
               token_count=2000, cost_usd=0.06)
            .tool("billing_api", duration_ms=2000)
            .tool("crm_update", duration_ms=1000)
        .end()
        .handoff("resolver", "responder", context_size=300)
        .agent("responder", duration_ms=3000,
               input_data={"resolution": "refund_issued"},
               output_data={"response": "We've issued a refund of $29.99."},
               token_count=1000, cost_usd=0.03)
            .llm_call("claude-respond", duration_ms=2000, token_count=800, cost_usd=0.024)
        .end()
        .build())


def etl_pipeline() -> ExecutionTrace:
    """Generate an ETL pipeline trace."""
    return (TraceBuilder("ETL: Daily user metrics")
        .agent("extractor", duration_ms=10000,
               output_data={"records": 50000, "source": "postgres"},
               token_count=0)
            .tool("db_query", duration_ms=8000)
            .tool("api_fetch", duration_ms=5000)
        .end()
        .handoff("extractor", "transformer", context_size=100000)
        .agent("transformer", duration_ms=15000,
               input_data={"records": 50000},
               output_data={"records_transformed": 48500, "dropped": 1500})
            .tool("data_clean", duration_ms=5000)
            .tool("feature_compute", duration_ms=8000)
        .end()
        .handoff("transformer", "loader", context_size=80000)
        .agent("loader", duration_ms=8000,
               input_data={"records_transformed": 48500},
               output_data={"records_loaded": 48500, "destination": "bigquery"})
            .tool("bq_insert", duration_ms=6000)
            .tool("validate_counts", duration_ms=1000)
        .end()
        .build())


# Template registry
TEMPLATES = {
    "research": research_pipeline,
    "code_review": code_review_pipeline,
    "support": support_pipeline,
    "etl": etl_pipeline,
}


def list_templates() -> list[str]:
    """List available template names."""
    return list(TEMPLATES.keys())


def create_from_template(name: str, **kwargs) -> ExecutionTrace:
    """Create a trace from a named template."""
    if name not in TEMPLATES:
        raise KeyError(f"Template '{name}' not found. Available: {list_templates()}")
    return TEMPLATES[name](**kwargs)
