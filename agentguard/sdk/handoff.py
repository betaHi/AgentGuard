"""Handoff recording utilities.

Explicitly record when work passes from one agent to another,
capturing context transfer, timing, and potential information loss.

Usage:
    from agentguard.sdk.handoff import record_handoff

    # After agent_a completes, before agent_b starts:
    record_handoff(
        from_agent="researcher",
        to_agent="analyst",
        context={"articles": articles, "topic": topic},
        summary="Passing 5 articles about AI to analyst",
    )
"""

from __future__ import annotations

import json
import sys
from typing import Any

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.recorder import get_recorder


def record_handoff(
    from_agent: str,
    to_agent: str,
    context: Any = None,
    summary: str = "",
    metadata: dict | None = None,
) -> Span:
    """Record a handoff event between two agents.

    This creates a HANDOFF span that captures the context transfer
    between agents. Use this to make handoffs visible in traces.

    Args:
        from_agent: Name of the agent handing off.
        to_agent: Name of the agent receiving.
        context: The data being passed (will be serialized for size tracking).
        summary: Human-readable description of what's being handed off.
        metadata: Additional metadata.

    Returns:
        The completed handoff Span, with ``context_size_bytes`` and
        ``context_passed`` populated. Pass this span to
        ``mark_context_used()`` after the receiver processes the handoff.

    Note:
        The span is immediately completed (handoffs are instantaneous events).
        Context is serialized only to measure size — the original object is
        not stored in the trace.

    Example::

        news = collector.run(topic)
        record_handoff("collector", "analyst", context=news, summary="5 articles")
        analysis = analyst.run(news)
    """
    recorder = get_recorder()

    # Calculate context size
    ctx_bytes = 0
    ctx_keys = []
    if context is not None:
        try:
            serialized = json.dumps(context, default=str)
            ctx_bytes = len(serialized.encode("utf-8"))
        except Exception:
            ctx_bytes = sys.getsizeof(context)

        if isinstance(context, dict):
            ctx_keys = list(context.keys())

    span = Span(
        span_type=SpanType.HANDOFF,
        name=f"{from_agent} → {to_agent}",
        parent_span_id=recorder.current_span_id,
        input_data={"from": from_agent, "to": to_agent, "summary": summary},
        output_data={"context_keys": ctx_keys, "context_size_bytes": ctx_bytes},
        metadata={
            "handoff.from": from_agent,
            "handoff.to": to_agent,
            "handoff.context_keys": ctx_keys,
            "handoff.context_size_bytes": ctx_bytes,
            **(metadata or {}),
        },
        handoff_from=from_agent,
        handoff_to=to_agent,
        context_passed={"keys": ctx_keys, "summary": summary} if summary else None,
        context_size_bytes=ctx_bytes,
    )

    span.complete()
    recorder.push_span(span)
    recorder.pop_span(span)

    return span


def detect_context_loss(
    sent_context: dict,
    received_input: dict,
    required_keys: list[str] | None = None,
) -> dict:
    """Detect if context was lost during a handoff.

    Compares the keys and serialized sizes of sent vs received data
    to identify missing information, unexpected additions, or size
    discrepancies.

    Args:
        sent_context: The data dict the sender passed at handoff time.
        received_input: The data dict the receiver actually received.
        required_keys: Keys that *must* be present in the received input.
            If any are missing, ``loss_detected`` is True regardless of
            other key comparisons.

    Returns:
        Dict containing:
            - ``missing_keys``: Keys in sent but not in received.
            - ``extra_keys``: Keys in received but not in sent.
            - ``required_missing``: Required keys that are absent.
            - ``sent_size_bytes``: Serialized size of sent context.
            - ``received_size_bytes``: Serialized size of received input.
            - ``size_delta_bytes``: ``received - sent`` (negative = shrinkage).
            - ``loss_detected``: True if any keys are missing or required keys absent.
    """
    sent_keys = set(sent_context.keys()) if isinstance(sent_context, dict) else set()
    recv_keys = set(received_input.keys()) if isinstance(received_input, dict) else set()

    missing = sent_keys - recv_keys
    extra = recv_keys - sent_keys

    sent_size = len(json.dumps(sent_context, default=str).encode("utf-8"))
    recv_size = len(json.dumps(received_input, default=str).encode("utf-8"))

    required_missing = []
    if required_keys:
        required_missing = [k for k in required_keys if k not in recv_keys]

    return {
        "missing_keys": list(missing),
        "extra_keys": list(extra),
        "required_missing": required_missing,
        "sent_size_bytes": sent_size,
        "received_size_bytes": recv_size,
        "size_delta_bytes": recv_size - sent_size,
        "loss_detected": len(missing) > 0 or len(required_missing) > 0,
    }



def mark_context_used(
    handoff_span: Span,
    used_keys: list[str],
    received_context: Any = None,
) -> dict:
    """Mark which context keys were actually used by the receiving agent.

    Call this after the receiver processes the handoff to track context
    utilization. Updates the handoff span in place with used/dropped key
    lists and a utilization ratio.

    Args:
        handoff_span: The handoff Span returned by ``record_handoff()``.
        used_keys: Keys that the receiver actually consumed.
        received_context: The data the receiver got (optional). If provided,
            its serialized size is recorded for comparison with sent size.

    Returns:
        Dict containing:
            - ``used_keys``: Keys the receiver consumed.
            - ``dropped_keys``: Keys that were sent but not used.
            - ``extra_used``: Keys the receiver used that were not in the
              original sent context (e.g., derived or injected data).
            - ``utilization_ratio``: Fraction of sent keys that were used
              (0.0–1.0). A low ratio suggests the sender is over-sharing.

    Example::

        h = record_handoff("collector", "analyst", context=data)
        result = analyst.run(data)
        mark_context_used(h, used_keys=["articles", "topic"])
    """
    sent_keys = handoff_span.metadata.get("handoff.context_keys", [])
    dropped = [k for k in sent_keys if k not in used_keys]
    extra_used = [k for k in used_keys if k not in sent_keys]

    handoff_span.context_used_keys = used_keys
    handoff_span.context_dropped_keys = dropped

    if received_context is not None:
        try:
            serialized = json.dumps(received_context, default=str)
            recv_bytes = len(serialized.encode("utf-8"))
        except Exception:
            recv_bytes = sys.getsizeof(received_context)
        handoff_span.context_received = {
            "size_bytes": recv_bytes,
            "keys": list(received_context.keys()) if isinstance(received_context, dict) else [],
        }

    # Utilization = fraction of sent keys that were used (capped at 1.0)
    used_from_sent = len([k for k in used_keys if k in sent_keys])
    utilization = used_from_sent / max(len(sent_keys), 1)

    handoff_span.metadata["handoff.used_keys"] = used_keys
    handoff_span.metadata["handoff.dropped_keys"] = dropped
    handoff_span.metadata["handoff.utilization"] = round(utilization, 2)

    return {
        "used_keys": used_keys,
        "dropped_keys": dropped,
        "extra_used": extra_used,
        "utilization_ratio": round(utilization, 2),
    }


def record_decision(
    coordinator: str,
    chosen_agent: str,
    alternatives: list[str] | None = None,
    rationale: str = "",
    criteria: dict | None = None,
    confidence: float | None = None,
    metadata: dict | None = None,
) -> Span:
    """Record an orchestration decision — why the coordinator chose one agent over others.

    Answers GUARDRAILS Q5: "Which orchestration decision caused downstream degradation?"

    Use this when a coordinator/router makes a routing decision. The decision
    is recorded as a HANDOFF span with decision metadata, so it appears in
    the trace timeline and can be correlated with downstream outcomes.

    Args:
        coordinator: Name of the agent/router making the decision.
        chosen_agent: Name of the agent that was selected.
        alternatives: Other agents that were considered but not chosen.
            Empty list or None means no alternatives were available.
        rationale: Human-readable explanation of why this agent was chosen.
            E.g. "Chose code-generator over code-improver because task is greenfield".
        criteria: Structured selection criteria as key-value pairs.
            E.g. {"task_type": "greenfield", "complexity": "high", "budget_remaining": 0.5}
        confidence: How confident the coordinator is in this choice (0.0-1.0).
            None means confidence was not assessed.
        metadata: Additional metadata to attach to the span.

    Returns:
        The decision Span, which can be used to correlate with downstream outcomes.

    Example::

        decision = record_decision(
            coordinator="router",
            chosen_agent="fast-model",
            alternatives=["slow-model", "cheap-model"],
            rationale="Chose fast-model: latency-sensitive request",
            criteria={"priority": "speed", "budget_ok": True},
            confidence=0.85,
        )
    """
    recorder = get_recorder()

    alts = alternatives or []
    decision_criteria = criteria or {}

    span = Span(
        span_type=SpanType.HANDOFF,
        name=f"{coordinator} → {chosen_agent} (decision)",
        parent_span_id=recorder.current_span_id,
        input_data={
            "coordinator": coordinator,
            "chosen": chosen_agent,
            "alternatives": alts,
            "rationale": rationale,
        },
        output_data={
            "decision": chosen_agent,
            "alternatives_count": len(alts),
        },
        metadata={
            "decision.coordinator": coordinator,
            "decision.chosen": chosen_agent,
            "decision.alternatives": alts,
            "decision.rationale": rationale,
            "decision.criteria": decision_criteria,
            "decision.confidence": confidence,
            "decision.type": "orchestration",
            **(metadata or {}),
        },
        handoff_from=coordinator,
        handoff_to=chosen_agent,
    )

    span.complete()
    recorder.push_span(span)
    recorder.pop_span(span)

    return span
