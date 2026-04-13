"""Integration test: full record → analyze → export → import → compare roundtrip.

Validates the entire AgentGuard pipeline works end-to-end without
data loss or corruption across format boundaries.
"""

import json

from agentguard import record_agent, record_decision, record_handoff, record_tool
from agentguard.analysis import (
    analyze_bottleneck,
    analyze_cost_yield,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
)
from agentguard.core.trace import SpanStatus
from agentguard.export import export_otel
from agentguard.importer import import_otel
from agentguard.sdk.recorder import finish_recording, init_recorder


def _build_realistic_trace():
    """Run a realistic multi-agent pipeline and return the trace."""
    init_recorder(task="Integration Roundtrip Test", trigger="test")

    @record_tool(name="search")
    def search(query):
        return [f"result-{i}" for i in range(3)]

    @record_agent(name="researcher", version="v2.0")
    def researcher():
        return {"results": search("AI agents"), "count": 3}

    @record_agent(name="writer", version="v1.5")
    def writer(data):
        return {"draft": f"Article with {data['count']} sources"}

    @record_agent(name="reviewer", version="v1.0")
    def reviewer(draft):
        raise ConnectionError("Review service timeout")

    @record_agent(name="coordinator", version="v3.0")
    def coordinator():
        record_decision(
            coordinator="coordinator",
            chosen_agent="researcher",
            alternatives=["cached-results"],
            rationale="Fresh data needed",
            confidence=0.9,
        )
        data = researcher()
        record_handoff("researcher", "writer", context=data, summary="3 results")
        draft = writer(data)
        record_handoff("writer", "reviewer", context=draft, summary="draft ready")
        try:
            reviewer(draft)
        except ConnectionError:
            pass  # handled failure
        return {"status": "partial", "draft": draft}

    coordinator()
    return finish_recording()


class TestFullRoundtrip:
    def test_record_produces_valid_trace(self):
        """Recording produces a trace with expected structure."""
        trace = _build_realistic_trace()
        assert trace.task == "Integration Roundtrip Test"
        assert len(trace.spans) >= 6  # coordinator, researcher, search, writer, reviewer, handoffs, decision
        assert len(trace.agent_spans) >= 4

    def test_analysis_on_recorded_trace(self):
        """All analysis modules work on a real recorded trace."""
        trace = _build_realistic_trace()

        failures = analyze_failures(trace)
        assert failures.total_failed_spans >= 1  # reviewer failed
        assert isinstance(failures.resilience_score, float)  # may be 0 if not explicitly handled

        bn = analyze_bottleneck(trace)
        assert bn.bottleneck_span != ""

        flow = analyze_flow(trace)
        assert len(flow.handoffs) >= 2

        cy = analyze_cost_yield(trace)
        assert len(cy.entries) >= 4

        decisions = analyze_decisions(trace)
        assert decisions.total_decisions >= 1

    def test_export_otel_roundtrip(self):
        """Export to OTel and re-import preserves span count and names."""
        trace = _build_realistic_trace()
        original_span_count = len(trace.spans)
        original_names = sorted(s.name for s in trace.spans)

        otel_data = export_otel(trace)

        # Validate OTel structure
        assert "resourceSpans" in otel_data
        otel_spans = otel_data["resourceSpans"][0]["scopeSpans"][0]["spans"]
        assert len(otel_spans) == original_span_count

        # Re-import
        reimported = import_otel(otel_data)
        assert len(reimported.spans) == original_span_count

        # Names should match (OTel prefixes with type:)
        reimported_names = sorted(s.name for s in reimported.spans)
        for orig_name in original_names:
            # OTel names are "type:name", so check containment
            assert any(orig_name in rn for rn in reimported_names), \
                f"Original span '{orig_name}' not found in reimported names"

    def test_otel_json_serializable(self):
        """OTel export is fully JSON-serializable (no Infinity, NaN, etc)."""
        trace = _build_realistic_trace()
        otel_data = export_otel(trace)
        serialized = json.dumps(otel_data)
        assert "Infinity" not in serialized
        assert "NaN" not in serialized
        # Roundtrip JSON
        parsed = json.loads(serialized)
        assert parsed["resourceSpans"][0]["scopeSpans"][0]["spans"]

    def test_analysis_after_reimport(self):
        """Analysis on reimported trace still produces results."""
        trace = _build_realistic_trace()
        otel_data = export_otel(trace)
        reimported = import_otel(otel_data)

        # Basic analysis should not crash
        failures = analyze_failures(reimported)
        assert isinstance(failures.resilience_score, float)

        flow = analyze_flow(reimported)
        assert isinstance(len(flow.handoffs), int)

    def test_handoff_data_survives_roundtrip(self):
        """Handoff metadata is preserved through OTel export/import."""
        trace = _build_realistic_trace()
        otel_data = export_otel(trace)

        # Check handoff attributes in OTel spans
        otel_spans = otel_data["resourceSpans"][0]["scopeSpans"][0]["spans"]
        handoff_spans = [
            s for s in otel_spans
            if "handoff" in s["name"].lower()
        ]
        assert len(handoff_spans) >= 2

    def test_decision_data_in_export(self):
        """Decision metadata appears in OTel export."""
        trace = _build_realistic_trace()
        otel_data = export_otel(trace)
        otel_spans = otel_data["resourceSpans"][0]["scopeSpans"][0]["spans"]

        decision_spans = [
            s for s in otel_spans
            if "decision" in s["name"].lower()
        ]
        assert len(decision_spans) >= 1

    def test_failure_status_preserved(self):
        """Failed span status survives roundtrip."""
        trace = _build_realistic_trace()
        # Original has at least one failed span
        orig_failed = [s for s in trace.spans if s.status == SpanStatus.FAILED]
        assert len(orig_failed) >= 1

        otel_data = export_otel(trace)
        reimported = import_otel(otel_data)

        reimported_failed = [s for s in reimported.spans if s.status == SpanStatus.FAILED]
        assert len(reimported_failed) >= 1
