"""Example: Multi-hop RAG pipeline with context degradation across five hops.

This example models a realistic retrieval-augmented generation workflow:

  coordinator
  ├── retriever      — fetches candidate documents and raw evidence
  ├── reranker       — narrows to the highest-value sources
  ├── generator      — drafts an answer from reduced context
  ├── fact-checker   — validates claims against remaining evidence
  └── synthesizer    — produces the final answer with unsupported claims removed

The key diagnostic point is not a hard failure. It is context degradation:
important evidence gets compressed or dropped across hops, and the fact-checker
has to remove one unsupported claim before synthesis.
"""

from __future__ import annotations

from agentguard import configure
from agentguard.analysis import analyze_bottleneck, analyze_context_flow, analyze_flow
from agentguard.builder import TraceBuilder
from agentguard.store import TraceStore
from agentguard.web.viewer import generate_report_from_trace


QUESTION = "How should enterprises deploy multi-agent RAG safely?"


def build_multi_hop_rag_trace(question: str = QUESTION):
    """Build a realistic multi-hop RAG trace with deliberate context loss."""
    retrieved_documents = [
        {
            "doc_id": "doc-1",
            "title": "Phased rollout for agent systems",
            "snippet": "Roll out behind approval gates and rollback plans.",
            "source_url": "https://example.com/doc-1",
        },
        {
            "doc_id": "doc-2",
            "title": "Human review checkpoints",
            "snippet": "Use human approval for high-impact actions.",
            "source_url": "https://example.com/doc-2",
        },
        {
            "doc_id": "doc-3",
            "title": "Observability for orchestration",
            "snippet": "Track handoffs, failures, and context retention.",
            "source_url": "https://example.com/doc-3",
        },
        {
            "doc_id": "doc-4",
            "title": "Autonomous remediation patterns",
            "snippet": "Only enable autonomous fixes after verification.",
            "source_url": "https://example.com/doc-4",
        },
        {
            "doc_id": "doc-5",
            "title": "Security boundaries for agents",
            "snippet": "Isolate credentials and sandbox tool execution.",
            "source_url": "https://example.com/doc-5",
        },
    ]

    reranked_documents = retrieved_documents[:3]
    generator_documents = reranked_documents[:2]

    return (
        TraceBuilder(f"Multi-Hop RAG: {question}")
        .agent("rag-coordinator", duration_ms=9800, input_data={"question": question})
            .agent(
                "retriever",
                duration_ms=1400,
                input_data={"question": question, "filters": {"year": 2026, "type": "best_practices"}},
                output_data={
                    "question": question,
                    "retrieved_documents": retrieved_documents,
                    "raw_quotes": [doc["snippet"] for doc in retrieved_documents],
                    "source_map": {doc["doc_id"]: doc["source_url"] for doc in retrieved_documents},
                    "retrieval_scores": {
                        "doc-1": 0.96,
                        "doc-2": 0.93,
                        "doc-3": 0.91,
                        "doc-4": 0.82,
                        "doc-5": 0.78,
                    },
                    "query_plan": {"subqueries": ["rollout", "human review", "observability"]},
                },
            )
                .tool("vector_search", duration_ms=650)
                .tool("metadata_lookup", duration_ms=220)
            .end()
            .agent(
                "reranker",
                duration_ms=1900,
                input_data={
                    "question": question,
                    "retrieved_documents": retrieved_documents,
                    "raw_quotes": [doc["snippet"] for doc in retrieved_documents],
                    "source_map": {doc["doc_id"]: doc["source_url"] for doc in retrieved_documents},
                    "retrieval_scores": {
                        "doc-1": 0.96,
                        "doc-2": 0.93,
                        "doc-3": 0.91,
                        "doc-4": 0.82,
                        "doc-5": 0.78,
                    },
                    "query_plan": {"subqueries": ["rollout", "human review", "observability"]},
                },
                output_data={
                    "question": question,
                    "top_documents": reranked_documents,
                    "evidence_table": [
                        {"doc_id": doc["doc_id"], "evidence": doc["snippet"]}
                        for doc in reranked_documents
                    ],
                    "source_map": {doc["doc_id"]: doc["source_url"] for doc in reranked_documents},
                    "ranking_rationale": "Prioritized rollout control, human review, and observability guidance.",
                    "rejected_doc_ids": ["doc-4", "doc-5"],
                },
            )
                .tool("cross_encoder_rerank", duration_ms=980)
            .end()
            .agent(
                "generator",
                duration_ms=4200,
                input_data={
                    "question": question,
                    "top_documents": generator_documents,
                    "evidence_table": [
                        {"doc_id": "doc-1", "evidence": retrieved_documents[0]["snippet"]},
                        {"doc_id": "doc-2", "evidence": retrieved_documents[1]["snippet"]},
                    ],
                },
                output_data={
                    "draft_answer": (
                        "Deploy behind approval gates, keep rollback plans ready, monitor handoffs, "
                        "and let agents auto-remediate production incidents without human review."
                    ),
                    "claims": [
                        "Use phased rollout with rollback controls.",
                        "Require human approval for high-impact actions.",
                        "Allow fully autonomous remediation in production once metrics look stable.",
                    ],
                    "citations": ["doc-1", "doc-2"],
                    "supporting_passages": [
                        retrieved_documents[0]["snippet"],
                        retrieved_documents[1]["snippet"],
                    ],
                    "unverified_claims": [
                        "Allow fully autonomous remediation in production once metrics look stable.",
                    ],
                },
                token_count=3400,
                cost_usd=0.09,
            )
                .tool("llm_generate_answer", duration_ms=3600)
            .end()
            .agent(
                "fact-checker",
                duration_ms=2500,
                input_data={
                    "question": question,
                    "claims": [
                        "Use phased rollout with rollback controls.",
                        "Require human approval for high-impact actions.",
                        "Allow fully autonomous remediation in production once metrics look stable.",
                    ],
                    "citations": ["doc-1", "doc-2"],
                },
                output_data={
                    "verified_claims": [
                        "Use phased rollout with rollback controls.",
                        "Require human approval for high-impact actions.",
                    ],
                    "unsupported_claims": [
                        "Allow fully autonomous remediation in production once metrics look stable.",
                    ],
                    "missing_citation_ids": ["doc-3"],
                    "verdict": "needs_revision",
                },
            )
                .tool("evidence_match", duration_ms=1200)
            .end()
            .agent(
                "synthesizer",
                duration_ms=2100,
                input_data={
                    "question": question,
                    "verified_claims": [
                        "Use phased rollout with rollback controls.",
                        "Require human approval for high-impact actions.",
                    ],
                    "unsupported_claims": [
                        "Allow fully autonomous remediation in production once metrics look stable.",
                    ],
                    "missing_citation_ids": ["doc-3"],
                },
                output_data={
                    "final_answer": (
                        "Enterprises should deploy multi-agent RAG with phased rollout, explicit rollback "
                        "controls, approval gates for high-impact actions, and orchestration observability."
                    ),
                    "removed_claim_count": 1,
                    "citations": ["doc-1", "doc-2"],
                    "confidence": "medium",
                },
                token_count=1800,
                cost_usd=0.04,
            )
                .tool("llm_synthesize", duration_ms=1500)
            .end()
        .end()
        .build()
    )


def run_example(question: str = QUESTION):
    """Run the multi-hop RAG diagnostic example and save outputs."""
    configure(output_dir=".agentguard/traces")
    trace = build_multi_hop_rag_trace(question)

    store = TraceStore()
    store.save(trace)

    flow = analyze_flow(trace)
    context_flow = analyze_context_flow(trace)
    bottleneck = analyze_bottleneck(trace)
    report_path = generate_report_from_trace(trace, output=".agentguard/multi-hop-rag-report.html")

    print("📚 Multi-Hop RAG Pipeline")
    print("=" * 60)
    print(f"Question: {question}")
    print(f"Agents: {flow.agent_count}")
    print(f"Handoffs inferred: {context_flow.handoff_count}")
    print(f"Context anomalies: {len(context_flow.anomalies)}")
    for point in context_flow.anomalies:
        print(f"  - {point.from_agent} → {point.to_agent}: {point.anomaly}")
        if point.keys_lost:
            print(f"    Lost keys: {point.keys_lost}")
        if point.truncation_detail:
            print(f"    Truncated: {point.truncation_detail}")
    print(f"Bottleneck: {bottleneck.bottleneck_span} ({bottleneck.bottleneck_duration_ms:.0f}ms)")
    print(f"HTML report: {report_path}")
    return trace


if __name__ == "__main__":
    run_example()