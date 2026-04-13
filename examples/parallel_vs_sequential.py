"""Performance optimization: parallel pipeline is 3x faster than sequential.

Demonstrates Q1 (bottleneck) and Q4 (cost-yield) analysis by comparing
two execution strategies for the same task:
  - Sequential: agents run one after another (9s total)
  - Parallel: agents run concurrently (3s total, same cost)

Shows how AgentGuard's analysis identifies the bottleneck in sequential
mode and confirms the parallel pipeline's superior cost-yield ratio.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agentguard.analysis import analyze_bottleneck, analyze_cost_yield
from agentguard.builder import TraceBuilder
from agentguard.scoring import score_trace


def build_sequential_trace():
    """Build a sequential pipeline: 3 agents run one after another.

    Total wall time: 9000ms (3000 + 3000 + 3000).
    Each agent costs $0.01, total $0.03.
    """
    return (TraceBuilder("data pipeline - sequential")
        .agent("coordinator", duration_ms=9200)
            .agent("extractor", duration_ms=3000,
                   token_count=1000, cost_usd=0.01,
                   output_data={"records": 500})
            .end()
            .agent("transformer", duration_ms=3000,
                   token_count=1000, cost_usd=0.01,
                   output_data={"transformed": 500})
            .end()
            .agent("loader", duration_ms=3000,
                   token_count=1000, cost_usd=0.01,
                   output_data={"loaded": 500})
            .end()
        .end()
        .build())


def build_parallel_trace():
    """Build a parallel pipeline: 3 agents run concurrently.

    Total wall time: 3200ms (all 3 overlap).
    Same per-agent cost ($0.01 each), total $0.03.
    The builder creates sequential spans, but we set coordinator
    duration to reflect the parallel wall time.
    """
    return (TraceBuilder("data pipeline - parallel")
        .agent("coordinator", duration_ms=3200)
            .agent("extractor", duration_ms=3000,
                   token_count=1000, cost_usd=0.01,
                   output_data={"records": 500})
            .end()
            .agent("transformer", duration_ms=3000,
                   token_count=1000, cost_usd=0.01,
                   output_data={"transformed": 500})
            .end()
            .agent("loader", duration_ms=3000,
                   token_count=1000, cost_usd=0.01,
                   output_data={"loaded": 500})
            .end()
        .end()
        .build())


def compare_pipelines():
    """Compare sequential vs parallel and print analysis."""
    seq_trace = build_sequential_trace()
    par_trace = build_parallel_trace()

    seq_bn = analyze_bottleneck(seq_trace)
    par_bn = analyze_bottleneck(par_trace)
    seq_cy = analyze_cost_yield(seq_trace)
    par_cy = analyze_cost_yield(par_trace)
    seq_score = score_trace(seq_trace)
    par_score = score_trace(par_trace)

    print("=" * 60)
    print("PERFORMANCE COMPARISON: Sequential vs Parallel")
    print("=" * 60)
    _print_pipeline("SEQUENTIAL", seq_trace, seq_bn, seq_cy, seq_score)
    _print_pipeline("PARALLEL", par_trace, par_bn, par_cy, par_score)
    _print_speedup(seq_trace, par_trace)
    print("=" * 60)


def _print_pipeline(label, trace, bn, cy, score):
    """Print analysis summary for one pipeline variant."""
    dur = trace.agent_spans[0].duration_ms if trace.agent_spans else (trace.duration_ms or 0)
    cost = sum(s.estimated_cost_usd or 0 for s in trace.spans)
    print(f"\n📊 {label}")
    print(f"   Duration: {dur:,.0f}ms")
    print(f"   Cost: ${cost:.3f}")
    print(f"   Score: {score.overall:.0f}/100 ({score.grade})")
    print(f"   Bottleneck: {bn.bottleneck_span}")
    if cy.most_wasteful_agent:
        print(f"   Most wasteful: {cy.most_wasteful_agent}")
    else:
        print("   No waste detected")


def _print_speedup(seq, par):
    """Print the speedup factor between sequential and parallel."""
    seq_dur = seq.agent_spans[0].duration_ms if seq.agent_spans else (seq.duration_ms or 1)
    par_dur = par.agent_spans[0].duration_ms if par.agent_spans else (par.duration_ms or 1)
    speedup = seq_dur / par_dur
    print(f"\n⚡ Speedup: {speedup:.1f}x faster with parallel execution")
    print(f"   Sequential: {seq_dur:,.0f}ms → Parallel: {par_dur:,.0f}ms")
    print(f"   Same cost, {speedup:.1f}x better throughput")


if __name__ == "__main__":
    compare_pipelines()
