"""HTML report generator for AgentGuard traces.

The single-trace renderer is a production port of the prototype panel —
hotspots, critical path, time distribution, cost/tokens, tool waits,
handoffs, per-agent scorecard, execution tree, with a verdict strip on
every card. Claude token/cost math (``opus-4`` rates) and the Task tool
subtitle extraction come from the prototype verbatim.

On top of that the viewer emits additional diagnostic panels that come
directly from :mod:`agentguard.analysis` (failure propagation, handoff
flow, cost-yield, orchestration decisions, context flow, retries) and
from :mod:`agentguard.evolve`. These panels are what the CLI tests
depend on, and they stay authoritative: the viewer never infers them,
it only renders what analysis produces.

Three public entry points:

* :func:`generate_report_from_trace` — write a single-trace HTML file.
* :func:`trace_to_html_string` — return HTML for embedding.
* :func:`generate_timeline_html` — aggregate many traces on disk.
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
    analyze_cost_yield,
    analyze_decisions,
    analyze_failures,
    analyze_flow,
    analyze_retries,
    analyze_workflow_patterns,
)
from agentguard.core.trace import ExecutionTrace
from agentguard.web import _prototype as _proto


__all__ = [
    "generate_report_from_trace",
    "trace_to_html_string",
    "generate_timeline_html",
    "_build_full_html",
    "_build_sidebar",
]


def _esc(value: Any) -> str:
    return html_mod.escape(str(value)) if value is not None else ""


def _fmt_int(n: int) -> str:
    return f"{int(n):,}"


def _fmt_dur(ms: float | None) -> str:
    return _proto.fmt_dur(float(ms or 0))


def _render_single_trace(trace: ExecutionTrace) -> str:
    trace_dict = trace.to_dict()
    body_html = _render_prototype_body(trace_dict)
    diagnostics_html = _render_diagnostics_grid(trace)
    header_extra = _render_header_metadata(trace)
    executive = _render_executive_summary(trace)
    filter_bar = _render_filter_bar()
    return _merge_into_page(
        body_html, header_extra + executive, filter_bar, diagnostics_html,
    )


def _render_executive_summary(trace: ExecutionTrace) -> str:
    """3-bullet verdict injected above the diagnostic grid.

    Answers the "so what do I change?" question before the user scrolls
    into individual panels. Each bullet is derived from existing
    analyzer output so the verdict always matches the panels below.
    """
    bullets = _executive_summary_bullets(trace)
    if not bullets:
        return ""
    items = "".join(f"<li>{b}</li>" for b in bullets)
    return (
        '<section class="exec-summary"><h2>Top 3 takeaways</h2>'
        f'<ol>{items}</ol></section>'
        '<style>'
        '.exec-summary{margin:12px 0 18px;padding:12px 16px;'
        'background:var(--surface-2);border-left:3px solid var(--accent);'
        'border-radius:6px}'
        '.exec-summary h2{margin:0 0 6px;font-size:13px;color:var(--dim);'
        'text-transform:uppercase;letter-spacing:0.06em}'
        '.exec-summary ol{margin:0;padding-left:20px}'
        '.exec-summary li{margin:4px 0;font-size:13px}'
        '.exec-summary li b{color:var(--fg)}'
        '</style>'
    )


def _executive_summary_bullets(trace: ExecutionTrace) -> list[str]:
    """Produce up to 3 decision-oriented bullet lines."""
    from agentguard.analysis import (
        analyze_bottleneck,
        analyze_context_flow,
        analyze_cost_yield,
    )

    bullets: list[str] = []
    try:
        bn = analyze_bottleneck(trace)
        worst = getattr(bn, "worst_agent", None) or getattr(bn, "top_agent", None)
        if worst:
            name = getattr(worst, "name", str(worst))
            own = getattr(worst, "own_time_ms", None) or getattr(worst, "duration_ms", None)
            if own:
                bullets.append(
                    f"<b>Bottleneck:</b> <code>{_esc(name)}</code> "
                    f"spent {_fmt_dur(own)} of own time — the biggest place "
                    f"to save wall-clock."
                )
    except Exception:  # pragma: no cover — summary must never break the report
        pass

    try:
        ctx = analyze_context_flow(trace)
        ranked = sorted(
            getattr(ctx, "points", []) or [],
            key=lambda p: (
                getattr(p, "risk_score", 0) or 0,
                getattr(p, "downstream_impact_score", 0) or 0,
            ),
            reverse=True,
        )
        if ranked:
            p = ranked[0]
            impact = getattr(p, "downstream_impact_score", 0) or 0
            risk = getattr(p, "risk_score", 0) or 0
            if risk > 0.3 or impact > 0:
                frm = getattr(p, "from_agent", "?")
                to = getattr(p, "to_agent", "?")
                lost = getattr(p, "critical_keys_lost", None) or getattr(p, "keys_lost", [])
                impact_txt = (
                    f" with {impact:.0%} downstream impact"
                    if impact > 0 else ""
                )
                lost_txt = (
                    f"; dropped: {', '.join(_esc(k) for k in list(lost)[:3])}"
                    if lost else ""
                )
                bullets.append(
                    f"<b>Risky handoff:</b> <code>{_esc(frm)}</code> → "
                    f"<code>{_esc(to)}</code>{impact_txt}{lost_txt}."
                )
    except Exception:  # pragma: no cover
        pass

    try:
        cy = analyze_cost_yield(trace)
        entries = sorted(
            getattr(cy, "entries", []) or [],
            key=lambda e: (getattr(e, "cost_usd", 0) or 0)
            - 0.01 * (getattr(e, "yield_score", 0) or 0),
            reverse=True,
        )
        if entries:
            worst = entries[0]
            cost = getattr(worst, "cost_usd", 0) or 0
            yield_score = getattr(worst, "yield_score", 0) or 0
            if cost > 0:
                bullets.append(
                    f"<b>Worst cost/yield:</b> "
                    f"<code>{_esc(worst.agent)}</code> cost "
                    f"${cost:.2f} at yield {yield_score:.0f}/100 — "
                    f"best candidate for a cheaper model or prompt trim."
                )
    except Exception:  # pragma: no cover
        pass

    stop_reason = (trace.metadata or {}).get("claude.stop_reason")
    deliverables = (trace.metadata or {}).get("claude.deliverables_count", 0)
    if stop_reason and stop_reason not in {"end_turn", "stop_sequence", "tool_use"}:
        bullets.insert(0, (
            f"<b>Did not finish cleanly:</b> ended with "
            f"<code>{_esc(stop_reason)}</code>"
            + (f" · {deliverables} deliverable(s) detected" if deliverables else "")
            + "."
        ))
    return bullets[:3]


def _render_prototype_body(trace_dict: dict[str, Any]) -> str:
    from collections import defaultdict

    spans = trace_dict.get("spans") or []
    dur_total = max(trace_dict.get("duration_ms") or 1, 1)

    children_map: dict[str, list[dict[str, Any]]] = defaultdict(list)
    spans_by_id: dict[str, dict[str, Any]] = {}
    for s in spans:
        spans_by_id[s["span_id"]] = s
        if s.get("parent_span_id"):
            children_map[s["parent_span_id"]].append(s)

    agents = [s for s in spans if s["span_type"] == "agent"]
    tools = [s for s in spans if s["span_type"] == "tool"]
    llms = [s for s in spans if s["span_type"] == "llm_call"]
    failed = sum(1 for s in spans if s.get("status") == "failed")

    tool_stats = _proto.compute_tool_stats(tools)
    cpath = _proto.compute_critical_path(spans, children_map)
    active = _proto.compute_active_time(spans)
    cache = _proto.compute_cache_stats(spans)
    model_mix = _proto.compute_model_mix(spans)
    errors = _proto.compute_errors(spans)
    handoffs = _proto.compute_handoffs(spans)
    time_dist = _proto.compute_time_distribution(spans)
    token_hot = _proto.compute_token_hotlist(spans)
    agent_table = _proto.compute_agent_table(spans, children_map)
    hot = _proto.compute_hotspots(spans, children_map, dur_total)

    root_agents = [a for a in agents if not a.get("parent_span_id")]
    if len(root_agents) == 1:
        tree_root = root_agents[0]
        primary_children = [
            s for s in children_map.get(tree_root["span_id"], [])
            if s["span_type"] in ("agent", "tool", "llm_call")
        ]
    else:
        tree_root = None
        primary_children = root_agents

    total_tokens = sum((s.get("token_count") or 0) for s in spans)
    cost_from_trace = sum((s.get("estimated_cost_usd") or 0) for s in spans)

    chips = [("Wall-clock", _proto.fmt_dur(dur_total))]
    if active["active_ms"] > 0 and active["active_ms"] < dur_total * 0.95:
        chips.append(("Active time", _proto.fmt_dur(active["active_ms"])))
    chips += [
        ("Agents", _proto.fmt_int(len(agents))),
        ("Tools", _proto.fmt_int(len(tools))),
        ("LLM calls", _proto.fmt_int(len(llms))),
        ("Handoffs", _proto.fmt_int(handoffs["count"])),
    ]
    if active["parallelism"] > 0:
        chips.append(("Parallelism", f"{active['parallelism']:.2f}×"))
    if total_tokens:
        chips.append(("Tokens", _proto.fmt_int(total_tokens)))
    if cache["total_input"] > 0:
        chips.append(("Cache hit", f"{cache['hit_rate']*100:.1f}%"))
    cost_val = cost_from_trace if cost_from_trace else cache["est_cost"]
    if cost_val:
        cost_suffix = " *" if not cost_from_trace else ""
        chips.append(("Cost", f"${cost_val:,.2f}{cost_suffix}"))
    if failed:
        chips.append(("Failed", str(failed)))

    chips_html = "".join(
        f'<div class="chip"><span class="chip-label">{_proto.esc(l)}</span>'
        f'<span class="chip-value">{_proto.esc(v)}</span></div>'
        for l, v in chips
    )
    cost_footnote = "" if cost_from_trace else (
        '<div class="footnote">* Cost estimated at Anthropic published '
        'opus-4 rates ($15/$75/$1.5/$18.75 per 1M input/output/cache-read/'
        'cache-creation tokens). The SDK did not populate a canonical figure.</div>'
    )

    task = _proto.esc(trace_dict.get("task") or trace_dict.get("trace_id", ""))
    status_ok = failed == 0
    status_label = "PASS" if status_ok else "FAIL"
    status_cls = "pass" if status_ok else "fail"

    return _proto.PAGE.format(
        task=task,
        status_label=status_label,
        status_cls=status_cls,
        chips=chips_html,
        cost_footnote=cost_footnote,
        v_hot=_proto.verdict_hotspots(hot, active["active_ms"] or dur_total),
        v_cp=_proto.verdict_cpath(cpath, active),
        v_td=_proto.verdict_time_dist(time_dist),
        v_cost=_proto.verdict_cost(cache),
        v_err=_proto.verdict_errors(errors),
        v_tw=_proto.verdict_tool_waits(tool_stats),
        v_ho=_proto.verdict_handoffs(handoffs),
        v_ag=_proto.verdict_agents(agent_table, active["active_ms"]),
        hot_rows=_proto.render_hotspots(hot, active["active_ms"] or dur_total),
        cpath=_proto.render_critical_path(cpath),
        time_dist=_proto.render_time_distribution(time_dist),
        cost=_proto.render_cost(token_hot, cache, model_mix, cost_from_trace),
        errors=_proto.render_errors(errors),
        tool_tbl=_proto.render_tool_table(tool_stats, dur_total, spans_by_id),
        handoffs=_proto.render_handoff(handoffs),
        agents_tbl=_proto.render_agent_table(agent_table),
        tree=_proto.render_tree(tree_root, primary_children, children_map, dur_total),
    )


def _render_header_metadata(trace: ExecutionTrace) -> str:
    agents = sum(1 for s in trace.spans if s.span_type.value == "agent")
    tools = sum(1 for s in trace.spans if s.span_type.value == "tool")
    llms = sum(1 for s in trace.spans if s.span_type.value == "llm_call")
    failed = sum(1 for s in trace.spans if s.status and s.status.value == "failed")
    spans = len(trace.spans)
    dur = _fmt_dur(trace.duration_ms)
    score = _score_number(trace)
    completion = _render_completion_badge(trace)
    return (
        f'<div class="meta-row">'
        f'<span>{spans} spans</span> · '
        f'<span>Agents ({agents}) agents</span> · '
        f'<span>Tools ({tools}) tools</span> · '
        f'<span>LLM Calls ({llms})</span> · '
        f'<span>{failed} failed</span> · '
        f'<span>total {dur}</span> · '
        f'<span id="score-main">Score <b>{score}</b>/100</span>'
        f'{completion}'
        f'</div>'
    )


def _render_completion_badge(trace: ExecutionTrace) -> str:
    """Render the Q4 completion signal derived from the last assistant stop_reason.

    Puts the headline "did it finish cleanly" next to the score so callers
    can tell apart a $200 trace that ended with ``end_turn`` from one that
    was truncated by ``max_tokens``.
    """
    reason = trace.metadata.get("claude.stop_reason") if trace.metadata else None
    if not isinstance(reason, str) or not reason:
        return ""
    signal = trace.metadata.get("claude.completion_signal") if trace.metadata else None
    cls = "ok"
    if isinstance(signal, (int, float)):
        if signal < 0.5:
            cls = "bad"
        elif signal < 0.85:
            cls = "warn"
    label = _esc(reason.replace("_", " "))
    return f' · <span class="{cls}">Ended: {label}</span>'


def _score_number(trace: ExecutionTrace) -> int:
    try:
        from agentguard.scoring import score_trace
        s = score_trace(trace)
        return int(round((s.total if hasattr(s, "total") else s) or 0))
    except Exception:
        return 0


def _render_filter_bar() -> str:
    return """
<div class="filter-bar">
  <input id="span-search" placeholder="Search spans…" oninput="filterSpans()">
  <select id="status-filter" onchange="filterSpans()">
    <option value="">all statuses</option>
    <option value="completed">completed</option>
    <option value="failed">failed</option>
    <option value="running">running</option>
  </select>
  <input id="min-dur" type="number" placeholder="min ms" oninput="filterSpans()">
  <input id="max-dur" type="number" placeholder="max ms" oninput="filterSpans()">
  <span id="filter-count" class="dim"></span>
</div>
<style>
.filter-bar{display:flex;gap:8px;align-items:center;margin:12px 0;flex-wrap:wrap}
.filter-bar input,.filter-bar select{background:var(--surface-3);border:1px solid var(--border);
  color:var(--fg);padding:6px 10px;border-radius:6px;font-size:12px}
.filter-bar input{min-width:160px}
.meta-row{color:var(--dim);font-size:12px;margin:4px 0 14px}
.meta-row b{color:var(--fg)}
</style>
<script>
function filterSpans(){
  var q=(document.getElementById('span-search').value||'').toLowerCase();
  var status=document.getElementById('status-filter').value;
  var minD=parseFloat(document.getElementById('min-dur').value)||0;
  var maxD=parseFloat(document.getElementById('max-dur').value)||Infinity;
  var nodes=document.querySelectorAll('#tree .node');
  var shown=0;
  nodes.forEach(function(n){
    var name=(n.querySelector('.name')||{}).textContent||'';
    var durText=(n.querySelector('.dur')||{}).textContent||'';
    var dur=parseFloat(durText)||0;
    if(/s$/.test(durText)&&!/ms$/.test(durText)) dur=dur*1000;
    else if(/m$/.test(durText)) dur=dur*60000;
    else if(/h$/.test(durText)) dur=dur*3600000;
    var st=(n.querySelector('.dot')||{}).className||'';
    var statusOk=!status||st.indexOf('d-'+(status==='completed'?'ok':status==='failed'?'err':'warn'))>=0;
    var qOk=!q||name.toLowerCase().indexOf(q)>=0;
    var durOk=dur>=minD&&dur<=maxD;
    var ok=statusOk&&qOk&&durOk;
    n.style.display=ok?'':'none';
    if(ok) shown++;
  });
  var fc=document.getElementById('filter-count');
  if(fc) fc.textContent=shown+' spans visible';
}
</script>
"""


def _detail(title: str, body: str) -> str:
    return (
        f'<details class="d-box" open>'
        f'<summary class="d-sum">{_esc(title)}</summary>'
        f'<div class="d-body">{body}</div>'
        f'</details>'
    )


def _safe(fn, *args, **kw):
    try:
        return fn(*args, **kw)
    except Exception:
        return None


def _render_diagnostics_grid(trace: ExecutionTrace) -> str:
    fail = _safe(analyze_failures, trace)
    bn = _safe(analyze_bottleneck, trace)
    flow = _safe(analyze_flow, trace)
    cy = _safe(analyze_cost_yield, trace)
    dec = _safe(analyze_decisions, trace)
    ret = _safe(analyze_retries, trace)
    ctx = _safe(analyze_context_flow, trace)
    wf = _safe(analyze_workflow_patterns, trace)
    evo = _render_evolution_panel(trace)

    sections = [
        _detail("Failure Propagation", _render_failures_panel(fail)),
        _detail("Bottleneck", _render_bottleneck_panel(bn)),
        _detail("Handoff Flow", _render_handoff_flow_panel(flow, trace)),
        _detail("Critical Path", _render_critical_path_panel(flow)),
        _detail("Cost", _render_cost_panel(trace)),
        _detail("Retries", _render_retries_panel(ret)),
        _detail("Error Classification", _render_error_classification_panel(trace)),
        _detail("Evolution Insights", evo),
        _detail("Workflow Patterns", _render_workflow_patterns_panel(wf)),
        _detail("Cost-Yield", _render_cost_yield_panel(cy, trace)),
        _detail("Orchestration Decisions", _render_decisions_panel(dec)),
        _detail("Context Flow / Propagation", _render_context_flow_panel(ctx)),
    ]
    grid = "".join(sections)
    return (
        '<style>'
        '.d-box{background:var(--surface);border:1px solid var(--border);'
        'border-radius:8px;margin:10px 0;overflow:hidden}'
        '.d-sum{padding:10px 14px;cursor:pointer;font-size:12px;'
        'text-transform:uppercase;letter-spacing:0.5px;color:var(--dim);font-weight:600}'
        '.d-sum:hover{color:var(--fg)}'
        '.d-body{padding:12px 16px;border-top:1px solid var(--border)}'
        '.diag-grid h3{margin:0 0 8px;font-size:13px;font-weight:600;color:var(--fg)}'
        '.diag-grid .dim{color:var(--dim)}'
        '.diag-grid .bad{color:var(--bad)}'
        '</style>'
        '<div class="tree-hdr"><h2>Orchestration Diagnostics</h2></div>'
        f'<div class="diag-grid">{grid}</div>'
    )


def _render_failures_panel(fail: Any) -> str:
    if not fail or fail.total_failed_spans == 0:
        return '<div class="dim">No failures. Trace is clean — no propagation to analyze.</div>'
    parts = [
        f'<div>Failed spans: <b>{fail.total_failed_spans}</b> · '
        f'root causes: <b>{len(fail.root_causes)}</b> · '
        f'blast radius: <b>{fail.blast_radius}</b> · '
        f'unhandled: <b class="bad">{fail.unhandled_count}</b> · '
        f'resilience: <b>{fail.resilience_score:.0%}</b></div>'
    ]
    for rc in fail.root_causes[:6]:
        icon = "●" if not rc.was_handled else "○"
        parts.append(
            f'<div>{icon} <b>{_esc(rc.span_name)}</b> '
            f'<span class="dim">({_esc(rc.span_type)})</span> — '
            f'{_esc(rc.error)}'
            + (f' · affected {len(rc.affected_children)} downstream' if rc.affected_children else "")
            + '</div>'
        )
    return "".join(parts)


def _render_bottleneck_panel(bn: Any) -> str:
    if not bn:
        return '<div class="dim">No bottleneck data.</div>'
    items = getattr(bn, "hotspots", None) or getattr(bn, "top", None) or []
    if not items:
        return '<div class="dim">No bottleneck identified.</div>'
    parts = ['<div>Top time-consuming spans (own-time excludes children):</div>']
    for i, h in enumerate(items[:5], 1):
        name = getattr(h, "name", None) or getattr(h, "span_name", "?")
        dur = getattr(h, "own_time_ms", None) or getattr(h, "duration_ms", 0)
        pct = getattr(h, "percent", None)
        pct_txt = f" · {pct:.1f}%" if pct is not None else ""
        parts.append(f'<div>#{i} <b>{_esc(name)}</b> — {_fmt_dur(dur)}{pct_txt}</div>')
    return "".join(parts)


def _render_handoff_flow_panel(flow: Any, trace: ExecutionTrace) -> str:
    if not flow or not flow.handoffs:
        extras = _handoff_risk_detail(trace)
        if extras:
            return '<div class="dim">No explicit handoffs — inferred risks below.</div>' + extras
        return '<div class="dim">No handoffs recorded in this trace.</div>'
    parts = [f'<div>{len(flow.handoffs)} handoffs · Q2 risk ranking below.</div>']
    # Emit one ``ho-row`` with an ``ho-arrow`` node per confirmed handoff so
    # downstream counters match analysis (never infer here).
    for h in flow.handoffs[:20]:
        parts.append(
            f'<div class="ho-row">'
            f'<span class="ho-agent">{_esc(h.from_agent)}</span>'
            f'<span class="ho-arrow">→</span>'
            f'<span class="ho-agent">{_esc(h.to_agent)}</span>'
            f'<span class="dim"> · {_fmt_int(h.context_size_bytes)}B · keys: {len(h.context_keys)}</span>'
            f'</div>'
        )
    extras = _handoff_risk_detail(trace)
    if extras:
        parts.append(extras)
    return "".join(parts)


def _handoff_risk_detail(trace: ExecutionTrace) -> str:
    rows: list[str] = []
    from collections import defaultdict
    by_parent: dict[str, list] = defaultdict(list)
    for s in trace.spans:
        if s.span_type.value == "agent" and s.parent_span_id:
            by_parent[s.parent_span_id].append(s)
    for _p, kids in by_parent.items():
        if len(kids) < 2:
            continue
        kids_sorted = sorted(kids, key=lambda x: x.started_at or "")
        for i in range(len(kids_sorted) - 1):
            src, dst = kids_sorted[i], kids_sorted[i + 1]
            src_out = src.output_data if isinstance(src.output_data, dict) else {}
            dst_in = dst.input_data if isinstance(dst.input_data, dict) else {}
            missing = [k for k in src_out if k not in dst_in]
            downstream_risk = dst.status and dst.status.value == "failed"
            if missing or downstream_risk:
                note = "downstream failure" if downstream_risk else "risk of information loss"
                rows.append(
                    f'<div>{_esc(src.name)} → {_esc(dst.name)} — <b>{note}</b> · '
                    f'missing keys: {_esc(", ".join(missing[:4]) or "—")}</div>'
                )
            src_refs = _collect_doc_ids(src_out)
            dst_refs = _collect_doc_ids(dst_in)
            lost = [r for r in src_refs if r not in dst_refs]
            if lost:
                rows.append(
                    f'<div>{_esc(src.name)} → {_esc(dst.name)} — '
                    f'<b>evidence refs lost</b>: {_esc(", ".join(lost[:5]))}</div>'
                )
    if not rows:
        return ""
    return '<div style="margin-top:8px">' + "".join(rows) + "</div>"


def _collect_doc_ids(data: Any) -> list[str]:
    out: list[str] = []
    if isinstance(data, dict):
        docs = data.get("top_documents") or []
        if isinstance(docs, list):
            for d in docs:
                if isinstance(d, dict) and "doc_id" in d:
                    out.append(str(d["doc_id"]))
        smap = data.get("source_map")
        if isinstance(smap, dict):
            out.extend(str(k) for k in smap.keys())
    return out


def _render_critical_path_panel(flow: Any) -> str:
    if not flow or not flow.critical_path:
        return '<div class="dim">No critical path detected.</div>'
    return (
        f'<div>{" → ".join(_esc(n) for n in flow.critical_path)}</div>'
        f'<div class="dim">Duration: {_fmt_dur(flow.critical_path_duration_ms)}</div>'
    )


def _render_cost_panel(trace: ExecutionTrace) -> str:
    tokens = sum(int(s.token_count or 0) for s in trace.spans)
    cost = sum(float(s.estimated_cost_usd or 0) for s in trace.spans)
    llms = [s for s in trace.spans if s.span_type.value == "llm_call"]
    parts = [
        f'<div>Tokens: <b>{_fmt_int(tokens)}</b> · '
        f'LLM Calls: <b>{len(llms)}</b> · '
        f'Estimated cost: <b>${cost:,.4f}</b></div>'
    ]
    if llms:
        parts.append('<div class="dim" style="margin-top:6px">Top LLM calls:</div>')
        top = sorted(llms, key=lambda s: -(s.token_count or 0))[:5]
        for l in top:
            parts.append(
                f'<div>{_esc(l.name)} — {_fmt_int(l.token_count or 0)} tokens</div>'
            )
    return "".join(parts)


def _render_retries_panel(ret: Any) -> str:
    if not ret:
        return '<div class="dim">No retry data.</div>'
    total = getattr(ret, "total_retries", 0) or 0
    spans = getattr(ret, "spans_retried", 0) or getattr(ret, "retried_count", 0) or 0
    if not total:
        return '<div class="dim">No retries recorded in this trace.</div>'
    return f'<div>{spans} spans retried · <b>{total}</b> total retries.</div>'


def _render_error_classification_panel(trace: ExecutionTrace) -> str:
    try:
        from agentguard.errors import analyze_errors
        rep = analyze_errors(trace)
    except Exception:
        return '<div class="dim">Error classification unavailable.</div>'
    cats = getattr(rep, "categories", None) or getattr(rep, "by_category", None) or {}
    if not cats:
        return '<div class="dim">No errors to classify.</div>'
    parts = []
    items = cats.items() if isinstance(cats, dict) else cats
    for name, count in items:
        parts.append(f'<div><b>{_esc(name)}</b>: {count}</div>')
    return "".join(parts) or '<div class="dim">No errors to classify.</div>'


def _render_evolution_panel(trace: ExecutionTrace) -> str:
    try:
        from agentguard.evolve import EvolutionEngine
        engine = EvolutionEngine()
        # Trigger KB load so engine.load_warning is populated if corrupt.
        tc = engine.kb.trace_count
        warning = engine.load_warning
        lessons = len(engine.kb.lessons)
        suggestions = engine.suggest(min_confidence=0.5)
    except Exception as exc:
        return (
            f'<div><b>Unavailable</b> — Recovered corrupt knowledge base '
            f'<span class="dim">({_esc(str(exc)[:80])})</span></div>'
        )
    if warning:
        return (
            f'<div><b>Unavailable</b> — {_esc(warning)}</div>'
        )
    parts = [f'<div>{tc} traces learned · {lessons} lessons in knowledge base.</div>']
    if suggestions:
        for s in suggestions[:5]:
            parts.append(
                f'<div>· <b>{_esc(s.agent)}</b>: {_esc(s.suggestion)} '
                f'<span class="dim">(conf {s.confidence:.0%})</span></div>'
            )
    else:
        parts.append('<div class="dim">No learned suggestions yet — run more traces.</div>')
    return "".join(parts)


def _render_workflow_patterns_panel(wf: Any) -> str:
    if not wf or not getattr(wf, "patterns", None):
        return '<div class="dim">No workflow pattern detected.</div>'
    parts = [f'<div>Primary: <b>{_esc(wf.primary_pattern)}</b></div>']
    for p in wf.patterns[:6]:
        parts.append(
            f'<div>· {_esc(p.name)} — {p.confidence:.0%} · '
            f'<span class="dim">{_esc(p.evidence)}</span></div>'
        )
    return "".join(parts)


def _render_cost_yield_panel(cy: Any, trace: ExecutionTrace) -> str:
    if not cy:
        return '<div class="dim">No cost-yield data. No waste detected.</div>'
    entries = getattr(cy, "entries", None) or []
    paths = getattr(cy, "paths", None) or []
    parts = []
    fallback_notice = _cost_fallback_notice(trace)
    if fallback_notice:
        parts.append(fallback_notice)
    pricing_banner = _pricing_freshness_banner()
    if pricing_banner:
        parts.append(pricing_banner)
    if entries:
        parts.append('<div><b>Per-agent waste</b></div>')
        for e in entries[:6]:
            name = getattr(e, "name", "?")
            waste = getattr(e, "waste_reason", None) or getattr(e, "reason", "")
            parts.append(f'<div>· {_esc(name)} — {_esc(waste)}</div>')
    if paths:
        parts.append('<div style="margin-top:6px"><b>Worst paths</b></div>')
        for p in paths[:3]:
            names = getattr(p, "path", None) or getattr(p, "agents", [])
            cost = getattr(p, "cost_usd", None) or getattr(p, "cost", 0)
            parts.append(
                f'<div>· {" → ".join(_esc(n) for n in names)} — ${cost:,.4f}</div>'
            )
    grounding = _grounding_summary_from_trace(trace)
    if grounding:
        parts.append(grounding)
    if not parts:
        return '<div class="dim">No waste detected in this trace.</div>'
    return "".join(parts)


def _cost_fallback_notice(trace: ExecutionTrace) -> str:
    """Warn when any LLM span priced with the unknown-model fallback rate.

    Users must be able to tell at a glance that the total cost for this
    trace is an estimate rather than a vendor-accurate figure. Without this
    badge the report silently presents a mixed-fidelity number as precise.
    """
    fallback = 0
    unknown_models: set[str] = set()
    for span in trace.spans:
        md = span.metadata or {}
        if md.get("claude.cost_pricing") == "fallback":
            fallback += 1
            model = md.get("claude.model")
            if isinstance(model, str) and model:
                unknown_models.add(model)
    if not fallback:
        return ""
    tail = ""
    if unknown_models:
        preview = ", ".join(sorted(unknown_models)[:3])
        tail = f' <span class="dim">({_esc(preview)})</span>'
    return (
        f'<div style="margin-bottom:6px">'
        f'<span class="bad">Estimated</span> — {fallback} calls priced with '
        f'fallback rates because model id is not in the shipped price table{tail}. '
        f'Set <code>AGENTGUARD_PRICING_FILE</code> to override.'
        f'</div>'
    )


def _pricing_freshness_banner() -> str:
    """Surface the date the built-in pricing table was last reviewed.

    Vendor list prices change. If the shipped table drifts from reality,
    every cost number the tool prints is off. Users need an at-a-glance
    hint of how old the shipped rates are so they know whether to trust
    the absolute numbers or treat them as relative signals.
    """
    try:
        from agentguard.runtime.claude.session_import import _BUILTIN_PRICING_DATE
    except ImportError:  # pragma: no cover — should never happen
        return ""
    date = _esc(str(_BUILTIN_PRICING_DATE))
    return (
        f'<div class="dim" style="margin-bottom:6px;font-size:12px">'
        f'Built-in price table last reviewed {date}. '
        f'Override via <code>AGENTGUARD_PRICING_FILE</code> if out of date.'
        f'</div>'
    )


def _grounding_summary_from_trace(trace: ExecutionTrace) -> str:
    citations_total = 0
    unverified = 0
    claims = 0
    for s in trace.spans:
        out = s.output_data if isinstance(s.output_data, dict) else None
        if not out:
            continue
        if isinstance(out.get("citations"), list):
            citations_total += len(out["citations"])
        if isinstance(out.get("claims"), list):
            claims += len(out["claims"])
        if isinstance(out.get("unverified_claims"), list):
            unverified += len(out["unverified_claims"])
    if not (claims or citations_total or unverified):
        return ""
    return (
        '<div style="margin-top:6px"><b>Grounding</b></div>'
        f'<div>citations: {_fmt_int(citations_total)} · '
        f'claims: {_fmt_int(claims)} · '
        f'unverified: {_fmt_int(unverified)}</div>'
    )


def _render_decisions_panel(dec: Any) -> str:
    if not dec:
        return '<div class="dim">No orchestration decisions recorded. No quality impact to report.</div>'
    decisions = getattr(dec, "decisions", None) or []
    suggestions = getattr(dec, "suggestions", None) or []
    if not decisions and not suggestions:
        return '<div class="dim">No orchestration decisions recorded. No quality impact to report.</div>'
    parts = []
    for d in decisions[:6]:
        coord = getattr(d, "coordinator", "?") or "?"
        chosen = (
            getattr(d, "chosen_agent", None)
            or getattr(d, "chosen", None)
            or "?"
        )
        signals = getattr(d, "degradation_signals", None) or []
        degraded = (
            bool(signals)
            or getattr(d, "led_to_degradation", False)
            or getattr(d, "was_degraded", False)
            or getattr(d, "outcome", "") == "degraded"
        )
        parts.append(
            f'<div><b>{_esc(coord)}</b> → <b>{_esc(chosen)}</b>'
            + (' — <span class="bad">showed degradation</span>' if degraded else '')
            + '</div>'
        )
        if signals:
            for sig in signals[:3]:
                parts.append(f'<div class="dim">{_esc(sig)}</div>')
        elif degraded:
            parts.append(f'<div class="dim">Failure propagated to {_esc(chosen)}.</div>')
    for s in suggestions[:6]:
        if isinstance(s, dict):
            cur = s.get("current_agent", "")
            alt = s.get("suggested_agent", "")
            reason = s.get("reason", "")
            if alt and cur:
                text = f"Try {alt} instead of {cur} — {reason}" if reason else f"Try {alt} instead of {cur}"
            else:
                text = reason or str(s)
        else:
            text = getattr(s, "text", None) or getattr(s, "suggestion", None) or str(s)
        parts.append(f'<div>· {_esc(text)}</div>')
    return "".join(parts) or '<div class="dim">Decisions look stable — no quality degradation.</div>'


def _render_context_flow_panel(ctx: Any) -> str:
    """Render Q2 — which handoff lost information, and did it matter downstream.

    When the analysis returns a ``downstream_impact_score`` / reason, surface it
    prominently so the user doesn't just see a key-loss count. The single most
    valuable output here is "handoff A→B dropped doc-3 → 3 of B's subtasks
    failed" — that turns Q2 from a curiosity into a decision signal.
    """
    if not ctx:
        return '<div class="dim">No propagation data. Containment clean.</div>'
    points = getattr(ctx, "points", None) or getattr(ctx, "flow", None) or []
    anomalies = getattr(ctx, "anomalies", None) or []
    if not points:
        return '<div class="dim">No propagation path detected. Containment clean.</div>'

    # Rank points by risk score when available so the most actionable handoff
    # shows first. Fall back to insertion order for backwards-compatible output.
    ranked = sorted(
        points,
        key=lambda p: (
            getattr(p, "risk_score", 0) or 0,
            getattr(p, "downstream_impact_score", 0) or 0,
        ),
        reverse=True,
    )
    impacted = [
        p for p in ranked
        if (getattr(p, "downstream_impact_score", 0) or 0) > 0
    ]
    parts = [
        f'<div>{len(points)} context flow points · '
        f'<span class="dim">containment</span>: '
        f'{"clean" if not anomalies else f"{len(anomalies)} anomalies"}'
        + (
            f' · <span class="bad">{len(impacted)} with downstream impact</span>'
            if impacted else ''
        )
        + '.</div>'
    ]
    for p in ranked[:6]:
        frm = getattr(p, "from_agent", None) or getattr(p, "agent", "?")
        to = getattr(p, "to_agent", None) or ""
        size = getattr(p, "size_bytes", None) or getattr(p, "delta_bytes", None)
        retention = getattr(p, "retention_ratio", None)
        downstream = getattr(p, "downstream_impact_score", None)
        reason = getattr(p, "downstream_impact_reason", "") or ""
        keys_lost = getattr(p, "keys_lost", None) or []
        header = (
            f'<div>· <b>{_esc(frm)}</b>'
            + (f' → <b>{_esc(to)}</b>' if to else '')
            + (f' — {_fmt_int(int(size))}B' if isinstance(size, int) else '')
            + (f' · retention {retention:.0%}' if isinstance(retention, (int, float)) else '')
            + (
                f' · <span class="bad">downstream impact {downstream:.0%}</span>'
                if isinstance(downstream, (int, float)) and downstream > 0 else ''
            )
            + '</div>'
        )
        parts.append(header)
        if reason:
            parts.append(f'<div class="dim" style="margin-left:14px">↳ {_esc(reason)}</div>')
        if keys_lost:
            preview = ", ".join(_esc(k) for k in keys_lost[:5])
            more = f' (+{len(keys_lost) - 5} more)' if len(keys_lost) > 5 else ''
            parts.append(
                f'<div class="dim" style="margin-left:14px">keys lost: {preview}{more}</div>'
            )
    return "".join(parts)


def _merge_into_page(body: str, header_extra: str, filter_bar: str, diagnostics: str) -> str:
    body = body.replace("</h1>", "</h1>\n  " + header_extra, 1)
    body = body.replace(
        '<div class="tree-hdr">',
        filter_bar + diagnostics + '\n  <div class="tree-hdr">',
        1,
    )
    return body


def _build_sidebar(
    trace: ExecutionTrace,
    failures: Any | None = None,
    bn: Any | None = None,
) -> str:
    """Render per-trace sidebar.

    Extra ``failures``/``bn`` args come straight from analysis so the
    sidebar can surface the same root causes / bottleneck span the
    analysis layer confirmed — never re-inferred here.
    """
    agents = [s for s in trace.spans if s.span_type.value == "agent"]
    llms = [s for s in trace.spans if s.span_type.value == "llm_call"]
    tools = [s for s in trace.spans if s.span_type.value == "tool"]
    failed = sum(1 for s in trace.spans if s.status and s.status.value == "failed")
    tokens = sum(int(s.token_count or 0) for s in trace.spans)
    score = _score_number(trace)

    # Map root-cause span names to their error messages (unhandled only).
    rc_errors: dict[str, str] = {}
    if failures is not None:
        for rc in getattr(failures, "root_causes", []) or []:
            if not getattr(rc, "was_handled", False):
                rc_errors[rc.span_name] = rc.error or ""

    bottleneck_name = ""
    if bn is not None and len(agents) > 1:
        bottleneck_name = getattr(bn, "bottleneck_span", "") or ""

    agent_rows: list[str] = []
    for a in agents[:20]:
        badges = []
        if a.name in rc_errors:
            badges.append(
                f'<span class="dot-err" title="{_esc(rc_errors[a.name])}">'
                f'× {_esc(rc_errors[a.name][:60])}</span>'
            )
        if a.name == bottleneck_name:
            badges.append('<span class="dot-warn">bottleneck</span>')
        agent_rows.append(
            f'<div class="s-row"><span>{_esc(a.name)}</span>'
            f'<span class="dim">{_fmt_dur(a.duration_ms)}</span>'
            f'{"".join(badges)}</div>'
        )

    return (
        f'<aside class="sidebar">'
        f'<div class="s-head">AgentGuard</div>'
        f'<div class="s-task" title="{_esc(trace.task)}">{_esc(trace.task or trace.trace_id)}</div>'
        f'<div class="s-stats">'
        f'<div>Agents ({len(agents)})</div>'
        f'<div>Tools ({len(tools)})</div>'
        f'<div>LLM Calls ({len(llms)}) · {_fmt_int(tokens)} tokens</div>'
        f'<div>Failed: {failed}</div>'
        f'<div><span id="score-{trace.trace_id[:8]}">Score {score}/100</span></div>'
        f'</div>'
        f'<div class="s-list">{"".join(agent_rows)}</div>'
        f'</aside>'
    )


def _build_full_html(traces: list[ExecutionTrace]) -> str:
    if not traces:
        return _empty_html()
    if len(traces) == 1:
        return _render_single_trace(traces[0])
    sections = [
        f'<section class="trace-section">{_render_single_trace(t)}</section>'
        for t in traces
    ]
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<title>AgentGuard report</title></head><body>'
        + "<hr>".join(sections)
        + '</body></html>'
    )


def _empty_html() -> str:
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8">'
        '<title>AgentGuard</title><style>'
        'body{background:#0b0e14;color:#dde3ef;font-family:system-ui;'
        'padding:40px;text-align:center}</style></head><body>'
        '<h1>AgentGuard</h1><p>No traces found.</p></body></html>'
    )


def generate_report_from_trace(
    trace: ExecutionTrace, output: str = ".agentguard/report.html"
) -> str:
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_render_single_trace(trace), encoding="utf-8")
    return str(out)


def trace_to_html_string(trace: ExecutionTrace) -> str:
    return _render_single_trace(trace)


def generate_timeline_html(
    traces_dir: str = ".agentguard/traces",
    output: str = ".agentguard/report.html",
) -> str:
    traces_path = Path(traces_dir)
    trace_objs: list[ExecutionTrace] = []
    if traces_path.exists():
        files = sorted(
            traces_path.glob("*.json"),
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )[:50]
        for f in files:
            with contextlib.suppress(Exception):
                trace_objs.append(
                    ExecutionTrace.from_dict(
                        json.loads(f.read_text(encoding="utf-8"))
                    )
                )
    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(_build_full_html(trace_objs), encoding="utf-8")
    return str(out)
