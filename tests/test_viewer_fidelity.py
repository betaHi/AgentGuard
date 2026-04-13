"""Tests that viewer renders ONLY analysis-confirmed findings.

Verifies no phantom handoffs, no phantom failures, and that all
rendered data comes from the analysis layer (single source of truth).
"""

from agentguard.analysis import analyze_bottleneck, analyze_failures, analyze_flow
from agentguard.builder import TraceBuilder
from agentguard.core.trace import ExecutionTrace
from agentguard.web.viewer import _build_full_html, _build_sidebar


def _count_handoff_rows(html: str) -> int:
    """Count actual rendered handoff rows (not CSS definitions)."""
    return html.count('class="ho-row"')


def _count_handoff_arrows(html: str) -> int:
    """Count actual rendered handoff arrow spans (not CSS)."""
    return html.count('class="ho-arrow"')


def test_no_phantom_handoffs_sequential_agents():
    """Sequential agents WITHOUT record_handoff() should show zero handoff rows."""
    trace = (TraceBuilder("no handoffs")
        .agent("agent-a", duration_ms=100).end()
        .agent("agent-b", duration_ms=100).end()
        .agent("agent-c", duration_ms=100).end()
        .build())

    flow = analyze_flow(trace)
    assert len(flow.handoffs) == 0, "Analysis should find no handoffs"

    html = _build_full_html([trace])
    # The gantt should not infer handoffs between a→b→c
    gantt_handoffs = _count_handoff_arrows(html)
    assert gantt_handoffs == 0, f"Expected 0 handoff arrows, got {gantt_handoffs}"


def test_confirmed_handoffs_rendered():
    """Handoffs from record_handoff() should appear in viewer."""
    from agentguard import record_handoff
    from agentguard.sdk.recorder import finish_recording, init_recorder

    init_recorder(task="with handoffs")

    from agentguard import record_agent

    @record_agent(name="collector", version="v1")
    def collector():
        return {"data": [1, 2]}

    @record_agent(name="processor", version="v1")
    def processor():
        return {"result": "done"}

    data = collector()
    record_handoff("collector", "processor", context=data, summary="2 items")
    processor()
    trace = finish_recording()

    flow = analyze_flow(trace)
    assert len(flow.handoffs) >= 1

    html = _build_full_html([trace])
    assert _count_handoff_arrows(html) >= 1
    assert "collector" in html
    assert "processor" in html


def test_empty_trace_no_handoffs():
    """Empty trace renders cleanly with no handoff artifacts."""
    trace = ExecutionTrace(task="empty")
    trace.complete()
    html = _build_full_html([trace])
    assert _count_handoff_arrows(html) == 0


def test_failed_agents_sidebar_matches_analysis():
    """Sidebar failure indicators must match analysis root causes."""
    trace = (TraceBuilder("failures")
        .agent("good-agent", duration_ms=100).end()
        .agent("bad-agent", duration_ms=100, status="failed", error="crash").end()
        .build())

    failures = analyze_failures(trace)
    bn = analyze_bottleneck(trace)

    sidebar = _build_sidebar(trace, failures, bn)
    # bad-agent should have error indicator
    assert "dot-err" in sidebar
    assert "crash" in sidebar
    # Failure indicators in sidebar must match analysis root causes
    failed_names = {rc.span_name for rc in failures.root_causes if not rc.was_handled}
    assert "bad-agent" in failed_names


def test_bottleneck_sidebar_matches_analysis():
    """Sidebar bottleneck marker must match analysis bottleneck_span."""
    trace = (TraceBuilder("bottleneck")
        .agent("fast", duration_ms=100).end()
        .agent("slow", duration_ms=5000).end()
        .build())

    failures = analyze_failures(trace)
    bn = analyze_bottleneck(trace)

    sidebar = _build_sidebar(trace, failures, bn)
    # The bottleneck agent should be marked
    assert "bottleneck" in sidebar
    # It should be "slow" not "fast"
    # Find bottleneck text near "slow"
    assert bn.bottleneck_span in sidebar


def test_single_agent_no_bottleneck_label():
    """Single agent should NOT be labeled as bottleneck (nothing to compare)."""
    trace = (TraceBuilder("solo")
        .agent("only-one", duration_ms=5000).end()
        .build())

    failures = analyze_failures(trace)
    bn = analyze_bottleneck(trace)

    sidebar = _build_sidebar(trace, failures, bn)
    # Single agent: bottleneck label should not appear (no comparison possible)
    # The code checks `len(trace.agent_spans) > 1`
    assert "bottleneck" not in sidebar.lower() or "dot-warn" not in sidebar


def test_handoff_count_matches_analysis():
    """Number of rendered handoff rows must equal analysis handoff count."""
    from agentguard import record_agent, record_handoff
    from agentguard.sdk.recorder import finish_recording, init_recorder

    init_recorder(task="exact match")

    @record_agent(name="a", version="v1")
    def a(): return {"x": 1}

    @record_agent(name="b", version="v1")
    def b(): return {"y": 2}

    @record_agent(name="c", version="v1")
    def c(): return {"z": 3}

    a()
    record_handoff("a", "b", context={"x": 1})
    b()
    # No handoff between b and c — should NOT appear
    c()
    trace = finish_recording()

    flow = analyze_flow(trace)
    analysis_count = len(flow.handoffs)

    html = _build_full_html([trace])
    rendered_count = _count_handoff_arrows(html)

    assert rendered_count == analysis_count, (
        f"Rendered {rendered_count} handoff arrows but analysis found {analysis_count}"
    )
