"""Trace summarizer — generate natural language summaries of traces.

Produces human-readable summaries by combining:
- Overall status and score
- Key events (failures, handoffs, retries)
- Performance highlights
- Recommendations
"""

from __future__ import annotations

from agentguard.core.trace import ExecutionTrace, SpanStatus, SpanType
from agentguard.metrics import extract_metrics
from agentguard.scoring import score_trace


def summarize_trace(trace: ExecutionTrace) -> str:
    """Generate a natural language summary of a trace.

    Returns a human-readable paragraph describing what happened.
    """
    score = score_trace(trace)
    metrics = extract_metrics(trace)

    parts = []

    # Opening
    status_text = "completed successfully" if trace.status == SpanStatus.COMPLETED else "failed"
    parts.append(f"The trace '{trace.task or 'unnamed'}' {status_text} "
                f"with a quality score of {score.overall:.0f}/100 ({score.grade}).")

    # Stats
    parts.append(f"It executed {metrics.span_count} spans across "
                f"{metrics.agent_count} agents and {metrics.tool_count} tools.")

    # Duration
    if trace.duration_ms:
        parts.append(f"Total duration was {trace.duration_ms:.0f}ms.")

    # Failures
    failed = [s for s in trace.spans if s.status == SpanStatus.FAILED]
    if failed:
        fail_names = [s.name for s in failed[:3]]
        parts.append(f"There were {len(failed)} failures: {', '.join(fail_names)}.")

        # Root cause
        errors = [s.error for s in failed if s.error]
        if errors:
            parts.append(f"Root error: {errors[0][:100]}")

    # Handoffs
    handoffs = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    if handoffs:
        parts.append(f"{len(handoffs)} handoffs occurred between agents.")
        dropped = [s for s in handoffs if s.context_dropped_keys]
        if dropped:
            parts.append(f"⚠ Context was lost at {len(dropped)} handoff(s).")

    # Retries
    retries = sum(s.retry_count for s in trace.spans)
    if retries > 0:
        parts.append(f"{retries} retries were needed.")

    # Cost
    if metrics.total_tokens > 0:
        parts.append(f"Token usage: {metrics.total_tokens:,} tokens (${metrics.total_cost_usd:.2f}).")

    # Recommendations
    weak = min(score.components, key=lambda c: c.score)
    if weak.score < 60:
        parts.append(f"Recommendation: Focus on {weak.name.lower()} (scored {weak.score:.0f}/100).")

    return " ".join(parts)


def summarize_brief(trace: ExecutionTrace) -> str:
    """One-line summary of a trace."""
    score = score_trace(trace)
    status = "✅" if trace.status == SpanStatus.COMPLETED else "❌"
    dur = f"{trace.duration_ms:.0f}ms" if trace.duration_ms else "?"
    return f"{status} {trace.task or 'unnamed'} — Score: {score.overall:.0f} ({score.grade}), {len(trace.spans)} spans, {dur}"
