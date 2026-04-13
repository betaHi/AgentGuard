"""ASCII visualization — render traces as ASCII art for terminals.

Provides terminal-friendly visualizations:
- Gantt chart (horizontal bars showing timing)
- Dependency arrows
- Status indicators
"""

from __future__ import annotations

from datetime import datetime

from agentguard.core.trace import ExecutionTrace, Span, SpanStatus


def _parse_ts(iso: str | None) -> float | None:
    """Parse ISO timestamp to epoch seconds."""
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).timestamp()
    except (ValueError, TypeError):
        return None


def gantt_chart(trace: ExecutionTrace, width: int = 60) -> str:
    """Render a Gantt-style ASCII chart.

    Each span gets a horizontal bar proportional to its duration.
    """
    timed = []
    for s in trace.spans:
        start = _parse_ts(s.started_at)
        end = _parse_ts(s.ended_at)
        if start is not None and end is not None:
            timed.append((s, start, end))

    if not timed:
        return "(no timed spans)"

    min_t = min(t[1] for t in timed)
    max_t = max(t[2] for t in timed)
    span_t = max_t - min_t or 1

    # Find max name length for padding
    max_name = max(len(s.name[:20]) for s, _, _ in timed)

    lines = []
    header = f"{'Span':<{max_name}} │{'':─<{width}}│ Duration"
    lines.append(header)
    lines.append("─" * len(header))

    for s, start, end in sorted(timed, key=lambda x: x[1]):
        name = s.name[:20].ljust(max_name)

        bar_start = int((start - min_t) / span_t * width)
        bar_end = int((end - min_t) / span_t * width)
        bar_len = max(bar_end - bar_start, 1)

        status_char = {
            SpanStatus.COMPLETED: "█",
            SpanStatus.FAILED: "▓",
            SpanStatus.RUNNING: "░",
            SpanStatus.TIMEOUT: "▒",
        }.get(s.status, "░")

        bar = " " * bar_start + status_char * bar_len + " " * (width - bar_start - bar_len)
        dur = f"{s.duration_ms:.0f}ms" if s.duration_ms else "?"

        lines.append(f"{name} │{bar}│ {dur}")

    lines.append("─" * len(header))

    # Legend
    lines.append("")
    lines.append("Legend: █ completed  ▓ failed  ░ running  ▒ timeout")

    return "\n".join(lines)


def status_summary(trace: ExecutionTrace) -> str:
    """One-line status summary with emoji."""
    total = len(trace.spans)
    completed = sum(1 for s in trace.spans if s.status == SpanStatus.COMPLETED)
    failed = sum(1 for s in trace.spans if s.status == SpanStatus.FAILED)

    bar_total = 20
    bar_ok = int(completed / max(total, 1) * bar_total)
    bar_fail = int(failed / max(total, 1) * bar_total)
    bar_other = bar_total - bar_ok - bar_fail

    bar = "🟢" * bar_ok + "🔴" * bar_fail + "⚪" * bar_other

    status = "✅" if trace.status == SpanStatus.COMPLETED else "❌"
    dur = f"{trace.duration_ms:.0f}ms" if trace.duration_ms else "?"

    return f"{status} {trace.task or 'unnamed'} [{bar}] {completed}/{total} ok, {dur}"


def span_distribution(trace: ExecutionTrace) -> str:
    """Show distribution of span types and statuses."""
    type_counts: dict[str, int] = {}
    status_counts: dict[str, int] = {}

    for s in trace.spans:
        type_counts[s.span_type.value] = type_counts.get(s.span_type.value, 0) + 1
        status_counts[s.status.value] = status_counts.get(s.status.value, 0) + 1

    lines = ["Span Distribution:"]

    # Type bars
    total = len(trace.spans) or 1
    for typ, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        bar_len = int(count / total * 30)
        bar = "█" * bar_len
        lines.append(f"  {typ:<10} {bar} {count}")

    lines.append("")
    lines.append("Status:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        icon = {"completed": "✅", "failed": "❌", "running": "🔄", "timeout": "⏰"}.get(status, "❓")
        lines.append(f"  {icon} {status}: {count}")

    return "\n".join(lines)


def _agent_summary_rows(trace: ExecutionTrace) -> list[dict]:
    """Extract agent span summaries for comparison."""
    rows = []
    for s in trace.spans:
        if s.span_type.value != "agent":
            continue
        dur = s.duration_ms
        rows.append({
            "name": s.name,
            "status": s.status.value if s.status else "unknown",
            "duration_ms": dur,
        })
    return rows


def _pad(text: str, width: int) -> str:
    """Left-align text, truncate if too long."""
    if len(text) > width:
        return text[:width - 1] + "…"
    return text.ljust(width)


def _status_icon(status: str) -> str:
    """Map status to icon."""
    return {"completed": "\u2713", "failed": "\u2717", "running": "\u25cb"}.get(status, "?")


def _diff_marker(left: dict, right: dict | None) -> str:
    """Return marker showing what changed between two agent rows."""
    if right is None:
        return " [+NEW]"
    if left is None:
        return " [-DEL]"
    markers = []
    if left["status"] != right["status"]:
        markers.append("status")
    ld = left.get("duration_ms") or 0
    rd = right.get("duration_ms") or 0
    if ld and rd and abs(ld - rd) / max(ld, rd, 1) > 0.2:
        markers.append(f"timing:{rd-ld:+.0f}ms")
    return f" [{', '.join(markers)}]" if markers else ""


def compare_view(
    trace_a: ExecutionTrace,
    trace_b: ExecutionTrace,
    label_a: str = "Baseline",
    label_b: str = "Candidate",
    col_width: int = 38,
) -> str:
    """Render two traces side-by-side with differences highlighted.

    Shows agent name, status icon, and duration for each trace.
    Highlights: status changes, timing differences (>20%), added/removed agents.

    Args:
        trace_a: Baseline trace (left side).
        trace_b: Candidate trace (right side).
        label_a: Label for baseline.
        label_b: Label for candidate.
        col_width: Width of each column.

    Returns:
        Multi-line string with side-by-side comparison.
    """
    rows_a = _agent_summary_rows(trace_a)
    rows_b = _agent_summary_rows(trace_b)

    map_a = {r["name"]: r for r in rows_a}
    map_b = {r["name"]: r for r in rows_b}
    all_names = list(dict.fromkeys(
        [r["name"] for r in rows_a] + [r["name"] for r in rows_b]
    ))

    sep = "│"
    header = _pad(label_a, col_width) + sep + _pad(label_b, col_width) + sep + " Diff"
    divider = "─" * col_width + "┼" + "─" * col_width + "┼" + "─" * 20

    lines = [
        f"# Trace Comparison: {label_a} vs {label_b}",
        "",
        header,
        divider,
    ]

    for name in all_names:
        a = map_a.get(name)
        b = map_b.get(name)
        left = _format_agent_cell(a, col_width) if a else _pad("(absent)", col_width)
        right = _format_agent_cell(b, col_width) if b else _pad("(absent)", col_width)
        diff = _diff_marker(a, b)
        lines.append(f"{left}{sep}{right}{sep}{diff}")

    # Summary
    lines.append(divider)
    added = len(set(map_b) - set(map_a))
    removed = len(set(map_a) - set(map_b))
    changed = _count_changes(map_a, map_b, all_names)
    lines.append(
        f"Summary: {len(all_names)} agents, "
        f"{changed} changed, {added} added, {removed} removed"
    )
    return "\n".join(lines)


def _format_agent_cell(row: dict, width: int) -> str:
    """Format one agent's info into a fixed-width cell."""
    icon = _status_icon(row["status"])
    dur = f"{row['duration_ms']:.0f}ms" if row.get("duration_ms") else "?ms"
    text = f"{icon} {row['name']} ({dur})"
    return _pad(text, width)


def _count_changes(
    map_a: dict, map_b: dict, all_names: list[str]
) -> int:
    """Count agents with status or significant timing differences."""
    count = 0
    for name in all_names:
        a, b = map_a.get(name), map_b.get(name)
        if a and b:
            if a["status"] != b["status"]:
                count += 1
            elif a.get("duration_ms") and b.get("duration_ms"):
                ad, bd = a["duration_ms"], b["duration_ms"]
                if abs(ad - bd) / max(ad, bd, 1) > 0.2:
                    count += 1
        elif a or b:
            count += 1
    return count


def agent_drill_down(
    trace: ExecutionTrace,
    agent_name: str,
    bar_width: int = 30,
) -> str:
    """Expand an agent to show individual tool/child timings.

    Answers the 'why is this agent slow?' follow-up to bottleneck
    analysis by breaking down time spent in each child span.

    Args:
        trace: The execution trace.
        agent_name: Name of the agent to drill into.
        bar_width: Width of the timing bar.

    Returns:
        Multi-line string with tool-level timing breakdown.
        Returns error message if agent not found.
    """
    agent_span = _find_agent_span(trace, agent_name)
    if agent_span is None:
        return f"Agent '{agent_name}' not found in trace."

    children = _get_sorted_children(trace, agent_span.span_id)
    agent_dur = agent_span.duration_ms or 0

    lines = _build_drill_header(agent_span, agent_dur, len(children))
    lines.extend(_build_child_rows(children, agent_dur, bar_width))
    lines.extend(_build_self_time(children, agent_dur, bar_width))
    return "\n".join(lines)


def _find_agent_span(
    trace: ExecutionTrace, agent_name: str
) -> Span | None:
    """Find the first agent span matching the name."""
    for s in trace.spans:
        if s.name == agent_name and s.span_type.value == "agent":
            return s
    return None


def _get_sorted_children(
    trace: ExecutionTrace, parent_id: str
) -> list[Span]:
    """Get child spans sorted by duration descending."""
    children = [
        s for s in trace.spans if s.parent_span_id == parent_id
    ]
    children.sort(key=lambda s: -(s.duration_ms or 0))
    return children


def _build_drill_header(
    agent_span: Span, agent_dur: float, child_count: int
) -> list[str]:
    """Build the header section of the drill-down view."""
    status = agent_span.status.value if agent_span.status else "unknown"
    icon = _status_icon(status)
    return [
        f"# Drill-down: {agent_span.name}",
        f"  Status: {icon} {status} | Duration: {agent_dur:.0f}ms | "
        f"Children: {child_count}",
        "",
        f"  {'Span':<20} {'Type':<10} {'Duration':>10} {'%':>6}  Bar",
        f"  {'─'*20} {'─'*10} {'─'*10} {'─'*6}  {'─'*30}",
    ]


def _build_child_rows(
    children: list[Span], parent_dur: float, bar_width: int
) -> list[str]:
    """Build rows for each child span with timing bars."""
    lines = []
    for child in children:
        dur = child.duration_ms or 0
        pct = (dur / parent_dur * 100) if parent_dur > 0 else 0
        bar_len = int(pct / 100 * bar_width)
        icon = _status_icon(child.status.value if child.status else "?")
        span_type = child.span_type.value if child.span_type else "?"
        bar_char = "▓" if child.status and child.status.value == "failed" else "█"
        bar = bar_char * max(bar_len, 1)
        name = child.name[:20]
        lines.append(
            f"  {icon} {name:<18} {span_type:<10} {dur:>8.0f}ms {pct:>5.1f}%  {bar}"
        )
    return lines


def _build_self_time(
    children: list[Span], parent_dur: float, bar_width: int
) -> list[str]:
    """Build the self-time row (time not in children)."""
    child_dur = sum(c.duration_ms or 0 for c in children)
    self_dur = max(parent_dur - child_dur, 0)
    self_pct = (self_dur / parent_dur * 100) if parent_dur > 0 else 0
    bar_len = int(self_pct / 100 * bar_width)
    return [
        f"  {'─'*20} {'─'*10} {'─'*10} {'─'*6}  {'─'*30}",
        f"  {'(self-time)':<20} {'':10} {self_dur:>8.0f}ms {self_pct:>5.1f}%  "
        f"{'░' * max(bar_len, 0)}",
    ]


def failure_timeline(
    trace: ExecutionTrace, width: int = 50
) -> str:
    """ASCII timeline showing failure propagation over time.

    Visualizes when failures occurred and how they spread,
    answering Q3: 'Which sub-agent failure started propagating?'

    Each row is a failed span. Timeline shows:
    - ▓ = failed span duration
    - → = propagation direction (parent to child)
    - 🛡 = contained (parent succeeded despite child failure)

    Args:
        trace: The execution trace.
        width: Width of the timeline bar area.

    Returns:
        Multi-line ASCII timeline string.
    """
    failed_spans = _get_failed_spans_sorted(trace)
    if not failed_spans:
        return "# Failure Timeline\n\nNo failures detected. ✓"

    time_range = _compute_time_range(trace)
    if time_range is None:
        return "# Failure Timeline\n\nCannot compute timeline (missing timestamps)."

    min_t, max_t = time_range
    span_map = {s.span_id: s for s in trace.spans}

    lines = _build_timeline_header(width)
    for span in failed_spans:
        row = _render_span_row(span, min_t, max_t, width, span_map)
        lines.append(row)

    lines.append(f"  {'─' * 22}┼{'─' * width}┤")
    lines.extend(_build_timeline_legend(failed_spans, span_map))
    return "\n".join(lines)


def _get_failed_spans_sorted(trace: ExecutionTrace) -> list[Span]:
    """Get failed spans sorted by start time."""
    failed = [s for s in trace.spans if s.status and s.status.value == "failed"]
    failed.sort(key=lambda s: s.started_at or "")
    return failed


def _compute_time_range(
    trace: ExecutionTrace,
) -> tuple[float, float] | None:
    """Compute min/max timestamps across all spans."""
    timestamps = []
    for s in trace.spans:
        if s.started_at:
            t = _parse_ts(s.started_at)
            if t is not None:
                timestamps.append(t)
        if s.ended_at:
            t = _parse_ts(s.ended_at)
            if t is not None:
                timestamps.append(t)
    if len(timestamps) < 2:
        return None
    return min(timestamps), max(timestamps)


def _build_timeline_header(width: int) -> list[str]:
    """Build the header for the timeline view."""
    return [
        "# Failure Timeline",
        "",
        f"  {'Span':<22}│{'early':^{width//2}}{'late':>{width - width//2}}│",
        f"  {'─' * 22}┼{'─' * width}┤",
    ]


def _render_span_row(
    span: Span, min_t: float, max_t: float,
    width: int, span_map: dict,
) -> str:
    """Render one failed span as a timeline row."""
    start = _parse_ts(span.started_at) or min_t
    end = _parse_ts(span.ended_at) or max_t
    duration = max_t - min_t
    if duration <= 0:
        duration = 1

    col_start = int((start - min_t) / duration * width)
    col_end = int((end - min_t) / duration * width)
    col_start = max(0, min(col_start, width - 1))
    col_end = max(col_start + 1, min(col_end, width))

    bar = [" "] * width
    for i in range(col_start, col_end):
        bar[i] = "▓"

    # Mark containment
    contained = _is_contained(span, span_map)
    suffix = " 🛡" if contained else " ✗"

    name = span.name[:20]
    return f"  {name:<22}│{''.join(bar)}│{suffix}"


def _is_contained(span: Span, span_map: dict) -> bool:
    """Check if a failed span was contained by its parent."""
    if not span.parent_span_id:
        return False
    parent = span_map.get(span.parent_span_id)
    if not parent:
        return False
    return parent.status and parent.status.value == "completed"


def _build_timeline_legend(
    failed_spans: list[Span], span_map: dict
) -> list[str]:
    """Build the legend/summary for the timeline."""
    contained = sum(1 for s in failed_spans if _is_contained(s, span_map))
    uncontained = len(failed_spans) - contained
    return [
        "",
        f"  Total failures: {len(failed_spans)} "
        f"(🛡 contained: {contained}, ✗ uncontained: {uncontained})",
        "  Legend: ▓ failed duration | 🛡 contained by parent | ✗ propagated",
    ]
