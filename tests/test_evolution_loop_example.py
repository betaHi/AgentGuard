"""Semantic tests for the evolution loop example."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_example_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "evolution_loop.py"
    spec = importlib.util.spec_from_file_location("evolution_loop", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_evolution_loop_accumulates_knowledge(tmp_path):
    module = _load_example_module()
    result = module.run_evolution_demo(str(tmp_path / "kb"))

    assert result["trace_count"] == 3
    assert result["suggestion_count"] >= 1
    assert result["trend_count"] >= 1


def test_evolution_loop_reports_recurring_failure(tmp_path):
    module = _load_example_module()
    result = module.run_evolution_demo(str(tmp_path / "kb"))

    assert "retry" in result["top_suggestion"].lower() or "fallback" in result["top_suggestion"].lower()
    assert result["top_trend"] in {"recurring_failure", "persistent_bottleneck"}
    assert "Improvement PRD" in result["prd"]