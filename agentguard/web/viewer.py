"""Standalone HTML trace report generator.

Generates a single HTML file with multi-agent orchestration diagnostics.
Zero JS framework dependencies.

KEY: This module consumes analysis results from agentguard.analysis,
NOT reimplementing diagnostic logic. Single source of truth.
"""

from __future__ import annotations

import html as html_mod
import json
from pathlib import Path
from typing import Any

from agentguard.core.trace import ExecutionTrace
from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck


def _esc(text: Any) -> str:
    return html_mod.escape(str(text)) if text else ""


def generate_timeline_html(
    traces_dir: str = ".agentguard/traces",
    output: str = ".agentguard/report.html",
) -> str:
    traces_path = Path(traces_dir)
    traces_data = []  # raw dicts for rendering
    trace_objs = []   # ExecutionTrace objects for analysis
    
    if traces_path.exists():
        for f in sorted(traces_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                raw = json.loads(f.read_text(encoding="utf-8"))
                traces_data.append(raw)
                trace_objs.append(ExecutionTrace.from_dict(raw))
            except Exception:
                pass
    
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_build_html(traces_data, trace_objs), encoding="utf-8")
    return str(out_path)


def _build_html(traces_data: list[dict], trace_objs: list[ExecutionTrace]) -> str:
    """Build HTML using analysis layer for all diagnostics."""
    
    # Aggregate stats from analysis
    total = len(trace_objs)
    passed = sum(1 for t in trace_objs if t.status.value == "completed")
    failed = total - passed
    all_agent_names = set()
    slowest_agent = ""
    slowest_dur = 0
    
    for t in trace_objs:
        for s in t.agent_spans:
            all_agent_names.add(s.name)
            d = s.duration_ms or 0
            if d > slowest_dur:
                slowest_dur = d
                slowest_agent = s.name
    
    avg_dur = sum((t.duration_ms or 0) for t in trace_objs) / max(total, 1)
    
    # Render trace cards using analysis results
    cards = []
    for raw, obj in zip(traces_data, trace_objs):
        cards.append(_render_trace_card(raw, obj))
    
    slowest_html = f'<div class="stat"><div class="v">{_esc(slowest_agent)}</div><div class="l">Slowest Agent</div></div>' if slowest_agent else ""
    cards_html = "\n".join(cards) if cards else '<div class="empty">No traces found.</div>'
    
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AgentGuard — Orchestration Report</title>
<style>
:root{{--bg:#0d1117;--sf:#161b22;--bd:#21262d;--tx:#c9d1d9;--dim:#8b949e;--br:#f0f6fc;
--gn:#3fb950;--rd:#f85149;--bl:#58a6ff;--yl:#d29922;--gn-bg:#1a3a1a;--rd-bg:#3a1a1a;--yl-bg:#3a2f1a;--bl-bg:#1a2a3a;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',monospace;background:var(--bg);color:var(--tx);padding:20px;max-width:1200px;margin:0 auto;}}
.hdr{{text-align:center;padding:24px 0;border-bottom:1px solid var(--bd);margin-bottom:20px;}}
.hdr h1{{font-size:22px;color:var(--br);}} .hdr p{{color:var(--dim);font-size:13px;margin-top:4px;}}
.stats{{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px;margin-bottom:20px;}}
.stat{{background:var(--sf);border:1px solid var(--bd);border-radius:6px;padding:12px;text-align:center;}}
.stat .v{{font-size:22px;font-weight:700;color:var(--br);}} .stat .l{{font-size:10px;color:var(--dim);margin-top:3px;text-transform:uppercase;letter-spacing:.5px;}}
.card{{background:var(--sf);border:1px solid var(--bd);border-radius:8px;margin-bottom:10px;overflow:hidden;}}
.card-hdr{{padding:10px 14px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--bd);cursor:pointer;}}
.card-hdr:hover{{background:rgba(255,255,255,.02);}}
.card-title{{font-weight:600;font-size:13px;color:var(--br);}}
.card-meta{{font-size:11px;color:var(--dim);}}
.badge{{padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600;}}
.b-pass{{background:var(--gn-bg);color:var(--gn);}} .b-fail{{background:var(--rd-bg);color:var(--rd);}}
.b-warn{{background:var(--yl-bg);color:var(--yl);}} .b-info{{background:var(--bl-bg);color:var(--bl);}}
.tl{{padding:12px 14px;display:none;}}
.tl.open{{display:block;}}
.diag{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:10px;font-size:11px;}}
.diag-item{{padding:3px 8px;border-radius:4px;}}
.span-row{{display:flex;align-items:center;padding:3px 0;font-size:12px;font-family:monospace;}}
.span-icon{{width:18px;text-align:center;margin-right:5px;flex-shrink:0;}}
.span-name{{font-weight:500;white-space:nowrap;}}
.span-ver{{color:var(--dim);font-size:10px;margin-left:4px;}}
.span-right{{margin-left:auto;display:flex;align-items:center;gap:6px;white-space:nowrap;}}
.span-dur{{color:var(--bl);font-size:11px;min-width:45px;text-align:right;}}
.span-err{{color:var(--rd);font-size:11px;padding:1px 0 1px 26px;}}
.bar-wrap{{flex:1;max-width:200px;margin-left:8px;height:6px;background:var(--bd);border-radius:3px;overflow:hidden;}}
.bar{{height:100%;border-radius:3px;min-width:2px;}}
.bar-ok{{background:var(--gn);}} .bar-err{{background:var(--rd);}}
.handoff{{font-size:11px;color:var(--yl);padding:2px 0 2px 20px;}}
.empty{{text-align:center;padding:60px;color:var(--dim);}}
.ft{{text-align:center;padding:16px;color:var(--dim);font-size:11px;border-top:1px solid var(--bd);margin-top:20px;}}
.section-label{{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.5px;margin:8px 0 4px;}}
</style></head><body>
<div class="hdr"><h1>🛡️ AgentGuard</h1><p>Multi-Agent Orchestration Report</p></div>
<div class="stats">
<div class="stat"><div class="v">{total}</div><div class="l">Traces</div></div>
<div class="stat"><div class="v">{len(all_agent_names)}</div><div class="l">Agents</div></div>
<div class="stat"><div class="v" style="color:var(--gn)">{passed}</div><div class="l">Passed</div></div>
<div class="stat"><div class="v" style="color:var(--rd)">{failed}</div><div class="l">Failed</div></div>
<div class="stat"><div class="v">{avg_dur/1000:.1f}s</div><div class="l">Avg Duration</div></div>
{slowest_html}
</div>
{cards_html}
<div class="ft">AgentGuard · Multi-Agent Orchestration Observability</div>
<script>
document.querySelectorAll('.card-hdr').forEach(h=>{{
h.addEventListener('click',()=>{{const t=h.nextElementSibling;t.classList.toggle('open');
h.querySelector('.arrow').textContent=t.classList.contains('open')?'▼':'▶';}});}});
const f=document.querySelector('.tl');if(f){{f.classList.add('open');const a=f.previousElementSibling.querySelector('.arrow');if(a)a.textContent='▼';}}
</script></body></html>'''


def _render_trace_card(raw: dict, trace: ExecutionTrace) -> str:
    """Render trace card using unified analysis results."""
    status = trace.status.value
    badge_cls = "b-pass" if status == "completed" else "b-fail"
    badge_txt = "PASS" if status == "completed" else "FAIL"
    dur = trace.duration_ms or 0
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    
    # === Use analysis layer for ALL diagnostics (single source of truth) ===
    failure_analysis = analyze_failures(trace)
    flow_analysis = analyze_flow(trace)
    bottleneck = analyze_bottleneck(trace) if len(trace.agent_spans) > 0 else None
    
    # Build diagnostic badges from analysis results
    diag = []
    diag.append(f'<span class="diag-item b-info">{flow_analysis.agent_count} agents</span>')
    diag.append(f'<span class="diag-item b-info">{flow_analysis.tool_count} tools</span>')
    
    if flow_analysis.handoffs:
        diag.append(f'<span class="diag-item b-info">{len(flow_analysis.handoffs)} handoffs</span>')
    
    # Failure diagnostics from analysis layer
    if failure_analysis.handled_count > 0:
        diag.append(f'<span class="diag-item b-warn">⚡ {failure_analysis.handled_count} handled failures</span>')
    if failure_analysis.unhandled_count > 0:
        diag.append(f'<span class="diag-item b-fail">🔴 {failure_analysis.unhandled_count} unhandled failures</span>')
    if failure_analysis.resilience_score < 1.0 and failure_analysis.total_failed_spans > 0:
        diag.append(f'<span class="diag-item b-{"warn" if failure_analysis.resilience_score > 0.5 else "fail"}">resilience: {failure_analysis.resilience_score:.0%}</span>')
    
    # Root cause from analysis layer
    for rc in failure_analysis.root_causes[:2]:
        if not rc.was_handled:
            diag.append(f'<span class="diag-item b-fail">💥 root cause: {_esc(rc.span_name)}</span>')
    
    # Bottleneck from analysis layer
    if bottleneck and len(trace.agent_spans) > 1:
        diag.append(f'<span class="diag-item b-warn">🐢 bottleneck: {_esc(bottleneck.bottleneck_span)} ({bottleneck.bottleneck_pct:.0f}%)</span>')
    
    # Critical path from analysis layer
    if flow_analysis.critical_path and len(flow_analysis.critical_path) > 1:
        cp = " → ".join(flow_analysis.critical_path[:4])
        if len(flow_analysis.critical_path) > 4:
            cp += " → ..."
        diag.append(f'<span class="diag-item b-info">path: {_esc(cp)}</span>')
    
    diag_html = "\n".join(diag)
    
    # Build tree from raw data
    spans = raw.get("spans", [])
    span_map = {}
    for s in spans:
        span_map[s["span_id"]] = {**s, "children": []}
    roots = []
    for s in spans:
        pid = s.get("parent_span_id")
        if pid and pid in span_map:
            span_map[pid]["children"].append(span_map[s["span_id"]])
        else:
            roots.append(span_map[s["span_id"]])
    
    # Handoff indicators from analysis layer
    handoff_pairs = {(h.from_agent, h.to_agent) for h in flow_analysis.handoffs}
    
    span_html = "\n".join(_render_span(r, 0, dur, handoff_pairs) for r in roots)
    
    return f'''<div class="card">
<div class="card-hdr">
<div><span class="arrow">▶</span> <span class="card-title">{_esc(raw.get("task","(unnamed)"))}</span>
<span class="card-meta"> · {_esc(raw.get("trigger",""))} · {dur_s} · {len(spans)} spans</span></div>
<span class="badge {badge_cls}">{badge_txt}</span></div>
<div class="tl"><div class="diag">{diag_html}</div>{span_html}</div></div>'''


def _render_span(span: dict, depth: int, trace_dur: float, handoff_pairs: set) -> str:
    icons = {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}
    icon = icons.get(span.get("span_type", ""), "●")
    name = _esc(span.get("name", ""))
    status = span.get("status", "")
    dur = span.get("duration_ms") or 0
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    ver = _esc(span.get("metadata", {}).get("agent_version", ""))
    
    s_badge = '<span class="badge b-pass">✓</span>' if status == "completed" else ('<span class="badge b-fail">✗</span>' if status == "failed" else "")
    ver_html = f'<span class="span-ver">({ver})</span>' if ver else ""
    pad = f'style="padding-left:{depth*18}px"'
    
    bar_pct = min(100, (dur / max(trace_dur, 1)) * 100)
    bar_cls = "bar-ok" if status == "completed" else "bar-err"
    bar_html = f'<div class="bar-wrap"><div class="bar {bar_cls}" style="width:{bar_pct:.0f}%"></div></div>'
    
    err = ""
    if span.get("error"):
        err = f'\n<div class="span-err" style="padding-left:{depth*18+26}px">⚠ {_esc(span["error"])}</div>'
    
    children = span.get("children", [])
    children_parts = []
    for i, c in enumerate(children):
        children_parts.append(_render_span(c, depth + 1, trace_dur, handoff_pairs))
        # Insert handoff from analysis layer between sequential agents
        if c.get("span_type") == "agent" and i + 1 < len(children) and children[i + 1].get("span_type") == "agent":
            fr = c.get("name", "")
            to = children[i + 1].get("name", "")
            if (fr, to) in handoff_pairs:  # only show analysis-confirmed handoffs
                ctx_info = ""
                # Try to get context info from the handoff analysis
                children_parts.append(f'<div class="handoff" style="padding-left:{(depth+1)*18}px">🔀 {_esc(fr)} → {_esc(to)}</div>')
    
    return f'''<div class="span-row" {pad}>
<span class="span-icon">{icon}</span><span class="span-name">{name}</span>{ver_html}
<span class="span-right">{s_badge}<span class="span-dur">{dur_s}</span>{bar_html}</span>
</div>{err}
{"\n".join(children_parts)}'''
