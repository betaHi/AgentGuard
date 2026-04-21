"""Generate a realistic HTML prototype for the current AgentGuard MVP."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.evolve import EvolutionEngine
from agentguard.web.viewer import generate_report_from_trace


BASE_TIME = datetime(2026, 4, 16, 12, 0, 0, tzinfo=UTC)


def _ts(offset_ms: int) -> str:
    """Convert a millisecond offset into an ISO timestamp."""
    return (BASE_TIME + timedelta(milliseconds=offset_ms)).isoformat()


def _span(
    name: str,
    span_type: SpanType,
    start_ms: int,
    end_ms: int,
    *,
    parent_span_id: str | None = None,
    status: SpanStatus = SpanStatus.COMPLETED,
    error: str | None = None,
    input_data: object | None = None,
    output_data: object | None = None,
    token_count: int | None = None,
    cost_usd: float | None = None,
    metadata: dict | None = None,
    handoff_from: str | None = None,
    handoff_to: str | None = None,
    context_size_bytes: int | None = None,
    context_dropped_keys: list[str] | None = None,
) -> Span:
    """Build a span with deterministic timestamps."""
    return Span(
        name=name,
        span_type=span_type,
        parent_span_id=parent_span_id,
        status=status,
        started_at=_ts(start_ms),
        ended_at=_ts(end_ms),
        error=error,
        input_data=input_data,
        output_data=output_data,
        token_count=token_count,
        estimated_cost_usd=cost_usd,
        metadata=metadata or {},
        handoff_from=handoff_from,
        handoff_to=handoff_to,
        context_size_bytes=context_size_bytes,
        context_dropped_keys=context_dropped_keys,
    )


def _review_handoff(parent_span_id: str) -> Span:
    """Build the explicit handoff that shows context loss into writing."""
    handoff = _span(
        name="reviewer-v2 → writer",
        span_type=SpanType.HANDOFF,
        start_ms=5200,
        end_ms=5200,
        parent_span_id=parent_span_id,
        handoff_from="reviewer-v2",
        handoff_to="writer",
        context_size_bytes=1800,
        context_dropped_keys=["evidence_table", "escalation_risks"],
    )
    handoff.metadata["handoff.context_keys"] = [
        "summary",
        "evidence_table",
        "escalation_risks",
    ]
    handoff.metadata["handoff.context_size_bytes"] = 1800
    return handoff


def _prototype_spans() -> list[Span]:
    """Build a composite orchestration trace that exercises MVP diagnostics."""
    coordinator = _span("briefing-coordinator", SpanType.AGENT, 0, 8200)
    collector = _span(
        "collector",
        SpanType.AGENT,
        120,
        980,
        parent_span_id=coordinator.span_id,
        input_data={"topic": "Enterprise rollout brief"},
        output_data={
            "source_docs": ["doc-a", "doc-b", "doc-c"],
            "evidence_table": ["approval gates", "rollback plan", "audit trail"],
            "escalation_risks": ["missing owner", "unapproved auto-remediation"],
        },
    )
    search = _span("search_docs", SpanType.TOOL, 160, 620, parent_span_id=collector.span_id)
    enrichment = _span("rank_sources", SpanType.TOOL, 640, 900, parent_span_id=collector.span_id)
    decision = _span(
        "briefing-coordinator → reviewer-v2 (decision)",
        SpanType.HANDOFF,
        1020,
        1020,
        parent_span_id=coordinator.span_id,
        handoff_from="briefing-coordinator",
        handoff_to="reviewer-v2",
        metadata={
            "decision.type": "orchestration",
            "decision.coordinator": "briefing-coordinator",
            "decision.chosen": "reviewer-v2",
            "decision.alternatives": ["stable-reviewer"],
            "decision.rationale": "Preferred deeper policy review despite higher latency",
            "decision.criteria": {"priority": "depth", "deadline": "same_day"},
            "decision.confidence": 0.64,
        },
    )
    reviewer = _span(
        "reviewer-v2",
        SpanType.AGENT,
        1100,
        5200,
        parent_span_id=coordinator.span_id,
        status=SpanStatus.FAILED,
        error="model overloaded during policy synthesis",
        input_data=collector.output_data,
        output_data={
            "summary": "Roll out behind approval gates and rollback controls.",
            "evidence_table": ["approval gates", "rollback plan"],
            "escalation_risks": ["missing owner", "unapproved auto-remediation"],
        },
        token_count=4200,
        cost_usd=0.11,
    )
    review_llm = _span(
        "policy_review_llm",
        SpanType.LLM_CALL,
        1480,
        4700,
        parent_span_id=reviewer.span_id,
        status=SpanStatus.FAILED,
        error="context window saturation",
        token_count=3900,
        cost_usd=0.10,
    )
    stable = _span(
        "stable-reviewer",
        SpanType.AGENT,
        1120,
        2550,
        parent_span_id=coordinator.span_id,
        input_data=collector.output_data,
        output_data={"summary": "Fallback reviewer completed a safe shorter brief."},
        token_count=1500,
        cost_usd=0.03,
    )
    review_handoff = _review_handoff(reviewer.span_id)
    writer = _span(
        "writer",
        SpanType.AGENT,
        5300,
        7150,
        parent_span_id=coordinator.span_id,
        input_data={"summary": reviewer.output_data["summary"]},
        output_data={"brief": "Executive rollout brief generated", "confidence": "medium"},
        token_count=1800,
        cost_usd=0.04,
    )
    writer_llm = _span(
        "write_brief",
        SpanType.LLM_CALL,
        5480,
        6900,
        parent_span_id=writer.span_id,
        token_count=1600,
        cost_usd=0.04,
    )
    notifier = _span(
        "notifier",
        SpanType.AGENT,
        7240,
        7600,
        parent_span_id=coordinator.span_id,
        status=SpanStatus.FAILED,
        error="slack webhook unreachable",
    )
    return [
        coordinator,
        collector,
        search,
        enrichment,
        decision,
        reviewer,
        review_llm,
        stable,
        review_handoff,
        writer,
        writer_llm,
        notifier,
    ]


def build_mvp_prototype_trace() -> ExecutionTrace:
    """Build the trace rendered by the HTML prototype."""
    trace = ExecutionTrace(
        task="MVP Prototype: Enterprise rollout briefing",
        trigger="demo",
        started_at=_ts(0),
        ended_at=_ts(8200),
        status=SpanStatus.COMPLETED,
    )
    for span in _prototype_spans():
        trace.add_span(span)
    return trace


def _seed_evolution_insights() -> None:
    """Seed the local knowledge base so the prototype shows evolution insights."""
    engine = EvolutionEngine()
    for _ in range(3):
        engine.learn(build_mvp_prototype_trace())


def generate_mvp_prototype(output: str = ".agentguard/prototypes/mvp-prototype.html") -> str:
    """Generate the HTML prototype and return its path."""
    _seed_evolution_insights()
    report_path = Path(output)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    return generate_report_from_trace(build_mvp_prototype_trace(), output=str(report_path))


def main() -> None:
    """Generate the prototype file for manual inspection."""
    report_path = generate_mvp_prototype()
    print("AgentGuard MVP HTML Prototype")
    print(f"Saved to: {report_path}")


if __name__ == "__main__":
    main()