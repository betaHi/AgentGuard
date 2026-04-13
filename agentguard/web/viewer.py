"""Standalone HTML report generator — orchestration diagnostics panel.

Generates a single HTML file matching the target prototype design:
- Left sidebar: agent health cards
- Main area: Gantt-style timeline with handoff indicators
- Bottom: diagnostics grid (failures, bottleneck, handoffs, critical path)

All diagnostics powered by analysis.py (single source of truth).
"""

from __future__ import annotations

import contextlib
import html as html_mod
import json
from pathlib import Path
from typing import Any

from agentguard.analysis import (
    analyze_bottleneck,
    analyze_context_flow,
    analyze_cost,
    analyze_cost_yield,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
    analyze_retries,
)
from agentguard.core.trace import ExecutionTrace, Span, SpanStatus, SpanType
from agentguard.errors import analyze_errors


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
            with contextlib.suppress(Exception):
                trace_objs.append(ExecutionTrace.from_dict(
                    json.loads(f.read_text(encoding="utf-8"))
                ))

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_build_full_html(trace_objs), encoding="utf-8")
    return str(out_path)


# --- HTML template constants ---
_VIEWER_CSS = """<style>
:root{{--bg:#0d1117;--sf:#161b22;--bd:#30363d;--tx:#c9d1d9;--dim:#8b949e;--br:#f0f6fc;
--gn:#3fb950;--rd:#f85149;--bl:#58a6ff;--yl:#e3b341;--pp:#bc8cff;
--gn-bg:#1b3a2a;--rd-bg:#3d1f1f;--yl-bg:#3d321e;--bl-bg:#1e2d3d;--pp-bg:#2d1e3d;}}
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
.g-row{{display:flex;align-items:center;padding:2px 0;min-height:24px;border-bottom:1px solid rgba(48,54,61,0.4);}}
.g-row:hover{{background:rgba(56,139,253,0.06);}}
.g-lbl{{width:180px;flex-shrink:0;display:flex;align-items:center;gap:5px;font-size:11px;padding-right:6px;overflow:hidden;}}
.g-lbl .icon{{font-size:12px;}} .g-lbl .nm{{font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.g-lbl .vr{{font-size:8px;color:var(--bl);background:var(--bl-bg);padding:1px 5px;border-radius:3px;white-space:nowrap;}}
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
.diag-grid{{display:grid;grid-template-columns:repeat(auto-fit, minmax(280px, 1fr));gap:10px;}}
.d-box{{background:var(--bg);border:1px solid var(--bd);border-radius:6px;padding:0;}}
.d-box summary{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);padding:10px 10px 5px;cursor:pointer;list-style:none;display:flex;align-items:center;gap:4px;}}
.d-box summary::-webkit-details-marker{{display:none;}}
.d-box summary::before{{content:'▶';font-size:8px;transition:transform .2s;}}
.d-box[open] summary::before{{transform:rotate(90deg);}}
.d-box .d-body{{padding:0 10px 10px;}}
.d-box h4{{font-size:9px;text-transform:uppercase;letter-spacing:.5px;color:var(--dim);margin:0;display:inline;}}
.d-box .val{{font-size:16px;font-weight:700;color:var(--br);}}
.d-box .det{{font-size:10px;color:var(--dim);margin-top:3px;}}
.d-box .items{{font-size:10px;margin-top:5px;}}
.d-box .item{{padding:1px 0;display:flex;align-items:center;gap:3px;}}
.ff-node{{padding:1px 6px;border-radius:3px;font-size:9px;}}
.ff-h{{background:var(--yl-bg);color:var(--yl);}} .ff-u{{background:var(--rd-bg);color:var(--rd);}}
.empty{{text-align:center;padding:60px;color:var(--dim);}}
.ft{{text-align:center;padding:12px;color:var(--dim);font-size:10px;border-top:1px solid var(--bd);margin-top:14px;}}
.zoom-bar{{display:flex;align-items:center;gap:6px;margin-bottom:8px;}}
.zoom-btn{{background:var(--sf);border:1px solid var(--bd);color:var(--tx);border-radius:4px;padding:2px 8px;font-size:12px;cursor:pointer;font-family:monospace;}}
.zoom-btn:hover{{background:var(--bd);color:var(--br);}}
.zoom-level{{font-size:10px;color:var(--dim);min-width:40px;text-align:center;}}
.tl-wrap{{overflow-x:auto;position:relative;}}
.tl-inner{{min-width:100%;transition:min-width 0.2s ease;}}
.tl-axis{{display:flex;padding:0 0 4px 180px;position:relative;height:18px;}}
.tl-axis .tick-mark{{position:absolute;top:0;font-size:9px;color:var(--dim);transform:translateX(-50%);}}
.tl-axis .tick-line{{position:absolute;top:14px;width:1px;height:4px;background:var(--bd);transform:translateX(-50%);}}
@media print
@media print{{body{{background:#fff;color:#000;}}.top-bar,.sidebar{{background:#f5f5f5;}}.main{{background:#fff;}}
.ag-card,.d-box{{border-color:#ddd;background:#fafafa;}}.g-bar.ok{{background:#28a745;}}.g-bar.err{{background:#dc3545;}}
.badge,.score-badge{{print-color-adjust:exact;-webkit-print-color-adjust:exact;}}}}
@media(max-width:768px){{.layout{{grid-template-columns:1fr;}}.sidebar{{border-right:none;border-bottom:1px solid var(--bd);max-height:200px;}}}}
</style>"""

_VIEWER_JS = """<script>
document.querySelectorAll(".g-row").forEach(function(row){{
  row.style.cursor="pointer";
  row.addEventListener("click",function(){{
    var ex=this.nextElementSibling;
    if(ex&&ex.classList.contains("g-detail")){{ex.remove();return;}}
    document.querySelectorAll(".g-detail").forEach(function(d){{d.remove();}});
    var bar=this.querySelector(".g-bar");
    if(!bar)return;
    var nm=this.querySelector(".nm");
    var name=nm?nm.textContent:"";
    var dur=bar.textContent||"";
    var icon=this.querySelector(".icon");
    var type=icon?icon.textContent:"";
    var cls=bar.classList.contains("err")?"❌ failed":bar.classList.contains("slow")?"⚠ slow":"✅ ok";
    var par=this.classList.contains("parallel")?" · ⚡ parallel":"";
    var detail=document.createElement("div");
    detail.className="g-detail";
    detail.style.cssText="padding:8px 12px 8px 196px;background:#161b22;border-bottom:1px solid #21262d;font-size:10px;color:#6e7681;animation:fadeIn 0.15s;";
    detail.innerHTML="<b style=color:#f0f6fc>"+type+" "+name+"</b> · "+dur+" · "+cls+par;
    this.after(detail);
  }});
}});
document.addEventListener("keydown",function(e){{
  if(e.key==="Escape")document.querySelectorAll(".g-detail").forEach(function(d){{d.remove();}});
}});
function filterSpans(){{
  var q=(document.getElementById("span-search").value||"").toLowerCase();
  var st=document.getElementById("status-filter").value;
  var minD=parseFloat(document.getElementById("min-dur").value)||0;
  var maxD=parseFloat(document.getElementById("max-dur").value)||Infinity;
  var rows=document.querySelectorAll(".g-row");
  var shown=0;
  rows.forEach(function(row){{
    var nm=row.querySelector(".nm");
    var name=nm?(nm.textContent||"").toLowerCase():"";
    var bar=row.querySelector(".g-bar");
    var durText=bar?bar.textContent.replace(/[^0-9.]/g,""):"";
    var dur=parseFloat(durText)||0;
    var isErr=bar&&bar.classList.contains("err");
    var isSlow=bar&&bar.classList.contains("slow");
    var statusOk=!st||(st==="err"&&isErr)||(st==="slow"&&isSlow)||(st==="ok"&&!isErr&&!isSlow);
    var nameOk=!q||name.indexOf(q)!==-1;
    var durOk=dur>=minD&&dur<=maxD;
    var show=nameOk&&statusOk&&durOk;
    row.style.display=show?"":"none";
    if(show)shown++;
  }});
  var ct=document.getElementById("filter-count");
  if(ct)ct.textContent=shown+"/"+rows.length+" spans";
}}
["span-search","status-filter","min-dur","max-dur"].forEach(function(id){{
  var el=document.getElementById(id);
  if(el)el.addEventListener("input",filterSpans);
}});
filterSpans();
var _zoomLevel=100;
function zoomGantt(dir){{
  if(dir===0){{_zoomLevel=100;}}
  else{{_zoomLevel=Math.max(50,Math.min(400,_zoomLevel+(dir*50)));}}
  var el=document.getElementById("gantt-inner");
  if(el){{el.style.minWidth=_zoomLevel+"%";}}
  var lbl=document.getElementById("zoom-pct");
  if(lbl){{lbl.textContent=_zoomLevel+"%";}}
}}
</script>"""


def _build_head(primary: ExecutionTrace, score: Any, status_cls: str,
                status_txt: str, dur_total: float, trace_count: int) -> str:
    """Build the HTML head + top bar with trace metadata."""
    return f"""<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>AgentGuard — Orchestration Panel</title>
{_VIEWER_CSS}</head><body>

<div class="top-bar">
<h1>🛡️ AgentGuard</h1>
<div class="meta">
{_esc(primary.task)}
<span class="badge {status_cls}" style="margin-left:8px">{status_txt}</span>
<span class="score-badge score-{score.grade.lower()}">{score.overall:.0f}/100 ({score.grade})</span>
{f'<span style="margin-left:8px;color:var(--dim)">{trace_count} traces</span>' if trace_count > 1 else ''}
</div>
<div class="meta-detail" style="font-size:11px;color:var(--dim);padding:2px 16px 0">
⏱ {dur_total/1000:.1f}s total
· 🤖 {len(primary.agent_spans)} agents
· 📊 {len(primary.spans)} spans
· 🔧 {sum(1 for s in primary.spans if s.span_type.value == 'tool')} tools
· 🔀 {sum(1 for s in primary.spans if s.span_type.value == 'handoff')} handoffs
· 🔴 {sum(1 for s in primary.spans if s.status and s.status.value == 'failed')} failed
· Trigger: {_esc(primary.trigger)}
</div></div>"""


def _build_trace_list(traces: list[ExecutionTrace]) -> str:
    """Build the trace selector sidebar section for multi-trace views."""
    if len(traces) <= 1:
        return ""
    items = []
    for i, t in enumerate(traces[:20]):
        st = "✅" if t.status.value == "completed" else "❌"
        dur = f"{t.duration_ms:.0f}ms" if t.duration_ms else "?"
        active = "font-weight:700;color:var(--br);" if i == 0 else ""
        items.append(f'<div style="padding:4px 0;font-size:10px;{active}">{st} {t.task or t.trace_id[:12]} · {dur}</div>')
    return (f'<div style="margin-top:12px;border-top:1px solid var(--bd);padding-top:8px">'
            f'<h2 style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:6px">'
            f'Recent Traces ({len(traces)})</h2>{"".join(items)}</div>')


def _build_body_layout(
    primary: ExecutionTrace,
    agent_cards: str, trace_list_html: str,
    timeline: str, diagnostics: str,
) -> str:
    """Build the main body layout: sidebar + timeline + diagnostics + footer."""
    return f"""<div class="layout">
<div class="sidebar">{agent_cards}{trace_list_html}</div>
<div class="main">
<h2>Execution Timeline</h2>
{timeline}
{diagnostics}
<details style="margin-top:14px;border:1px solid var(--bd);border-radius:6px;padding:8px;">
<summary style="cursor:pointer;font-size:10px;color:var(--dim);padding:4px;">📋 Raw Trace JSON</summary>
<pre style="background:var(--bg);border:1px solid var(--bd);border-radius:4px;padding:8px;font-size:9px;color:var(--dim);overflow-x:auto;max-height:300px;margin-top:8px;">{_esc(primary.to_json(indent=2)[:5000])}</pre>
</details>
<div class="ft">AgentGuard · Orchestration Observability · {len(primary.spans)} spans · {primary.trace_id}</div>
</div></div>

{_VIEWER_JS}
</body></html>"""


def _build_full_html(traces: list[ExecutionTrace]) -> str:
    """Build complete HTML report for one or more traces.

    Orchestrates analysis, then assembles head, sidebar, timeline,
    diagnostics, and scripts into a single HTML document.
    """
    if not traces:
        return _build_empty_html()

    primary = traces[0]
    failures = analyze_failures(primary)
    flow = analyze_flow(primary)
    bn = analyze_bottleneck(primary) if primary.agent_spans else None
    ctx = analyze_context_flow(primary)
    dur_total = primary.duration_ms or 1

    from agentguard.scoring import score_trace as _score_trace
    _score = _score_trace(primary)

    agent_cards = _build_sidebar(primary, failures, bn)
    timeline = _build_gantt(primary, flow, dur_total)

    retries = analyze_retries(primary)
    cost = analyze_cost(primary)
    error_report = analyze_errors(primary)
    cost_yield = analyze_cost_yield(primary)
    decisions = analyze_decisions(primary)
    from agentguard.propagation import analyze_propagation
    propagation = analyze_propagation(primary)
    diagnostics = _build_diagnostics(failures, bn, flow, ctx, retries, cost, error_report,
                                     cost_yield, decisions, propagation)

    status_txt = "PASS" if primary.status == SpanStatus.COMPLETED else "FAIL"
    status_cls = "b-pass" if primary.status == SpanStatus.COMPLETED else "b-fail"
    trace_list_html = _build_trace_list(traces)

    head = _build_head(primary, _score, status_cls, status_txt, dur_total, len(traces))
    body = _build_body_layout(primary, agent_cards, trace_list_html, timeline, diagnostics)
    return head + "\n" + body


def _build_empty_html() -> str:
    return '''<!DOCTYPE html><html><head><title>AgentGuard</title>
<style>body{background:#0d1117;color:#8b949e;font-family:monospace;display:flex;justify-content:center;align-items:center;height:100vh;}
</style></head><body><div style="text-align:center"><h1>🛡️ AgentGuard</h1><p>No traces found. Record some agent executions first.</p></div><script>
document.querySelectorAll(".g-row").forEach(function(row){{
  row.style.cursor="pointer";
  row.addEventListener("click",function(){{
    var ex=this.nextElementSibling;
    if(ex&&ex.classList.contains("g-detail")){{ex.remove();return;}}
    document.querySelectorAll(".g-detail").forEach(function(d){{d.remove();}});
    var bar=this.querySelector(".g-bar");
    if(!bar)return;
    var nm=this.querySelector(".nm");
    var name=nm?nm.textContent:"";
    var dur=bar.textContent||"";
    var icon=this.querySelector(".icon");
    var type=icon?icon.textContent:"";
    var cls=bar.classList.contains("err")?"❌ failed":bar.classList.contains("slow")?"⚠ slow":"✅ ok";
    var par=this.classList.contains("parallel")?" · ⚡ parallel":"";
    var detail=document.createElement("div");
    detail.className="g-detail";
    detail.style.cssText="padding:8px 12px 8px 196px;background:#161b22;border-bottom:1px solid #21262d;font-size:10px;color:#6e7681;animation:fadeIn 0.15s;";
    detail.innerHTML="<b style=color:#f0f6fc>"+type+" "+name+"</b> · "+dur+" · "+cls+par;
    this.after(detail);
  }});
}});
document.addEventListener("keydown",function(e){{
  if(e.key==="Escape")document.querySelectorAll(".g-detail").forEach(function(d){{d.remove();}});
}});
var _zoomLevel=100;
function zoomGantt(dir){
  if(dir===0){_zoomLevel=100;}
  else{_zoomLevel=Math.max(50,Math.min(400,_zoomLevel+(dir*50)));}
  var el=document.getElementById("gantt-inner");
  if(el){el.style.minWidth=_zoomLevel+"%";}
  var lbl=document.getElementById("zoom-pct");
  if(lbl){lbl.textContent=_zoomLevel+"%";}
}
</script>
</body></html>'''


def _sidebar_agent_card(s, dur_total: float, failed_agents: set, warned_agents: set, bn_name: str, multi: bool) -> str:
    """Build a single agent card for the sidebar."""
    dur = s.duration_ms or 0
    pct = (dur / dur_total) * 100
    ver = _esc(s.metadata.get("agent_version", ""))
    if s.status == SpanStatus.FAILED or s.name in failed_agents:
        dot_cls, bar_color = "dot-err", "var(--rd)"
        extra = f'<span style="color:var(--rd)">✗ {_esc(s.error or "failed")[:30]}</span>'
    elif s.name == bn_name and multi:
        dot_cls, bar_color = "dot-warn", "var(--yl)"
        extra = f'<span style="color:var(--yl)">🐢 bottleneck ({pct:.0f}%)</span>'
    elif s.name in warned_agents:
        dot_cls, bar_color = "dot-warn", "var(--yl)"
        extra = '<span style="color:var(--yl)">⚡ fallback used</span>'
    else:
        dot_cls, bar_color = "dot-ok", "var(--gn)"
        extra = '<span>✓ pass</span>'
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    return f'''<div class="ag-card">
<div class="ag-name"><span class="dot {dot_cls}"></span> {_esc(s.name)} <span style="font-size:9px;color:var(--dim)">{ver}</span></div>
<div class="ag-stats"><span>{dur_s}</span>{extra}</div>
<div class="ag-bar"><div class="ag-bar-fill" style="width:{max(pct,2):.0f}%;background:{bar_color}"></div></div>
</div>'''


def _sidebar_tool_cards(trace: ExecutionTrace, dur_total: float, bn_name: str) -> str:
    """Build tool span cards for the sidebar (top 8 by duration)."""
    tools = sorted(trace.tool_spans, key=lambda s: -(s.duration_ms or 0))
    if not tools:
        return ""
    parts = ['<div style="margin-top:8px;border-top:1px solid var(--bd);padding-top:8px">',
             f'<h2 style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:6px">Tools ({len(trace.tool_spans)})</h2>']
    for s in tools[:8]:
        dur = s.duration_ms or 0
        pct = (dur / dur_total) * 100
        dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
        if s.status == SpanStatus.FAILED:
            dot_cls, bar_color = "dot-err", "var(--rd)"
            extra = f'<span style="color:var(--rd)">\u2717 {_esc(s.error or "failed")[:30]}</span>'
        elif s.name == bn_name:
            dot_cls, bar_color = "dot-warn", "var(--yl)"
            extra = f'<span style="color:var(--yl)">\U0001f422 bottleneck ({pct:.0f}%)</span>'
        elif pct > 20:
            dot_cls, bar_color = "dot-warn", "var(--yl)"
            extra = f'<span style="color:var(--yl)">{pct:.0f}% of trace</span>'
        else:
            dot_cls, bar_color = "dot-ok", "var(--gn)"
            extra = '<span>\u2713</span>'
        parts.append(f'''<div class="ag-card">
<div class="ag-name"><span class="dot {dot_cls}"></span> \U0001f527 {_esc(s.name)}</div>
<div class="ag-stats"><span>{dur_s}</span>{extra}</div>
<div class="ag-bar"><div class="ag-bar-fill" style="width:{max(pct,2):.0f}%;background:{bar_color}"></div></div>
</div>''')
    parts.append('</div>')
    return "\n".join(parts)


def _sidebar_llm_summary(trace: ExecutionTrace) -> str:
    """Build LLM calls summary section for the sidebar."""
    llm_spans = [s for s in trace.spans if s.span_type == SpanType.LLM_CALL]
    if not llm_spans:
        return ""
    total_tokens = sum(s.token_count or 0 for s in llm_spans)
    total_cost = sum(s.estimated_cost_usd or 0 for s in llm_spans)
    return (f'<div style="margin-top:8px;border-top:1px solid var(--bd);padding-top:8px">'
            f'<h2 style="font-size:10px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin-bottom:6px">LLM Calls ({len(llm_spans)})</h2>'
            f'<div class="ag-card"><div class="ag-stats"><span>{total_tokens:,} tokens</span><span>${total_cost:.4f}</span></div></div>'
            f'</div>')


def _build_sidebar(trace: ExecutionTrace, failures, bn) -> str:
    """Build the sidebar with agent cards, tool cards, and LLM summary."""
    dur_total = trace.duration_ms or 1
    failed_agents = {rc.span_name for rc in failures.root_causes if not rc.was_handled}
    warned_agents = {rc.span_name for rc in failures.root_causes if rc.was_handled}
    bn_name = bn.bottleneck_span if bn else ""
    multi = len(trace.agent_spans) > 1

    agents = sorted(trace.agent_spans, key=lambda s: (
        0 if s.status == SpanStatus.FAILED else 1, -(s.duration_ms or 0)))

    cards = [f'<h2>Agents ({len(trace.agent_spans)})</h2>']
    for s in agents:
        cards.append(_sidebar_agent_card(s, dur_total, failed_agents, warned_agents, bn_name, multi))
    cards.append(_sidebar_tool_cards(trace, dur_total, bn_name))
    cards.append(_sidebar_llm_summary(trace))
    return "\n".join(cards)


def _detect_parallel_spans(trace: ExecutionTrace) -> set[str]:
    """Detect spans that execute in parallel (overlapping time, same parent)."""
    from datetime import datetime as _dt
    parallel_ids: set[str] = set()
    timed = []
    for s in trace.spans:
        if s.span_type in (SpanType.AGENT, SpanType.TOOL):
            try:
                start = _dt.fromisoformat(s.started_at) if s.started_at else None
                end = _dt.fromisoformat(s.ended_at) if s.ended_at else None
                if start and end:
                    timed.append((s, start, end))
            except Exception:
                pass
    for i, (a, a_s, a_e) in enumerate(timed):
        for _j, (b, b_s, b_e) in enumerate(timed[i+1:], i+1):
            if a_s < b_e and b_s < a_e and a.parent_span_id == b.parent_span_id:
                parallel_ids.add(a.span_id)
                parallel_ids.add(b.span_id)
    return parallel_ids


def _build_time_axis(dur_total: float, steps: int = 8) -> str:
    """Build the Gantt chart time axis with labeled tick marks."""
    step_ms = dur_total / steps
    marks = []
    for i in range(steps + 1):
        ms = i * step_ms
        pct = (i / steps) * 100
        label = f"{int(ms)}ms" if ms < 1000 else f"{ms / 1000:.1f}s"
        marks.append(
            f'<span class="tick-mark" style="left:{pct:.1f}%">{label}</span>'
            f'<span class="tick-line" style="left:{pct:.1f}%"></span>'
        )
    return f'<div class="tl-axis">{"".join(marks)}</div>'


_GANTT_ZOOM_BAR = (
    '<div class="zoom-bar">'
    '<button class="zoom-btn" onclick="zoomGantt(-1)" title="Zoom out">−</button>'
    '<span class="zoom-level" id="zoom-pct">100%</span>'
    '<button class="zoom-btn" onclick="zoomGantt(1)" title="Zoom in">+</button>'
    '<button class="zoom-btn" onclick="zoomGantt(0)" title="Reset zoom">⟲</button>'
    '</div>'
)

_GANTT_SEARCH_BAR = (
    '<div style="padding:8px 12px;background:var(--bg);border-bottom:1px solid var(--bd);'
    'display:flex;gap:8px;align-items:center;flex-wrap:wrap;font-size:11px">'
    '<input id="span-search" type="text" placeholder="Search agent name..." '
    'style="background:#0d1117;border:1px solid var(--bd);color:var(--fg);padding:4px 8px;'
    'border-radius:4px;width:180px;font-size:11px">'
    '<select id="status-filter" style="background:#0d1117;border:1px solid var(--bd);'
    'color:var(--fg);padding:4px;border-radius:4px;font-size:11px">'
    '<option value="">All statuses</option>'
    '<option value="ok">Completed</option>'
    '<option value="err">Failed</option>'
    '<option value="slow">Slow</option>'
    '</select>'
    '<label style="color:var(--dim)">Min ms: <input id="min-dur" type="number" min="0" '
    'style="background:#0d1117;border:1px solid var(--bd);color:var(--fg);padding:4px;'
    'border-radius:4px;width:60px;font-size:11px"></label>'
    '<label style="color:var(--dim)">Max ms: <input id="max-dur" type="number" min="0" '
    'style="background:#0d1117;border:1px solid var(--bd);color:var(--fg);padding:4px;'
    'border-radius:4px;width:60px;font-size:11px"></label>'
    '<span id="filter-count" style="color:var(--dim);margin-left:auto"></span>'
    '</div>'
)


def _build_gantt(trace: ExecutionTrace, flow, dur_total: float) -> str:
    """Build the full Gantt timeline: axis, rows, zoom/search controls."""
    parallel_ids = _detect_parallel_spans(trace)
    header = _build_time_axis(dur_total)

    span_map = {s.span_id: s for s in trace.spans}
    children_map: dict[str, list[Span]] = {}
    for s in trace.spans:
        if s.parent_span_id:
            children_map.setdefault(s.parent_span_id, []).append(s)

    roots = [s for s in trace.spans if s.parent_span_id is None or s.parent_span_id not in span_map]
    handoff_pairs = {(h.from_agent, h.to_agent): h for h in flow.handoffs}

    rows = []
    for root in roots:
        rows.extend(_render_gantt_rows(root, 0, trace.started_at, dur_total,
                                       children_map, span_map, handoff_pairs, parallel_ids))

    inner = header + "\n" + "\n".join(rows)
    return f'{_GANTT_ZOOM_BAR}{_GANTT_SEARCH_BAR}<div class="tl-wrap"><div class="tl-inner" id="gantt-inner">{inner}</div></div>'


def _render_handoff_row(depth: int, from_name: str, to_name: str, ctx_bytes: int) -> str:
    """Render a handoff indicator row between agents."""
    ctx_str = f"{ctx_bytes:,}B" if ctx_bytes else ""
    badge = f'<span class="ctx-badge">{ctx_str}</span>' if ctx_str else ""
    return f'''<div class="ho-row"><div class="ho-line" style="padding-left:{depth*16}px">
<span>🔀</span><span class="ho-arrow"></span><span>{_esc(from_name)} → {_esc(to_name)}</span>
{badge}
</div></div>'''


def _render_span_bar(span: Span, depth: int, trace_start: str, dur_total: float, parallel_ids) -> str:
    """Render a single span as a Gantt bar row."""
    from datetime import datetime
    try:
        t_start = datetime.fromisoformat(trace_start)
        s_start = datetime.fromisoformat(span.started_at) if span.started_at else t_start
        offset_ms = (s_start - t_start).total_seconds() * 1000
    except Exception:
        offset_ms = 0
    dur = span.duration_ms or 0
    left_pct = (offset_ms / max(dur_total, 1)) * 100
    width_pct = (dur / max(dur_total, 1)) * 100
    icons = {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}
    icon = icons.get(span.span_type.value, "●")
    bar_cls = "err" if span.status == SpanStatus.FAILED else "ok"
    dur_s = f"{dur:.0f}ms" if dur < 1000 else f"{dur/1000:.1f}s"
    ver = _esc(span.metadata.get("agent_version", ""))
    ver_html = f'<span class="vr">{ver}</span>' if ver else ""
    opacity = "opacity:0.65;" if span.span_type == SpanType.TOOL else ""
    err_html = ""
    if span.error:
        err_left = min(left_pct + width_pct + 1, 95)
        err_html = f'<div class="g-err" style="left:{err_left}%">⚠ {_esc(span.error)[:40]}</div>'
    retry_html = ""
    if span.retry_count > 0:
        retry_left = min(left_pct + width_pct + 1, 95)
        retry_html = f'<div class="g-ann" style="left:{retry_left}%;color:var(--yl)">🔄×{span.retry_count}</div>'
    par_cls = " parallel" if (parallel_ids and span.span_id in parallel_ids) else ""
    return f'''<div class="g-row{par_cls}" style="{opacity}">
<div class="g-lbl" style="padding-left:{depth*16}px"><span class="icon">{icon}</span><span class="nm">{_esc(span.name)}</span>{ver_html}</div>
<div class="g-bar-area"><div class="g-bar {bar_cls}" style="left:{left_pct:.1f}%;width:{max(width_pct,0.5):.1f}%">{dur_s}</div>{err_html}{retry_html}</div>
</div>'''


def _render_gantt_rows(span: Span, depth: int, trace_start: str, dur_total: float,
                       children_map, span_map, handoff_pairs, parallel_ids=None) -> list[str]:
    """Recursively render a span and its children as Gantt rows."""
    rows = []
    if span.span_type == SpanType.HANDOFF:
        ctx_size = span.context_size_bytes or 0
        rows.append(_render_handoff_row(depth, span.name, "", ctx_size))
        return rows

    rows.append(_render_span_bar(span, depth, trace_start, dur_total, parallel_ids))

    children = sorted(children_map.get(span.span_id, []), key=lambda s: s.started_at or "")
    for i, child in enumerate(children):
        rows.extend(_render_gantt_rows(child, depth + 1, trace_start, dur_total,
                                       children_map, span_map, handoff_pairs, parallel_ids))
        if (child.span_type == SpanType.AGENT and
            i + 1 < len(children) and children[i + 1].span_type == SpanType.AGENT):
            pair_key = (child.name, children[i + 1].name)
            if pair_key in handoff_pairs:
                h = handoff_pairs[pair_key]
                rows.append(_render_handoff_row(
                    (depth + 1), child.name, children[i + 1].name, h.context_size_bytes or 0))
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

def _build_context_waterfall(ctx) -> str:
    """Build a context flow waterfall chart showing size at each handoff.

    Each handoff is rendered as a horizontal bar proportional to context
    size, with color coding for anomalies (red=loss, yellow=bloat/truncation,
    green=ok).
    """
    if not ctx.points:
        return ""

    max_size = max((p.size_bytes for p in ctx.points), default=1) or 1

    bars = []
    for p in ctx.points:
        pct = (p.size_bytes / max_size) * 100
        if p.anomaly in ("loss", "truncation"):
            color = "var(--rd)"
            icon = "\u26a0"
        elif p.anomaly == "bloat":
            color = "var(--yl)"
            icon = "\u26a0"
        else:
            color = "var(--gn)"
            icon = "\u2713"

        size_str = f"{p.size_bytes:,}B" if p.size_bytes < 10000 else f"{p.size_bytes/1024:.1f}KB"
        detail = ""
        if hasattr(p, "truncation_detail") and p.truncation_detail:
            detail = f' <span style="color:var(--dim);font-size:9px">\u2702 {_esc(p.truncation_detail)}</span>'
        elif p.keys_lost:
            detail = f' <span style="color:var(--rd);font-size:9px">lost: {_esc(", ".join(p.keys_lost[:3]))}</span>'

        bars.append(
            f'<div style="display:flex;align-items:center;gap:6px;margin:3px 0;font-size:10px">'
            f'<span style="min-width:160px;color:var(--dim)">{icon} {_esc(p.from_agent)} \u2192 {_esc(p.to_agent)}</span>'
            f'<div style="flex:1;height:14px;background:var(--bd);border-radius:3px;overflow:hidden">'
            f'<div style="width:{max(pct,2):.0f}%;height:100%;background:{color};border-radius:3px"></div>'
            f'</div>'
            f'<span style="min-width:60px;text-align:right;color:var(--tx)">{size_str}</span>'
            f'{detail}'
            f'</div>'
        )

    return (
        f'<div class="diag" style="margin-top:10px">'
        f'<h3 style="font-size:11px;color:var(--br);margin-bottom:8px">'
        f'\U0001f4ca Context Flow Waterfall ({len(ctx.points)} handoffs, {ctx.total_context_bytes:,}B total)</h3>'
        f'<div style="padding:4px 8px">{"".join(bars)}</div>'
        f'</div>'
    )


def _panel_failures(failures) -> str:
    """Build failure propagation panel HTML."""
    items = []
    for rc in failures.root_causes:
        cls = "ff-h" if rc.was_handled else "ff-u"
        label = "handled" if rc.was_handled else "unhandled"
        items.append(f'<div class="item"><span class="ff-node {cls}">{_esc(rc.span_name)} · {label}</span></div>')
    fail_html = "\n".join(items) if items else '<div class="item" style="color:var(--gn)">No failures</div>'
    res_color = "var(--gn)" if failures.resilience_score >= 0.8 else ("var(--yl)" if failures.resilience_score >= 0.5 else "var(--rd)")
    return f"""<details class="d-box" open>
<summary><h4>🔴 Failure Propagation</h4></summary>
<div class="d-body">
<div class="val" style="color:{res_color}">{failures.resilience_score:.0%} resilience</div>
<div class="det">{failures.total_failed_spans} failed · {failures.handled_count} handled · {failures.unhandled_count} unhandled</div>
<div class="items">{fail_html}</div>
</div></details>"""


def _panel_bottleneck(bn) -> str:
    """Build bottleneck panel HTML."""
    if not bn:
        return ""
    items = []
    for a in bn.agent_rankings[:5]:
        color = "var(--yl)" if a["name"] == bn.bottleneck_span else ("var(--rd)" if a["status"] == "failed" else "var(--gn)")
        items.append(f'<div class="item"><span style="color:{color}">{_esc(a["name"])}</span> <span style="color:var(--dim)">{a["duration_ms"]:.0f}ms ({a["pct"]:.0f}%)</span></div>')
    bn_html = "\n".join(items)
    return f"""<details class="d-box" open>
<summary><h4>🐢 Bottleneck</h4></summary>
<div class="d-body">
<div class="val">{_esc(bn.bottleneck_span)}</div>
<div class="det">{bn.bottleneck_duration_ms:.0f}ms ({bn.bottleneck_pct:.0f}%)</div>
<div class="items">{bn_html}</div>
</div></details>"""


def _panel_handoffs(flow, ctx) -> str:
    """Build handoff flow + critical path + context anomalies panel HTML."""
    ho_items = []
    for h in flow.handoffs:
        ctx_str = f"{h.context_size_bytes:,}B" if h.context_size_bytes else "?"
        ho_items.append(f'<div class="item">{_esc(h.from_agent)} → {_esc(h.to_agent)} <span class="ctx-badge">{ctx_str}</span></div>')
    ho_html = "\n".join(ho_items) if ho_items else '<div class="item" style="color:var(--dim)">No handoffs detected</div>'
    cp = " → ".join(flow.critical_path[:6]) if flow.critical_path else "N/A"
    ctx_items = []
    for a in ctx.anomalies:
        if a.anomaly == "loss":
            ctx_items.append(f'<div class="item" style="color:var(--rd)">⚠ {_esc(a.from_agent)} → {_esc(a.to_agent)}: lost {a.keys_lost}</div>')
        elif a.anomaly == "bloat":
            ctx_items.append(f'<div class="item" style="color:var(--yl)">⚠ {_esc(a.from_agent)} → {_esc(a.to_agent)}: +{a.size_delta_bytes:,}B</div>')
    ctx_note = "\n".join(ctx_items) if ctx_items else '<div class="item" style="color:var(--gn)">No anomalies</div>'
    return f"""<details class="d-box" open>
<summary><h4>🔀 Handoff Flow</h4></summary>
<div class="d-body">
<div class="val">{len(flow.handoffs)} handoffs</div>
<div class="det">Total: {ctx.total_context_bytes:,}B · Anomalies: {len(ctx.anomalies)}</div>
<div class="items">{ho_html}</div>
</div></details>

<details class="d-box" open>
<summary><h4>📊 Critical Path</h4></summary>
<div class="d-body">
<div class="val" style="font-size:12px">{_esc(cp)}</div>
<div class="det">{flow.critical_path_duration_ms:.0f}ms · {len(flow.critical_path)} hops</div>
<div class="items">{ctx_note}</div>
</div></details>"""


def _panel_cost(cost) -> str:
    """Build cost & tokens panel HTML."""
    return f"""<details class="d-box" open>
<summary><h4>💰 Cost & Tokens</h4></summary>
<div class="d-body">
<div class="val">${cost["total_cost_usd"]:.4f}</div>
<div class="det">{cost["total_tokens"]:,} tokens · {_esc(cost.get("most_expensive", "N/A"))} most expensive</div>
</div></details>"""


def _panel_retries(retries) -> str:
    """Build retries panel HTML."""
    return f"""<details class="d-box" open>
<summary><h4>🔄 Retries</h4></summary>
<div class="d-body">
<div class="val">{retries["retry_count"]} retries</div>
<div class="det">{retries["total_wasted_attempts"]} wasted attempts</div>
</div></details>"""


def _panel_errors(error_report) -> str:
    """Build error classification panel HTML."""
    cats = "".join(f'<div class="item"><span style="color:var(--dim)">{_esc(cat)}: {count}</span></div>' for cat, count in (error_report.by_category if error_report else {}).items())
    return f"""<details class="d-box" open>
<summary><h4>🐛 Error Classification</h4></summary>
<div class="d-body">
<div class="val">{error_report.total_errors if error_report else 0} errors</div>
<div class="det">{error_report.retryable_count if error_report else 0} retryable</div>
<div class="items">{cats}</div>
</div></details>"""


def _panel_cost_yield(cost_yield) -> str:
    """Build cost-yield analysis panel HTML."""
    wasteful = f"Most wasteful: {_esc(cost_yield.most_wasteful_agent)}" if cost_yield and cost_yield.most_wasteful_agent else "No waste detected"
    detail = f"Waste score: {cost_yield.waste_score:.0f}/100" if cost_yield else ""
    recs = cost_yield.recommendations[:3] if cost_yield else []
    items = "\n".join(f'<div class="item">💡 {_esc(r)}</div>' for r in recs) if recs else '<div class="item" style="color:var(--gn)">No recommendations</div>'
    return f"""<details class="d-box" open>
<summary><h4>📈 Cost-Yield Analysis</h4></summary>
<div class="d-body">
<div class="val">{wasteful}</div>
<div class="det">{detail}</div>
<div class="items">{items}</div>
</div></details>"""


def _panel_decisions(decisions) -> str:
    """Build orchestration decisions panel HTML."""
    quality = f"{decisions.decision_quality_score:.0%} quality" if decisions else "N/A"
    detail = f"{decisions.total_decisions} decisions · {decisions.decisions_leading_to_failure} led to failure" if decisions else ""
    items = []
    if decisions:
        for d in decisions.decisions[:3]:
            icon = "✗" if d.led_to_failure else "✓"
            items.append(f'<div class="item">{icon} {_esc(d.coordinator)} chose {_esc(d.chosen_agent)}</div>')
    items_html = "\n".join(items) if items else '<div class="item" style="color:var(--dim)">No decisions recorded</div>'
    return f"""<details class="d-box" open>
<summary><h4>🎯 Orchestration Decisions</h4></summary>
<div class="d-body">
<div class="val">{quality}</div>
<div class="det">{detail}</div>
<div class="items">{items_html}</div>
</div></details>"""


def _panel_propagation(propagation) -> str:
    """Build causal chains panel HTML."""
    containment = f"{propagation.containment_rate:.0%} containment" if propagation else "N/A"
    detail = f"{propagation.total_failures} failures · depth {propagation.max_depth}" if propagation else ""
    items = []
    if propagation:
        for c in propagation.causal_chains[:3]:
            icon = "🟡" if c.contained else "🔴"
            items.append(f'<div class="item">{icon} {_esc(c.root_span_name)}: {_esc(c.root_error[:40])}</div>')
    items_html = "\n".join(items) if items else '<div class="item" style="color:var(--gn)">No propagation</div>'
    return f"""<details class="d-box" open>
<summary><h4>💥 Causal Chains</h4></summary>
<div class="d-body">
<div class="val">{containment}</div>
<div class="det">{detail}</div>
<div class="items">{items_html}</div>
</div></details>"""


def _build_diagnostics(failures, bn, flow, ctx, retries=None, cost=None, error_report=None,
                       cost_yield=None, decisions=None, propagation=None) -> str:
    """Assemble all diagnostic panels into a grid."""
    panels = [
        _panel_failures(failures),
        _panel_bottleneck(bn),
        _panel_handoffs(flow, ctx),
        _panel_cost(cost) if cost else "",
        _panel_retries(retries) if retries else "",
        _panel_errors(error_report),
        _panel_cost_yield(cost_yield),
        _panel_decisions(decisions),
        _panel_propagation(propagation),
    ]
    grid = "\n".join(p for p in panels if p)
    return f'''<div class="diag">
<h3>Orchestration Diagnostics</h3>
<div class="diag-grid">
{grid}
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
