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
from typing import Any, Optional

from agentguard.core.trace import Span, SpanType
from agentguard.sdk.recorder import get_recorder


def record_handoff(
    from_agent: str,
    to_agent: str,
    context: Any = None,
    summary: str = "",
    metadata: Optional[dict] = None,
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
        The handoff Span.
    
    Example:
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
    required_keys: Optional[list[str]] = None,
) -> dict:
    """Detect if context was lost during a handoff.
    
    Compares what was sent vs what was received to identify
    missing or changed keys.
    
    Args:
        sent_context: What the sender passed.
        received_input: What the receiver actually got.
        required_keys: Keys that must be present (optional).
    
    Returns:
        Dict with: missing_keys, extra_keys, size_delta, loss_detected
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
    
    Call this after the receiver processes the handoff to track context utilization.
    
    Args:
        handoff_span: The handoff span returned by record_handoff.
        used_keys: Keys that the receiver actually used.
        received_context: What the receiver got (for size comparison).
    
    Returns:
        Dict with: used_keys, dropped_keys, utilization_ratio
    
    Example:
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
