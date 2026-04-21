"""Semantic tests for the multi-hop RAG example."""

from __future__ import annotations

import importlib.util
from pathlib import Path

from agentguard.analysis import analyze_bottleneck, analyze_context_flow, analyze_flow


EXAMPLE_PATH = Path(__file__).resolve().parents[1] / "examples" / "multi_hop_rag_pipeline.py"


def _load_example_module():
    spec = importlib.util.spec_from_file_location("multi_hop_rag_pipeline", EXAMPLE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_multi_hop_rag_trace_shape():
    module = _load_example_module()
    trace = module.build_multi_hop_rag_trace()

    agent_names = [span.name for span in trace.agent_spans]
    assert "retriever" in agent_names
    assert "reranker" in agent_names
    assert "generator" in agent_names
    assert "fact-checker" in agent_names
    assert "synthesizer" in agent_names


def test_multi_hop_rag_context_anomalies_detected():
    module = _load_example_module()
    trace = module.build_multi_hop_rag_trace()

    report = analyze_context_flow(trace)
    anomaly_pairs = {(point.from_agent, point.to_agent, point.anomaly) for point in report.anomalies}

    assert report.handoff_count >= 4
    assert len(report.anomalies) >= 2
    assert ("reranker", "generator", "loss") in anomaly_pairs
    assert ("generator", "fact-checker", "loss") in anomaly_pairs


def test_multi_hop_rag_bottleneck_and_flow():
    module = _load_example_module()
    trace = module.build_multi_hop_rag_trace()

    flow = analyze_flow(trace)
    bottleneck = analyze_bottleneck(trace)

    assert flow.agent_count == 6
    assert bottleneck.bottleneck_span in {"generator", "llm_generate_answer"}
    assert "generator" in bottleneck.critical_path
    assert bottleneck.bottleneck_duration_ms >= 3600


def test_multi_hop_rag_final_answer_removes_unsupported_claim():
    module = _load_example_module()
    trace = module.build_multi_hop_rag_trace()

    synthesizer = next(span for span in trace.agent_spans if span.name == "synthesizer")
    fact_checker = next(span for span in trace.agent_spans if span.name == "fact-checker")

    assert fact_checker.output_data["unsupported_claims"]
    assert synthesizer.output_data["removed_claim_count"] == 1