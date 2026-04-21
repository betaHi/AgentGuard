"""Tests for dense terminal diagnostics rendering."""

from __future__ import annotations

from agentguard.builder import TraceBuilder
from agentguard.terminal_diagnostics import render_dense_diagnostics


def test_render_dense_diagnostics_includes_artifacts_and_sections() -> None:
    """Dense diagnostics should expose the terminal-first sections and artifacts."""
    trace = (
        TraceBuilder("dense diagnostics")
        .agent("coordinator", duration_ms=4000)
            .agent(
                "generator",
                duration_ms=1500,
                token_count=1200,
                cost_usd=0.05,
                output_data={
                    "claims": ["c1", "c2", "c3"],
                    "citations": ["doc-1", "doc-2"],
                    "unverified_claims": ["c3"],
                },
            )
            .end()
            .agent(
                "reviewer",
                duration_ms=1800,
                status="failed",
                error="timeout",
                input_data={"notes": "kept"},
            )
            .end()
        .end()
        .build()
    )

    text = render_dense_diagnostics(
        trace,
        trace_path="/tmp/trace.json",
        html_report="/tmp/report.html",
    )

    assert "AGENTGUARD DIAGNOSE" in text
    assert "[failures]" in text
    assert "[context]" in text
    assert "[cost-yield]" in text
    assert "[decisions]" in text
    assert "trace=/tmp/trace.json" in text
    assert "html=/tmp/report.html" in text
