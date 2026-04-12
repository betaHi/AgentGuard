"""Tests for benchmark harness."""

import pytest
from agentguard.benchmark import run_benchmark


class TestBenchmark:
    def test_basic(self):
        suite = run_benchmark(trace_count=3, agents_per_trace=3, seed=42)
        assert suite.trace_count == 3
        assert len(suite.results) >= 10  # at least 10 modules benchmarked

    def test_all_modules_run(self):
        suite = run_benchmark(trace_count=2, agents_per_trace=2, seed=42)
        names = {r.name for r in suite.results}
        assert "scoring" in names
        assert "metrics" in names
        assert "timeline" in names

    def test_report(self):
        suite = run_benchmark(trace_count=2, seed=42)
        report = suite.to_report()
        assert "Benchmark" in report
        assert "Module" in report

    def test_to_dict(self):
        suite = run_benchmark(trace_count=2, seed=42)
        d = suite.to_dict()
        assert "results" in d
        assert "total_ms" in d
