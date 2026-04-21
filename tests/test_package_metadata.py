"""Tests for package metadata and top-level package direction."""

from __future__ import annotations

import tomllib
from pathlib import Path

import agentguard


def test_pyproject_description_matches_diagnostics_direction() -> None:
    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))

    assert data["project"]["description"] == "Diagnostics for multi-agent orchestration."
    assert "diagnostics" in data["project"]["keywords"]
    assert "orchestration" in data["project"]["keywords"]


def test_top_level_package_docstring_mentions_diagnostics() -> None:
    assert agentguard.__doc__ is not None
    assert "diagnostics for multi-agent orchestration" in agentguard.__doc__.lower()
    assert "claude live runtime capture" in agentguard.__doc__.lower()