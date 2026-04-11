"""AgentGuard CLI — command-line interface.

Usage:
    agentguard show <trace_file>      Show a trace
    agentguard list [--dir DIR]       List traces
    agentguard eval <trace_file>      Evaluate a trace against rules
    agentguard report [--dir DIR]     Generate HTML report
    agentguard guard [--dir DIR]      Start continuous monitoring
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.core.eval_schema import EvaluationResult, RuleVerdict


# ANSI color codes
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BG_RED = "\033[41m"
    BG_GREEN = "\033[42m"


def _status_badge(status: str) -> str:
    if status == "completed":
        return f"{C.BG_GREEN}{C.WHITE} ✓ PASS {C.RESET}"
    elif status == "failed":
        return f"{C.BG_RED}{C.WHITE} ✗ FAIL {C.RESET}"
    elif status == "timeout":
        return f"{C.YELLOW}⏱ TIMEOUT{C.RESET}"
    return f"{C.DIM}● {status}{C.RESET}"


def _type_icon(span_type: str) -> str:
    return {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}.get(span_type, "●")


def _fmt_duration(ms: Optional[float]) -> str:
    if ms is None: return f"{C.DIM}—{C.RESET}"
    if ms < 1000: return f"{ms:.0f}ms"
    if ms < 60000: return f"{ms/1000:.1f}s"
    return f"{ms/60000:.1f}m"


def _render_tree(span: dict, indent: int = 0, is_last: bool = True, prefix: str = "") -> list[str]:
    lines = []
    connector = "" if indent == 0 else (prefix + "└── " if is_last else prefix + "├── ")
    child_prefix = "" if indent == 0 else (prefix + "    " if is_last else prefix + "│   ")
    
    icon = _type_icon(span.get("span_type", ""))
    name = span.get("name", "unknown")
    status = span.get("status", "running")
    duration = _fmt_duration(span.get("duration_ms"))
    badge = _status_badge(status)
    version = span.get("metadata", {}).get("agent_version", "")
    ver_str = f" {C.DIM}({version}){C.RESET}" if version else ""
    
    lines.append(f"{connector}{icon} {C.BOLD}{name}{C.RESET}{ver_str}  {badge}  {C.CYAN}{duration}{C.RESET}")
    
    if span.get("error"):
        lines.append(f"{child_prefix}   {C.RED}⚠ {span['error']}{C.RESET}")
    
    children = span.get("children", [])
    for i, child in enumerate(children):
        lines.extend(_render_tree(child, indent + 1, i == len(children) - 1, child_prefix))
    return lines


def cmd_show(args):
    """Display a trace file."""
    path = Path(args.file)
    if not path.exists():
        print(f"{C.RED}Error: File not found: {args.file}{C.RESET}", file=sys.stderr)
        sys.exit(1)
    
    data = json.loads(path.read_text(encoding="utf-8"))
    trace = ExecutionTrace.from_dict(data)
    
    print(f"\n{C.BOLD}{'═' * 60}{C.RESET}")
    print(f"{C.BOLD}  🛡️  AgentGuard Trace Report{C.RESET}")
    print(f"{C.BOLD}{'═' * 60}{C.RESET}\n")
    print(f"  {C.DIM}Trace ID:{C.RESET}    {trace.trace_id}")
    print(f"  {C.DIM}Task:{C.RESET}        {trace.task or '(unnamed)'}")
    print(f"  {C.DIM}Trigger:{C.RESET}     {trace.trigger}")
    print(f"  {C.DIM}Status:{C.RESET}      {_status_badge(trace.status.value)}")
    print(f"  {C.DIM}Duration:{C.RESET}    {C.CYAN}{_fmt_duration(trace.duration_ms)}{C.RESET}")
    print(f"  {C.DIM}Agents:{C.RESET}      {len(trace.agent_spans)}")
    print(f"  {C.DIM}Tool calls:{C.RESET}  {len(trace.tool_spans)}")
    print(f"  {C.DIM}Total spans:{C.RESET} {len(trace.spans)}\n")
    print(f"  {C.BOLD}Execution Timeline{C.RESET}")
    print(f"  {'─' * 50}")
    
    # Build tree
    span_map = {s["span_id"]: {**s, "children": []} for s in data.get("spans", [])}
    roots = []
    for s in data.get("spans", []):
        pid = s.get("parent_span_id")
        if pid and pid in span_map:
            span_map[pid]["children"].append(span_map[s["span_id"]])
        else:
            roots.append(span_map[s["span_id"]])
    
    for i, root in enumerate(roots):
        for line in _render_tree(root, 0, i == len(roots) - 1, "  "):
            print(f"  {line}")
    
    print(f"\n{C.BOLD}{'═' * 60}{C.RESET}\n")


def cmd_list(args):
    """List trace files."""
    dir_path = Path(args.dir)
    if not dir_path.exists():
        print(f"{C.YELLOW}No traces found in {args.dir}{C.RESET}")
        return
    
    files = sorted(dir_path.glob("*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        print(f"{C.YELLOW}No traces found in {args.dir}{C.RESET}")
        return
    
    print(f"\n{C.BOLD}  🛡️  AgentGuard Traces{C.RESET}")
    print(f"  {'─' * 50}")
    for f in files[:20]:
        data = json.loads(f.read_text(encoding="utf-8"))
        badge = _status_badge(data.get("status", "unknown"))
        task = data.get("task", "(unnamed)")
        spans = len(data.get("spans", []))
        dur = _fmt_duration(data.get("duration_ms"))
        print(f"  {badge}  {C.BOLD}{task}{C.RESET}  {C.CYAN}{dur}{C.RESET}  {C.DIM}({spans} spans)  {f.name}{C.RESET}")
    print()


def cmd_eval(args):
    """Evaluate a trace against rules."""
    path = Path(args.file)
    if not path.exists():
        print(f"{C.RED}Error: File not found: {args.file}{C.RESET}", file=sys.stderr)
        sys.exit(1)
    
    data = json.loads(path.read_text(encoding="utf-8"))
    trace = ExecutionTrace.from_dict(data)
    
    # Load rules from config or CLI
    rules = []
    config_path = Path(args.config) if args.config else Path("agentguard.json")
    if config_path.exists():
        config = json.loads(config_path.read_text(encoding="utf-8"))
        for agent_cfg in config.get("agents", []):
            for test in agent_cfg.get("tests", []):
                rules.extend(test.get("assertions", []))
    
    if not rules:
        # Default rules if no config
        rules = [
            {"type": "min_count", "target": "output_data", "value": 1, "name": "has-output"},
        ]
    
    from agentguard.eval.rules import evaluate_rules
    
    print(f"\n{C.BOLD}  🛡️  AgentGuard Evaluation{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Trace:{C.RESET} {trace.trace_id}")
    print(f"  {C.DIM}Task:{C.RESET}  {trace.task}\n")
    
    for span in trace.agent_spans:
        output = span.output_data or {}
        results = evaluate_rules(output, rules)
        
        passed = sum(1 for r in results if r.verdict.value == "pass")
        total = len(results)
        overall = "pass" if passed == total else "fail"
        badge = _status_badge("completed" if overall == "pass" else "failed")
        
        print(f"  {_type_icon('agent')} {C.BOLD}{span.name}{C.RESET}  {badge}  ({passed}/{total} rules)")
        for r in results:
            icon = f"{C.GREEN}✓{C.RESET}" if r.verdict.value == "pass" else f"{C.RED}✗{C.RESET}"
            print(f"    {icon} {r.name}: {r.verdict.value}")
            if r.detail:
                print(f"      {C.DIM}{r.detail}{C.RESET}")
    print()


def cmd_report(args):
    """Generate HTML report."""
    from agentguard.web.viewer import generate_timeline_html
    output = generate_timeline_html(traces_dir=args.dir, output=args.output)
    print(f"  🌐 Report generated: {output}")


def cmd_guard(args):
    """Start continuous monitoring."""
    from agentguard.guard import Guard, StdoutAlert, FileAlert
    
    handlers = [StdoutAlert()]
    if args.log:
        handlers.append(FileAlert(args.log))
    
    guard = Guard(
        traces_dir=args.dir,
        alert_handlers=handlers,
        fail_threshold=args.threshold,
    )
    guard.watch(interval=args.interval)


def main():
    parser = argparse.ArgumentParser(
        prog="agentguard",
        description="🛡️ AgentGuard — Record, Replay, Evaluate, and Guard your AI Agents.",
    )
    sub = parser.add_subparsers(dest="command")
    
    # show
    p = sub.add_parser("show", help="Display a trace file")
    p.add_argument("file", help="Path to trace JSON file")
    
    # list
    p = sub.add_parser("list", help="List recorded traces")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    
    # eval
    p = sub.add_parser("eval", help="Evaluate a trace against rules")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--config", help="Path to config file (agentguard.json)")
    
    # report
    p = sub.add_parser("report", help="Generate HTML report")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    p.add_argument("--output", default=".agentguard/report.html", help="Output HTML path")
    
    # guard
    p = sub.add_parser("guard", help="Start continuous monitoring")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    p.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    p.add_argument("--threshold", type=int, default=3, help="Consecutive failures before critical alert")
    p.add_argument("--log", help="Alert log file path")
    
    args = parser.parse_args()
    
    cmds = {"show": cmd_show, "list": cmd_list, "eval": cmd_eval, "report": cmd_report, "guard": cmd_guard}
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
