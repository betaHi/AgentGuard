"""Tests for CLI analyze --json structured output."""

import json

from agentguard.builder import TraceBuilder
from agentguard.cli.main import _build_analysis_dict, _build_trace_metadata


def _sample_trace():
    return (TraceBuilder("cli test")
        .agent("researcher", duration_ms=3000)
            .tool("search", duration_ms=2000)
        .end()
        .agent("writer", duration_ms=1000).end()
        .build())


class TestAnalyzeJson:
    def test_all_sections_present(self):
        """JSON output includes all analysis sections."""
        result = _build_analysis_dict(_sample_trace())
        required = ["trace", "score", "failures", "flow", "bottleneck",
                     "context_flow", "cost_yield", "decisions", "counterfactual", "workflow_patterns", "propagation"]
        for key in required:
            assert key in result, f"Missing section: {key}"

    def test_trace_metadata(self):
        result = _build_analysis_dict(_sample_trace())
        meta = result["trace"]
        assert meta["task"] == "cli test"
        assert meta["agent_count"] == 2
        assert meta["span_count"] >= 3
        assert "tool_count" in meta
        assert "failed_count" in meta

    def test_json_serializable(self):
        """Full output is JSON-serializable."""
        result = _build_analysis_dict(_sample_trace())
        serialized = json.dumps(result, default=str)
        parsed = json.loads(serialized)
        assert "trace" in parsed

    def test_score_present(self):
        result = _build_analysis_dict(_sample_trace())
        assert "overall" in result["score"]
        assert "grade" in result["score"]

    def test_build_trace_metadata_counts(self):
        trace = _sample_trace()
        meta = _build_trace_metadata(trace)
        assert meta["agent_count"] == 2
        assert meta["tool_count"] == 1
        assert meta["handoff_count"] == 0

    def test_matches_viewer_sections(self):
        """JSON sections match what the HTML viewer renders."""
        result = _build_analysis_dict(_sample_trace())
        # CLI structured analysis includes the viewer sections plus counterfactual.
        viewer_sections = ["failures", "bottleneck", "flow",
                           "context_flow", "cost_yield", "decisions",
                           "counterfactual",
                           "workflow_patterns",
                           "propagation"]
        for section in viewer_sections:
            assert section in result

    def test_context_flow_includes_semantic_criticality(self):
        trace = (TraceBuilder("cli context")
            .agent("coordinator", duration_ms=3000)
                .agent("sender", duration_ms=1000, output_data={"query": "refund", "notes": "n", "priority": "high"})
                .end()
                .agent("receiver", duration_ms=1000, input_data={"notes": "n"})
                .end()
            .end()
            .build())
        result = _build_analysis_dict(trace)
        point = result["context_flow"]["points"][0]
        assert set(point["critical_keys_lost"]) == {"query", "priority"}
        assert point["semantic_retention_score"] is not None

    def test_context_flow_includes_downstream_impact(self):
        trace = (TraceBuilder("cli context impact")
            .agent("coordinator", duration_ms=3000)
                .agent("sender", duration_ms=1000, output_data={"query": "refund", "notes": "n", "priority": "high"})
                .end()
                .agent("receiver", duration_ms=1000, status="failed", error="missing query", input_data={"notes": "n"})
                .end()
            .end()
            .build())
        result = _build_analysis_dict(trace)
        point = result["context_flow"]["points"][0]
        assert point["downstream_impact_score"] is not None
        assert "downstream failure" in point["downstream_impact_reason"]

    def test_context_flow_includes_risk_fields(self):
        trace = (TraceBuilder("cli context risk")
            .agent("coordinator", duration_ms=3000)
                .agent("sender", duration_ms=1000, output_data={"query": "refund", "notes": "n", "priority": "high"})
                .end()
                .agent("receiver", duration_ms=1000, status="failed", error="missing query", input_data={"notes": "n"})
                .end()
            .end()
            .build())
        result = _build_analysis_dict(trace)
        point = result["context_flow"]["points"][0]
        assert point["risk_score"] is not None
        assert point["risk_label"] in {"high", "severe"}

    def test_context_flow_includes_reference_loss_fields(self):
        trace = (TraceBuilder("cli reference loss")
            .agent("coordinator", duration_ms=3000)
                .agent(
                    "sender",
                    duration_ms=1000,
                    output_data={
                        "top_documents": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}, {"doc_id": "doc-3"}],
                        "source_map": {"doc-1": "u1", "doc-2": "u2", "doc-3": "u3"},
                    },
                )
                .end()
                .agent(
                    "receiver",
                    duration_ms=1000,
                    input_data={
                        "top_documents": [{"doc_id": "doc-1"}, {"doc_id": "doc-2"}],
                        "source_map": {"doc-1": "u1", "doc-2": "u2"},
                    },
                )
                .end()
            .end()
            .build())
        result = _build_analysis_dict(trace)
        point = result["context_flow"]["points"][0]
        assert point["reference_ids_lost"] == ["doc-3"]
        assert point["reference_ids_sent"]

    def test_cost_yield_includes_grounding_breakdown(self):
        trace = (TraceBuilder("cli grounding breakdown")
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
        result = _build_analysis_dict(trace)
        agent = next(item for item in result["cost_yield"]["agents"] if item["agent"] == "generator")
        path = result["cost_yield"]["path_summaries"][0]
        assert agent["grounding_issue_count"] == 1
        assert agent["citation_coverage"] is not None
        assert path["grounding_issue_count"] >= 1
        assert path["citation_coverage"] is not None
