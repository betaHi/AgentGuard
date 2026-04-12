"""Benchmark harness — run analysis modules at scale with timing.

Measures performance of all analysis modules on synthetic traces
to identify bottlenecks and ensure scalability.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from agentguard.core.trace import ExecutionTrace
from agentguard.generate import generate_trace, generate_batch


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""
    name: str
    iterations: int
    total_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "iterations": self.iterations,
            "total_ms": round(self.total_ms, 1),
            "avg_ms": round(self.avg_ms, 2),
            "min_ms": round(self.min_ms, 2),
            "max_ms": round(self.max_ms, 2),
        }


@dataclass
class BenchmarkSuite:
    """Results of a benchmark suite."""
    results: list[BenchmarkResult]
    trace_count: int
    total_ms: float
    
    def to_dict(self) -> dict:
        return {
            "trace_count": self.trace_count,
            "total_ms": round(self.total_ms, 1),
            "results": [r.to_dict() for r in self.results],
        }
    
    def to_report(self) -> str:
        lines = [
            "# Benchmark Results",
            "",
            f"Traces: {self.trace_count} | Total: {self.total_ms:.0f}ms",
            "",
            f"| {'Module':<30} | {'Avg (ms)':>10} | {'Min (ms)':>10} | {'Max (ms)':>10} |",
            f"|{'-'*30}--|{'-'*10}--|{'-'*10}--|{'-'*10}--|",
        ]
        for r in sorted(self.results, key=lambda r: -r.avg_ms):
            lines.append(f"| {r.name:<30} | {r.avg_ms:>10.2f} | {r.min_ms:>10.2f} | {r.max_ms:>10.2f} |")
        return "\n".join(lines)


def _bench(name: str, fn: Callable, traces: list[ExecutionTrace]) -> BenchmarkResult:
    """Run a function on each trace and measure timing."""
    times = []
    for trace in traces:
        start = time.perf_counter()
        try:
            fn(trace)
        except Exception:
            pass
        elapsed = (time.perf_counter() - start) * 1000
        times.append(elapsed)
    
    return BenchmarkResult(
        name=name,
        iterations=len(traces),
        total_ms=sum(times),
        avg_ms=sum(times) / max(len(times), 1),
        min_ms=min(times) if times else 0,
        max_ms=max(times) if times else 0,
    )


def run_benchmark(
    trace_count: int = 10,
    agents_per_trace: int = 5,
    seed: int = 42,
) -> BenchmarkSuite:
    """Run the full benchmark suite.
    
    Generates synthetic traces and benchmarks all analysis modules.
    """
    traces = generate_batch(count=trace_count, agents=agents_per_trace, seed=seed)
    
    start = time.perf_counter()
    results = []
    
    # Import all modules to benchmark
    from agentguard.scoring import score_trace
    from agentguard.metrics import extract_metrics
    from agentguard.timeline import build_timeline
    from agentguard.flowgraph import build_flow_graph
    from agentguard.propagation import analyze_propagation
    from agentguard.context_flow import analyze_context_flow_deep
    from agentguard.correlation import analyze_correlations
    from agentguard.annotations import auto_annotate
    from agentguard.tree import compute_tree_stats
    from agentguard.normalize import normalize_trace
    from agentguard.summarize import summarize_trace
    from agentguard.schema import validate_trace_dict
    from agentguard.dependency import build_dependency_graph
    
    benchmarks = [
        ("scoring", score_trace),
        ("metrics", extract_metrics),
        ("timeline", build_timeline),
        ("flow_graph", build_flow_graph),
        ("propagation", analyze_propagation),
        ("context_flow", analyze_context_flow_deep),
        ("correlations", analyze_correlations),
        ("auto_annotate", auto_annotate),
        ("tree_stats", compute_tree_stats),
        ("normalize", lambda t: normalize_trace(t)),
        ("summarize", summarize_trace),
        ("schema_validate", lambda t: validate_trace_dict(t.to_dict())),
        ("dependency_graph", build_dependency_graph),
    ]
    
    for name, fn in benchmarks:
        results.append(_bench(name, fn, traces))
    
    total_ms = (time.perf_counter() - start) * 1000
    
    return BenchmarkSuite(
        results=results,
        trace_count=trace_count,
        total_ms=total_ms,
    )
