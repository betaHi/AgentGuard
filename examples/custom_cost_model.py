"""Custom cost model example — demonstrates cost_fn/yield_fn parameters.

Shows how to use analyze_cost_yield with custom pricing logic
instead of the default span.estimated_cost_usd field.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard.analysis import analyze_cost_yield
from agentguard.builder import TraceBuilder
from agentguard.core.trace import Span


def custom_cost(span: Span) -> float:
    """Custom cost model: charge $0.01/1K tokens + $0.001/second of compute."""
    tokens = span.token_count or 0
    duration_s = (span.duration_ms or 0) / 1000
    return (tokens / 1000) * 0.01 + duration_s * 0.001


def custom_yield(span: Span) -> float:
    """Custom yield: score based on output richness and success."""
    if span.status.value != "completed":
        return 0.0
    if not span.output_data:
        return 20.0
    # More output keys = higher yield (heuristic)
    keys = len(span.output_data) if isinstance(span.output_data, dict) else 1
    return min(keys * 25.0, 100.0)


def main() -> None:
    trace = (TraceBuilder("Research pipeline with custom costs")
        .agent("researcher", duration_ms=8000,
               output_data={"articles": [1, 2, 3], "summary": "...", "sources": ["a", "b"]},
               token_count=2000, cost_usd=0.06)
            .llm_call("gpt4", duration_ms=5000, token_count=1500, cost_usd=0.04)
        .end()
        .agent("writer", duration_ms=12000,
               output_data={"draft": "long text..."},
               token_count=5000, cost_usd=0.15)
            .llm_call("gpt4", duration_ms=10000, token_count=4000, cost_usd=0.12)
        .end()
        .agent("reviewer", duration_ms=3000,
               status="failed", error="Timeout",
               token_count=500, cost_usd=0.01)
        .end()
        .build())

    print("=" * 60)
    print("Default cost model (span.estimated_cost_usd)")
    print("=" * 60)
    default_report = analyze_cost_yield(trace)
    print(default_report.to_report())

    print("\n" + "=" * 60)
    print("Custom cost model (tokens + compute time)")
    print("=" * 60)
    custom_report = analyze_cost_yield(trace, cost_fn=custom_cost, yield_fn=custom_yield)
    print(custom_report.to_report())

    print("\nCustom costs per agent:")
    for e in custom_report.entries:
        print(f"  {e.agent}: ${e.cost_usd:.4f} (yield: {e.yield_score:.0f})")


if __name__ == "__main__":
    main()
