"""Tests for HTML viewer diagnostics panel completeness."""

from agentguard.builder import TraceBuilder
from agentguard.analysis import analyze_decisions
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.web.viewer import trace_to_html_string


def _sample_trace():
    return (TraceBuilder("viewer")
        .agent("coordinator", duration_ms=5000)
            .agent("researcher", duration_ms=3000)
                .tool("search", duration_ms=2000)
            .end()
            .agent("writer", duration_ms=1000).end()
        .end()
        .build())


class TestViewerPanels:
    def test_all_panels_present(self, tmp_path, monkeypatch):
        """All analysis panels render in HTML output."""
        from agentguard.evolve import EvolutionEngine

        monkeypatch.chdir(tmp_path)
        engine = EvolutionEngine()
        engine.learn(_sample_trace())
        html = trace_to_html_string(_sample_trace())
        panels = [
            "Failure Propagation", "Bottleneck", "Handoff Flow",
            "Critical Path", "Cost", "Retries", "Error Classification",
            "Evolution Insights", "Workflow Patterns",
            "Cost-Yield", "Orchestration Decisions",
        ]
        for panel in panels:
            assert panel in html, f"Panel '{panel}' missing from HTML"

    def test_evolution_panel_shows_learned_state(self, tmp_path, monkeypatch):
        from agentguard.evolve import EvolutionEngine

        monkeypatch.chdir(tmp_path)
        engine = EvolutionEngine()
        trace = (TraceBuilder("viewer evolution")
            .agent("coordinator", duration_ms=5000)
                .agent("reviewer", duration_ms=3200).end()
                .agent("notifier", duration_ms=300, status="failed", error="webhook timeout").end()
            .end()
            .build())
        for _ in range(3):
            engine.learn(trace)

        html = trace_to_html_string(trace)
        assert "Evolution Insights" in html
        assert "traces learned" in html
        assert "lessons" in html
        assert "No learned suggestions yet" not in html

    def test_cost_yield_panel_content(self):
        html = trace_to_html_string(_sample_trace())
        assert "waste" in html.lower() or "No waste" in html

    def test_decisions_panel_content(self):
        html = trace_to_html_string(_sample_trace())
        assert "quality" in html.lower() or "No decisions" in html

    def test_decisions_panel_shows_degradation_signals_and_suggestions(self):
        trace = ExecutionTrace(task="viewer decision impact")
        router = Span(name="router", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        decision = Span(
            name="router → buggy-agent (decision)",
            span_type=SpanType.HANDOFF,
            parent_span_id=router.span_id,
            status=SpanStatus.COMPLETED,
            metadata={
                "decision.type": "orchestration",
                "decision.coordinator": "router",
                "decision.chosen": "buggy-agent",
                "decision.alternatives": ["stable-agent"],
                "decision.rationale": "Tried the newest worker",
            },
        )
        buggy = Span(
            name="buggy-agent",
            span_type=SpanType.AGENT,
            parent_span_id=router.span_id,
            status=SpanStatus.FAILED,
            error="crash",
        )
        stable = Span(
            name="stable-agent",
            span_type=SpanType.AGENT,
            parent_span_id=router.span_id,
            status=SpanStatus.COMPLETED,
        )
        for span in [router, decision, buggy, stable]:
            trace.add_span(span)
        trace.complete()

        decisions = analyze_decisions(trace)
        assert decisions.suggestions

        html = trace_to_html_string(trace)
        assert "showed degradation" in html
        assert "Failure propagated to buggy-agent" in html
        assert "Try stable-agent instead of buggy-agent" in html

    def test_propagation_panel_content(self):
        html = trace_to_html_string(_sample_trace())
        assert "containment" in html.lower() or "No propagation" in html

    def test_handoff_panel_shows_ranked_context_risk(self):
        trace = ExecutionTrace(task="viewer context risk")
        parent = Span(name="coordinator", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        sender = Span(
            name="sender",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            output_data={"query": "refund", "priority": "high", "notes": "keep"},
        )
        receiver = Span(
            name="receiver",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.FAILED,
            error="missing query",
            input_data={"notes": "keep"},
        )
        for span in [parent, sender, receiver]:
            trace.add_span(span)
        trace.complete()

        html = trace_to_html_string(trace)
        assert "risk" in html.lower()
        assert "downstream" in html.lower()
        assert "sender" in html and "receiver" in html

    def test_handoff_panel_shows_evidence_reference_loss(self):
        trace = ExecutionTrace(task="viewer evidence refs")
        parent = Span(name="coordinator", span_type=SpanType.AGENT, status=SpanStatus.COMPLETED)
        sender = Span(
            name="reranker",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            output_data={
                "top_documents": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}, {"doc_id": "doc-3"}],
                "source_map": {"doc-1": "u1", "doc-2": "u2", "doc-3": "u3"},
            },
        )
        receiver = Span(
            name="generator",
            span_type=SpanType.AGENT,
            parent_span_id=parent.span_id,
            status=SpanStatus.COMPLETED,
            input_data={
                "top_documents": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}],
                "source_map": {"doc-1": "u1", "doc-2": "u2"},
            },
        )
        for span in [parent, sender, receiver]:
            trace.add_span(span)
        trace.complete()

        html = trace_to_html_string(trace)
        assert "evidence refs" in html.lower()
        assert "doc-3" in html

    def test_cost_yield_panel_shows_grounding_breakdown(self):
        trace = (TraceBuilder("viewer grounding")
            .agent("coordinator", duration_ms=3000)
                .agent(
                    "generator",
                    duration_ms=1200,
                    token_count=1200,
                    cost_usd=0.05,
                    output_data={
                        "claims": ["c1", "c2", "c3"],
                        "citations": ["doc-1", "doc-2"],
                        "unverified_claims": ["c3"],
                    },
                )
                .end()
            .end()
            .build())
        html = trace_to_html_string(trace)
        assert "grounding" in html.lower()
        assert "citations" in html.lower()

    def test_empty_trace_no_crash(self):
        """Empty trace produces valid HTML."""
        from agentguard.core.trace import ExecutionTrace
        trace = ExecutionTrace(task="empty")
        trace.complete()
        html = trace_to_html_string(trace)
        assert "<!DOCTYPE html>" in html

    def test_html_is_valid_string(self):
        html = trace_to_html_string(_sample_trace())
        assert isinstance(html, str)
        assert len(html) > 1000

    def test_viewer_assets_do_not_emit_escaped_template_braces(self):
        html = trace_to_html_string(_sample_trace())
        assert ":root{{" not in html
        assert "body{{" not in html
        assert "function(row){{" not in html

    def test_evolution_panel_degrades_on_corrupt_knowledge(self, tmp_path, monkeypatch):
        knowledge_dir = tmp_path / ".agentguard" / "knowledge"
        knowledge_dir.mkdir(parents=True)
        (knowledge_dir / "knowledge.json").write_text("{broken", encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        html = trace_to_html_string(_sample_trace())
        assert "Evolution Insights" in html
        assert "Unavailable" in html
        assert "Recovered corrupt knowledge base" in html


class TestTraceMetadataHeader:
    def test_task_name_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "viewer" in html  # task name

    def test_agent_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "agents" in html

    def test_span_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "spans" in html

    def test_duration_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "total" in html

    def test_failed_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "failed" in html

    def test_tools_count_shown(self):
        html = trace_to_html_string(_sample_trace())
        assert "tools" in html


class TestCollapsiblePanels:
    def test_panels_use_details_element(self):
        html = trace_to_html_string(_sample_trace())
        assert html.count('<details') >= 10

    def test_panels_have_summary(self):
        html = trace_to_html_string(_sample_trace())
        assert html.count('<summary') >= 10

    def test_panels_open_by_default(self):
        html = trace_to_html_string(_sample_trace())
        assert "d-box" in html and "open" in html

    def test_panels_have_body(self):
        html = trace_to_html_string(_sample_trace())
        assert html.count('d-body') >= 10


class TestSearchFilter:
    def test_search_input_present(self):
        html = trace_to_html_string(_sample_trace())
        assert 'span-search' in html

    def test_status_filter_present(self):
        html = trace_to_html_string(_sample_trace())
        assert 'status-filter' in html

    def test_duration_filters_present(self):
        html = trace_to_html_string(_sample_trace())
        assert 'min-dur' in html
        assert 'max-dur' in html

    def test_filter_js_present(self):
        html = trace_to_html_string(_sample_trace())
        assert 'filterSpans' in html

    def test_filter_count_present(self):
        html = trace_to_html_string(_sample_trace())
        assert 'filter-count' in html
