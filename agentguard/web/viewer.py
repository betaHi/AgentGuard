"""Standalone HTML report generator — orchestration diagnostics panel.

Generates a single HTML file matching the target prototype design:
- Left sidebar: agent health cards
- Main area: Gantt-style timeline with handoff indicators
- Bottom: diagnostics grid (failures, bottleneck, handoffs, critical path)

All diagnostics powered by analysis.py (single source of truth).
"""

from __future__ import annotations

import html as html_mod
import json
from pathlib import Path
from typing import Any

from agentguard.core.trace import ExecutionTrace, Span, SpanType, SpanStatus
from agentguard.analysis import analyze_failures, analyze_flow, analyze_bottleneck, analyze_context_flow, analyze_retries, analyze_cost

def _try_evolve(trace):
    """Try to get evolution suggestions if knowledge exists."""
    try:
        from agentguard.evolve import EvolutionEngine
        engine = EvolutionEngine()
        if engine.kb.trace_count > 0:
            return engine.suggest(min_confidence=0.6)[:3]
    except Exception:
        pass
    return []


def _esc(text: Any) -> str:
    return html_mod.escape(str(text)) if text else ""


def generate_timeline_html(
    traces_dir: str = ".agentguard/traces",
    output: str = ".agentguard/report.html",
) -> str:
    traces_path = Path(traces_dir)
    trace_objs = []
    
    if traces_path.exists():
        for f in sorted(traces_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
            try:
                trace_objs.append(ExecutionTrace.from_dict(
                    json.loads(f.read_text(encoding="utf-8"))
                ))
            except Exception:
                pass
    
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_build_full_html(trace_objs), encoding="utf-8")
    return str(out_path)


def _build_full_html(traces: list[ExecutionTrace]) -> str:
    if not traces:
        return _build_empty_html()
    
    # Use the most recent trace as the primary display
    primary = traces[0]
    failures = analyze_failures(primary)
    flow = analyze_flow(primary)
    bn = analyze_bottleneck(primary) if primary.agent_spans else None
    ctx = analyze_context_flow(primary)
    
    dur_total = primary.duration_ms or 1
    
    # Score the trace
    from agentguard.scoring import score_trace as _score_trace
    _score = _score_trace(primary)
    
    # Build sidebar agent cards
    agent_cards = _build_sidebar(primary, failures, bn)
    
    # Build Gantt timeline
    timeline = _build_gantt(primary, flow, dur_total)
    
    # Build diagnostics grid
    retries = analyze_retries(primary)
    cost = analyze_cost(primary)
    diagnostics = _build_diagnostics(failures, bn, flow, ctx, retries, cost)
    
    # Trace selector (if multiple traces)
    trace_count = len(traces)
    status_txt = "PASS" if primary.status == SpanStatus.COMPLETED else "FAIL"
    status_cls = "b-pass" if primary.status == SpanStatus.COMPLETED else "b-fail"
    
    return f'''<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AgentGuard — Orchestration Panel</title>
<style>
:root{{--bg:#0d1117;--sf:#161b22;--bd:#21262d;--tx:#c9d1d9;--dim:#6e7681;--br:#f0f6fc;
--gn:#3fb950;--rd:#f85149;--bl:#58a6ff;--yl:#d29922;--pp:#bc8cff;
--gn-bg:#1a3a1a;--rd-bg:#3a1a1a;--yl-bg:#3a2f1a;--bl-bg:#1a2a3a;--pp-bg:#2a1a3a;}}
*{{margin:0;padding:0;box-sizing:border-box;}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',system-ui,monospace;background:var(--bg);color:var(--tx);}}
.top-bar{{background:var(--sf);border-bottom:1px solid var(--bd);padding:10px 20px;display:flex;align-items:center;justify-content:space-between;}}
.top-bar h1{{font-size:14px;color:var(--br);}} .top-bar .meta{{font-size:11px;color:var(--dim);}}
.badge{{padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600;}}
.b-pass{{background:var(--gn-bg);color:var(--gn);}} .b-fail{{background:var(--rd-bg);color:var(--rd);}}
.b-warn{{background:var(--yl-bg);color:var(--yl);}} .b-info{{background:var(--bl-bg);color:var(--bl);}}
.b-pp{{background:var(--pp-bg);color:var(--pp);}}
.layout{{display:grid;grid-template-columns:240px 1fr;min-height:calc(100vh - 42px);}}
.sidebar{{background:var(--sf);border-right:1px solid var(--bd);padding:12px;overflow-y:auto;}}
.sidebar h2{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:10px;}}
.ag-card{{background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:8px 10px;margin-bottom:6px;}}
.ag-name{{font-weight:600;font-size:12px;color:var(--br);display:flex;align-items:center;gap:5px;}}
.ag-stats{{font-size:10px;color:var(--dim);margin-top:3px;display:flex;gap:8px;}}
.ag-bar{{height:3px;border-radius:2px;margin-top:4px;background:var(--bd);}}
.ag-bar-fill{{height:100%;border-radius:2px;}}
.dot{{width:7px;height:7px;border-radius:50%;display:inline-block;flex-shrink:0;}}
.dot-ok{{background:var(--gn);}} .dot-err{{background:var(--rd);}} .dot-warn{{background:var(--yl);}}
.main{{padding:14px 16px;overflow-x:auto;}}
.main h2{{font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:8px;}}
.tl-header{{display:flex;padding:0 0 6px 180px;border-bottom:1px solid var(--bd);margin-bottom:2px;}}
.tl-header .tick{{font-size:9px;color:var(--dim);flex:1;text-align:center;}}
.g-row{{display:flex;align-items:center;padding:2px 0;min-height:24px;border-bottom:1px solid rgba(48,54,61,0.2);}}
.g-row:hover{{background:rgba(56,139,253,0.03);}}
.g-lbl{{width:180px;flex-shrink:0;display:flex;align-items:center;gap:5px;font-size:11px;padding-right:6px;overflow:hidden;}}
.g-lbl .icon{{font-size:12px;}} .g-lbl .nm{{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.g-lbl .vr{{font-size:9px;color:var(--dim);}}
.g-bar-area{{flex:1;position:relative;height:18px;}}
.g-bar{{position:absolute;height:12px;top:3px;border-radius:3px;min-width:3px;display:flex;align-items:center;justify-content:flex-end;padding:0 3px;font-size:8px;color:rgba(255,255,255,0.7);}}
.g-bar.ok{{background:linear-gradient(90deg,#238636,#2ea043);}}
.g-bar.err{{background:linear-gradient(90deg,#da3633,#f85149);}}
.g-bar.slow{{background:linear-gradient(90deg,#9e6a03,#d29922);}}
.g-bar.ho{{background:var(--pp);height:2px;top:8px;}}
.g-err{{position:absolute;top:-1px;font-size:8px;color:var(--rd);white-space:nowrap;}}
.g-ann{{position:absolute;top:-1px;font-size:8px;white-space:nowrap;}}
.ho-row{{display:flex;align-items:center;min-height:16px;}}
.ho-line{{margin-left:180px;flex:1;display:flex;align-items:center;gap:3px;font-size:9px;color:var(--pp);}}
.ho-arrow{{height:1px;width:40px;background:var(--pp);}}
.ctx-badge{{background:var(--pp-bg);color:var(--pp);padding:1px 5px;border-radius:3px;font-size:8px;}}
.diag{{background:var(--sf);border:1px solid var(--bd);border-radius:8px;padding:14px;margin-top:14px;}}
.diag h3{{font-size:11px;color:var(--br);margin-bottom:10px;}}
.diag-grid{{display:grid;grid-template-columns:1fr 1fr;gap:10px;}}
.d-box{{background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:10px;}}
.d-box h4{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);margin-bottom:5px;}}
.d-box .val{{font-size:16px;font-weight:700;color:var(--br);}}
.d-box .det{{font-size:10px;color:var(--dim);margin-top:3px;}}
.d-box .items{{font-size:10px;margin-top:5px;}}
.d-box .item{{padding:1px 0;display:flex;align-items:center;gap:3px;}}
.ff-node{{padding:1px 6px;border-radius:3px;font-size:9px;}}
.ff-h{{background:var(--yl-bg);color:var(--yl);}} .ff-u{{background:var(--rd-bg);color:var(--rd);}}
.empty{{text-align:center;padding:60px;color:var(--dim);}}
.ft{{text-align:center;padding:12px;color:var(--dim);font-size:10px;border-top:1px solid var(--bd);margin-top:14px;}}
</style></head><body>

<div class="top-bar">
<h1>🛡️ AgentGuard</h1>
<div class="meta">
{_esc(primary.task)} · {_esc(primary.trigger)} · {dur_total/1000:.1f}s · {len(primary.spans)} spans
<span class="badge {status_cls}" style="margin-left:8px">{status_txt}</span>
{f'<span style="margin-left:8px;color:var(--dim)">{trace_count} traces</span>' if trace_count > 1 else ''}
<span class="score-badge score-{_score.grade.lower()}">{_score.overall:.0f}/100 ({_score.grade})</span>
</div></div>

<div class="layout">
<div class="sidebar">{agent_cards}</div>
<div class="main">
<h2>Execution Timeline</h2>
{timeline}
{diagnostics}
<div class="ft">AgentGuard · Orchestration Observability</div>
</div></div>

</body></html>'''


def _build_empty_html() -> str:
    return '''<!DOCTYPE html><html><head><title>AgentGuard</title>
<style>body{background:#0d1117;color:#8b949e;font-family:monospace;display:flex;justify-content:center;align-items:center;height:100vh;}
</style></head><body><div style="text-align:center"><h1>🛡️ AgentGuard</h1><p>No traces found. Record some agent executions first.</p></div></body></html>'''


def _build_sidebar(trace: ExecutionTrace, failures, bn) -> str:
    cards = [f'<h2>Agents ({len(trace.agent_spans)})</h2>']
    dur_total = trace.duration_ms or 1
    
    # Get failure info per agent
    failed_agents = {rc.span_name for rc in failures.root_causes if not rc.was_handled}
    warned_agents = {rc.span_name for rc in failures.root_causes if rc.was_handled}
    bn_name = bn.bottleneck_span if bn else ""
    
    # Sort: failed first, then by duration desc
    agents = sorted(trace.agent_spans, key=lambda s: (
        0 if s.status == SpanStatus.FAILED else 1,
        -(s.duration_ms or 0)
    ))
    
    for s in agents:
        dur = s.duration_ms or 0
        pct = (dur / dur_total) * 100
        ver = _esc(s.metadata.get("agent_version", ""))
        
        if s.status == SpanStatus.FAILED or s.name in failed_agents:
            dot_cls = "dot-err"
            bar_color = "var(--rd)"
            extra = f'<span style="color:var(--rd)">✗ {_esc(s.error or "failed")[:30]}</span>'
        elif s.name == bn_name and len(trace.agent_spans) > 1:
            dot_cls = "dot-warn"
            bar_color = "var(--yl)"
            extra = f'<span style="color:var(--yl)">🐢 bottleneck ({pct:.0f}%)</span>'
        elif s.name in warned_agents:
            dot_cls = "dot-warn"
            bar_color = "var(--yl)"
            extra = '<span style="color:var(--yl)">⚡ fallback used</span>'
        else:
            dot_cls = "dot-ok"
            bar_color = "var(--gn)"
            extra = '<span>✓ pass</span>'
        
        dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
        
        cards.append(f'''<div class="ag-card">
<div class="ag-name"><span class="dot {dot_cls}"></span> {_esc(s.name)} <span style="font-size:9px;color:var(--dim)">{ver}</span></div>
<div class="ag-stats"><span>{dur_s}</span>{extra}</div>
<div class="ag-bar"><div class="ag-bar-fill" style="width:{max(pct,2):.0f}%;background:{bar_color}"></div></div>
</div>''')
    
    return "\n".join(cards)


def _build_gantt(trace: ExecutionTrace, flow, dur_total: float) -> str:
    # Detect parallel groups for visual highlighting
    from datetime import datetime as _dt
    parallel_span_ids = set()
    timed_agents = []
    for s in trace.spans:
        if s.span_type in (SpanType.AGENT, SpanType.TOOL):
            try:
                start = _dt.fromisoformat(s.started_at) if s.started_at else None
                end = _dt.fromisoformat(s.ended_at) if s.ended_at else None
                if start and end:
                    timed_agents.append((s, start, end))
            except: pass
    
    # Find overlapping spans (parallel execution)
    for i, (a, a_s, a_e) in enumerate(timed_agents):
        for j, (b, b_s, b_e) in enumerate(timed_agents[i+1:], i+1):
            if a_s < b_e and b_s < a_e:  # overlap
                if a.parent_span_id == b.parent_span_id:  # same parent
                    parallel_span_ids.add(a.span_id)
                    parallel_span_ids.add(b.span_id)
    
    # Time axis
    steps = 6
    step_ms = dur_total / steps
    ticks = "".join(f'<div class="tick">{int(i*step_ms)}ms</div>' for i in range(steps + 1))
    header = f'<div class="tl-header">{ticks}</div>'
    
    # Build span tree for rendering
    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)
    
    roots = [s for s in trace.spans if s.parent_span_id is None or s.parent_span_id not in span_map]
    
    # Handoff pairs from analysis
    handoff_pairs = {(h.from_agent, h.to_agent): h for h in flow.handoffs}
    
    # Compute time offsets — use started_at relative to trace start
    trace_start = trace.started_at
    
    rows = []
    for root in roots:
        rows.extend(_render_gantt_rows(root, 0, trace_start, dur_total, children_map, span_map, handoff_pairs, parallel_span_ids))
    
    return header + "\n" + "\n".join(rows)


def _render_gantt_rows(span: Span, depth: int, trace_start: str, dur_total: float,
                       children_map, span_map, handoff_pairs, parallel_ids=None) -> list[str]:
    from datetime import datetime
    rows = []
    
    # Calculate position
    try:
        t_start = datetime.fromisoformat(trace_start)
        s_start = datetime.fromisoformat(span.started_at) if span.started_at else t_start
        offset_ms = (s_start - t_start).total_seconds() * 1000
    except:
        offset_ms = 0
    
    dur = span.duration_ms or 0
    left_pct = (offset_ms / max(dur_total, 1)) * 100
    width_pct = (dur / max(dur_total, 1)) * 100
    
    # Determine bar style
    icons = {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}
    icon = icons.get(span.span_type.value, "●")
    
    if span.span_type == SpanType.HANDOFF:
        # Render handoff as a special row
        ctx_size = span.context_size_bytes or 0
        ctx_str = f"{ctx_size:,}B" if ctx_size else ""
        rows.append(f'''<div class="ho-row"><div class="ho-line" style="padding-left:{depth*16}px">
<span>🔀</span><span class="ho-arrow"></span><span>{_esc(span.name)}</span>
{f'<span class="ctx-badge">{ctx_str}</span>' if ctx_str else ''}
</div></div>''')
        return rows
    
    bar_cls = "ok"
    annotation = ""
    if span.status == SpanStatus.FAILED:
        bar_cls = "err"
    
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    ver = _esc(span.metadata.get("agent_version", ""))
    ver_html = f'<span class="vr">({ver})</span>' if ver else ""
    
    opacity = "opacity:0.65;" if span.span_type == SpanType.TOOL else ""
    
    # Error annotation
    err_html = ""
    if span.error:
        err_left = min(left_pct + width_pct + 1, 95)
        err_html = f'<div class="g-err" style="left:{err_left}%">⚠ {_esc(span.error)[:40]}</div>'
    
    par_cls = " parallel" if (parallel_ids and span.span_id in parallel_ids) else ""
    rows.append(f'''<div class="g-row{par_cls}" style="{opacity}">
<div class="g-lbl" style="padding-left:{depth*16}px"><span class="icon">{icon}</span><span class="nm">{_esc(span.name)}</span>{ver_html}</div>
<div class="g-bar-area"><div class="g-bar {bar_cls}" style="left:{left_pct:.1f}%;width:{max(width_pct,0.5):.1f}%">{dur_s}</div>{err_html}</div>
</div>''')
    
    # Render children
    children = children_map.get(span.span_id, [])
    children_sorted = sorted(children, key=lambda s: s.started_at or "")
    
    for i, child in enumerate(children_sorted):
        rows.extend(_render_gantt_rows(child, depth + 1, trace_start, dur_total, children_map, span_map, handoff_pairs, parallel_ids))
        
        # Insert handoff between sequential agents (only if analysis confirmed)
        if (child.span_type == SpanType.AGENT and 
            i + 1 < len(children_sorted) and 
            children_sorted[i + 1].span_type == SpanType.AGENT):
            pair_key = (child.name, children_sorted[i + 1].name)
            if pair_key in handoff_pairs:
                h = handoff_pairs[pair_key]
                ctx_str = f"{h.context_size_bytes:,}B" if h.context_size_bytes else ""
                rows.append(f'''<div class="ho-row"><div class="ho-line" style="padding-left:{(depth+1)*16}px">
<span>🔀</span><span class="ho-arrow"></span><span>{_esc(child.name)} → {_esc(children_sorted[i+1].name)}</span>
{f'<span class="ctx-badge">{ctx_str}</span>' if ctx_str else ''}
</div></div>''')
    
    return rows


def _build_suggestions_panel(trace) -> str:
    suggestions = _try_evolve(trace)
    if not suggestions:
        return ''
    items = []
    for s in suggestions:
        icon = {'failure': '🔴', 'bottleneck': '🐢', 'handoff': '🔀'}.get(s.category, '•')
        items.append(f'<div class="item">{icon} <b>{_esc(s.agent)}</b> ({s.confidence:.0%}): {_esc(s.suggestion[:60])}</div>')
    return f'<div class="d-box" style="grid-column:1/-1"><h4>🧠 Learned Suggestions</h4><div class="items">{chr(10).join(items)}</div></div>'

def _build_diagnostics(failures, bn, flow, ctx, retries=None, cost=None) -> str:
    # Failure panel
    fail_items = []
    for rc in failures.root_causes:
        cls = "ff-h" if rc.was_handled else "ff-u"
        label = "handled" if rc.was_handled else "unhandled"
        fail_items.append(f'<div class="item"><span class="ff-node {cls}">{_esc(rc.span_name)} · {label}</span></div>')
    fail_html = "\n".join(fail_items) if fail_items else '<div class="item" style="color:var(--gn)">No failures</div>'
    
    res_color = "var(--gn)" if failures.resilience_score >= 0.8 else ("var(--yl)" if failures.resilience_score >= 0.5 else "var(--rd)")
    
    # Bottleneck panel
    bn_items = []
    if bn:
        for a in bn.agent_rankings[:5]:
            bar_w = max(a["pct"], 2)
            color = "var(--yl)" if a["name"] == bn.bottleneck_span else ("var(--rd)" if a["status"] == "failed" else "var(--gn)")
            bn_items.append(f'<div class="item"><span style="color:{color}">{_esc(a["name"])}</span> <span style="color:var(--dim)">{a["duration_ms"]:.0f}ms ({a["pct"]:.0f}%)</span></div>')
    bn_html = "\n".join(bn_items) if bn_items else ""
    
    # Handoff panel  
    ho_items = []
    for h in flow.handoffs:
        ctx_str = f"{h.context_size_bytes:,}B" if h.context_size_bytes else "?"
        ho_items.append(f'<div class="item">{_esc(h.from_agent)} → {_esc(h.to_agent)} <span class="ctx-badge">{ctx_str}</span></div>')
    ho_html = "\n".join(ho_items) if ho_items else '<div class="item" style="color:var(--dim)">No handoffs detected</div>'
    
    # Critical path
    cp = " → ".join(flow.critical_path[:6]) if flow.critical_path else "N/A"
    
    # Context flow anomalies
    ctx_items = []
    for a in ctx.anomalies:
        if a.anomaly == "loss":
            ctx_items.append(f'<div class="item" style="color:var(--rd)">⚠ {_esc(a.from_agent)} → {_esc(a.to_agent)}: lost {a.keys_lost}</div>')
        elif a.anomaly == "bloat":
            ctx_items.append(f'<div class="item" style="color:var(--yl)">⚠ {_esc(a.from_agent)} → {_esc(a.to_agent)}: +{a.size_delta_bytes:,}B</div>')
    ctx_note = "\n".join(ctx_items) if ctx_items else '<div class="item" style="color:var(--gn)">No anomalies</div>'
    
    return f'''<div class="diag">
<h3>Orchestration Diagnostics</h3>
<div class="diag-grid">

<div class="d-box">
<h4>🔴 Failure Propagation</h4>
<div class="val" style="color:{res_color}">{failures.resilience_score:.0%} resilience</div>
<div class="det">{failures.total_failed_spans} failed · {failures.handled_count} handled · {failures.unhandled_count} unhandled</div>
<div class="items">{fail_html}</div>
</div>

<div class="d-box">
<h4>🐢 Bottleneck</h4>
<div class="val">{_esc(bn.bottleneck_span) if bn else "N/A"}</div>
<div class="det">{f"{bn.bottleneck_duration_ms:.0f}ms ({bn.bottleneck_pct:.0f}%)" if bn else ""}</div>
<div class="items">{bn_html}</div>
</div>

<div class="d-box">
<h4>🔀 Handoff Flow</h4>
<div class="val">{len(flow.handoffs)} handoffs</div>
<div class="det">Total: {ctx.total_context_bytes:,}B</div>
<div class="items">{ho_html}</div>
</div>

<div class="d-box">
<h4>📊 Critical Path & Context</h4>
<div class="val" style="font-size:12px">{_esc(cp)}</div>
<div class="det">{flow.critical_path_duration_ms:.0f}ms</div>
<div class="items">{ctx_note}</div>
</div>

</div></div>'''


def generate_report_from_trace(trace: ExecutionTrace, output: str = ".agentguard/report.html") -> str:
    """Generate HTML report from a single trace object (no file I/O needed)."""
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_build_full_html([trace]), encoding="utf-8")
    return str(out_path)


def trace_to_html_string(trace: ExecutionTrace) -> str:
    """Generate HTML string from a trace (for embedding/serving)."""
    return _build_full_html([trace])
