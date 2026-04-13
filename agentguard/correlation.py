"""Span correlation — link events across the trace by causality, timing, and pattern.

Provides:
- Failure-to-handoff correlation: which handoff caused which failure?
- Span fingerprinting: unique signature for detecting similar patterns
- Pattern detection: repeated failure patterns, recurring bottlenecks
- Timeline correlation: events that co-occur in time windows
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType


@dataclass
class SpanFingerprint:
    """Unique signature for a span's structural position and behavior."""
    span_id: str
    name: str
    fingerprint: str  # hash of structural properties
    pattern_key: str  # simplified key for grouping similar spans

    def to_dict(self) -> dict:
        return {
            "span_id": self.span_id,
            "name": self.name,
            "fingerprint": self.fingerprint,
            "pattern_key": self.pattern_key,
        }


@dataclass
class CorrelatedEvent:
    """Two events that are correlated in a trace."""
    event_a: dict
    event_b: dict
    correlation_type: str  # "causal", "temporal", "structural"
    confidence: float  # 0-1
    explanation: str

    def to_dict(self) -> dict:
        return {
            "event_a": self.event_a,
            "event_b": self.event_b,
            "type": self.correlation_type,
            "confidence": round(self.confidence, 2),
            "explanation": self.explanation,
        }


@dataclass
class CorrelationReport:
    """Complete correlation analysis for a trace."""
    fingerprints: list[SpanFingerprint]
    correlations: list[CorrelatedEvent]
    patterns: list[dict]  # recurring patterns found

    def to_dict(self) -> dict:
        return {
            "fingerprints": [f.to_dict() for f in self.fingerprints],
            "correlations": [c.to_dict() for c in self.correlations],
            "patterns": self.patterns,
        }

    def to_report(self) -> str:
        lines = [
            "# Span Correlation Analysis",
            "",
            f"- **Fingerprints:** {len(self.fingerprints)}",
            f"- **Correlations:** {len(self.correlations)}",
            f"- **Patterns:** {len(self.patterns)}",
            "",
        ]
        for c in self.correlations:
            icon = {"causal": "🔗", "temporal": "⏱️", "structural": "🏗️"}.get(c.correlation_type, "📎")
            lines.append(f"{icon} [{c.correlation_type}] {c.explanation} (confidence: {c.confidence:.0%})")

        if self.patterns:
            lines.append("")
            lines.append("## Recurring Patterns")
            for p in self.patterns:
                lines.append(f"- **{p['name']}**: seen {p['count']} times — {p.get('description', '')}")

        return "\n".join(lines)


def fingerprint_span(span: Span, parent_name: str = "") -> SpanFingerprint:
    """Generate a structural fingerprint for a span.

    The fingerprint captures the span's position in the tree and its
    behavioral characteristics, making it possible to detect similar
    patterns across different traces.
    """
    # Pattern key: simplified grouping key
    pattern_key = f"{span.span_type.value}:{span.name}"
    if parent_name:
        pattern_key = f"{parent_name}/{pattern_key}"

    # Fingerprint: hash of structural properties
    props = {
        "type": span.span_type.value,
        "name": span.name,
        "parent": parent_name,
        "status": span.status.value,
        "has_error": span.error is not None,
        "has_handoff": span.handoff_from is not None,
        "has_retry": span.retry_count > 0,
        "has_children": bool(span.children),
        "input_keys": sorted(span.input_data.keys()) if isinstance(span.input_data, dict) else [],
        "output_keys": sorted(span.output_data.keys()) if isinstance(span.output_data, dict) else [],
    }
    fp_hash = hashlib.sha256(json.dumps(props, sort_keys=True).encode()).hexdigest()[:16]

    return SpanFingerprint(
        span_id=span.span_id,
        name=span.name,
        fingerprint=fp_hash,
        pattern_key=pattern_key,
    )


def correlate_failures_to_handoffs(trace: ExecutionTrace) -> list[CorrelatedEvent]:
    """Find causal links between handoffs and subsequent failures.

    If agent B fails shortly after receiving a handoff from agent A,
    the handoff might be the cause (context loss, bad data, etc.).
    """
    {s.span_id: s for s in trace.spans}
    correlations = []

    handoff_spans = [s for s in trace.spans if s.span_type == SpanType.HANDOFF]
    failed_spans = [s for s in trace.spans if s.status == SpanStatus.FAILED]

    for handoff in handoff_spans:
        to_agent = handoff.handoff_to or ""
        dropped_keys = handoff.context_dropped_keys or []
        utilization = handoff.metadata.get("handoff.utilization", 1.0)

        # Find failures in the receiving agent
        for failed in failed_spans:
            if failed.name == to_agent:
                # Calculate confidence based on context quality
                confidence = 0.3  # base confidence

                if dropped_keys:
                    confidence += 0.3  # context loss increases likelihood
                if utilization < 0.5:
                    confidence += 0.2  # low utilization = receiver struggled

                # Check temporal proximity
                h_end = _parse_time(handoff.ended_at)
                f_start = _parse_time(failed.started_at)
                if h_end and f_start and f_start >= h_end:
                    gap_ms = (f_start - h_end).total_seconds() * 1000
                    if gap_ms < 5000:
                        confidence += 0.2  # close in time = more likely causal

                confidence = min(confidence, 1.0)

                explanation = (
                    f"Agent '{to_agent}' failed after receiving handoff from '{handoff.handoff_from}'"
                )
                if dropped_keys:
                    explanation += f" (dropped keys: {dropped_keys})"

                correlations.append(CorrelatedEvent(
                    event_a={"type": "handoff", "span_id": handoff.span_id,
                             "from": handoff.handoff_from, "to": to_agent},
                    event_b={"type": "failure", "span_id": failed.span_id,
                             "agent": failed.name, "error": failed.error},
                    correlation_type="causal",
                    confidence=confidence,
                    explanation=explanation,
                ))

    return correlations


def _pattern_repeated_failures(trace: ExecutionTrace) -> list[dict]:
    """Detect agents that fail multiple times."""
    counts: dict[str, int] = {}
    for s in trace.spans:
        if s.status == SpanStatus.FAILED:
            counts[s.name] = counts.get(s.name, 0) + 1
    return [{
        "name": f"repeated_failure:{name}", "type": "repeated_failure",
        "agent": name, "count": count,
        "description": f"Agent '{name}' failed {count} times",
    } for name, count in counts.items() if count >= 2]


def _pattern_retry_storms(trace: ExecutionTrace) -> list[dict]:
    """Detect retry storms (>=3 spans retrying)."""
    retry_spans = [s for s in trace.spans if s.retry_count > 0]
    if len(retry_spans) < 3:
        return []
    total = sum(s.retry_count for s in retry_spans)
    return [{"name": "retry_storm", "type": "retry_storm",
             "count": total, "spans": len(retry_spans),
             "description": f"Retry storm: {total} retries across {len(retry_spans)} spans"}]


def _pattern_slow_agents(agent_durations: list[tuple[str, float]]) -> list[dict]:
    """Detect agents >2x slower than average."""
    if len(agent_durations) < 2:
        return []
    avg = sum(d for _, d in agent_durations) / len(agent_durations)
    return [{
        "name": f"slow_agent:{name}", "type": "slow_agent",
        "agent": name, "duration_ms": dur, "avg_duration_ms": avg, "count": 1,
        "description": f"Agent '{name}' is {dur/avg:.1f}x slower than average ({dur:.0f}ms vs {avg:.0f}ms)",
    } for name, dur in agent_durations if dur > avg * 2]


def _pattern_failure_clusters(trace: ExecutionTrace, span_map: dict) -> list[dict]:
    """Detect multiple failures under the same parent."""
    parent_failures: dict[str, list[str]] = {}
    for s in trace.spans:
        if s.status == SpanStatus.FAILED and s.parent_span_id:
            parent_failures.setdefault(s.parent_span_id, []).append(s.name)
    results = []
    for pid, names in parent_failures.items():
        if len(names) >= 2:
            pname = span_map[pid].name if pid in span_map else pid
            results.append({
                "name": f"failure_cluster:{pname}", "type": "failure_cluster",
                "parent": pname, "failed_children": names, "count": len(names),
                "description": f"{len(names)} failures under '{pname}': {', '.join(names)}",
            })
    return results


def _pattern_timing_clusters(agent_durations: list[tuple[str, float]]) -> list[dict]:
    """Detect agent pairs with similar durations (within 10%)."""
    if len(agent_durations) < 3:
        return []
    from itertools import combinations
    clusters = [
        (n1, n2) for (n1, d1), (n2, d2) in combinations(agent_durations, 2)
        if d1 > 0 and d2 > 0 and abs(d1 - d2) / max(d1, d2) < 0.1
    ]
    if not clusters:
        return []
    return [{"name": "timing_cluster", "type": "timing_cluster",
             "pairs": clusters, "count": len(clusters),
             "description": f"{len(clusters)} agent pairs with similar timing (within 10%)"}]


def detect_patterns(trace: ExecutionTrace) -> list[dict]:
    """Detect recurring patterns: repeated failures, retry storms, slow chains, clusters."""
    span_map = {s.span_id: s for s in trace.spans}
    agent_durations = [
        (s.name, s.duration_ms or 0)
        for s in trace.spans if s.span_type == SpanType.AGENT and s.duration_ms
    ]
    return (
        _pattern_repeated_failures(trace)
        + _pattern_retry_storms(trace)
        + _pattern_slow_agents(agent_durations)
        + _pattern_failure_clusters(trace, span_map)
        + _pattern_timing_clusters(agent_durations)
    )


def analyze_correlations(trace: ExecutionTrace) -> CorrelationReport:
    """Complete correlation analysis for a trace.

    Combines fingerprinting, failure-handoff correlation, and pattern detection.
    """
    span_map = {s.span_id: s for s in trace.spans}
    parent_names: dict[str, str] = {}

    for s in trace.spans:
        if s.parent_span_id and s.parent_span_id in span_map:
            parent_names[s.span_id] = span_map[s.parent_span_id].name

    # Generate fingerprints
    fingerprints = [
        fingerprint_span(s, parent_names.get(s.span_id, ""))
        for s in trace.spans
    ]

    # Find correlations
    correlations = correlate_failures_to_handoffs(trace)

    # Detect patterns
    patterns = detect_patterns(trace)

    return CorrelationReport(
        fingerprints=fingerprints,
        correlations=correlations,
        patterns=patterns,
    )


def _parse_time(iso_str: str | None) -> datetime | None:
    """Parse ISO timestamp."""
    if not iso_str:
        return None
    try:
        return datetime.fromisoformat(iso_str)
    except (ValueError, TypeError):
        return None
