"""Dense terminal diagnostics for AgentGuard traces."""

from __future__ import annotations

from typing import Any

from agentguard.analysis import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost_yield,
    analyze_counterfactual,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
)
from agentguard.core.trace import ExecutionTrace
from agentguard.scoring import score_trace


def _fmt_duration(ms: float | None) -> str:
    """Format milliseconds for compact terminal output."""
    if ms is None:
        return "?"
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60000:
        return f"{ms / 1000:.1f}s"
    return f"{ms / 60000:.1f}m"


def _fmt_percent(value: float | None) -> str:
    """Format percentages without forcing callers to guard None."""
    if value is None:
        return "?"
    return f"{value:.0%}"


def _trace_cost_usd(trace: ExecutionTrace) -> float:
    """Compute best-effort total estimated cost from spans."""
    return sum((span.estimated_cost_usd or 0.0) for span in trace.spans)


def _headline_line(trace: ExecutionTrace) -> str:
    """Build the top headline line for a dense report."""
    score = score_trace(trace)
    status = trace.status.value if trace.status else "unknown"
    return (
        f"task={trace.task or '(unnamed)'} | status={status} | grade={score.grade} {score.overall:.0f}/100 "
        f"| duration={_fmt_duration(trace.duration_ms)}"
    )


def _inventory_line(trace: ExecutionTrace) -> str:
    """Build the inventory line for spans, agents, and failures."""
    failed = sum(
        1
        for span in trace.spans
        if span.status is not None and span.status.value == "failed"
    )
    tools = sum(1 for span in trace.spans if span.span_type.value == "tool")
    handoffs = sum(1 for span in trace.spans if span.span_type.value == "handoff")
    return (
        f"spans={len(trace.spans)} | agents={len(trace.agent_spans)} | tools={tools} | "
        f"handoffs={handoffs} | failed={failed} | cost=${_trace_cost_usd(trace):.4f}"
    )


def _path_line(trace: ExecutionTrace) -> str:
    """Build a single-line summary of the dominant execution path."""
    flow = analyze_flow(trace)
    bottleneck = analyze_bottleneck(trace) if trace.agent_spans else None
    cost_yield = analyze_cost_yield(trace)
    critical_path = " -> ".join(flow.critical_path[:5]) if flow.critical_path else "n/a"
    bottleneck_name = bottleneck.bottleneck_span if bottleneck else "n/a"
    bottleneck_dur = _fmt_duration(bottleneck.bottleneck_duration_ms if bottleneck else None)
    return (
        f"bottleneck={bottleneck_name} ({bottleneck_dur}) | worst_path={cost_yield.worst_path or 'n/a'} "
        f"| critical_path={critical_path}"
    )


def _failure_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense failure-propagation lines."""
    failures = analyze_failures(trace)
    lines = [
        f"failed_spans={failures.total_failed_spans} | root_causes={len(failures.root_causes)} | "
        f"blast_radius={failures.blast_radius} | resilience={_fmt_percent(failures.resilience_score)}"
    ]
    for root_cause in failures.root_causes[:3]:
        handling = "handled" if root_cause.was_handled else "unhandled"
        lines.append(
            f"- {root_cause.span_name} [{root_cause.span_type}] {handling}: {root_cause.error}"
        )
    return lines


def _context_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense context-risk lines."""
    context_flow = analyze_context_flow(trace)
    lines = [
        f"handoffs={context_flow.handoff_count} | anomalies={len(context_flow.anomalies)} | "
        f"top_risks={len([point for point in context_flow.ranked_points if point.risk_label != 'ok'][:3])}"
    ]
    for point in [p for p in context_flow.ranked_points if p.risk_label != "ok"][:3]:
        detail = f"risk={_fmt_percent(point.risk_score)} semantic={_fmt_percent(point.semantic_retention_score)}"
        if point.critical_keys_lost:
            detail += f" critical={','.join(point.critical_keys_lost[:3])}"
        elif point.reference_ids_lost:
            detail += f" refs={','.join(point.reference_ids_lost[:3])}"
        if point.downstream_impact_reason:
            detail += f" impact={point.downstream_impact_reason}"
        lines.append(f"- {point.from_agent} -> {point.to_agent} [{point.risk_label}] {detail}")
    return lines


def _cost_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense cost-yield lines."""
    cost_yield = analyze_cost_yield(trace)
    lines = [
        f"highest_cost={cost_yield.highest_cost_agent} | lowest_yield={cost_yield.lowest_yield_agent} | "
        f"wasteful={cost_yield.most_wasteful_agent or 'n/a'}"
    ]
    for path in cost_yield.path_summaries[:2]:
        lines.append(
            f"- {(' -> '.join(path.agents))} [{path.path_kind}] cost=${path.total_cost_usd:.4f} "
            f"yield={path.avg_yield_score:.0f}/100 waste={path.waste_score:.0f}/100"
        )
    for recommendation in cost_yield.recommendations[:2]:
        lines.append(f"- action: {recommendation}")
    return lines


def _decision_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense decision and counterfactual lines."""
    decisions = analyze_decisions(trace)
    counterfactual = analyze_counterfactual(trace)
    lines = [
        f"decisions={decisions.total_decisions} | degraded={decisions.decisions_with_degradation} | "
        f"suboptimal={counterfactual.suboptimal_count} | catastrophic={counterfactual.catastrophic_count}"
    ]
    for decision in decisions.decisions[:2]:
        signals = "; ".join(decision.degradation_signals[:2]) or "no degradation"
        lines.append(f"- {decision.coordinator} -> {decision.chosen_agent}: {signals}")
    for suggestion in decisions.suggestions[:2]:
        lines.append(
            f"- suggest {suggestion['suggested_agent']} instead of {suggestion['current_agent']}: {suggestion['reason']}"
        )
    for result in counterfactual.results[:2]:
        if result.best_alternative:
            lines.append(
                f"- counterfactual {result.chosen_agent} => {result.best_alternative} [{result.verdict}]"
            )
    return lines


def _artifact_lines(trace_path: str | None, html_report: str | None) -> list[str]:
    """Build artifact lines for saved trace and HTML outputs."""
    lines = []
    if trace_path:
        lines.append(f"trace={trace_path}")
    if html_report:
        lines.append(f"html={html_report}")
    if not lines:
        lines.append("html=not-exported")
    return lines


def _section(title: str, lines: list[str]) -> list[str]:
    """Render one named section with a fallback for empty content."""
    body = lines or ["- none"]
    return [f"[{title}]"] + body + [""]


def render_dense_diagnostics(
    trace: ExecutionTrace,
    *,
    trace_path: str | None = None,
    html_report: str | None = None,
) -> str:
    """Render a high-density text diagnostics view for terminal and Claude Code."""
    lines = [
        "AGENTGUARD DIAGNOSE",
        "=" * 72,
        _headline_line(trace),
        _inventory_line(trace),
        _path_line(trace),
        "",
    ]
    lines.extend(_section("failures", _failure_lines(trace)))
    lines.extend(_section("context", _context_lines(trace)))
    lines.extend(_section("cost-yield", _cost_lines(trace)))
    lines.extend(_section("decisions", _decision_lines(trace)))
    lines.extend(_section("artifacts", _artifact_lines(trace_path, html_report)))
    return "\n".join(lines).rstrip() + "\n"