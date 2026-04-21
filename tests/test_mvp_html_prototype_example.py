"""Semantic tests for the MVP HTML prototype example."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_example_module():
    path = Path(__file__).resolve().parents[1] / "examples" / "mvp_html_prototype.py"
    spec = importlib.util.spec_from_file_location("mvp_html_prototype", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_mvp_prototype_generates_html(tmp_path, monkeypatch):
    module = _load_example_module()
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "prototype.html"

    path = module.generate_mvp_prototype(str(output))
    html = output.read_text(encoding="utf-8")

    assert path == str(output)
    assert output.exists()
    assert "Orchestration Diagnostics" in html
    assert "Evolution Insights" in html
    assert "Workflow Patterns" in html
    assert "Orchestration Decisions" in html


def test_mvp_prototype_trace_has_mvp_signals():
    module = _load_example_module()
    trace = module.build_mvp_prototype_trace()

    names = {span.name for span in trace.spans}
    assert "briefing-coordinator → reviewer-v2 (decision)" in names
    assert "reviewer-v2 → writer" in names
    assert "stable-reviewer" in names
    assert "notifier" in names