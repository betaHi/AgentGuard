"""Pricing freshness banner contract."""

from __future__ import annotations

import re
from datetime import date

from agentguard.builder import TraceBuilder
from agentguard.runtime.claude.session_import import _BUILTIN_PRICING_DATE
from agentguard.web.viewer import (
    _pricing_freshness_banner,
    _render_cost_yield_panel,
)
from agentguard.analysis import analyze_cost_yield


def test_pricing_date_constant_is_iso_and_plausible():
    """The constant must parse and be not-from-the-future."""
    parsed = date.fromisoformat(_BUILTIN_PRICING_DATE)
    assert parsed <= date.today(), "_BUILTIN_PRICING_DATE is in the future"


def test_banner_renders_date_and_override_hint():
    html = _pricing_freshness_banner()
    assert _BUILTIN_PRICING_DATE in html
    assert "AGENTGUARD_PRICING_FILE" in html


def test_cost_yield_panel_includes_banner():
    """The pricing banner must appear on any cost-yield panel we render."""
    trace = (
        TraceBuilder("pricing-banner")
        .agent("root", duration_ms=1000, token_count=100, cost_usd=0.05,
               output_data={"ok": True})
        .end()
        .build()
    )
    cy = analyze_cost_yield(trace)
    html = _render_cost_yield_panel(cy, trace)
    # The banner should be present when there IS a cost-yield report.
    assert _BUILTIN_PRICING_DATE in html, (
        "pricing freshness banner must be rendered in the cost-yield panel"
    )


def test_banner_date_format_is_yyyy_mm_dd():
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", _BUILTIN_PRICING_DATE)
