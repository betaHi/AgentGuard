"""Tests for user-overridable model pricing."""

from __future__ import annotations

import json
from pathlib import Path

from agentguard.runtime.claude.session_import import (
    _estimate_cost_usd,
    _pricing_for,
)


def test_env_pricing_file_overrides_builtin_rates(monkeypatch, tmp_path):
    """Users must be able to add new model ids without patching the code."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps({
        "gpt-5.4": {
            "input": 2.50,
            "output": 20.0,
            "cache_read": 0.25,
            "cache_creation": 2.50,
        }
    }), encoding="utf-8")
    monkeypatch.setenv("AGENTGUARD_PRICING_FILE", str(pricing_file))

    rates, is_known = _pricing_for("gpt-5.4")

    assert is_known, "override should mark the model as known"
    assert rates["input"] == 2.50
    assert rates["output"] == 20.0

    cost, used_fallback = _estimate_cost_usd(
        model="gpt-5.4",
        input_tokens=1_000_000,
        output_tokens=100_000,
        cache_read=0,
        cache_creation=0,
    )
    # 1M input @ $2.50 + 100K output @ $20.0/M = 2.50 + 2.0 = 4.50
    assert cost == 4.50
    assert not used_fallback


def test_override_takes_precedence_over_builtin(monkeypatch, tmp_path):
    """Override entries are checked before the built-in table."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps({
        # Override Opus with a cheaper custom contract rate.
        "opus": {"input": 1.0, "output": 5.0, "cache_read": 0.10, "cache_creation": 1.0},
    }), encoding="utf-8")
    monkeypatch.setenv("AGENTGUARD_PRICING_FILE", str(pricing_file))

    rates, is_known = _pricing_for("claude-opus-4.7")

    assert is_known
    assert rates["input"] == 1.0  # override wins over built-in $15


def test_malformed_pricing_file_is_ignored(monkeypatch, tmp_path):
    """A malformed override must not break importing — fall back to built-ins."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setenv("AGENTGUARD_PRICING_FILE", str(pricing_file))

    rates, is_known = _pricing_for("claude-opus-4.7")

    # Built-in Opus rates still apply.
    assert is_known
    assert rates["input"] == 15.0


def test_entries_with_missing_keys_are_skipped(monkeypatch, tmp_path):
    """Entries missing any required rate key must be skipped, not crash."""
    pricing_file = tmp_path / "pricing.json"
    pricing_file.write_text(json.dumps({
        "broken-model": {"input": 1.0},  # missing output, cache_read, cache_creation
        "good-model": {
            "input": 2.0, "output": 5.0, "cache_read": 0.2, "cache_creation": 2.0,
        },
    }), encoding="utf-8")
    monkeypatch.setenv("AGENTGUARD_PRICING_FILE", str(pricing_file))

    _, broken_known = _pricing_for("broken-model")
    good_rates, good_known = _pricing_for("good-model")

    assert not broken_known
    assert good_known
    assert good_rates["output"] == 5.0
