"""Standalone HTML trace report generator.

Generates a single HTML file with dark-theme multi-agent timeline visualization.
Zero JS framework dependencies — vanilla HTML/CSS/JS only.
"""

from __future__ import annotations

import html
import json
from pathlib import Path


def _esc(text: str) -> str:
    """Escape text for safe HTML insertion."""
    return html.escape(str(text)) if text else ""


def generate_timeline_html(
    traces_dir: str = ".agentguard/traces",
    output: str = ".agentguard/report.html",
) -> str:
    """Generate a standalone HTML report with multi-agent timeline.
    
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
    
    html = _build_html(traces)
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    return str(out_path)


def _build_html(traces: list[dict]) -> str:
    total_spans = sum(len(t.get("spans", [])) for t in traces)
    passed = sum(1 for t in traces if t.get("status") == "completed")
    failed = sum(1 for t in traces if t.get("status") == "failed")
    total_duration = sum(t.get("duration_ms", 0) or 0 for t in traces)
    avg_duration = total_duration / max(len(traces), 1)
    
    trace_cards = "\n".join(_render_trace_card(t) for t in traces)
    
    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AgentGuard — Trace Report</title>
<style>
:root {{
  --bg: #0d1117; --surface: #161b22; --border: #21262d;
  --text: #c9d1d9; --text-dim: #8b949e; --text-bright: #f0f6fc;
  --green: #3fb950; --red: #f85149; --blue: #58a6ff; --yellow: #d29922;
  --green-bg: #1a3a1a; --red-bg: #3a1a1a;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, monospace;
       background: var(--bg); color: var(--text); padding: 20px; max-width: 1200px; margin: 0 auto; }}
.header {{ text-align: center; padding: 30px 0; border-bottom: 1px solid var(--border); margin-bottom: 24px; }}
.header h1 {{ font-size: 24px; color: var(--text-bright); letter-spacing: -0.5px; }}
.header p {{ color: var(--text-dim); margin-top: 6px; font-size: 14px; }}
.stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }}
.stat {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; padding: 16px; text-align: center; }}
.stat .v {{ font-size: 28px; font-weight: 700; color: var(--text-bright); }}
.stat .l {{ font-size: 11px; color: var(--text-dim); margin-top: 4px; text-transform: uppercase; letter-spacing: 0.5px; }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 12px; overflow: hidden; }}
.card-hdr {{ padding: 12px 16px; display: flex; justify-content: space-between; align-items: center;
             border-bottom: 1px solid var(--border); cursor: pointer; }}
.card-hdr:hover {{ background: rgba(255,255,255,0.02); }}
.card-title {{ font-weight: 600; font-size: 14px; color: var(--text-bright); }}
.card-meta {{ font-size: 12px; color: var(--text-dim); }}
.badge {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; }}
.badge-pass {{ background: var(--green-bg); color: var(--green); }}
.badge-fail {{ background: var(--red-bg); color: var(--red); }}
.timeline {{ padding: 12px 16px; display: none; }}
.timeline.open {{ display: block; }}
.span {{ display: flex; align-items: center; padding: 4px 0; font-size: 13px; font-family: monospace; }}
.span-icon {{ width: 20px; text-align: center; margin-right: 6px; flex-shrink: 0; }}
.span-name {{ font-weight: 500; }}
.span-ver {{ color: var(--text-dim); font-size: 11px; margin-left: 4px; }}
.span-right {{ margin-left: auto; display: flex; align-items: center; gap: 8px; }}
.span-dur {{ color: var(--blue); font-size: 12px; min-width: 50px; text-align: right; }}
.span-err {{ color: var(--red); font-size: 12px; padding: 2px 0 2px 28px; }}
.empty {{ text-align: center; padding: 60px; color: var(--text-dim); }}
.footer {{ text-align: center; padding: 20px; color: var(--text-dim); font-size: 12px; border-top: 1px solid var(--border); margin-top: 24px; }}
</style>
</head>
<body>

<div class="header">
  <h1>🛡️ AgentGuard</h1>
  <p>Multi-Agent Trace Report</p>
</div>

<div class="stats">
  <div class="stat"><div class="v">{len(traces)}</div><div class="l">Traces</div></div>
  <div class="stat"><div class="v">{total_spans}</div><div class="l">Total Spans</div></div>
  <div class="stat"><div class="v" style="color:var(--green)">{passed}</div><div class="l">Passed</div></div>
  <div class="stat"><div class="v" style="color:var(--red)">{failed}</div><div class="l">Failed</div></div>
  <div class="stat"><div class="v">{avg_duration/1000:.1f}s</div><div class="l">Avg Duration</div></div>
</div>

{trace_cards if traces else '<div class="empty">No traces found.<br>Record some agent executions to see them here.</div>'}

<div class="footer">Generated by AgentGuard · github.com/betaHi/AgentGuard</div>

<script>
document.querySelectorAll('.card-hdr').forEach(h => {{
  h.addEventListener('click', () => {{
    const tl = h.nextElementSibling;
    tl.classList.toggle('open');
    h.querySelector('.arrow').textContent = tl.classList.contains('open') ? '▼' : '▶';
  }});
}});
// Open first card by default
const first = document.querySelector('.timeline');
if (first) {{ first.classList.add('open'); const a = first.previousElementSibling.querySelector('.arrow'); if(a) a.textContent = '▼'; }}
</script>
</body>
</html>'''


def _render_trace_card(trace: dict) -> str:
    status = trace.get("status", "unknown")
    badge_cls = "badge-pass" if status == "completed" else "badge-fail"
    badge_txt = "PASS" if status == "completed" else "FAIL"
    dur = trace.get("duration_ms")
    dur_s = f"{dur:.0f}ms" if dur and dur < 1000 else (f"{dur/1000:.1f}s" if dur else "—")
    spans = trace.get("spans", [])
    
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
    
    span_html = "\n".join(_render_span(r, 0) for r in roots)
    
    return f'''<div class="card">
  <div class="card-hdr">
    <div>
      <span class="arrow">▶</span>
      <span class="card-title">{_esc(trace.get("task", "(unnamed)"))}</span>
      <span class="card-meta"> · {trace.get("trigger", "")} · {dur_s} · {len(spans)} spans</span>
    </div>
    <span class="badge {badge_cls}">{badge_txt}</span>
  </div>
  <div class="timeline">{span_html}</div>
</div>'''


def _render_span(span: dict, depth: int) -> str:
    icons = {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}
    icon = icons.get(span.get("span_type", ""), "●")
    name = _esc(span.get("name", ""))
    status = span.get("status", "")
    dur = span.get("duration_ms")
    dur_s = f"{dur:.0f}ms" if dur and dur < 1000 else (f"{dur/1000:.1f}s" if dur else "")
    ver = _esc(span.get("metadata", {}).get("agent_version", ""))
    
    s_badge = f'<span class="badge badge-pass">✓</span>' if status == "completed" else (f'<span class="badge badge-fail">✗</span>' if status == "failed" else "")
    ver_html = f'<span class="span-ver">({ver})</span>' if ver else ""
    pad = f'style="padding-left:{depth*20}px"'
    
    err = ""
    if span.get("error"):
        err = f'\n<div class="span-err" style="padding-left:{depth*20+28}px">⚠ {span["error"]}</div>'
    
    children = "\n".join(_render_span(c, depth + 1) for c in span.get("children", []))
    
    return f'''<div class="span" {pad}>
  <span class="span-icon">{icon}</span>
  <span class="span-name">{name}</span>{ver_html}
  <span class="span-right">{s_badge}<span class="span-dur">{dur_s}</span></span>
</div>{err}
{children}'''
