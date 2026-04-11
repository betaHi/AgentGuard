"""Simple web viewer for traces — single HTML page, zero JS framework deps."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional


def generate_timeline_html(traces_dir: str = ".agentguard/traces", output: str = ".agentguard/report.html") -> str:
    """Generate a standalone HTML report with multi-agent timeline."""
    traces_path = Path(traces_dir)
    traces = []
    
    if traces_path.exists():
        for f in sorted(traces_path.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:20]:
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
    """Build the complete HTML page."""
    trace_cards = "\n".join(_render_trace_card(t) for t in traces)
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>🛡️ AgentGuard — Trace Report</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; 
       background: #0d1117; color: #c9d1d9; padding: 20px; }}
.header {{ text-align: center; padding: 30px 0; border-bottom: 1px solid #21262d; margin-bottom: 30px; }}
.header h1 {{ font-size: 28px; color: #f0f6fc; }}
.header p {{ color: #8b949e; margin-top: 8px; }}
.stats {{ display: flex; gap: 20px; justify-content: center; margin: 20px 0; }}
.stat {{ background: #161b22; border: 1px solid #21262d; border-radius: 8px; padding: 16px 24px; text-align: center; }}
.stat .value {{ font-size: 24px; font-weight: 700; color: #f0f6fc; }}
.stat .label {{ font-size: 12px; color: #8b949e; margin-top: 4px; }}
.trace-card {{ background: #161b22; border: 1px solid #21262d; border-radius: 12px; 
               margin-bottom: 20px; overflow: hidden; }}
.trace-header {{ padding: 16px 20px; display: flex; justify-content: space-between; 
                  align-items: center; border-bottom: 1px solid #21262d; }}
.trace-title {{ font-weight: 600; color: #f0f6fc; }}
.trace-meta {{ font-size: 12px; color: #8b949e; }}
.badge {{ padding: 3px 10px; border-radius: 12px; font-size: 12px; font-weight: 600; }}
.badge-pass {{ background: #1a3a1a; color: #3fb950; }}
.badge-fail {{ background: #3a1a1a; color: #f85149; }}
.timeline {{ padding: 16px 20px; }}
.span {{ display: flex; align-items: center; padding: 6px 0; font-size: 14px; }}
.span-indent {{ display: inline-block; }}
.span-icon {{ margin-right: 8px; }}
.span-name {{ font-weight: 500; color: #c9d1d9; }}
.span-version {{ color: #8b949e; font-size: 12px; margin-left: 6px; }}
.span-status {{ margin-left: auto; padding-left: 16px; }}
.span-duration {{ color: #58a6ff; font-size: 12px; margin-left: 12px; min-width: 50px; text-align: right; }}
.span-error {{ color: #f85149; font-size: 12px; padding-left: 40px; margin-top: 2px; }}
.bar {{ height: 4px; border-radius: 2px; margin-top: 4px; }}
.bar-pass {{ background: #238636; }}
.bar-fail {{ background: #da3633; }}
.empty {{ text-align: center; padding: 60px; color: #8b949e; }}
</style>
</head>
<body>
<div class="header">
  <h1>🛡️ AgentGuard</h1>
  <p>Multi-Agent Trace Report</p>
</div>

<div class="stats">
  <div class="stat">
    <div class="value">{len(traces)}</div>
    <div class="label">Traces</div>
  </div>
  <div class="stat">
    <div class="value">{sum(len(t.get('spans',[])) for t in traces)}</div>
    <div class="label">Total Spans</div>
  </div>
  <div class="stat">
    <div class="value">{sum(1 for t in traces if t.get('status')=='completed')}</div>
    <div class="label">Passed</div>
  </div>
  <div class="stat">
    <div class="value">{sum(1 for t in traces if t.get('status')=='failed')}</div>
    <div class="label">Failed</div>
  </div>
</div>

{trace_cards if traces else '<div class="empty">No traces found. Record some agent executions first.</div>'}

</body>
</html>"""


def _render_trace_card(trace: dict) -> str:
    """Render a single trace as an HTML card."""
    status = trace.get("status", "unknown")
    badge_class = "badge-pass" if status == "completed" else "badge-fail"
    badge_text = "✓ PASS" if status == "completed" else "✗ FAIL"
    duration = trace.get("duration_ms")
    dur_str = f"{duration:.0f}ms" if duration and duration < 1000 else (f"{duration/1000:.1f}s" if duration else "—")
    
    # Build tree
    spans = trace.get("spans", [])
    span_map = {s["span_id"]: s for s in spans}
    for s in spans:
        s["_children"] = []
    roots = []
    for s in spans:
        pid = s.get("parent_span_id")
        if pid and pid in span_map:
            span_map[pid]["_children"].append(s)
        else:
            roots.append(s)
    
    span_html = "\n".join(_render_span_html(r, 0) for r in roots)
    
    return f"""<div class="trace-card">
  <div class="trace-header">
    <div>
      <span class="trace-title">{trace.get('task', '(unnamed)')}</span>
      <span class="trace-meta"> · {trace.get('trigger', '')} · {dur_str} · {len(spans)} spans</span>
    </div>
    <span class="badge {badge_class}">{badge_text}</span>
  </div>
  <div class="timeline">{span_html}</div>
</div>"""


def _render_span_html(span: dict, depth: int) -> str:
    """Render a span and its children as HTML."""
    icons = {"agent": "🤖", "tool": "🔧", "llm_call": "🧠", "handoff": "🔀"}
    icon = icons.get(span.get("span_type", ""), "●")
    name = span.get("name", "")
    status = span.get("status", "running")
    duration = span.get("duration_ms")
    dur_str = f"{duration:.0f}ms" if duration and duration < 1000 else (f"{duration/1000:.1f}s" if duration else "")
    version = span.get("metadata", {}).get("agent_version", "")
    
    status_badge = f'<span class="badge badge-pass">✓</span>' if status == "completed" else f'<span class="badge badge-fail">✗</span>' if status == "failed" else ""
    version_html = f'<span class="span-version">({version})</span>' if version else ""
    indent = f'style="padding-left: {depth * 24}px"'
    
    error_html = ""
    if span.get("error"):
        error_html = f'\n    <div class="span-error" style="padding-left: {depth * 24 + 32}px">⚠ {span["error"]}</div>'
    
    children_html = "\n".join(_render_span_html(c, depth + 1) for c in span.get("_children", []))
    
    return f"""    <div class="span" {indent}>
      <span class="span-icon">{icon}</span>
      <span class="span-name">{name}</span>{version_html}
      <span class="span-status">{status_badge}</span>
      <span class="span-duration">{dur_str}</span>
    </div>{error_html}
{children_html}"""
