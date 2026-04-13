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

def _load_trace_file(filepath: str) -> ExecutionTrace:
    """Load and parse a trace JSON file with user-friendly error messages.

    Args:
        filepath: Path to the trace JSON file.

    Returns:
        Parsed ExecutionTrace.

    Raises:
        SystemExit: If file not found or JSON is invalid.
    """
    path = Path(filepath)
    if not path.exists():
        print(f"{C.RED}Error: File not found: {filepath}{C.RESET}", file=sys.stderr)
        sys.exit(1)
    try:
        text = path.read_text(encoding="utf-8")
    except PermissionError:
        print(f"{C.RED}Error: Permission denied reading: {filepath}{C.RESET}", file=sys.stderr)
        sys.exit(1)
    except OSError as e:
        print(f"{C.RED}Error: Cannot read file: {filepath} ({e}){C.RESET}", file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"{C.RED}Error: Invalid JSON in {filepath}: {e.args[0]}{C.RESET}", file=sys.stderr)
        sys.exit(1)
    try:
        return ExecutionTrace.from_dict(data)
    except (KeyError, TypeError, ValueError) as e:
        print(f"{C.RED}Error: Invalid trace format in {filepath}: {e}{C.RESET}", file=sys.stderr)
        sys.exit(1)




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
    trace = _load_trace_file(args.file)
    data = json.loads(Path(args.file).read_text(encoding="utf-8"))
    
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
    trace = _load_trace_file(args.file)
    
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
        has_failures = False
        for r in results:
            if r.verdict.value == 'fail':
                has_failures = True
            icon = f"{C.GREEN}✓{C.RESET}" if r.verdict.value == "pass" else f"{C.RED}✗{C.RESET}"
            print(f"    {icon} {r.name}: {r.verdict.value}")
            if r.detail:
                print(f"      {C.DIM}{r.detail}{C.RESET}")
    print()
    if has_failures:
        sys.exit(1)


def cmd_search(args):
    """Search spans across all traces."""
    from agentguard.query import TraceStore
    
    store = TraceStore(args.dir)
    traces = store.load_all()
    
    matches = []
    for t in traces:
        for s in t.spans:
            if args.name and args.name.lower() not in s.name.lower():
                continue
            if args.type and s.span_type.value != args.type:
                continue
            if args.failed and s.status.value != "failed":
                continue
            matches.append((t, s))
    
    print(f"\n{C.BOLD}  🔍 Span Search Results ({len(matches)} matches){C.RESET}")
    line = "─" * 50
    print(f"  {line}")
    
    for t, s in matches[:20]:
        badge = _status_badge(s.status.value)
        dur = _fmt_duration(s.duration_ms)
        print(f"  {_type_icon(s.span_type.value)} {C.BOLD}{s.name}{C.RESET} {badge} {C.CYAN}{dur}{C.RESET}")
        print(f"    {C.DIM}trace: {t.task} ({t.trace_id}){C.RESET}")
        if s.error:
            print(f"    {C.RED}⚠ {s.error[:60]}{C.RESET}")
    print()


def cmd_merge(args):
    """Merge distributed child traces into parent."""
    from agentguard.sdk.distributed import merge_child_traces
    
    trace = _load_trace_file(args.file)
    traces_dir = str(Path(args.file).parent)
    
    merged = merge_child_traces(trace, traces_dir, cleanup=not args.keep)
    print(f"  Merged {len(merged.spans)} spans into {args.file}")
    if not args.keep:
        print(f"  Child files cleaned up")


def cmd_merge_dir(args):
    """Merge all trace files in a directory into a single trace."""
    dir_path = Path(args.dir)
    if not dir_path.exists():
        print(f"{C.RED}Error: Directory not found: {args.dir}{C.RESET}", file=sys.stderr)
        sys.exit(1)

    files = sorted(dir_path.glob("*.json"), key=lambda f: f.stat().st_mtime)
    if not files:
        print(f"{C.YELLOW}No trace files found in {args.dir}{C.RESET}")
        return

    # Load all traces
    traces = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            traces.append(ExecutionTrace.from_dict(data))
        except Exception as e:
            print(f"  {C.YELLOW}⚠ Skipping {f.name}: {e}{C.RESET}")

    if not traces:
        print(f"{C.YELLOW}No valid traces found in {args.dir}{C.RESET}")
        return

    # Merge: use first trace as base, append spans from the rest
    merged = traces[0]
    for t in traces[1:]:
        for span in t.spans:
            span.trace_id = merged.trace_id
            merged.spans.append(span)

    # Update duration to cover all spans
    if merged.ended_at and len(traces) > 1:
        latest_end = max(
            (t.ended_at for t in traces if t.ended_at),
            default=merged.ended_at,
        )
        merged.ended_at = latest_end

    # Write merged trace
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(merged.to_json(), encoding="utf-8")

    print(f"  {C.GREEN}✓{C.RESET} Merged {len(traces)} traces ({len(merged.spans)} total spans)")
    print(f"  {C.DIM}Output:{C.RESET} {output}")


def cmd_validate(args):
    """Validate trace integrity."""
    from agentguard.validate import validate_trace
    
    trace = _load_trace_file(args.file)
    result = validate_trace(trace)
    
    print(f"\n{C.BOLD}  🔍 Trace Validation{C.RESET}")
    line = "─" * 50
    print(f"  {line}")
    
    if result.valid:
        print(f"  {C.GREEN}✓ Valid{C.RESET} ({len(result.warnings)} warnings)")
    else:
        print(f"  {C.RED}✗ Invalid{C.RESET} ({len(result.errors)} errors, {len(result.warnings)} warnings)")
    
    for issue in result.issues:
        icon = f"{C.RED}✗{C.RESET}" if issue.severity == "error" else f"{C.YELLOW}⚠{C.RESET}"
        span_info = f" [{issue.span_id}]" if issue.span_id else ""
        print(f"    {icon}{span_info} {issue.message}")
    
    print()
    if not result.valid:
        sys.exit(1)


def cmd_diff(args):
    """Compare two traces side by side."""
    from agentguard.diff import diff_traces
    
    trace_a = _load_trace_file(args.trace_a)
    trace_b = _load_trace_file(args.trace_b)
    
    result = diff_traces(trace_a, trace_b)
    
    print(f"\n{C.BOLD}  🔍 Trace Diff{C.RESET}")
    line = "─" * 50
    print(f"  {line}")
    print(f"  {C.DIM}Trace A:{C.RESET} {trace_a.trace_id} ({trace_a.task})")
    print(f"  {C.DIM}Trace B:{C.RESET} {trace_b.trace_id} ({trace_b.task})")
    print(f"  {C.DIM}Changes:{C.RESET} {len(result.diffs)}")
    print(f"  {C.GREEN}Improvements:{C.RESET} {len(result.improvements)}")
    print(f"  {C.RED}Regressions:{C.RESET}  {len(result.regressions)}")
    
    if result.spans_added:
        print(f"\n  {C.GREEN}+ Spans added:{C.RESET}")
        for s in result.spans_added:
            print(f"    + {s}")
    
    if result.spans_removed:
        print(f"\n  {C.RED}- Spans removed:{C.RESET}")
        for s in result.spans_removed:
            print(f"    - {s}")
    
    if result.diffs:
        print(f"\n  {C.BOLD}Changes:{C.RESET}")
        for d in result.diffs:
            icon = f"{C.GREEN}📈{C.RESET}" if d.verdict == "improved" else f"{C.RED}📉{C.RESET}" if d.verdict == "regressed" else "🔄"
            print(f"    {icon} {C.BOLD}{d.name}{C.RESET} ({d.span_type}) — {d.field}: {d.value_a} → {d.value_b}")
    
    if not result.has_changes:
        print(f"\n  {C.GREEN}No differences found.{C.RESET}")
    
    print()


def _output_structured_json(trace) -> None:
    """Output ALL analysis results as structured JSON.

    Matches exactly what the HTML viewer renders, ensuring
    CLI and viewer produce identical diagnostic data.
    """
    import json
    from agentguard.analysis import (
        analyze_failures, analyze_flow, analyze_bottleneck,
        analyze_context_flow, analyze_retries, analyze_cost,
        analyze_cost_yield, analyze_decisions,
    )
    from agentguard.propagation import analyze_propagation
    from agentguard.scoring import score_trace

    result = _build_analysis_dict(trace)
    print(json.dumps(result, indent=2, default=str))


def _build_analysis_dict(trace) -> dict:
    """Build the complete analysis dictionary for JSON output."""
    from agentguard.analysis import (
        analyze_failures, analyze_flow, analyze_bottleneck,
        analyze_context_flow, analyze_cost_yield, analyze_decisions,
    )
    from agentguard.propagation import analyze_propagation
    from agentguard.scoring import score_trace

    failures = analyze_failures(trace)
    flow = analyze_flow(trace)
    bn = analyze_bottleneck(trace) if trace.agent_spans else None
    ctx = analyze_context_flow(trace)
    cost_yield = analyze_cost_yield(trace)
    decisions = analyze_decisions(trace)
    propagation = analyze_propagation(trace)
    score = score_trace(trace)

    return {
        "trace": _build_trace_metadata(trace),
        "score": {"overall": score.overall, "grade": score.grade},
        "failures": failures.to_dict(),
        "flow": flow.to_dict(),
        "bottleneck": bn.to_dict() if bn else None,
        "context_flow": ctx.to_dict(),
        "cost_yield": cost_yield.to_dict(),
        "decisions": decisions.to_dict(),
        "propagation": propagation.to_dict(),
    }


def _build_trace_metadata(trace) -> dict:
    """Extract trace metadata matching the viewer header."""
    return {
        "task": trace.task,
        "trigger": trace.trigger,
        "duration_ms": trace.duration_ms,
        "span_count": len(trace.spans),
        "agent_count": len(trace.agent_spans),
        "tool_count": sum(
            1 for s in trace.spans if s.span_type.value == "tool"
        ),
        "handoff_count": sum(
            1 for s in trace.spans if s.span_type.value == "handoff"
        ),
        "failed_count": sum(
            1 for s in trace.spans
            if s.status and s.status.value == "failed"
        ),
        "status": trace.status.value if trace.status else "unknown",
    }


def cmd_analyze(args):
    """Analyze failure propagation and flow in a trace."""
    trace = _load_trace_file(args.file)

    if getattr(args, 'json', False):
        _output_structured_json(trace)
        return
    
    from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck, analyze_context_flow, analyze_retries, analyze_cost, analyze_timing
    
    # Failure analysis
    failures = analyze_failures(trace)
    print(f"\n{C.BOLD}  🔍 Failure Propagation Analysis{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Failed spans:{C.RESET}     {failures.total_failed_spans}")
    print(f"  {C.DIM}Root causes:{C.RESET}      {len(failures.root_causes)}")
    print(f"  {C.DIM}Blast radius:{C.RESET}     {failures.blast_radius} spans")
    print(f"  {C.DIM}Handled:{C.RESET}          {failures.handled_count}")
    print(f"  {C.DIM}Unhandled:{C.RESET}        {failures.unhandled_count}")
    
    score = failures.resilience_score
    color = C.GREEN if score >= 0.7 else (C.YELLOW if score >= 0.3 else C.RED)
    print(f"  {C.DIM}Resilience:{C.RESET}       {color}{score:.0%}{C.RESET}")
    
    for rc in failures.root_causes:
        icon = f"{C.YELLOW}🟡{C.RESET}" if rc.was_handled else f"{C.RED}🔴{C.RESET}"
        handled_str = f"{C.GREEN}(handled){C.RESET}" if rc.was_handled else f"{C.RED}(unhandled){C.RESET}"
        print(f"\n  {icon} {C.BOLD}{rc.span_name}{C.RESET} [{rc.span_type}] {handled_str}")
        print(f"     {C.DIM}{rc.error}{C.RESET}")
        if rc.affected_children:
            print(f"     {C.DIM}→ {len(rc.affected_children)} downstream spans affected{C.RESET}")
    
    # Flow analysis
    flow = analyze_flow(trace)
    print(f"\n{C.BOLD}  📊 Flow Analysis{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Agents:{C.RESET}           {flow.agent_count}")
    print(f"  {C.DIM}Tools:{C.RESET}            {flow.tool_count}")
    print(f"  {C.DIM}Handoffs:{C.RESET}         {len(flow.handoffs)}")
    print(f"  {C.DIM}Critical path:{C.RESET}    {' → '.join(flow.critical_path)}")
    
    for h in flow.handoffs:
        ctx_str = f"{h.context_size_bytes}B" if h.context_size_bytes else "?"
        print(f"\n  🔀 {C.BOLD}{h.from_agent}{C.RESET} → {C.BOLD}{h.to_agent}{C.RESET}  ({ctx_str})")
        if h.context_keys:
            print(f"     {C.DIM}context: {h.context_keys}{C.RESET}")
    
    print()



def cmd_propagation(args):
    """Analyze failure propagation with causal chains."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.propagation import analyze_propagation
    
    trace = _load_trace_file(args.file)
    result = analyze_propagation(trace)
    print(result.to_report())


def cmd_flowgraph(args):
    """Build and display multi-agent flow graph."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.flowgraph import build_flow_graph
    
    trace = _load_trace_file(args.file)
    graph = build_flow_graph(trace)
    
    if args.mermaid:
        print(graph.to_mermaid())
    else:
        print(graph.to_report())


def cmd_context_flow(args):
    """Analyze context flow through the agent pipeline."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.context_flow import analyze_context_flow_deep
    
    trace = _load_trace_file(args.file)
    result = analyze_context_flow_deep(trace)
    print(result.to_report())


def cmd_score(args):
    """Score a trace on quality dimensions."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.scoring import score_trace
    
    trace = _load_trace_file(args.file)
    expected = args.expected_ms if hasattr(args, 'expected_ms') and args.expected_ms else None
    score = score_trace(trace, expected_duration_ms=expected)
    print(score.to_report())


def cmd_aggregate(args):
    """Aggregate analysis across multiple traces."""
    import os, json
    from agentguard.core.trace import ExecutionTrace
    from agentguard.aggregate import aggregate_traces
    
    traces_dir = args.dir
    traces = []
    if os.path.isdir(traces_dir):
        for f in sorted(os.listdir(traces_dir)):
            if f.endswith(".json"):
                try:
                    data = json.loads(open(os.path.join(traces_dir, f)).read())
                    traces.append(ExecutionTrace.from_dict(data))
                except Exception:
                    pass
    
    if not traces:
        print("No traces found.")
        return
    
    result = aggregate_traces(traces)
    print(result.to_report())


def cmd_annotate(args):
    """Auto-annotate a trace."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.annotations import auto_annotate
    
    trace = _load_trace_file(args.file)
    store = auto_annotate(trace)
    summary = store.summary()
    
    print(f"Annotations: {summary['total']}")
    print(f"  By severity: {summary['by_severity']}")
    print(f"  By category: {summary['by_category']}")
    
    for span_id, anns in store.to_dict().items():
        for ann in anns:
            icon = {"info": "ℹ️", "warning": "⚠️", "error": "🔴", "critical": "💀"}.get(ann["severity"], "📎")
            print(f"  {icon} [{ann['category']}] {ann['message']}")


def cmd_correlate(args):
    """Analyze span correlations."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.correlation import analyze_correlations
    
    trace = _load_trace_file(args.file)
    result = analyze_correlations(trace)
    print(result.to_report())



def cmd_timeline(args):
    """Display trace as chronological event timeline."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.timeline import build_timeline
    
    trace = _load_trace_file(args.file)
    tl = build_timeline(trace)
    print(tl.to_text(max_events=args.max or 50))


def cmd_metrics(args):
    """Extract metrics from a trace."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.metrics import extract_metrics
    import json as _json
    
    trace = _load_trace_file(args.file)
    m = extract_metrics(trace)
    
    if args.prometheus:
        print(m.to_prometheus())
    else:
        print(_json.dumps(m.to_dict(), indent=2))


def cmd_schema(args):
    """Print the trace JSON schema."""
    from agentguard.schema import get_schema
    import json as _json
    print(_json.dumps(get_schema(), indent=2))



def cmd_span_diff(args):
    """Span-level diff between two traces."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.span_diff import diff_spans
    
    trace_a = _load_trace_file(args.trace_a)
    trace_b = _load_trace_file(args.trace_b)
    result = diff_spans(trace_a, trace_b)
    print(result.to_report())


def cmd_sla(args):
    """Check trace against SLA constraints."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.sla import SLAChecker
    
    trace = _load_trace_file(args.file)
    checker = SLAChecker()
    
    if args.max_duration:
        checker.max_duration_ms(args.max_duration)
    if args.min_score:
        checker.min_score(args.min_score)
    if args.max_cost:
        checker.max_cost_usd(args.max_cost)
    if args.max_error_rate:
        checker.max_error_rate(args.max_error_rate)
    
    result = checker.check(trace)
    print(result.to_report())


def cmd_dependencies(args):
    """Show agent dependency graph."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.dependency import build_dependency_graph
    
    trace = _load_trace_file(args.file)
    graph = build_dependency_graph(trace)
    
    if args.mermaid:
        print(graph.to_mermaid())
    else:
        print(graph.to_report())


def cmd_benchmark(args):
    """Run performance benchmark on analysis modules."""
    from agentguard.benchmark import run_benchmark
    suite = run_benchmark(trace_count=args.traces, agents_per_trace=args.agents)
    print(suite.to_report())


def cmd_generate(args):
    """Generate synthetic traces."""
    from agentguard.generate import generate_trace
    from agentguard.store import TraceStore
    
    store = TraceStore(directory=args.dir)
    for i in range(args.count):
        trace = generate_trace(agents=args.agents, failure_rate=args.failure_rate, seed=i)
        path = store.save(trace)
        print(f"  Generated: {trace.trace_id} ({len(trace.spans)} spans)")
    print(f"Saved {args.count} traces to {args.dir}")


def cmd_summarize(args):
    """Summarize a trace in natural language."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.summarize import summarize_trace, summarize_brief
    
    trace = _load_trace_file(args.file)
    if args.brief:
        print(summarize_brief(trace))
    else:
        print(summarize_trace(trace))


def cmd_tree(args):
    """Display trace as indented tree."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.tree import tree_to_text
    
    trace = _load_trace_file(args.file)
    print(tree_to_text(trace))


def cmd_compare(args):
    """Compare two traces comprehensively."""
    from agentguard.core.trace import ExecutionTrace
    from agentguard.comparison import compare_traces
    
    trace_a = _load_trace_file(args.trace_a)
    trace_b = _load_trace_file(args.trace_b)
    result = compare_traces(trace_a, trace_b)
    print(result.to_report())



def cmd_init(args):
    """Scaffold a new AgentGuard project with default config and directories."""
    traces_dir = Path(".agentguard/traces")
    config_file = Path("agentguard.json")

    created = []

    # Create traces directory
    if not traces_dir.exists():
        traces_dir.mkdir(parents=True, exist_ok=True)
        created.append(str(traces_dir))

    # Create default config
    if not config_file.exists():
        default_config = {
            "traces_dir": ".agentguard/traces",
            "report_output": ".agentguard/report.html",
            "agents": [],
        }
        config_file.write_text(json.dumps(default_config, indent=2) + "\n", encoding="utf-8")
        created.append(str(config_file))
    else:
        print(f"  {C.YELLOW}⚠ {config_file} already exists, skipping{C.RESET}")

    if created:
        print(f"\n  {C.GREEN}🛡️  AgentGuard initialized!{C.RESET}")
        for f in created:
            print(f"  {C.GREEN}+{C.RESET} {f}")
        print(f"\n  Next steps:")
        print(f"    1. Add @record_agent / @record_tool decorators to your code")
        print(f"    2. Run your agents")
        print(f"    3. agentguard list")
        print()
    else:
        print(f"\n  {C.DIM}Already initialized — nothing to do.{C.RESET}\n")


def cmd_doctor(args):
    """Check AgentGuard installation health and environment."""
    import platform

    print(f"\n  {C.BOLD}🛡️  AgentGuard Doctor{C.RESET}")
    print(f"  {'─' * 50}")

    all_ok = True

    # 1. Python version
    py_ver = platform.python_version()
    py_ok = tuple(int(x) for x in py_ver.split(".")[:2]) >= (3, 11)
    icon = f"{C.GREEN}✓{C.RESET}" if py_ok else f"{C.RED}✗{C.RESET}"
    if not py_ok:
        all_ok = False
    print(f"  {icon} Python {py_ver} {'(>= 3.11 required)' if not py_ok else ''}")

    # 2. AgentGuard importable
    try:
        from agentguard import __version__
        print(f"  {C.GREEN}✓{C.RESET} AgentGuard {__version__}")
    except ImportError as e:
        print(f"  {C.RED}✗{C.RESET} AgentGuard import failed: {e}")
        all_ok = False

    # 3. Core modules
    core_modules = [
        ("agentguard.core.trace", "Trace schema"),
        ("agentguard.sdk.decorators", "SDK decorators"),
        ("agentguard.sdk.context", "SDK context managers"),
        ("agentguard.sdk.distributed", "Distributed tracing"),
        ("agentguard.analysis", "Analysis engine"),
        ("agentguard.web.viewer", "HTML viewer"),
    ]
    for mod_name, label in core_modules:
        try:
            __import__(mod_name)
            print(f"  {C.GREEN}✓{C.RESET} {label} ({mod_name})")
        except ImportError as e:
            print(f"  {C.RED}✗{C.RESET} {label} ({mod_name}): {e}")
            all_ok = False

    # 4. Traces directory
    traces_dir = Path(".agentguard/traces")
    if traces_dir.exists():
        trace_count = len(list(traces_dir.glob("*.json")))
        print(f"  {C.GREEN}✓{C.RESET} Traces directory ({trace_count} traces)")
    else:
        print(f"  {C.YELLOW}⚠{C.RESET} Traces directory not found (run: agentguard init)")

    # 5. Config file
    config_path = Path("agentguard.json")
    if config_path.exists():
        try:
            json.loads(config_path.read_text(encoding="utf-8"))
            print(f"  {C.GREEN}✓{C.RESET} Config file (agentguard.json)")
        except json.JSONDecodeError as e:
            print(f"  {C.RED}✗{C.RESET} Config file has invalid JSON: {e.args[0]}")
            all_ok = False
    else:
        print(f"  {C.YELLOW}⚠{C.RESET} Config file not found (run: agentguard init)")

    # Summary
    if all_ok:
        print(f"\n  {C.GREEN}All checks passed!{C.RESET}\n")
    else:
        print(f"\n  {C.RED}Some checks failed. See above for details.{C.RESET}\n")
        sys.exit(1)


def cmd_version(args):
    """Show AgentGuard version."""
    from agentguard import __version__
    print(f"AgentGuard {__version__}")



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
    
    # init
    sub.add_parser("init", help="Initialize AgentGuard in current directory")

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
    
    # doctor
    sub.add_parser("doctor", help="Check installation health")

    # version
    sub.add_parser("version", help="Show version")
    
    # report
    p = sub.add_parser("report", help="Generate HTML report")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    p.add_argument("--output", default=".agentguard/report.html", help="Output HTML path")
    
    # search
    p = sub.add_parser("search", help="Search spans across traces")
    p.add_argument("--name", help="Filter by span name")
    p.add_argument("--type", choices=["agent","tool","llm_call","handoff"], help="Filter by type")
    p.add_argument("--failed", action="store_true", help="Only failed spans")
    p.add_argument("--dir", default=".agentguard/traces")
    
    # merge
    p = sub.add_parser("merge", help="Merge distributed child traces")
    p.add_argument("file", help="Parent trace file")
    p.add_argument("--keep", action="store_true", help="Keep child files after merge")
    
    # merge-dir
    p = sub.add_parser("merge-dir", help="Merge all traces in a directory into one")
    p.add_argument("dir", help="Directory containing trace JSON files")
    p.add_argument("--output", default=".agentguard/merged.json", help="Output file path")

    # validate
    p = sub.add_parser("validate", help="Validate trace integrity")
    p.add_argument("file", help="Path to trace JSON file")
    
    # diff
    p = sub.add_parser("diff", help="Compare two traces")
    p.add_argument("trace_a", help="First trace file")
    p.add_argument("trace_b", help="Second trace file")
    
    # analyze
    p = sub.add_parser("analyze", help="Analyze failure propagation and flow")
    p.add_argument("file", help="Path to trace JSON file")
    
    # propagation
    p = sub.add_parser("propagation", help="Analyze failure propagation chains")
    p.add_argument("file", help="Path to trace JSON file")
    
    # flowgraph
    p = sub.add_parser("flowgraph", help="Build multi-agent flow graph")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--mermaid", action="store_true", help="Output as Mermaid diagram")
    
    # context-flow
    p = sub.add_parser("context-flow", help="Analyze context flow through pipeline")
    p.add_argument("file", help="Path to trace JSON file")
    
    # span-diff
    p = sub.add_parser("span-diff", help="Span-level diff between traces")
    p.add_argument("trace_a", help="First trace")
    p.add_argument("trace_b", help="Second trace")
    
    # sla
    p = sub.add_parser("sla", help="Check trace against SLA")
    p.add_argument("file", help="Trace file")
    p.add_argument("--max-duration", type=float, help="Max duration in ms")
    p.add_argument("--min-score", type=float, help="Min quality score")
    p.add_argument("--max-cost", type=float, help="Max cost in USD")
    p.add_argument("--max-error-rate", type=float, help="Max error rate (0-1)")
    
    # dependencies
    p = sub.add_parser("dependencies", help="Agent dependency graph")
    p.add_argument("file", help="Trace file")
    p.add_argument("--mermaid", action="store_true", help="Mermaid output")
    
    # benchmark
    p = sub.add_parser("benchmark", help="Performance benchmark")
    p.add_argument("--traces", type=int, default=10, help="Number of traces")
    p.add_argument("--agents", type=int, default=5, help="Agents per trace")
    
    # generate
    p = sub.add_parser("generate", help="Generate synthetic traces")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--agents", type=int, default=3)
    p.add_argument("--failure-rate", type=float, default=0.1)
    p.add_argument("--dir", default=".agentguard/traces")
    
    # summarize
    p = sub.add_parser("summarize", help="Natural language summary")
    p.add_argument("file", help="Trace file")
    p.add_argument("--brief", action="store_true")
    
    # tree
    p = sub.add_parser("tree", help="Display as indented tree")
    p.add_argument("file", help="Trace file")
    
    # compare
    p = sub.add_parser("compare", help="Comprehensive trace comparison")
    p.add_argument("trace_a", help="First trace")
    p.add_argument("trace_b", help="Second trace")
    
    # timeline
    p = sub.add_parser("timeline", help="Display trace as event timeline")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--max", type=int, help="Max events to show")
    
    # metrics
    p = sub.add_parser("metrics", help="Extract metrics from a trace")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--prometheus", action="store_true", help="Output Prometheus format")
    
    # schema
    p = sub.add_parser("schema", help="Print trace JSON schema")
    
    # score
    p = sub.add_parser("score", help="Score a trace on quality dimensions")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--expected-ms", type=float, help="Expected duration in ms")
    
    # aggregate
    p = sub.add_parser("aggregate", help="Aggregate analysis across traces")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    
    # annotate
    p = sub.add_parser("annotate", help="Auto-annotate a trace")
    p.add_argument("file", help="Path to trace JSON file")
    
    # correlate
    p = sub.add_parser("correlate", help="Analyze span correlations")
    p.add_argument("file", help="Path to trace JSON file")
    
    # guard
    p = sub.add_parser("guard", help="Start continuous monitoring")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    p.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    p.add_argument("--threshold", type=int, default=3, help="Consecutive failures before critical alert")
    p.add_argument("--log", help="Alert log file path")
    
    args = parser.parse_args()
    
    cmds = {"init": cmd_init, "doctor": cmd_doctor, "show": cmd_show, "list": cmd_list, "search": cmd_search, "eval": cmd_eval, "merge": cmd_merge, "merge-dir": cmd_merge_dir, "validate": cmd_validate, "diff": cmd_diff, "analyze": cmd_analyze, "propagation": cmd_propagation, "flowgraph": cmd_flowgraph, "context-flow": cmd_context_flow, "span-diff": cmd_span_diff, "sla": cmd_sla, "dependencies": cmd_dependencies, "benchmark": cmd_benchmark, "generate": cmd_generate, "summarize": cmd_summarize, "tree": cmd_tree, "compare": cmd_compare, "timeline": cmd_timeline, "metrics": cmd_metrics, "schema": cmd_schema, "score": cmd_score, "aggregate": cmd_aggregate, "annotate": cmd_annotate, "correlate": cmd_correlate, "version": cmd_version, "report": cmd_report, "guard": cmd_guard}
    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
