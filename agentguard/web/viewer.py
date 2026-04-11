"""Standalone HTML trace report generator.

Generates a single HTML file with multi-agent orchestration diagnostics.
Zero JS framework dependencies — vanilla HTML/CSS/JS only.

Focus: orchestration timeline, handoff visibility, failure propagation.
"""

from __future__ import annotations

import html as html_mod
import json
from pathlib import Path
from typing import Optional


def _esc(text) -> str:
    """Escape text for safe HTML insertion."""
    return html_mod.escape(str(text)) if text else ""


def generate_timeline_html(
    traces_dir: str = ".agentguard/traces",
    output: str = ".agentguard/report.html",
) -> str:
    """Generate a standalone HTML report with orchestration diagnostics.
    
    Args:
        traces_dir: Directory containing trace JSON files.
        output: Path for the output HTML file.
    
    Returns:
        Path to the generated HTML file.
    """
    traces_path = Path(traces_dir)
    traces = []
    
    if traces_path.exists():
        for f in sorted(traces_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                traces.append(json.loads(f.read_text(encoding="utf-8")))
            except Exception:
                pass
    
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_build_html(traces), encoding="utf-8")
    return str(out_path)


def _compute_stats(traces: list[dict]) -> dict:
    """Compute orchestration-specific statistics."""
    total_spans = sum(len(t.get("spans", [])) for t in traces)
    all_agents = []
    agent_durations: dict[str, list[float]] = {}
    failed_count = 0
    total_dur = 0
    
    for t in traces:
        spans = t.get("spans", [])
        dur = t.get("duration_ms") or 0
        total_dur += dur
        if t.get("status") == "failed":
            failed_count += 1
        for s in spans:
            if s.get("span_type") == "agent":
                name = s.get("name", "")
                all_agents.append(name)
                d = s.get("duration_ms")
                if d:
                    agent_durations.setdefault(name, []).append(d)
    
    # Find slowest agent (by average)
    slowest_agent = ""
    slowest_avg = 0
    for name, durs in agent_durations.items():
        avg = sum(durs) / len(durs)
        if avg > slowest_avg:
            slowest_avg = avg
            slowest_agent = name
    
    unique_agents = len(set(all_agents))
    avg_dur = total_dur / max(len(traces), 1)
    
    return {
        "traces": len(traces),
        "spans": total_spans,
        "agents": unique_agents,
        "passed": len(traces) - failed_count,
        "failed": failed_count,
        "avg_duration": avg_dur,
        "slowest_agent": slowest_agent,
        "slowest_avg_ms": slowest_avg,
    }


def _trace_summary(trace: dict) -> dict:
    """Compute per-trace diagnostic summary."""
    spans = trace.get("spans", [])
    agents = [s for s in spans if s.get("span_type") == "agent"]
    tools = [s for s in spans if s.get("span_type") == "tool"]
    failed = [s for s in spans if s.get("status") == "failed"]
    
    # Slowest agent
    slowest = max(agents, key=lambda s: s.get("duration_ms") or 0) if agents else None
    
    # First failure
    first_fail = None
    for s in spans:
        if s.get("status") == "failed":
            first_fail = s
            break
    
    # Detect fallback: a failed tool followed by a successful tool under same parent
    has_fallback = False
    parent_tools: dict[str, list[dict]] = {}
    for s in tools:
        pid = s.get("parent_span_id", "")
        parent_tools.setdefault(pid, []).append(s)
    for pid, ts in parent_tools.items():
        statuses = [t.get("status") for t in ts]
        if "failed" in statuses and "completed" in statuses:
            has_fallback = True
            break
    
    # Failure propagation: agent failed because its tool failed
    has_propagation = False
    failed_tool_parents = {s.get("parent_span_id") for s in tools if s.get("status") == "failed"}
    for a in agents:
        if a.get("status") == "failed" and a.get("span_id") in failed_tool_parents:
            has_propagation = True
            break
    
    # Handoff count: sequential agents under same parent
    handoff_count = 0
    parent_agents: dict[str, list[dict]] = {}
    for a in agents:
        pid = a.get("parent_span_id", "")
        parent_agents.setdefault(pid, []).append(a)
    for pid, ags in parent_agents.items():
        if len(ags) >= 2:
            handoff_count += len(ags) - 1
    
    return {
        "agent_count": len(agents),
        "tool_count": len(tools),
        "failed_count": len(failed),
        "slowest": slowest,
        "first_fail": first_fail,
        "has_fallback": has_fallback,
        "has_propagation": has_propagation,
        "handoff_count": handoff_count,
    }


def _build_html(traces: list[dict]) -> str:
    stats = _compute_stats(traces)
    trace_cards = "\n".join(_render_trace_card(t) for t in traces)
    
    slowest_html = f'<div class="stat"><div class="v">{_esc(stats["slowest_agent"])}</div><div class="l">Slowest Agent</div></div>' if stats["slowest_agent"] else ""
    
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
</style></head><body>
<div class="hdr"><h1>🛡️ AgentGuard</h1><p>Multi-Agent Orchestration Report</p></div>
<div class="stats">
<div class="stat"><div class="v">{stats["traces"]}</div><div class="l">Traces</div></div>
<div class="stat"><div class="v">{stats["agents"]}</div><div class="l">Agents</div></div>
<div class="stat"><div class="v" style="color:var(--gn)">{stats["passed"]}</div><div class="l">Passed</div></div>
<div class="stat"><div class="v" style="color:var(--rd)">{stats["failed"]}</div><div class="l">Failed</div></div>
<div class="stat"><div class="v">{stats["avg_duration"]/1000:.1f}s</div><div class="l">Avg Duration</div></div>
{slowest_html}
</div>
{trace_cards if traces else '<div class="empty">No traces found.</div>'}
<div class="ft">AgentGuard · Multi-Agent Orchestration Observability</div>
<script>
document.querySelectorAll('.card-hdr').forEach(h=>{{
h.addEventListener('click',()=>{{const t=h.nextElementSibling;t.classList.toggle('open');
h.querySelector('.arrow').textContent=t.classList.contains('open')?'▼':'▶';}});}});
const f=document.querySelector('.tl');if(f){{f.classList.add('open');const a=f.previousElementSibling.querySelector('.arrow');if(a)a.textContent='▼';}}
</script></body></html>'''


def _render_trace_card(trace: dict) -> str:
    status = trace.get("status", "unknown")
    badge_cls = "b-pass" if status == "completed" else "b-fail"
    badge_txt = "PASS" if status == "completed" else "FAIL"
    dur = trace.get("duration_ms") or 0
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    spans = trace.get("spans", [])
    summary = _trace_summary(trace)
    
    # Diagnostic badges
    diag = []
    diag.append(f'<span class="diag-item b-info">{summary["agent_count"]} agents</span>')
    diag.append(f'<span class="diag-item b-info">{summary["tool_count"]} tools</span>')
    if summary["handoff_count"] > 0:
        diag.append(f'<span class="diag-item b-info">{summary["handoff_count"]} handoffs</span>')
    if summary["has_fallback"]:
        diag.append(f'<span class="diag-item b-warn">⚡ fallback detected</span>')
    if summary["has_propagation"]:
        diag.append(f'<span class="diag-item b-fail">🔴 failure propagation</span>')
    if summary["slowest"] and summary["agent_count"] > 1:
        diag.append(f'<span class="diag-item b-warn">🐢 slowest: {_esc(summary["slowest"]["name"])}</span>')
    if summary["first_fail"]:
        diag.append(f'<span class="diag-item b-fail">💥 first fail: {_esc(summary["first_fail"]["name"])}</span>')
    diag_html = "\n".join(diag)
    
    # Build tree
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
    
    span_html = "\n".join(_render_span(r, 0, dur) for r in roots)
    
    return f'''<div class="card">
<div class="card-hdr">
<div><span class="arrow">▶</span> <span class="card-title">{_esc(trace.get("task","(unnamed)"))}</span>
<span class="card-meta"> · {_esc(trace.get("trigger",""))} · {dur_s} · {len(spans)} spans</span></div>
<span class="badge {badge_cls}">{badge_txt}</span></div>
<div class="tl"><div class="diag">{diag_html}</div>{span_html}</div></div>'''


def _render_span(span: dict, depth: int, trace_dur: float) -> str:
    icons = {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}
    icon = icons.get(span.get("span_type", ""), "●")
    name = _esc(span.get("name", ""))
    status = span.get("status", "")
    dur = span.get("duration_ms") or 0
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    ver = _esc(span.get("metadata", {}).get("agent_version", ""))
    
    s_badge = f'<span class="badge b-pass">✓</span>' if status == "completed" else (f'<span class="badge b-fail">✗</span>' if status == "failed" else "")
    ver_html = f'<span class="span-ver">({ver})</span>' if ver else ""
    pad = f'style="padding-left:{depth*18}px"'
    
    # Timeline bar
    bar_pct = min(100, (dur / max(trace_dur, 1)) * 100)
    bar_cls = "bar-ok" if status == "completed" else "bar-err"
    bar_html = f'<div class="bar-wrap"><div class="bar {bar_cls}" style="width:{bar_pct:.0f}%"></div></div>'
    
    err = ""
    if span.get("error"):
        err = f'\n<div class="span-err" style="padding-left:{depth*18+26}px">⚠ {_esc(span["error"])}</div>'
    
    # Detect handoff: if this agent is followed by another agent under same parent
    handoff_html = ""
    children = span.get("children", [])
    agent_children = [c for c in children if c.get("span_type") == "agent"]
    if len(agent_children) >= 2:
        for i in range(len(agent_children) - 1):
            fr = _esc(agent_children[i].get("name", ""))
            to = _esc(agent_children[i + 1].get("name", ""))
            handoff_html += f'\n<div class="handoff" style="padding-left:{(depth+1)*18}px">🔀 handoff: {fr} → {to}</div>'
    
    children_html_parts = []
    for i, c in enumerate(children):
        children_html_parts.append(_render_span(c, depth + 1, trace_dur))
        # Insert handoff indicator between sequential agents
        if c.get("span_type") == "agent" and i + 1 < len(children) and children[i + 1].get("span_type") == "agent":
            fr = _esc(c.get("name", ""))
            to = _esc(children[i + 1].get("name", ""))
            children_html_parts.append(f'<div class="handoff" style="padding-left:{(depth+1)*18}px">🔀 {fr} → {to}</div>')
    
    children_html = "\n".join(children_html_parts)
    
    return f'''<div class="span-row" {pad}>
<span class="span-icon">{icon}</span><span class="span-name">{name}</span>{ver_html}
<span class="span-right">{s_badge}<span class="span-dur">{dur_s}</span>{bar_html}</span>
</div>{err}
{children_html}'''
