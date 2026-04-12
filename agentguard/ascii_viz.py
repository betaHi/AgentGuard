"""ASCII visualization — render traces as ASCII art for terminals.

Provides terminal-friendly visualizations:
- Gantt chart (horizontal bars showing timing)
- Dependency arrows
- Status indicators
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


def _parse_ts(iso: Optional[str]) -> Optional[float]:
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


def _diff_marker(left: dict, right: Optional[dict]) -> str:
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
