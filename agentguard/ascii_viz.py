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
