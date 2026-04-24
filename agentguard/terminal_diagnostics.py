"""Dense terminal diagnostics for AgentGuard traces."""

from __future__ import annotations

import os
import re
import sys
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


# --------------------------------------------------------------------------- #
# ANSI palette — only applied when stdout is a real TTY (or FORCE_COLOR is
# set), so captured output, pipes, and Claude-Code hook stdin/stdout stay
# plain-text and test substring assertions keep working untouched.
# --------------------------------------------------------------------------- #
class _Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"


def _color_enabled(color: bool | None) -> bool:
    """Decide whether to emit ANSI color.

    Precedence:
        explicit arg > NO_COLOR > FORCE_COLOR > stdout.isatty().
    """
    if color is not None:
        return color
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


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


# Target width of the rendered report (in monospace cells). Kept tight so
# a 80-col terminal still fits the dashed rule on one line.
_WIDTH = 74


def _banner_lines() -> list[str]:
    """Top banner: boxed ``AGENTGUARD DIAGNOSE`` title.

    The substring ``AGENTGUARD DIAGNOSE`` is preserved verbatim for
    substring assertions. Box-drawing characters are ASCII-safe Unicode
    and render in every modern terminal; non-TTY consumers keep the same
    characters (just without ANSI color).
    """
    inner = _WIDTH - 2
    title = "  \U0001F6E1\uFE0F  AGENTGUARD DIAGNOSE"
    pad = max(0, inner - len(title))
    rule = "\u2500" * inner
    return [
        f"\u256D{rule}\u256E",
        f"\u2502{title}{' ' * pad}\u2502",
        f"\u2570{rule}\u256F",
    ]


def _summary_block(trace: ExecutionTrace) -> list[str]:
    """Aligned key/value block that answers "what happened?" at a glance.

    Layout mirrors the terminal prototype: a left-aligned ``label`` column
    followed by the value. The previous pipe-delimited headline is split
    across multiple lines so the eye can scan top-to-bottom rather than
    parsing ``|`` separators. All field names (``task``, ``status``,
    ``grade``, ``cost``, ``bottleneck``) remain present so downstream
    grep-style consumers keep working.
    """
    score = score_trace(trace)
    status = trace.status.value if trace.status else "unknown"
    failed = sum(
        1 for s in trace.spans
        if s.status is not None and s.status.value == "failed"
    )
    tools = sum(1 for s in trace.spans if s.span_type.value == "tool")
    handoffs = sum(1 for s in trace.spans if s.span_type.value == "handoff")

    flow = analyze_flow(trace)
    bottleneck = analyze_bottleneck(trace) if trace.agent_spans else None
    critical = " \u2192 ".join(flow.critical_path[:5]) if flow.critical_path else "n/a"
    bn_name = bottleneck.bottleneck_span if bottleneck else "n/a"
    bn_dur = _fmt_duration(bottleneck.bottleneck_duration_ms if bottleneck else None)

    def lbl(text: str) -> str:
        return f"{text:<11}"

    return [
        f"  {lbl('task')}{trace.task or '(unnamed)'}",
        f"  {lbl('status')}\u25CF {status}    grade  {score.grade} {score.overall:.0f}/100    duration  {_fmt_duration(trace.duration_ms)}",
        f"  {lbl('inventory')}{len(trace.spans):,} spans \u00B7 {len(trace.agent_spans):,} agents \u00B7 {tools:,} tools \u00B7 {handoffs:,} handoffs \u00B7 failed={failed}",
        f"  {lbl('cost')}${_trace_cost_usd(trace):.4f}",
        f"  {lbl('bottleneck')}{bn_name} ({bn_dur})",
        f"  {lbl('critical')}{critical}",
    ]


def _failure_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense failure-propagation lines.

    Leads with the verdict (``\u2713`` clean or ``\u2717``/``\u26A0`` with root
    cause), follows with a dim one-line stat ribbon so the numbers are
    available but secondary.
    """
    failures = analyze_failures(trace)
    stats = (
        f"spans={failures.total_failed_spans} \u00B7 root_causes={len(failures.root_causes)}"
        f" \u00B7 blast_radius={failures.blast_radius}"
        f" \u00B7 resilience={_fmt_percent(failures.resilience_score)}"
    )
    if failures.total_failed_spans == 0:
        return ["\u2713 No failures in this session.", stats]
    lines: list[str] = []
    for root_cause in failures.root_causes[:3]:
        handling = "handled" if root_cause.was_handled else "unhandled"
        icon = "\u26A0" if root_cause.was_handled else "\u2717"
        lines.append(
            f"{icon} {root_cause.span_name} [{root_cause.span_type}] {handling}: {root_cause.error}"
        )
    lines.append(stats)
    return lines


def _context_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense context-risk lines."""
    context_flow = analyze_context_flow(trace)
    risky = [p for p in context_flow.ranked_points if p.risk_label != "ok"][:3]
    stats = (
        f"handoffs={context_flow.handoff_count} \u00B7 anomalies={len(context_flow.anomalies)}"
        f" \u00B7 top_risks={len(risky)}"
    )
    if context_flow.handoff_count == 0:
        return ["\u2014 No handoffs between agents detected.", stats]
    if not risky and not context_flow.anomalies:
        return [
            "\u2713 All handoffs look clean \u2014 no critical-key loss or semantic drift flagged.",
            stats,
        ]
    lines: list[str] = []
    for point in risky:
        detail = (
            f"risk={_fmt_percent(point.risk_score)}"
            f" semantic={_fmt_percent(point.semantic_retention_score)}"
        )
        if point.critical_keys_lost:
            detail += f" critical={','.join(point.critical_keys_lost[:3])}"
        elif point.reference_ids_lost:
            detail += f" refs={','.join(point.reference_ids_lost[:3])}"
        if point.downstream_impact_reason:
            detail += f" impact={point.downstream_impact_reason}"
        lines.append(
            f"\u26A0 {point.from_agent} \u2192 {point.to_agent} [{point.risk_label}] {detail}"
        )
    lines.append(stats)
    return lines


def _cost_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense cost-yield lines with highlight + path cards + actions."""
    cost_yield = analyze_cost_yield(trace)
    wasteful = cost_yield.most_wasteful_agent or "n/a"
    lines = [
        f"\U0001F4B0 highest cost    {cost_yield.highest_cost_agent}",
        f"\u26A0  lowest yield    {cost_yield.lowest_yield_agent}",
        f"\U0001F525 most wasteful   {wasteful}",
    ]
    for path in cost_yield.path_summaries[:2]:
        arrow = " \u2192 "
        # Normalize negative-zero waste (e.g. -0.0 -> 0.0).
        waste = 0 if -0.5 < path.waste_score < 0 else int(path.waste_score)
        lines.append("")
        lines.append(f"[ {path.path_kind} ] {arrow.join(path.agents)}")
        lines.append(
            f"   cost=${path.total_cost_usd:.4f}  yield={path.avg_yield_score:.0f}/100"
            f"  waste={waste}/100"
        )
    if cost_yield.recommendations:
        lines.append("")
        lines.append("actions")
        for recommendation in cost_yield.recommendations[:2]:
            lines.append(f"\u2192 {recommendation}")
    return lines


def _decision_lines(trace: ExecutionTrace) -> list[str]:
    """Build dense decision and counterfactual lines."""
    decisions = analyze_decisions(trace)
    counterfactual = analyze_counterfactual(trace)
    stats = (
        f"decisions={decisions.total_decisions} \u00B7 degraded={decisions.decisions_with_degradation}"
        f" \u00B7 suboptimal={counterfactual.suboptimal_count}"
        f" \u00B7 catastrophic={counterfactual.catastrophic_count}"
    )
    if decisions.total_decisions == 0:
        return [
            "\u2014 No coordinator/subagent decision points detected \u2014 run is linear.",
            stats,
        ]
    lines: list[str] = []
    for decision in decisions.decisions[:2]:
        signals = "; ".join(decision.degradation_signals[:2]) or "no degradation"
        icon = "\u2717" if decision.led_to_degradation else "\u2713"
        lines.append(f"{icon} {decision.coordinator} \u2192 {decision.chosen_agent}: {signals}")
    for suggestion in decisions.suggestions[:2]:
        lines.append(
            f"\u2192 suggest {suggestion['suggested_agent']} instead of {suggestion['current_agent']}: {suggestion['reason']}"
        )
    for result in counterfactual.results[:2]:
        if result.best_alternative:
            lines.append(
                f"\u21BA counterfactual {result.chosen_agent} \u21D2 {result.best_alternative} [{result.verdict}]"
            )
    lines.append(stats)
    return lines


def _artifact_lines(trace_path: str | None, html_report: str | None) -> list[str]:
    """Build artifact lines for saved trace and HTML outputs.

    The canonical substrings ``trace=`` and ``html=`` are retained for
    downstream parsers / tests; the visible ``trace  <path>`` /
    ``html  <path>`` presentation is produced by the colorizer on TTY.
    """
    lines: list[str] = []
    if trace_path:
        lines.append(f"\U0001F4C4 trace={trace_path}")
    if html_report:
        lines.append(f"\U0001F310 html={html_report}")
    if not lines:
        lines.append("html=not-exported")
    return lines


def _section(title: str, lines: list[str]) -> list[str]:
    """Render one named section with a fallback for empty content.

    Layout mirrors the terminal prototype: ``\u25B8 title  \u2500\u2500\u2500\u2500``
    (no brackets). Downstream consumers can still grep for the section
    name (``failures``, ``context``, ``cost-yield``, etc.) because those
    substrings remain verbatim in the header.
    """
    header = f"\u25B8 {title}"
    fill = max(2, _WIDTH - len(header) - 2)
    rule = "\u2500" * fill
    body = lines or ["- none"]
    indented = [f"  {line}" if line else "" for line in body]
    return [f"{header}  {rule}"] + indented + [""]


# --------------------------------------------------------------------------- #
# Colorizer — applies ANSI to a few well-known patterns only when color is
# enabled. Leaves the underlying text (including all substrings the tests
# assert on, like ``AGENTGUARD DIAGNOSE`` or ``[failures]``) completely
# unchanged; ANSI codes are wrapped around matches, never injected inside
# the significant characters themselves.
# --------------------------------------------------------------------------- #
_SECTION_TAGS = ("failures", "context", "cost-yield", "decisions", "artifacts")


def _grade_color(letter: str) -> str:
    """Map a letter grade to an ANSI color code."""
    return {
        "A": _Ansi.GREEN,
        "B": _Ansi.GREEN,
        "C": _Ansi.YELLOW,
        "D": _Ansi.YELLOW,
        "F": _Ansi.RED,
    }.get(letter.upper(), _Ansi.YELLOW)


def _status_color(status: str) -> str:
    """Map a trace status string to an ANSI color code."""
    return {
        "completed": _Ansi.GREEN,
        "failed": _Ansi.RED,
        "timeout": _Ansi.YELLOW,
        "cancelled": _Ansi.YELLOW,
    }.get(status, _Ansi.DIM)


def _colorize(text: str) -> str:
    """Apply ANSI colors to the dense-diagnostics output.

    Color is applied in three layers:
      1. Banner box + title (bold white title, cyan box rules).
      2. Section header ``\u25B8 name  \u2500\u2500\u2500\u2500`` (bold blue).
      3. Inline key/value highlights (grade, status, cost, yield, waste,
         resilience, failed counters) and leading-icon lines (\u2713 green,
         \u2717 red, \u26A0 yellow, \U0001F525 / \U0001F4B0 yellow,
         \U0001F4C4 / \U0001F310 cyan).
    """
    a = _Ansi
    text = _color_banner(text)
    text = _color_sections(text)
    out: list[str] = []
    for raw in text.splitlines():
        out.append(_color_line(raw, a))
    return "\n".join(out)


def _color_banner(text: str) -> str:
    a = _Ansi
    # Title: bold white (highest contrast) over cyan-bordered box.
    text = re.sub(
        r"(\U0001F6E1\uFE0F\s+AGENTGUARD DIAGNOSE)",
        lambda m: f"{a.BOLD}{m.group(1)}{a.RESET}",
        text,
    )
    # Box-drawing rules: full-line (top/bottom) → cyan.
    text = re.sub(
        r"^([\u2500\u256D\u256E\u2570\u256F]+)$",
        lambda m: f"{a.CYAN}{m.group(1)}{a.RESET}",
        text, flags=re.MULTILINE,
    )
    # Side rails on the title line: leading and trailing ``│`` → cyan.
    text = re.sub(
        r"^(\u2502)(.*)(\u2502)$",
        lambda m: f"{a.CYAN}{m.group(1)}{a.RESET}{m.group(2)}{a.CYAN}{m.group(3)}{a.RESET}",
        text, flags=re.MULTILINE,
    )
    return text


def _color_sections(text: str) -> str:
    a = _Ansi
    for tag in _SECTION_TAGS:
        text = re.sub(
            rf"^(\u25B8) {re.escape(tag)}(\s+)([\u2500]+)$",
            lambda m, t=tag: (
                f"{a.BLUE}{m.group(1)}{a.RESET} {a.BOLD}{a.BLUE}{t}{a.RESET}"
                f"{m.group(2)}{a.DIM}{m.group(3)}{a.RESET}"
            ),
            text, flags=re.MULTILINE,
        )
    return text


def _color_kv(line: str) -> str:
    a = _Ansi
    line = re.sub(
        r"\bgrade\s+([A-F])\b",
        lambda m: f"grade  {_grade_color(m.group(1))}{a.BOLD}{m.group(1)}{a.RESET}",
        line,
    )
    line = re.sub(
        r"(\u25CF)\s+(completed|failed|timeout|cancelled|unknown)\b",
        lambda m: f"{_status_color(m.group(2))}{m.group(1)}{a.RESET} "
                  f"{_status_color(m.group(2))}{m.group(2)}{a.RESET}",
        line,
    )
    line = re.sub(
        r"\bfailed=(\d+)\b",
        lambda m: (
            f"failed={a.GREEN}0{a.RESET}" if m.group(1) == "0"
            else f"failed={a.RED}{a.BOLD}{m.group(1)}{a.RESET}"
        ),
        line,
    )
    line = re.sub(
        r"\bfailed_spans=(\d+)\b",
        lambda m: (
            f"failed_spans={a.GREEN}0{a.RESET}" if m.group(1) == "0"
            else f"failed_spans={a.RED}{a.BOLD}{m.group(1)}{a.RESET}"
        ),
        line,
    )
    line = re.sub(
        r"\bresilience=(\d+)%",
        lambda m: (
            f"resilience={a.GREEN}100%{a.RESET}" if m.group(1) == "100"
            else f"resilience={a.YELLOW}{m.group(1)}%{a.RESET}"
        ),
        line,
    )
    line = re.sub(
        r"\bcost=\$([\d.]+)",
        lambda m: f"cost={a.YELLOW}${m.group(1)}{a.RESET}",
        line,
    )
    line = re.sub(
        r"\byield=(\d+)/100",
        lambda m: (
            f"yield={a.GREEN}{m.group(1)}/100{a.RESET}"
            if int(m.group(1)) >= 70
            else f"yield={a.YELLOW}{m.group(1)}/100{a.RESET}"
        ),
        line,
    )
    line = re.sub(
        r"\bwaste=(\d+)/100",
        lambda m: (
            f"waste={a.GREEN}{m.group(1)}/100{a.RESET}"
            if int(m.group(1)) <= 30
            else f"waste={a.YELLOW}{m.group(1)}/100{a.RESET}"
        ),
        line,
    )
    # Artifact lines: color path after ``trace=``/``html=`` cyan, key dim.
    # Visually render the ``=`` as a double-space separator so the output
    # reads ``trace  <path>`` / ``html  <path>`` (matches the prototype)
    # while the raw text stream keeps ``trace=``/``html=`` for parsers.
    line = re.sub(
        r"\b(trace|html)=([^\s].*)$",
        lambda m: f"{a.DIM}{m.group(1)}{a.RESET}  {a.CYAN}{m.group(2)}{a.RESET}",
        line,
    )
    return line


_VERDICT_COLORS = {
    "\u2713": _Ansi.GREEN,   # check
    "\u2717": _Ansi.RED,     # cross
    "\u26A0": _Ansi.YELLOW,  # warning
    "\u2014": _Ansi.DIM,     # em-dash (neutral / N/A)
    "\u2192": _Ansi.CYAN,    # right-arrow (action hint)
    "\u21BA": _Ansi.MAGENTA, # counterfactual
    "\U0001F4B0": _Ansi.YELLOW,  # money bag — highest cost
    "\U0001F525": _Ansi.RED,     # fire — most wasteful
    "\U0001F4C4": _Ansi.CYAN,    # page — trace artifact
    "\U0001F310": _Ansi.CYAN,    # globe — html artifact
}


def _color_line(raw: str, a: type) -> str:
    """Colorize a single already-laid-out line."""
    line = _color_kv(raw)
    stripped = raw.lstrip()
    # Leading verdict icon → color the icon only; leave the rest as kv'd.
    for icon, code in _VERDICT_COLORS.items():
        if stripped.startswith(icon):
            indent_len = len(raw) - len(stripped)
            indent = raw[:indent_len]
            rest = _color_kv(stripped[len(icon):])
            return f"{indent}{code}{icon}{a.RESET}{rest}"
    # Path card: ``[ critical_path ] agent -> agent`` etc. (padded
    # brackets read as a pill on TTY).
    m = re.match(r"^(\s*)\[ ([a-z_]+) \]\s+(.+)$", raw)
    if m and m.group(2) in {"critical_path", "handoff_chain", "longest_chain"}:
        indent, tag, body = m.group(1), m.group(2), m.group(3)
        return f"{indent}{a.BLUE}[ {tag} ]{a.RESET} {a.MAGENTA}{body}{a.RESET}"
    # Summary-block label column: two-space indent + label + value.
    m = re.match(r"^(  )(task|status|inventory|cost|bottleneck|critical)(\s+)(.*)$", raw)
    if m:
        indent, label, gap, body = m.groups()
        return f"{indent}{a.DIM}{label}{a.RESET}{gap}{_color_kv(body)}"
    return line


def render_dense_diagnostics(
    trace: ExecutionTrace,
    *,
    trace_path: str | None = None,
    html_report: str | None = None,
    color: bool | None = None,
) -> str:
    """Render a high-density text diagnostics view for terminal and Claude Code.

    Layout mirrors the terminal prototype (boxed header, aligned summary
    block, ``\u25B8 section`` rules, icon-led verdict lines, dim stats
    ribbons). A safe layer of ANSI coloring is applied when stdout is a
    TTY or ``FORCE_COLOR`` is set. All canonical substrings
    (``AGENTGUARD DIAGNOSE``, ``failures``, ``context``, ``cost-yield``,
    ``decisions``, ``artifacts``, ``trace=``, ``html=``) are preserved
    verbatim so pipelines / tests keep parsing the output as they do today.
    """
    lines: list[str] = []
    lines.extend(_banner_lines())
    lines.append("")
    lines.extend(_summary_block(trace))
    lines.append("")
    lines.extend(_section("failures", _failure_lines(trace)))
    lines.extend(_section("context", _context_lines(trace)))
    lines.extend(_section("cost-yield", _cost_lines(trace)))
    lines.extend(_section("decisions", _decision_lines(trace)))
    lines.extend(_section("artifacts", _artifact_lines(trace_path, html_report)))
    text = "\n".join(lines).rstrip() + "\n"
    if _color_enabled(color):
        text = _colorize(text)
    return text