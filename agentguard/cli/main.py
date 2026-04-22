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
from datetime import datetime
from typing import Any

from agentguard.core.trace import ExecutionTrace


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


def _fmt_duration(ms: float | None) -> str:
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


def _default_trace_output(output: str | None, trace_id: str) -> Path:
    """Resolve the output path for a persisted trace."""
    if output:
        return Path(output)
    return Path(".agentguard/traces") / f"{trace_id}.json"


def _write_trace_file(trace: ExecutionTrace, output: str | None) -> str:
    """Persist a trace JSON file and return the final path."""
    out_path = _default_trace_output(output, trace.trace_id)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(trace.to_json(), encoding="utf-8")
    return str(out_path)




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


def cmd_show(args) -> None:
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


def cmd_list(args) -> None:
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


def cmd_eval(args) -> None:
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


def cmd_search(args) -> None:
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


def cmd_merge(args) -> None:
    """Merge distributed child traces into parent."""
    from agentguard.sdk.distributed import merge_child_traces

    trace = _load_trace_file(args.file)
    traces_dir = str(Path(args.file).parent)

    merged = merge_child_traces(trace, traces_dir, cleanup=not args.keep)
    print(f"  Merged {len(merged.spans)} spans into {args.file}")
    if not args.keep:
        print("  Child files cleaned up")


def cmd_merge_dir(args) -> None:
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


def cmd_validate(args) -> None:
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


def cmd_diff(args) -> None:
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


    result = _build_analysis_dict(trace)
    print(json.dumps(result, indent=2, default=str))


def _cli_fail(message: str) -> None:
    """Exit a CLI command with a clear user-facing error."""
    print(f"{C.RED}Error: {message}{C.RESET}", file=sys.stderr)
    sys.exit(1)


def _require_positive(name: str, value: int) -> None:
    """Validate positive integer CLI arguments."""
    if value < 1:
        _cli_fail(f"{name} must be >= 1")


def _build_analysis_dict(trace) -> dict:
    """Build the complete analysis dictionary for JSON output."""
    from agentguard.analysis import (
        analyze_bottleneck,
        analyze_counterfactual,
        analyze_context_flow,
        analyze_cost_yield,
        analyze_decisions,
        analyze_failures,
        analyze_flow,
        analyze_workflow_patterns,
    )
    from agentguard.propagation import analyze_propagation
    from agentguard.scoring import score_trace

    failures = analyze_failures(trace)
    flow = analyze_flow(trace)
    bn = analyze_bottleneck(trace) if trace.agent_spans else None
    ctx = analyze_context_flow(trace)
    cost_yield = analyze_cost_yield(trace)
    decisions = analyze_decisions(trace)
    counterfactual = analyze_counterfactual(trace)
    workflow_patterns = analyze_workflow_patterns(trace)
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
        "counterfactual": counterfactual.to_dict(),
        "workflow_patterns": workflow_patterns.to_dict(),
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


def _generate_html_report(trace: ExecutionTrace, output: str | None) -> str | None:
    """Generate an HTML report for a single trace when requested."""
    if not output:
        return None
    from agentguard.web.viewer import generate_report_from_trace

    return generate_report_from_trace(trace, output=output)


def _default_html_report_path(trace_path: str | None, trace_id: str | None = None) -> str:
    """Derive a companion HTML report path for a trace.

    Preference order:
    1. Next to the trace file: ``foo.json`` -> ``foo.html``
    2. ``.agentguard/reports/<trace_id>.html`` when only a trace id is known.
    3. ``.agentguard/report.html`` as a last resort.
    """
    if trace_path:
        p = Path(trace_path)
        if p.suffix:
            return str(p.with_suffix(".html"))
        return str(p.parent / f"{p.name}.html")
    if trace_id:
        return str(Path(".agentguard") / "reports" / f"{trace_id}.html")
    return str(Path(".agentguard") / "report.html")


def _print_dense_diagnostics(
    trace: ExecutionTrace,
    *,
    trace_path: str | None = None,
    html_report: str | None = None,
) -> None:
    """Render the high-density terminal diagnostics view."""
    from agentguard.terminal_diagnostics import render_dense_diagnostics

    print(render_dense_diagnostics(trace, trace_path=trace_path, html_report=html_report), end="")


def _print_analysis(trace: ExecutionTrace) -> None:
    """Render the human-readable CLI diagnostics summary for a trace."""
    from agentguard.analysis import (
        analyze_context_flow,
        analyze_counterfactual,
        analyze_cost_yield,
        analyze_decisions,
        analyze_failures,
        analyze_flow,
        analyze_workflow_patterns,
    )

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

    context_flow = analyze_context_flow(trace)
    print(f"\n{C.BOLD}  🧠 Context Flow{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Handoffs:{C.RESET}         {context_flow.handoff_count}")
    print(f"  {C.DIM}Anomalies:{C.RESET}        {len(context_flow.anomalies)}")
    top_risks = [point for point in context_flow.ranked_points if point.risk_label != 'ok'][:3]
    if not top_risks:
        print(f"  {C.DIM}Top risk:{C.RESET}         none")
    for point in top_risks:
        print(
            f"\n  {C.RED if point.risk_label in {'severe', 'high'} else C.YELLOW}⚠{C.RESET} "
            f"{C.BOLD}{point.from_agent}{C.RESET} → {C.BOLD}{point.to_agent}{C.RESET} [{point.risk_label}]"
        )
        print(f"     {C.DIM}risk {point.risk_score:.0%} · semantic {((point.semantic_retention_score or 0) * 100):.0f}%{C.RESET}")
        if point.critical_keys_lost:
            print(f"     {C.DIM}critical loss: {point.critical_keys_lost}{C.RESET}")
        if point.reference_ids_lost:
            print(f"     {C.DIM}evidence refs: {point.reference_ids_lost[:3]}{C.RESET}")
        if point.downstream_impact_reason:
            print(f"     {C.DIM}{point.downstream_impact_reason}{C.RESET}")

    cost_yield = analyze_cost_yield(trace)
    print(f"\n{C.BOLD}  📈 Cost-Yield Analysis{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Highest cost:{C.RESET}     {cost_yield.highest_cost_agent}")
    print(f"  {C.DIM}Lowest yield:{C.RESET}     {cost_yield.lowest_yield_agent}")
    print(f"  {C.DIM}Most wasteful:{C.RESET}    {cost_yield.most_wasteful_agent or 'N/A'}")
    print(f"  {C.DIM}Worst path:{C.RESET}       {cost_yield.worst_path or 'N/A'}")
    if cost_yield.critical_path_summary:
        cp = cost_yield.critical_path_summary
        print(
            f"  {C.DIM}Critical path:{C.RESET}    {' → '.join(cp.agents)} · ${cp.total_cost_usd:.4f} · yield {cp.avg_yield_score:.0f}/100"
        )
    for path in cost_yield.path_summaries[:2]:
        grounding = ""
        if path.claim_count and path.citation_coverage is not None:
            grounding = (
                f"\n     {C.DIM}grounding issues {path.grounding_issue_count} · citations {path.citation_coverage:.0%}"
                f" · unsupported {path.unsupported_claim_count} · missing refs {path.missing_citation_count}{C.RESET}"
            )
        print(
            f"\n  • {C.BOLD}{' → '.join(path.agents)}{C.RESET} [{path.path_kind}]"
            f"\n     {C.DIM}${path.total_cost_usd:.4f}, yield {path.avg_yield_score:.0f}/100, waste {path.waste_score:.0f}/100{C.RESET}"
            f"{grounding}"
        )
    for recommendation in cost_yield.recommendations[:2]:
        print(f"\n  💡 {recommendation}")

    workflow = analyze_workflow_patterns(trace)
    print(f"\n{C.BOLD}  🧭 Workflow Patterns{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Primary:{C.RESET}          {workflow.primary_pattern}")
    for pattern in workflow.patterns:
        heur = " (heuristic)" if pattern.heuristic else ""
        print(f"  • {pattern.name}{heur} — {pattern.evidence}")

    decisions = analyze_decisions(trace)
    print(f"\n{C.BOLD}  🎯 Decision Impact{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Decisions:{C.RESET}        {decisions.total_decisions}")
    print(f"  {C.DIM}Degradation:{C.RESET}      {decisions.decisions_with_degradation}")
    print(f"  {C.DIM}Quality:{C.RESET}          {decisions.decision_quality_score:.0%}")
    for decision in decisions.decisions[:3]:
        icon = f"{C.RED}✗{C.RESET}" if decision.led_to_degradation else f"{C.GREEN}✓{C.RESET}"
        print(f"\n  {icon} {C.BOLD}{decision.coordinator}{C.RESET} chose {C.BOLD}{decision.chosen_agent}{C.RESET}")
        for signal in decision.degradation_signals[:3]:
            print(f"     {C.DIM}→ {signal}{C.RESET}")
    for suggestion in decisions.suggestions[:2]:
        print(f"\n  💡 Consider {C.BOLD}{suggestion['suggested_agent']}{C.RESET} instead of {C.BOLD}{suggestion['current_agent']}{C.RESET}")
        print(f"     {C.DIM}{suggestion['reason']}{C.RESET}")

    counterfactual = analyze_counterfactual(trace)
    print(f"\n{C.BOLD}  ↺ Counterfactual{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Decisions:{C.RESET}        {counterfactual.total_decisions}")
    print(f"  {C.DIM}Suboptimal:{C.RESET}       {counterfactual.suboptimal_count}")
    print(f"  {C.DIM}Catastrophic:{C.RESET}     {counterfactual.catastrophic_count}")
    print(f"  {C.DIM}Regret:{C.RESET}           {counterfactual.total_regret_ms:.0f}ms")
    for result in counterfactual.results[:3]:
        icon = (
            f"{C.RED}✗{C.RESET}" if result.verdict == "catastrophic"
            else f"{C.YELLOW}⚠{C.RESET}" if result.verdict == "suboptimal"
            else f"{C.GREEN}✓{C.RESET}"
        )
        print(f"\n  {icon} {C.BOLD}{result.coordinator}{C.RESET} chose {C.BOLD}{result.chosen_agent}{C.RESET} [{result.verdict}]")
        if result.best_alternative:
            print(f"     {C.DIM}best alt: {result.best_alternative} ({result.evidence_runs} run(s), {result.evidence_source}){C.RESET}")
        if result.rationale:
            print(f"     {C.DIM}{result.rationale}{C.RESET}")

    print()


def cmd_analyze(args) -> None:
    """Analyze failure propagation and flow in a trace."""
    trace = _load_trace_file(args.file)

    if getattr(args, 'json', False):
        _output_structured_json(trace)
        return

    _print_analysis(trace)


def cmd_diagnose(args) -> None:
    """Render a high-density terminal diagnosis and optional HTML report."""
    trace = _load_trace_file(args.file)
    report_target = args.report_output or _default_html_report_path(args.file)
    report_output = _generate_html_report(trace, report_target)
    _print_dense_diagnostics(trace, trace_path=args.file, html_report=report_output)



def cmd_propagation(args) -> None:
    """Analyze failure propagation with causal chains."""
    from agentguard.propagation import analyze_propagation

    trace = _load_trace_file(args.file)
    result = analyze_propagation(trace)
    print(result.to_report())


def cmd_flowgraph(args) -> None:
    """Build and display multi-agent flow graph."""
    from agentguard.flowgraph import build_flow_graph

    trace = _load_trace_file(args.file)
    graph = build_flow_graph(trace)

    if args.mermaid:
        print(graph.to_mermaid())
    else:
        print(graph.to_report())


def cmd_context_flow(args) -> None:
    """Analyze context flow through the agent pipeline."""
    from agentguard.context_flow import analyze_context_flow_deep

    trace = _load_trace_file(args.file)
    result = analyze_context_flow_deep(trace)
    print(result.to_report())


def cmd_score(args) -> None:
    """Score a trace on quality dimensions."""
    from agentguard.scoring import score_trace

    trace = _load_trace_file(args.file)
    expected = args.expected_ms if hasattr(args, 'expected_ms') and args.expected_ms else None
    score = score_trace(trace, expected_duration_ms=expected)
    print(score.to_report())


def cmd_summary(args) -> None:
    """Print a one-line health summary of a trace (like git status)."""
    trace = _load_trace_file(args.file)
    line = _format_summary_line(trace)
    print(line)


def _format_summary_line(trace) -> str:
    """Build a single-line trace health summary.

    Format: [GRADE] task — duration · agents · failures · score
    Example: [A] user lookup — 2.1s · 3 agents · 0 failures · 95/100
    """
    from agentguard.analysis import analyze_failures
    from agentguard.scoring import score_trace

    score = score_trace(trace)
    failures = analyze_failures(trace)
    dur = trace.duration_ms
    dur_str = f"{dur/1000:.1f}s" if dur and dur >= 1000 else f"{dur:.0f}ms" if dur else "?"
    n_agents = len(trace.agent_spans)
    n_failed = failures.total_failed_spans
    status = trace.status.value if trace.status else "unknown"

    grade_colors = {"A": C.GREEN, "B": C.GREEN, "C": C.YELLOW, "D": C.RED, "F": C.RED}
    gc = grade_colors.get(score.grade, C.DIM)
    status_icon = "✅" if status == "completed" else "❌" if status == "failed" else "⏳"

    return (
        f"{gc}[{score.grade}]{C.RESET} "
        f"{status_icon} {C.BOLD}{trace.task}{C.RESET} — "
        f"{dur_str} · {n_agents} agents · "
        f"{C.RED if n_failed else C.GREEN}{n_failed} failures{C.RESET} · "
        f"{gc}{score.overall:.0f}/100{C.RESET}"
    )


def cmd_aggregate(args) -> None:
    """Aggregate analysis across multiple traces."""
    import json
    import os

    from agentguard.aggregate import aggregate_traces
    from agentguard.core.trace import ExecutionTrace

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


def cmd_annotate(args) -> None:
    """Auto-annotate a trace."""
    from agentguard.annotations import auto_annotate

    trace = _load_trace_file(args.file)
    store = auto_annotate(trace)
    summary = store.summary()

    print(f"Annotations: {summary['total']}")
    print(f"  By severity: {summary['by_severity']}")
    print(f"  By category: {summary['by_category']}")

    for _span_id, anns in store.to_dict().items():
        for ann in anns:
            icon = {"info": "ℹ️", "warning": "⚠️", "error": "🔴", "critical": "💀"}.get(ann["severity"], "📎")
            print(f"  {icon} [{ann['category']}] {ann['message']}")


def cmd_correlate(args) -> None:
    """Analyze span correlations."""
    from agentguard.correlation import analyze_correlations

    trace = _load_trace_file(args.file)
    result = analyze_correlations(trace)
    print(result.to_report())



def cmd_timeline(args) -> None:
    """Display trace as chronological event timeline."""
    from agentguard.timeline import build_timeline

    trace = _load_trace_file(args.file)
    tl = build_timeline(trace)
    print(tl.to_text(max_events=args.max or 50))


def cmd_metrics(args) -> None:
    """Extract metrics from a trace."""
    import json as _json

    from agentguard.metrics import extract_metrics

    trace = _load_trace_file(args.file)
    m = extract_metrics(trace)

    if args.prometheus:
        print(m.to_prometheus())
    else:
        print(_json.dumps(m.to_dict(), indent=2))


def cmd_schema(args) -> None:
    """Print the trace JSON schema."""
    import json as _json

    from agentguard.schema import get_schema
    print(_json.dumps(get_schema(), indent=2))



def cmd_span_diff(args) -> None:
    """Span-level diff between two traces."""
    from agentguard.span_diff import diff_spans

    trace_a = _load_trace_file(args.trace_a)
    trace_b = _load_trace_file(args.trace_b)
    result = diff_spans(trace_a, trace_b)
    print(result.to_report())


def cmd_sla(args) -> None:
    """Check trace against SLA constraints."""
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


def cmd_dependencies(args) -> None:
    """Show agent dependency graph."""
    from agentguard.dependency import build_dependency_graph

    trace = _load_trace_file(args.file)
    graph = build_dependency_graph(trace)

    if args.mermaid:
        print(graph.to_mermaid())
    else:
        print(graph.to_report())


def cmd_benchmark(args) -> None:
    """Run performance benchmark on analysis modules."""
    from agentguard.benchmark import run_benchmark
    suite = run_benchmark(trace_count=args.traces, agents_per_trace=args.agents)
    print(suite.to_report())


def _evolution_engine(knowledge_dir: str):
    """Create the evolution engine for CLI commands."""
    from agentguard.evolve import EvolutionEngine

    return EvolutionEngine(knowledge_dir=knowledge_dir)


def cmd_learn(args) -> None:
    """Learn from a trace and persist recurring lessons."""
    trace = _load_trace_file(args.file)
    engine = _evolution_engine(args.knowledge_dir)
    reflection = engine.learn(trace)
    comparison = engine.compare_to_best(trace)

    print(f"\n{C.BOLD}  🧠 Evolution Learn{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Trace:{C.RESET}            {trace.trace_id}")
    print(f"  {C.DIM}Lessons:{C.RESET}          {len(reflection.lessons)}")
    print(f"  {C.DIM}Patterns:{C.RESET}         {len(reflection.patterns_detected)}")
    print(f"  {C.DIM}Traces learned:{C.RESET}   {engine.kb.trace_count}")
    print(f"  {C.DIM}Knowledge dir:{C.RESET}    {args.knowledge_dir}")
    print(f"  {C.DIM}Trend vs best:{C.RESET}    {comparison['trend']}")
    if engine.load_warning:
        print(f"  {C.YELLOW}Recovered:{C.RESET}        {engine.load_warning}")

    for lesson in reflection.lessons[:5]:
        icon = {"failure": "🔴", "bottleneck": "🐢", "handoff": "🔀"}.get(lesson.category, "•")
        print(f"\n  {icon} {C.BOLD}{lesson.agent}{C.RESET}")
        print(f"     {lesson.observation}")
        print(f"     → {lesson.suggestion}")
    print()


def cmd_suggest(args) -> None:
    """Show learned high-confidence suggestions."""
    engine = _evolution_engine(args.knowledge_dir)
    _require_positive("limit", args.limit)
    try:
        suggestions = engine.suggest(min_confidence=args.min_confidence)
    except ValueError as exc:
        _cli_fail(str(exc))

    print(f"\n{C.BOLD}  💡 Evolution Suggestions{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Knowledge dir:{C.RESET}    {args.knowledge_dir}")
    print(f"  {C.DIM}Traces learned:{C.RESET}   {engine.kb.trace_count}")
    if engine.load_warning:
        print(f"  {C.YELLOW}Recovered:{C.RESET}        {engine.load_warning}")

    if not suggestions:
        print(f"  {C.DIM}No suggestions yet. Learn from more traces first.{C.RESET}\n")
        return

    for lesson in suggestions[: args.limit]:
        print(f"\n  {C.BOLD}{lesson.agent}{C.RESET} [{lesson.category}]")
        print(f"     confidence: {lesson.confidence:.0%} · seen {lesson.occurrences}x")
        if lesson.evidence:
            latest = lesson.evidence[-1]
            print(f"     evidence: {latest.get('task') or '(unnamed)'} · {latest.get('trace_id')} · {latest.get('span')}")
        print(f"     {lesson.observation}")
        print(f"     → {lesson.suggestion}")
    print()


def cmd_trends(args) -> None:
    """Show recurring evolution trends from the knowledge base."""
    engine = _evolution_engine(args.knowledge_dir)
    _require_positive("window", args.window)
    _require_positive("limit", args.limit)
    try:
        trends = engine.detect_trends(window=args.window)
    except ValueError as exc:
        _cli_fail(str(exc))

    print(f"\n{C.BOLD}  📈 Evolution Trends{C.RESET}")
    print(f"  {'─' * 50}")
    if engine.load_warning:
        print(f"  {C.YELLOW}Recovered:{C.RESET}        {engine.load_warning}")
    if not trends:
        print(f"  {C.DIM}No trends yet. Learn from more traces first.{C.RESET}\n")
        return

    for trend in trends[: args.limit]:
        sev = trend.get("severity", "info")
        color = C.RED if sev == "high" else (C.YELLOW if sev == "medium" else C.GREEN)
        print(f"  {color}{trend['type']}{C.RESET} · {trend['agent']} · {trend['occurrences']}x")
        print(f"     {trend['message']}")
    print()


def cmd_prd(args) -> None:
    """Generate a markdown PRD from recurring evolution patterns."""
    engine = _evolution_engine(args.knowledge_dir)
    try:
        print(engine.generate_prd(min_occurrences=args.min_occurrences))
    except ValueError as exc:
        _cli_fail(str(exc))


def cmd_auto_apply(args) -> None:
    """Generate or apply config patches from evolution knowledge."""
    trace = _load_trace_file(args.file)
    engine = _evolution_engine(args.knowledge_dir)
    _require_positive("limit", args.limit)
    try:
        result = engine.auto_apply(
            trace,
            min_confidence=args.min_confidence,
            dry_run=not args.write,
        )
    except ValueError as exc:
        _cli_fail(str(exc))

    print(f"\n{C.BOLD}  🛠 Evolution Auto-Apply{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Status:{C.RESET}           {result['status']}")
    print(f"  {C.DIM}Patches:{C.RESET}          {result.get('patch_count', 0)}")
    print(f"  {C.DIM}Current score:{C.RESET}    {result.get('current_score', 0):.1f}")
    print(f"  {C.DIM}Trend:{C.RESET}            {result.get('trend', 'n/a')}")
    if engine.load_warning:
        print(f"  {C.YELLOW}Recovered:{C.RESET}        {engine.load_warning}")

    for patch in result.get("patches", [])[: args.limit]:
        print(f"\n  {C.BOLD}{patch['agent']}{C.RESET} [{patch['category']}] {patch['confidence']:.0%}")
        print(f"     {patch['suggestion']}")
        print(f"     config: {json.dumps(patch['config'], ensure_ascii=False)}")

    if result.get("config_path"):
        print(f"\n  {C.GREEN}Updated:{C.RESET} {result['config_path']}")
    print()


def cmd_generate(args) -> None:
    """Generate synthetic traces."""
    from agentguard.generate import generate_trace
    from agentguard.store import TraceStore

    store = TraceStore(directory=args.dir)
    for i in range(args.count):
        trace = generate_trace(agents=args.agents, failure_rate=args.failure_rate, seed=i)
        store.save(trace)
        print(f"  Generated: {trace.trace_id} ({len(trace.spans)} spans)")
    print(f"Saved {args.count} traces to {args.dir}")


def cmd_summarize(args) -> None:
    """Summarize a trace in natural language."""
    from agentguard.summarize import summarize_brief, summarize_trace

    trace = _load_trace_file(args.file)
    if args.brief:
        print(summarize_brief(trace))
    else:
        print(summarize_trace(trace))


def cmd_tree(args) -> None:
    """Display trace as indented tree."""
    from agentguard.tree import tree_to_text

    trace = _load_trace_file(args.file)
    print(tree_to_text(trace))


def cmd_compare(args) -> None:
    """Compare two traces comprehensively."""
    from agentguard.comparison import compare_traces

    trace_a = _load_trace_file(args.trace_a)
    trace_b = _load_trace_file(args.trace_b)
    result = compare_traces(trace_a, trace_b)
    print(result.to_report())



def cmd_init(args) -> None:
    """Scaffold a new AgentGuard project with default config and directories."""
    traces_dir = Path(".agentguard/traces")
    knowledge_dir = Path(".agentguard/knowledge")
    config_file = Path("agentguard.json")

    created = []

    # Create traces directory
    if not traces_dir.exists():
        traces_dir.mkdir(parents=True, exist_ok=True)
        created.append(str(traces_dir))

    if not knowledge_dir.exists():
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        created.append(str(knowledge_dir))

    # Create default config
    if not config_file.exists():
        default_config = {
            "traces_dir": ".agentguard/traces",
            "knowledge_dir": ".agentguard/knowledge",
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
        print("\n  Next steps:")
        print("    1. Add @record_agent / @record_tool decorators to your code")
        print("    2. Run your agents")
        print("    3. agentguard list")
        print()
    else:
        print(f"\n  {C.DIM}Already initialized — nothing to do.{C.RESET}\n")


def _doctor_check_claude_readiness(all_ok: bool) -> bool:
    """Run the three checks that decide if `diagnose-claude-session` will work.

    Returns the updated ``all_ok`` flag. Each check prints one line with a
    green/yellow/red icon so the operator can see at a glance whether the
    tool is ready on this machine. A red mark flips ``all_ok`` to False.
    """
    # (a) Claude Agent SDK installed and within supported range.
    try:
        from agentguard.runtime.claude.session_import import (
            _SDK_MIN_VERSION,
            _SDK_MAX_EXCLUSIVE,
            _parse_sdk_version,
        )
        import claude_agent_sdk  # type: ignore[import-not-found]
        sdk_ver_str = getattr(claude_agent_sdk, "__version__", "")
        parsed = _parse_sdk_version(sdk_ver_str)
        if parsed is None:
            print(f"  {C.YELLOW}⚠{C.RESET} claude-agent-sdk installed but version unreadable")
        elif _SDK_MIN_VERSION <= parsed < _SDK_MAX_EXCLUSIVE:
            print(f"  {C.GREEN}✓{C.RESET} claude-agent-sdk {sdk_ver_str} (supported)")
        else:
            low = ".".join(str(n) for n in _SDK_MIN_VERSION)
            high = ".".join(str(n) for n in _SDK_MAX_EXCLUSIVE)
            print(
                f"  {C.RED}✗{C.RESET} claude-agent-sdk {sdk_ver_str} "
                f"outside supported range [{low}, {high})"
            )
            all_ok = False
    except ImportError:
        print(
            f"  {C.YELLOW}⚠{C.RESET} claude-agent-sdk not installed "
            f"(pip install 'agentguard[claude]' to diagnose Claude sessions)"
        )

    # (b) Claude projects directory readable.
    projects_dir = Path.home() / ".claude" / "projects"
    if projects_dir.is_dir():
        try:
            next(projects_dir.iterdir(), None)
            print(f"  {C.GREEN}✓{C.RESET} Claude sessions at {projects_dir}")
        except OSError as e:
            print(f"  {C.RED}✗{C.RESET} {projects_dir} not readable: {e}")
            all_ok = False
    else:
        print(
            f"  {C.YELLOW}⚠{C.RESET} {projects_dir} not found "
            f"(no Claude sessions to diagnose yet)"
        )

    # (c) Pricing table freshness.
    try:
        from agentguard.runtime.claude.session_import import _BUILTIN_PRICING_DATE
        from datetime import date
        parsed_date = date.fromisoformat(_BUILTIN_PRICING_DATE)
        age_days = (date.today() - parsed_date).days
        if age_days < 180:
            print(
                f"  {C.GREEN}✓{C.RESET} Pricing table reviewed "
                f"{_BUILTIN_PRICING_DATE} ({age_days}d ago)"
            )
        else:
            print(
                f"  {C.YELLOW}⚠{C.RESET} Pricing table reviewed "
                f"{_BUILTIN_PRICING_DATE} ({age_days}d ago) — consider "
                f"overriding via AGENTGUARD_PRICING_FILE"
            )
    except (ImportError, ValueError) as e:
        print(f"  {C.YELLOW}⚠{C.RESET} Pricing table date unreadable: {e}")

    return all_ok


def cmd_doctor(args) -> None:
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

    knowledge_dir = Path(".agentguard/knowledge")
    if knowledge_dir.exists():
        kb_file = knowledge_dir / "knowledge.json"
        status = "knowledge base ready" if kb_file.exists() else "knowledge dir ready"
        print(f"  {C.GREEN}✓{C.RESET} Knowledge directory ({status})")
    else:
        print(f"  {C.YELLOW}⚠{C.RESET} Knowledge directory not found (run: agentguard init)")

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

    # 6. Claude session readiness — the three checks that determine whether
    #    `diagnose-claude-session` will work on this machine right now.
    all_ok = _doctor_check_claude_readiness(all_ok)

    # Summary
    if all_ok:
        print(f"\n  {C.GREEN}All checks passed!{C.RESET}\n")
    else:
        print(f"\n  {C.RED}Some checks failed. See above for details.{C.RESET}\n")
        sys.exit(1)


def cmd_version(args) -> None:
    """Show AgentGuard version."""
    from agentguard import __version__
    print(f"AgentGuard {__version__}")


def _format_timestamp_ms(timestamp_ms: int | None) -> str:
    """Format millisecond timestamps for CLI output."""
    if not timestamp_ms:
        return "unknown"
    return datetime.fromtimestamp(timestamp_ms / 1000).strftime("%Y-%m-%d %H:%M")


def cmd_list_claude_sessions(args) -> None:
    """List Claude sessions available for import."""
    from agentguard.runtime.claude import list_claude_sessions
    from agentguard.runtime.claude.session_import import ClaudeSessionImportError

    all_projects = getattr(args, "all", False)
    group_by_project = getattr(args, "group_by_project", False)
    effective_limit = None if all_projects else args.limit

    try:
        sessions = list_claude_sessions(
            directory=args.directory,
            limit=effective_limit,
            include_worktrees=not args.no_worktrees,
        )
    except ClaudeSessionImportError as exc:
        guidance = [str(exc)]
        if "claude-agent-sdk" in str(exc):
            guidance.append("Install it with: pip install claude-agent-sdk")
        _cli_fail(". ".join(guidance))

    if args.project:
        project_root = str(Path(args.project).resolve())
        sessions = [
            session for session in sessions
            if session.cwd and (
                session.cwd == project_root or session.cwd.startswith(project_root + "/")
            )
        ]

    compact = not sys.stdout.isatty()

    if compact:
        print("Claude Sessions")
        print("-" * 50)
    else:
        print(f"\n{C.BOLD}  Claude Sessions{C.RESET}")
        print(f"  {'─' * 50}")
    if not sessions:
        scope = f" for {args.project}" if args.project else ""
        if compact:
            print(f"No Claude sessions found{scope}.")
        else:
            print(f"  {C.DIM}No Claude sessions found{scope}.{C.RESET}\n")
        return

    if group_by_project:
        _print_sessions_grouped_by_project(sessions, compact=compact)
        return

    for session in sessions:
        _print_session_entry(session, compact=compact)


def _print_session_entry(session, *, compact: bool = False) -> None:
    """Print a single Claude session summary block."""
    title = session.custom_title or session.summary
    if compact:
        # One plain-text line per session. Designed for LLM / pipeline
        # consumption: no ANSI, no emoji, stable column order.
        updated = _format_timestamp_ms(session.last_modified)
        cwd = session.cwd or "-"
        branch = session.git_branch or "-"
        print(f"{session.session_id}\t{updated}\t{branch}\t{cwd}\t{title}")
        return
    print(f"  {C.BOLD}{title}{C.RESET}")
    print(f"    {C.DIM}session:{C.RESET} {session.session_id}")
    print(f"    {C.DIM}updated:{C.RESET} {_format_timestamp_ms(session.last_modified)}")
    if session.cwd:
        print(f"    {C.DIM}cwd:{C.RESET}     {session.cwd}")
    if session.git_branch:
        print(f"    {C.DIM}branch:{C.RESET}  {session.git_branch}")
    if session.first_prompt and session.first_prompt != session.summary:
        print(f"    {C.DIM}prompt:{C.RESET}  {session.first_prompt[:120]}")
    print()


def _print_sessions_grouped_by_project(sessions, *, compact: bool = False) -> None:
    """Print Claude sessions grouped by their working directory."""
    groups: dict[str, list] = {}
    for session in sessions:
        key = session.cwd or "(unknown project)"
        groups.setdefault(key, []).append(session)

    def _group_sort_key(item: tuple[str, list]) -> int:
        _, entries = item
        return -max((entry.last_modified or 0) for entry in entries)

    ordered = sorted(groups.items(), key=_group_sort_key)

    if compact:
        # Compact grouped format for pipelines / LLM ingestion: one header
        # line per project, one line per session, no ANSI, no emoji.
        for cwd, entries in ordered:
            plural = "s" if len(entries) != 1 else ""
            print(f"[{cwd}] ({len(entries)} session{plural})")
            for session in entries:
                title = session.custom_title or session.summary
                updated = _format_timestamp_ms(session.last_modified)
                branch = session.git_branch or "-"
                print(f"  {session.session_id}\t{updated}\t{branch}\t{title}")
        return

    for cwd, entries in ordered:
        print(f"  {C.BOLD}{cwd}{C.RESET}  {C.DIM}({len(entries)} session{'s' if len(entries) != 1 else ''}){C.RESET}")
        for session in entries:
            title = session.custom_title or session.summary
            print(f"    {C.BOLD}•{C.RESET} {title}")
            print(f"      {C.DIM}session:{C.RESET} {session.session_id}")
            print(f"      {C.DIM}updated:{C.RESET} {_format_timestamp_ms(session.last_modified)}")
            if session.git_branch:
                print(f"      {C.DIM}branch:{C.RESET}  {session.git_branch}")
        print()


def cmd_import_claude_session(args) -> None:
    """Import a Claude session into a local AgentGuard trace and optional HTML report."""
    from agentguard.runtime.claude import import_claude_session
    from agentguard.runtime.claude.session_import import ClaudeSessionImportError
    try:
        trace = import_claude_session(
            args.session_id,
            directory=args.directory,
            include_subagents=not args.no_subagents,
        )
    except ClaudeSessionImportError as exc:
        guidance = [str(exc)]
        if "claude-agent-sdk" in str(exc):
            guidance.append("Install it with: pip install claude-agent-sdk")
        elif not args.directory:
            guidance.append("Retry with --directory <claude-session-dir> if the SDK cannot find this session in its default lookup path")
        _cli_fail(". ".join(guidance))

    output = _write_trace_file(trace, args.output)
    report_output = _generate_html_report(trace, args.report_output)

    print(f"\n{C.BOLD}  Claude Session Imported{C.RESET}")
    print(f"  {'─' * 50}")
    print(f"  {C.DIM}Session:{C.RESET}         {args.session_id}")
    print(f"  {C.DIM}Task:{C.RESET}            {trace.task or '(unnamed)'}")
    print(f"  {C.DIM}Agents:{C.RESET}          {len(trace.agent_spans)}")
    print(f"  {C.DIM}Spans:{C.RESET}           {len(trace.spans)}")
    print(f"  {C.DIM}Trace JSON:{C.RESET}      {output}")
    if report_output:
        print(f"  {C.DIM}HTML report:{C.RESET}     {report_output}")
    if getattr(args, "analyze", False):
        _print_analysis(trace)
    print()


def cmd_diagnose_claude_session(args) -> None:
    """Import and diagnose a Claude session in one terminal-first flow."""
    from agentguard.runtime.claude import import_claude_session
    from agentguard.runtime.claude.session_import import ClaudeSessionImportError

    try:
        trace = import_claude_session(
            args.session_id,
            directory=args.directory,
            include_subagents=not args.no_subagents,
        )
    except ClaudeSessionImportError as exc:
        guidance = [str(exc)]
        if "claude-agent-sdk" in str(exc):
            guidance.append("Install it with: pip install claude-agent-sdk")
        elif not args.directory:
            guidance.append("Retry with --directory <claude-session-dir> if the SDK cannot find this session in its default lookup path")
        _cli_fail(". ".join(guidance))

    output = _write_trace_file(trace, args.output)
    report_target = args.report_output or _default_html_report_path(output, trace.trace_id)
    _apply_expected_artifacts(trace, getattr(args, "expected_artifact", []))
    report_output = _generate_html_report(trace, report_target)
    _print_dense_diagnostics(trace, trace_path=output, html_report=report_output)


def _apply_expected_artifacts(trace, paths: list[str]) -> None:
    """Downgrade the Q4 completion signal when user-declared outputs are missing.

    When ``--expected-artifact`` is passed, every path must exist on disk
    for the task to count as completed. Missing paths force the trace's
    completion signal to 0 and mark the root span's quality to 0 so the
    cost-yield analysis stops treating the run as a clean success.
    """
    if not paths:
        return
    from pathlib import Path

    missing = [p for p in paths if not Path(p).exists()]
    trace.metadata["expected_artifacts.checked"] = list(paths)
    trace.metadata["expected_artifacts.missing"] = missing
    if missing:
        trace.metadata["claude.completion_signal"] = 0.0
        trace.metadata["claude.stop_reason"] = "missing_expected_artifacts"
        if trace.spans:
            trace.spans[0].metadata["claude.quality"] = 0.0
            trace.spans[0].metadata["claude.stop_reason"] = "missing_expected_artifacts"



def cmd_report(args) -> None:
    """Generate HTML report."""
    from agentguard.web.viewer import generate_timeline_html
    output = generate_timeline_html(traces_dir=args.dir, output=args.output)
    print(f"  🌐 Report generated: {output}")


def cmd_guard(args) -> None:
    """Start continuous monitoring."""
    from agentguard.guard import FileAlert, Guard, StdoutAlert

    handlers = [StdoutAlert()]
    if args.log:
        handlers.append(FileAlert(args.log))

    guard = Guard(
        traces_dir=args.dir,
        alert_handlers=handlers,
        fail_threshold=args.threshold,
    )
    guard.watch(interval=args.interval)


# Core product commands — the only ones shown in ``--help``. Everything else
# is kept registered for backwards compatibility but hidden via
# ``_hide_non_core_commands`` so the publishable surface is narrow.
_CORE_COMMANDS: set[str] = {
    "list-claude-sessions",
    "diagnose-claude-session",
    "diagnose",
    "report",
    "doctor",
    "version",
}


def _hide_non_core_commands(sub: Any) -> None:
    """Hide non-core subcommands from ``--help`` output.

    The subcommand remains registered so existing scripts and tests keep
    working, but it is removed from the rendered help listing so that new
    users see a narrow, publishable surface.
    """
    try:
        actions = sub._choices_actions  # type: ignore[attr-defined]
    except AttributeError:  # pragma: no cover — argparse internals changed
        return
    sub._choices_actions = [  # type: ignore[attr-defined]
        action for action in actions
        if getattr(action, "dest", None) in _CORE_COMMANDS
    ]


def _register_subcommands(sub: Any) -> None:
    """Register all CLI subcommands with argparse.

    Each block adds a subparser with its arguments. Grouped by category
    for readability. The dispatch table is populated in main().
    """
    # Core commands
    sub.add_parser("init", help="Initialize AgentGuard in current directory")
    sub.add_parser("doctor", help="Check installation health")
    sub.add_parser("version", help="Show version")
    p = sub.add_parser("list-claude-sessions", help="List Claude sessions available for import")
    p.add_argument("--directory", help="Claude session directory")
    p.add_argument("--limit", type=int, default=10, help="Maximum sessions to show")
    p.add_argument("--all", action="store_true", help="List all sessions across all projects (ignores --limit)")
    p.add_argument("--project", help="Filter sessions by project path / cwd")
    p.add_argument("--group-by-project", action="store_true", help="Group output by project cwd")
    p.add_argument("--no-worktrees", action="store_true", help="Exclude Claude worktree sessions")
    sub.add_parser("schema", help="Print trace JSON schema")

    p = sub.add_parser("import-claude-session", help="Import a Claude session into a trace")
    p.add_argument("session_id", help="Claude session id")
    p.add_argument("--directory", help="Claude session directory")
    p.add_argument("--no-subagents", action="store_true", help="Skip subagent transcript import")
    p.add_argument("--output", help="Output trace JSON path")
    p.add_argument("--report-output", help="Optional HTML report output path")
    p.add_argument("--analyze", action="store_true", help="Print diagnostics summary after import")

    # Trace viewing
    p = sub.add_parser("show", help="Display a trace file")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("list", help="List recorded traces")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")

    p = sub.add_parser("tree", help="Display as indented tree")
    p.add_argument("file", help="Trace file")

    p = sub.add_parser("timeline", help="Display trace as event timeline")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--max", type=int, help="Max events to show")

    p = sub.add_parser("summary", help="One-line trace health summary")
    p.add_argument("file", help="Path to trace JSON file")


def _register_analysis_commands(sub: Any) -> None:
    """Register analysis subcommands."""
    p = sub.add_parser("analyze", help="Analyze failure propagation and flow")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("diagnose", help="Dense terminal diagnosis for a trace")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--report-output", help="Optional HTML report output path")

    p = sub.add_parser("diagnose-claude-session", help="Import and densely diagnose a Claude session")
    p.add_argument("session_id", help="Claude session id")
    p.add_argument("--directory", help="Claude session directory")
    p.add_argument("--no-subagents", action="store_true", help="Skip subagent transcript import")
    p.add_argument("--output", help="Output trace JSON path")
    p.add_argument("--report-output", help="Optional HTML report output path")
    p.add_argument(
        "--expected-artifact",
        action="append",
        default=[],
        help="Path that must exist for the task to count as completed. May be "
             "repeated. When any expected artifact is missing the Q4 "
             "completion signal is downgraded.",
    )

    p = sub.add_parser("learn", help="Learn evolution lessons from a trace")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--knowledge-dir", default=".agentguard/knowledge", help="Knowledge base directory")

    p = sub.add_parser("suggest", help="Show learned evolution suggestions")
    p.add_argument("--knowledge-dir", default=".agentguard/knowledge", help="Knowledge base directory")
    p.add_argument("--min-confidence", type=float, default=0.6, help="Minimum confidence threshold")
    p.add_argument("--limit", type=int, default=10, help="Maximum suggestions to show")

    p = sub.add_parser("trends", help="Show recurring evolution trends")
    p.add_argument("--knowledge-dir", default=".agentguard/knowledge", help="Knowledge base directory")
    p.add_argument("--window", type=int, default=10, help="Recent trace window to analyze")
    p.add_argument("--limit", type=int, default=10, help="Maximum trends to show")

    p = sub.add_parser("prd", help="Generate improvement PRD from learned patterns")
    p.add_argument("--knowledge-dir", default=".agentguard/knowledge", help="Knowledge base directory")
    p.add_argument("--min-occurrences", type=int, default=3, help="Minimum recurring count")

    p = sub.add_parser("auto-apply", help="Generate or apply evolution config patches")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--knowledge-dir", default=".agentguard/knowledge", help="Knowledge base directory")
    p.add_argument("--min-confidence", type=float, default=0.8, help="Minimum confidence threshold")
    p.add_argument("--limit", type=int, default=10, help="Maximum patches to show")
    p.add_argument("--write", action="store_true", help="Write patches into agentguard.json")

    p = sub.add_parser("eval", help="Evaluate a trace against rules")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--config", help="Path to config file (agentguard.json)")

    p = sub.add_parser("score", help="Score a trace on quality dimensions")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--expected-ms", type=float, help="Expected duration in ms")

    p = sub.add_parser("propagation", help="Analyze failure propagation chains")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("flowgraph", help="Build multi-agent flow graph")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--mermaid", action="store_true", help="Output as Mermaid diagram")

    p = sub.add_parser("context-flow", help="Analyze context flow through pipeline")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("metrics", help="Extract metrics from a trace")
    p.add_argument("file", help="Path to trace JSON file")
    p.add_argument("--prometheus", action="store_true", help="Output Prometheus format")

    p = sub.add_parser("correlate", help="Analyze span correlations")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("annotate", help="Auto-annotate a trace")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("summarize", help="Natural language summary")
    p.add_argument("file", help="Trace file")
    p.add_argument("--brief", action="store_true")

    p = sub.add_parser("dependencies", help="Agent dependency graph")
    p.add_argument("file", help="Trace file")
    p.add_argument("--mermaid", action="store_true", help="Mermaid output")


def _register_comparison_commands(sub: Any) -> None:
    """Register comparison and merge subcommands."""
    p = sub.add_parser("diff", help="Compare two traces")
    p.add_argument("trace_a", help="First trace file")
    p.add_argument("trace_b", help="Second trace file")

    p = sub.add_parser("span-diff", help="Span-level diff between traces")
    p.add_argument("trace_a", help="First trace")
    p.add_argument("trace_b", help="Second trace")

    p = sub.add_parser("compare", help="Comprehensive trace comparison")
    p.add_argument("trace_a", help="First trace")
    p.add_argument("trace_b", help="Second trace")

    p = sub.add_parser("merge", help="Merge distributed child traces")
    p.add_argument("file", help="Parent trace file")
    p.add_argument("--keep", action="store_true", help="Keep child files after merge")

    p = sub.add_parser("merge-dir", help="Merge all traces in a directory into one")
    p.add_argument("dir", help="Directory containing trace JSON files")
    p.add_argument("--output", default=".agentguard/merged.json", help="Output file path")

    p = sub.add_parser("aggregate", help="Aggregate analysis across traces")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")


def _register_ops_commands(sub: Any) -> None:
    """Register operational subcommands: search, validate, SLA, etc."""
    p = sub.add_parser("search", help="Search spans across traces")
    p.add_argument("--name", help="Filter by span name")
    p.add_argument("--type", choices=["agent","tool","llm_call","handoff"], help="Filter by type")
    p.add_argument("--failed", action="store_true", help="Only failed spans")
    p.add_argument("--dir", default=".agentguard/traces")

    p = sub.add_parser("validate", help="Validate trace integrity")
    p.add_argument("file", help="Path to trace JSON file")

    p = sub.add_parser("sla", help="Check trace against SLA")
    p.add_argument("file", help="Trace file")
    p.add_argument("--max-duration", type=float, help="Max duration in ms")
    p.add_argument("--min-score", type=float, help="Min quality score")
    p.add_argument("--max-cost", type=float, help="Max cost in USD")
    p.add_argument("--max-error-rate", type=float, help="Max error rate (0-1)")

    p = sub.add_parser("report", help="Generate HTML report")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    p.add_argument("--output", default=".agentguard/report.html", help="Output HTML path")

    p = sub.add_parser("benchmark", help="Performance benchmark")
    p.add_argument("--traces", type=int, default=10, help="Number of traces")
    p.add_argument("--agents", type=int, default=5, help="Agents per trace")

    p = sub.add_parser("generate", help="Generate synthetic traces")
    p.add_argument("--count", type=int, default=10)
    p.add_argument("--agents", type=int, default=3)
    p.add_argument("--failure-rate", type=float, default=0.1)
    p.add_argument("--dir", default=".agentguard/traces")

    p = sub.add_parser("guard", help="Start continuous monitoring")
    p.add_argument("--dir", default=".agentguard/traces", help="Traces directory")
    p.add_argument("--interval", type=int, default=60, help="Check interval in seconds")
    p.add_argument("--threshold", type=int, default=3, help="Consecutive failures before critical alert")
    p.add_argument("--log", help="Alert log file path")


def main() -> None:
    """CLI entry point. Parses args and dispatches to command handlers."""
    parser = argparse.ArgumentParser(
        prog="agentguard",
        description=(
            "AgentGuard — Diagnostics for multi-agent orchestration.\n\n"
            "Primary workflow:\n"
            "  agentguard list-claude-sessions        # 1. find a session\n"
            "  agentguard diagnose-claude-session ID  # 2. import + diagnose + render HTML\n"
            "  agentguard diagnose TRACE.json         # 3. diagnose an exported trace\n"
            "  agentguard report TRACE.json           # 4. render interactive HTML\n\n"
            "All other subcommands remain available for advanced/compatibility use."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(
        dest="command",
        metavar="<command>",
        title="commands",
    )

    _register_subcommands(sub)
    _register_analysis_commands(sub)
    _register_comparison_commands(sub)
    _register_ops_commands(sub)

    _hide_non_core_commands(sub)

    args = parser.parse_args()

    cmds = {
        "init": cmd_init, "doctor": cmd_doctor, "version": cmd_version,
        "list-claude-sessions": cmd_list_claude_sessions,
        "import-claude-session": cmd_import_claude_session,
        "schema": cmd_schema, "show": cmd_show, "list": cmd_list,
        "tree": cmd_tree, "timeline": cmd_timeline, "summary": cmd_summary,
        "analyze": cmd_analyze, "diagnose": cmd_diagnose,
        "diagnose-claude-session": cmd_diagnose_claude_session,
        "learn": cmd_learn, "suggest": cmd_suggest,
        "trends": cmd_trends, "prd": cmd_prd, "auto-apply": cmd_auto_apply,
        "eval": cmd_eval, "score": cmd_score,
        "propagation": cmd_propagation, "flowgraph": cmd_flowgraph,
        "context-flow": cmd_context_flow, "metrics": cmd_metrics,
        "correlate": cmd_correlate, "annotate": cmd_annotate,
        "summarize": cmd_summarize, "dependencies": cmd_dependencies,
        "diff": cmd_diff, "span-diff": cmd_span_diff, "compare": cmd_compare,
        "merge": cmd_merge, "merge-dir": cmd_merge_dir, "aggregate": cmd_aggregate,
        "search": cmd_search, "validate": cmd_validate, "sla": cmd_sla,
        "report": cmd_report, "benchmark": cmd_benchmark, "generate": cmd_generate,
        "guard": cmd_guard,
    }

    if args.command in cmds:
        cmds[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
