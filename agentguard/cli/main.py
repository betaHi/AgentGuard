"""AgentGuard CLI — command-line interface for trace inspection.

Usage:
    python -m agentguard.cli.main show <trace_file>
    python -m agentguard.cli.main list [--dir <traces_dir>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus


# ANSI color codes
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"


def _status_badge(status: str) -> str:
    """Render a colored status badge."""
    if status == "completed":
        return f"{C.BG_GREEN}{C.WHITE} ✓ PASS {C.RESET}"
    elif status == "failed":
        return f"{C.BG_RED}{C.WHITE} ✗ FAIL {C.RESET}"
    elif status == "timeout":
        return f"{C.YELLOW}⏱ TIMEOUT{C.RESET}"
    else:
        return f"{C.DIM}● {status}{C.RESET}"


def _type_icon(span_type: str) -> str:
    """Get icon for span type."""
    icons = {
        "agent": "🤖",
        "tool": "🔧",
        "llm_call": "🧠",
        "handoff": "🔀",
    }
    return icons.get(span_type, "●")


def _format_duration(ms: Optional[float]) -> str:
    """Format duration for display."""
    if ms is None:
        return f"{C.DIM}—{C.RESET}"
    if ms < 1000:
        return f"{ms:.0f}ms"
    elif ms < 60000:
        return f"{ms/1000:.1f}s"
    else:
        return f"{ms/60000:.1f}m"


def _render_span_tree(span: dict, indent: int = 0, is_last: bool = True, prefix: str = "") -> list[str]:
    """Render a span and its children as a tree."""
    lines = []
    
    # Tree connector
    if indent == 0:
        connector = ""
    elif is_last:
        connector = prefix + "└── "
    else:
        connector = prefix + "├── "
    
    # Child prefix
    if indent == 0:
        child_prefix = ""
    elif is_last:
        child_prefix = prefix + "    "
    else:
        child_prefix = prefix + "│   "
    
    # Span info
    icon = _type_icon(span.get("span_type", ""))
    name = span.get("name", "unknown")
    status = span.get("status", "running")
    duration = _format_duration(span.get("duration_ms"))
    badge = _status_badge(status)
    
    # Version info for agents
    version_str = ""
    meta = span.get("metadata", {})
    if meta.get("agent_version"):
        version_str = f" {C.DIM}({meta['agent_version']}){C.RESET}"
    
    line = f"{connector}{icon} {C.BOLD}{name}{C.RESET}{version_str}  {badge}  {C.CYAN}{duration}{C.RESET}"
    lines.append(line)
    
    # Error detail
    if span.get("error"):
        err_prefix = child_prefix + "   "
        lines.append(f"{err_prefix}{C.RED}⚠ {span['error']}{C.RESET}")
    
    # Children
    children = span.get("children", [])
    for i, child in enumerate(children):
        is_child_last = (i == len(children) - 1)
        lines.extend(_render_span_tree(child, indent + 1, is_child_last, child_prefix))
    
    return lines


def show_trace(filepath: str) -> None:
    """Display a trace file in a readable format."""
    path = Path(filepath)
    if not path.exists():
        print(f"{C.RED}Error: File not found: {filepath}{C.RESET}", file=sys.stderr)
        sys.exit(1)
    
    data = json.loads(path.read_text(encoding="utf-8"))
    trace = ExecutionTrace.from_dict(data)
    
    # Header
    print()
    print(f"{C.BOLD}{'═' * 60}{C.RESET}")
    print(f"{C.BOLD}  🛡️  AgentGuard Trace Report{C.RESET}")
    print(f"{C.BOLD}{'═' * 60}{C.RESET}")
    print()
    
    # Trace info
    print(f"  {C.DIM}Trace ID:{C.RESET}    {trace.trace_id}")
    print(f"  {C.DIM}Task:{C.RESET}        {trace.task or '(unnamed)'}")
    print(f"  {C.DIM}Trigger:{C.RESET}     {trace.trigger}")
    print(f"  {C.DIM}Status:{C.RESET}      {_status_badge(trace.status.value)}")
    print(f"  {C.DIM}Duration:{C.RESET}    {C.CYAN}{_format_duration(trace.duration_ms)}{C.RESET}")
    print(f"  {C.DIM}Agents:{C.RESET}      {len(trace.agent_spans)}")
    print(f"  {C.DIM}Tool calls:{C.RESET}  {len(trace.tool_spans)}")
    print(f"  {C.DIM}Total spans:{C.RESET} {len(trace.spans)}")
    print()
    
    # Timeline
    print(f"  {C.BOLD}Execution Timeline{C.RESET}")
    print(f"  {'─' * 50}")
    
    # Build tree and render
    tree_data = data.copy()
    # Rebuild tree from flat spans
    span_map = {}
    for s in tree_data.get("spans", []):
        s["children"] = []
        span_map[s["span_id"]] = s
    
    roots = []
    for s in tree_data.get("spans", []):
        parent_id = s.get("parent_span_id")
        if parent_id and parent_id in span_map:
            span_map[parent_id]["children"].append(s)
        else:
            roots.append(s)
    
    for i, root in enumerate(roots):
        is_last = (i == len(roots) - 1)
        lines = _render_span_tree(root, 0, is_last, "  ")
        for line in lines:
            print(f"  {line}")
    
    print()
    print(f"{C.BOLD}{'═' * 60}{C.RESET}")
    print()


def list_traces(directory: str = ".agentguard/traces") -> None:
    """List all trace files in a directory."""
    dir_path = Path(directory)
    if not dir_path.exists():
        print(f"{C.YELLOW}No traces found in {directory}{C.RESET}")
        return
    
    files = sorted(dir_path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print(f"{C.YELLOW}No traces found in {directory}{C.RESET}")
        return
    
    print()
    print(f"{C.BOLD}  🛡️  AgentGuard Traces{C.RESET}")
    print(f"  {'─' * 50}")
    
    for f in files[:20]:
        data = json.loads(f.read_text(encoding="utf-8"))
        status = data.get("status", "unknown")
        task = data.get("task", "(unnamed)")
        spans = len(data.get("spans", []))
        duration = _format_duration(data.get("duration_ms"))
        badge = _status_badge(status)
        
        print(f"  {badge}  {C.BOLD}{task}{C.RESET}  {C.CYAN}{duration}{C.RESET}  {C.DIM}({spans} spans)  {f.name}{C.RESET}")
    
    print()


def main():
    parser = argparse.ArgumentParser(
        prog="agentguard",
        description="🛡️ AgentGuard — Record, Replay, Evaluate, and Guard your AI Agents.",
    )
    subparsers = parser.add_subparsers(dest="command")
    
    # show
    show_parser = subparsers.add_parser("show", help="Display a trace file")
    show_parser.add_argument("file", help="Path to trace JSON file")
    
    # list
    list_parser = subparsers.add_parser("list", help="List recorded traces")
    list_parser.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    
    args = parser.parse_args()
    
    if args.command == "show":
        show_trace(args.file)
    elif args.command == "list":
        list_traces(args.dir)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
