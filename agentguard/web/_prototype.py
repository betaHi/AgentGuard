"""AgentGuard diagnostic HTML prototype — v3.

Fixes and additions vs v2:

- Layout reorder: Hotspots → CP | TimeDist → Cost | Failures → ToolWaits
  → Handoffs → Agents → Tree.
- Filters: root agent and single-child pass-through agents are excluded
  from hotspots (they otherwise always pin #1 at 100%).
- Numeric formatting: tabular-nums removed from human-readable durations
  so "1.4h" no longer renders as "1. 4h".
- Parallelism replaced with *active time* using a sweep-line union of
  span intervals. Idle gaps no longer dilute the metric.
- tool:Agent rows now carry a subtitle (subagent_type + description)
  pulled from Claude's Task tool input, so duplicates become
  distinguishable.
- Cost estimate derived from Anthropic published rates for opus-4.x
  when the SDK didn't populate ``estimated_cost_usd``.
- Every card has a short interpretation banner (verdict + one sentence).
"""

from __future__ import annotations

import html
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def fmt_dur(ms: float) -> str:
    if ms <= 0:
        return "0"
    if ms < 1000:
        return f"{ms:.0f}ms"
    if ms < 60_000:
        return f"{ms/1000:.1f}s"
    if ms < 3_600_000:
        return f"{ms/60_000:.1f}m"
    if ms < 86_400_000:
        return f"{ms/3_600_000:.1f}h"
    return f"{ms/86_400_000:.1f}d"


def fmt_int(n: int) -> str:
    return f"{n:,}"


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    k = max(0, min(len(xs) - 1, int(round((len(xs) - 1) * q))))
    return xs[k]


def parse_ts(ts: str | None) -> datetime | None:
    if not isinstance(ts, str) or not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------


# Anthropic published rates ($ / 1M tokens) for the claude-opus-4 family.
# Used only when the SDK didn't populate estimated_cost_usd.
OPUS_INPUT_RATE = 15.0
OPUS_OUTPUT_RATE = 75.0
OPUS_CACHE_READ_RATE = 1.50
OPUS_CACHE_CREATION_RATE = 18.75


def compute_tool_stats(tools):
    by_name = defaultdict(list)
    slowest = {}
    for t in tools:
        d = float(t.get("duration_ms") or 0)
        by_name[t["name"]].append(d)
        if d > (slowest.get(t["name"], {}).get("duration_ms", -1) or -1):
            slowest[t["name"]] = t
    out = []
    for name, durs in by_name.items():
        out.append({
            "name": name,
            "calls": len(durs),
            "total": sum(durs),
            "p50": percentile(durs, 0.50),
            "p95": percentile(durs, 0.95),
            "max": max(durs),
            "slowest_span_id": slowest[name]["span_id"],
        })
    out.sort(key=lambda x: -x["total"])
    return out


def compute_critical_path(spans, children_map):
    roots = [s for s in spans if not s.get("parent_span_id")]
    if not roots:
        return []
    root = max(roots, key=lambda s: s.get("duration_ms") or 0)
    path = [root]
    cur = root
    while True:
        kids = [c for c in children_map.get(cur["span_id"], []) if c["span_type"] != "handoff"]
        if not kids:
            break
        nxt = max(kids, key=lambda s: s.get("duration_ms") or 0)
        if (nxt.get("duration_ms") or 0) <= 0:
            break
        path.append(nxt)
        cur = nxt
    return path


def compute_active_time(spans) -> dict:
    """Union of (started, ended) intervals across every leaf span.

    ``parallelism = leaf_sum / wall`` was misleading because wall-clock
    included big idle gaps (the session stayed open for days). Active
    time takes the union of intervals so idle periods are removed.
    """
    intervals = []
    for s in spans:
        if s["span_type"] not in ("tool", "llm_call"):
            continue
        a, b = parse_ts(s.get("started_at")), parse_ts(s.get("ended_at"))
        if a and b and b >= a:
            intervals.append((a, b))
    if not intervals:
        return {"active_ms": 0, "leaf_sum_ms": 0, "wall_ms": 0, "parallelism": 0}
    intervals.sort()
    merged = [list(intervals[0])]
    for a, b in intervals[1:]:
        if a <= merged[-1][1]:
            if b > merged[-1][1]:
                merged[-1][1] = b
        else:
            merged.append([a, b])
    active = sum((b - a).total_seconds() * 1000 for a, b in merged)
    first = intervals[0][0]
    last = max(b for _, b in intervals)
    wall = (last - first).total_seconds() * 1000
    leaf_sum = sum((b - a).total_seconds() * 1000 for a, b in intervals)
    return {
        "active_ms": active,
        "leaf_sum_ms": leaf_sum,
        "wall_ms": wall,
        "parallelism": leaf_sum / active if active > 0 else 0,
    }


def compute_cache_stats(spans):
    input_toks = output_toks = cache_read = cache_creation = 0
    for s in spans:
        m = s.get("metadata") or {}
        input_toks += int(m.get("claude.usage.input_tokens", 0) or 0)
        output_toks += int(m.get("claude.usage.output_tokens", 0) or 0)
        cache_read += int(m.get("claude.usage.cache_read_input_tokens", 0) or 0)
        cache_creation += int(m.get("claude.usage.cache_creation_input_tokens", 0) or 0)
    total_input = input_toks + cache_read + cache_creation
    hit_rate = (cache_read / total_input) if total_input else 0.0
    est_cost = (
        input_toks / 1_000_000 * OPUS_INPUT_RATE
        + output_toks / 1_000_000 * OPUS_OUTPUT_RATE
        + cache_read / 1_000_000 * OPUS_CACHE_READ_RATE
        + cache_creation / 1_000_000 * OPUS_CACHE_CREATION_RATE
    )
    # Hypothetical cost if cache was disabled.
    uncached_cost = (
        (input_toks + cache_read + cache_creation) / 1_000_000 * OPUS_INPUT_RATE
        + output_toks / 1_000_000 * OPUS_OUTPUT_RATE
    )
    return {
        "input": input_toks,
        "output": output_toks,
        "cache_read": cache_read,
        "cache_creation": cache_creation,
        "total_input": total_input,
        "hit_rate": hit_rate,
        "est_cost": est_cost,
        "uncached_cost": uncached_cost,
    }


def compute_model_mix(spans):
    tally = {}
    for s in spans:
        m = (s.get("metadata") or {}).get("claude.model")
        if not m:
            continue
        row = tally.setdefault(m, {"model": m, "calls": 0, "tokens": 0})
        row["calls"] += 1
        row["tokens"] += int(s.get("token_count") or 0)
    return sorted(tally.values(), key=lambda x: -x["tokens"])


def compute_errors(spans):
    failed = [s for s in spans if s.get("status") == "failed"]
    retried = [s for s in spans if int(s.get("retry_count") or 0) > 0]
    total_retries = sum(int(s.get("retry_count") or 0) for s in retried)
    clusters = {}
    for s in failed:
        err = s.get("error") or "unknown"
        key = re.sub(r"\d+", "#", err)[:80]
        c = clusters.setdefault(key, {"message": key, "count": 0, "examples": []})
        c["count"] += 1
        if len(c["examples"]) < 3:
            c["examples"].append(s["name"])
    return {
        "failed_count": len(failed),
        "retried_spans": len(retried),
        "total_retries": total_retries,
        "clusters": sorted(clusters.values(), key=lambda x: -x["count"])[:6],
    }


def compute_handoffs(spans):
    ho = [s for s in spans if s["span_type"] == "handoff"]
    ctx_sizes = [int(s.get("context_size_bytes") or 0) for s in ho]
    return {
        "count": len(ho),
        "avg_bytes": (sum(ctx_sizes) / len(ctx_sizes)) if ctx_sizes else 0,
        "max_bytes": max(ctx_sizes) if ctx_sizes else 0,
        "series": ctx_sizes,
    }


def _walk(root_id, children_map):
    out = []
    stack = list(children_map.get(root_id, []))
    while stack:
        n = stack.pop()
        out.append(n)
        stack.extend(children_map.get(n["span_id"], []))
    return out


def compute_agent_table(spans, children_map):
    agents = [s for s in spans if s["span_type"] == "agent"]
    rows = []
    for a in agents:
        descendants = _walk(a["span_id"], children_map)
        tools = [d for d in descendants if d["span_type"] == "tool"]
        llms = [d for d in descendants if d["span_type"] == "llm_call"]
        tokens = sum(int(d.get("token_count") or 0) for d in descendants)
        cache_read = sum(
            int(((d.get("metadata") or {}).get("claude.usage.cache_read_input_tokens", 0)) or 0)
            for d in llms
        )
        total_input = sum(
            int(((d.get("metadata") or {}).get("claude.usage.input_tokens", 0)) or 0)
            + int(((d.get("metadata") or {}).get("claude.usage.cache_read_input_tokens", 0)) or 0)
            + int(((d.get("metadata") or {}).get("claude.usage.cache_creation_input_tokens", 0)) or 0)
            for d in llms
        )
        rows.append({
            "span_id": a["span_id"],
            "name": a["name"],
            "duration_ms": a.get("duration_ms") or 0,
            "status": a.get("status") or "completed",
            "tools": len(tools),
            "tool_wait_ms": sum(float(t.get("duration_ms") or 0) for t in tools),
            "llm_calls": len(llms),
            "tokens": tokens,
            "cache_hit": (cache_read / total_input) if total_input else 0.0,
        })
    rows.sort(key=lambda r: -r["duration_ms"])
    return rows


def compute_time_distribution(spans):
    by = defaultdict(float)
    for s in spans:
        if s["span_type"] == "tool":
            by[f"{s['name']}"] += float(s.get("duration_ms") or 0)
        elif s["span_type"] == "llm_call":
            by["LLM"] += float(s.get("duration_ms") or 0)
    total = sum(by.values()) or 1
    rows = [{"label": k, "ms": v, "pct": v / total * 100} for k, v in by.items()]
    rows.sort(key=lambda r: -r["ms"])
    return rows[:10]


def compute_token_hotlist(spans):
    llms = [s for s in spans if s["span_type"] == "llm_call" and (s.get("token_count") or 0) > 0]
    llms.sort(key=lambda s: -(s.get("token_count") or 0))
    return llms[:5]


def compute_hotspots(spans, children_map, dur_total, limit=5):
    """Return the top-N time-consuming spans, ignoring pass-through wrappers.

    A span is considered a *wrapper* when a single child accounts for ≥95%
    of its duration — reporting both is noise, the wrapper just shadows
    the real hotspot. The absolute root is always considered a wrapper
    (it equals wall-clock by definition).
    """
    ranked = []
    root_ids = {s["span_id"] for s in spans if not s.get("parent_span_id")}
    for s in spans:
        if s["span_type"] == "handoff":
            continue
        dur = s.get("duration_ms") or 0
        if dur <= 0:
            continue
        if s["span_id"] in root_ids:
            continue
        kids = children_map.get(s["span_id"], [])
        if kids:
            max_kid = max((c.get("duration_ms") or 0) for c in kids)
            if dur > 0 and max_kid / dur >= 0.95:
                continue
        ranked.append((dur, s))
    ranked.sort(key=lambda x: -x[0])
    return [s for _, s in ranked[:limit]]


def span_subtitle(s) -> str:
    """Human-friendly second-line text for a span (tool input summary, etc)."""
    m = s.get("metadata") or {}
    sub = m.get("claude.tool_input.subagent_type")
    desc = m.get("claude.tool_input.description")
    summary = m.get("claude.tool_summary") or (s.get("input_data") or {}).get("command")
    file_path = m.get("claude.tool_input.file_path")
    pattern = m.get("claude.tool_input.pattern")
    pieces = []
    if sub:
        pieces.append(sub)
    if desc:
        pieces.append(desc)
    elif summary:
        pieces.append(summary)
    elif file_path:
        pieces.append(file_path)
    elif pattern:
        pieces.append(pattern)
    text = " · ".join(p.strip() for p in pieces if p and p.strip())
    return text[:110]


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def verdict(tone: str, text: str) -> str:
    return f'<div class="verdict v-{tone}">{text}</div>'


def render_hotspots(hot, dur_total):
    if not hot:
        return "<div class='empty'>No hotspots (trace too small).</div>"
    rows = []
    for i, s in enumerate(hot, 1):
        dur = s.get("duration_ms") or 0
        pct = (dur / dur_total) * 100
        kind = {"agent": "AGENT", "tool": "TOOL", "llm_call": "LLM"}.get(s["span_type"], s["span_type"])
        subtitle = span_subtitle(s)
        sub_html = f'<span class="subtitle">{esc(subtitle)}</span>' if subtitle else ""
        rows.append(
            f'<div class="hot-row" onclick="jumpToSpan(\'{esc(s["span_id"])}\')">'
            f'<span class="hot-rank">#{i}</span>'
            f'<span class="kind k-{s["span_type"]}">{kind}</span>'
            f'<div class="hot-name"><div class="name">{esc(s["name"])}</div>{sub_html}</div>'
            f'<span class="hot-pct">{pct:.1f}%</span>'
            f'<span class="dur">{fmt_dur(dur)}</span>'
            f'</div>'
        )
    return "".join(rows)


def render_critical_path(path):
    if not path:
        return "<div class='empty'>No critical path detected.</div>"
    items = []
    for i, s in enumerate(path):
        dur = s.get("duration_ms") or 0
        kind = {"agent": "AGENT", "tool": "TOOL", "llm_call": "LLM"}.get(s["span_type"], s["span_type"])
        subtitle = span_subtitle(s)
        sub_html = f'<div class="subtitle">{esc(subtitle)}</div>' if subtitle else ""
        arrow = "<span class='cp-arrow'>→</span>" if i > 0 else ""
        items.append(
            f'{arrow}<span class="cp-node" onclick="jumpToSpan(\'{esc(s["span_id"])}\')">'
            f'<span class="kind k-{s["span_type"]}">{kind}</span>'
            f'<div class="cp-info"><div class="cp-name">{esc(s["name"])}</div>{sub_html}</div>'
            f'<span class="dur">{fmt_dur(dur)}</span>'
            f'</span>'
        )
    return f'<div class="cp">{"".join(items)}</div>'


def render_time_distribution(rows):
    if not rows:
        return "<div class='empty'>No time data.</div>"
    total = sum(r["ms"] for r in rows) or 1
    palette = ["#5dd2f3", "#a48cf5", "#f0b957", "#43c57a", "#ef5a5a",
               "#6b9bf7", "#e27fb8", "#7ad3c0", "#c8a26d", "#9298a8"]
    segs = []
    legend = []
    for i, r in enumerate(rows):
        c = palette[i % len(palette)]
        pct = r["ms"] / total * 100
        segs.append(
            f'<span class="td-seg" style="width:{pct:.2f}%;background:{c}" '
            f'title="{esc(r["label"])} — {fmt_dur(r["ms"])} ({pct:.1f}%)"></span>'
        )
        legend.append(
            f'<div class="td-leg-row"><span class="td-sw" style="background:{c}"></span>'
            f'<span class="name">{esc(r["label"])}</span>'
            f'<span class="dur">{fmt_dur(r["ms"])}</span>'
            f'<span class="dim">{pct:.1f}%</span></div>'
        )
    return (
        f'<div class="td-bar">{"".join(segs)}</div>'
        f'<div class="td-legend">{"".join(legend)}</div>'
    )


def render_tool_table(tool_stats, dur_total, spans_by_id):
    rows = []
    for t in tool_stats[:12]:
        pct = (t["total"] / dur_total * 100) if dur_total else 0
        amp = (t["p95"] / t["p50"]) if t["p50"] > 0 else 0
        amp_html = f"{amp:.0f}×" if amp > 0 else "—"
        amp_cls = "bad" if amp >= 50 else ("warn" if amp >= 10 else "dim")
        rows.append(
            f'<tr onclick="jumpToSpan(\'{esc(t["slowest_span_id"])}\')">'
            f'<td class="name">{esc(t["name"])}</td>'
            f'<td class="num">{fmt_int(t["calls"])}</td>'
            f'<td class="num">{fmt_dur(t["total"])}</td>'
            f'<td class="num dim">{fmt_dur(t["p50"])}</td>'
            f'<td class="num warn">{fmt_dur(t["p95"])}</td>'
            f'<td class="num bad">{fmt_dur(t["max"])}</td>'
            f'<td class="num {amp_cls}">{amp_html}</td>'
            f'<td class="bar-cell"><span class="bar-inline" style="width:{min(pct,100):.1f}%"></span></td>'
            f'<td class="num dim">{pct:.1f}%</td>'
            f'</tr>'
        )
    return (
        '<table class="tbl"><thead><tr>'
        '<th>Tool</th><th class="num">Calls</th><th class="num">Total</th>'
        '<th class="num">p50</th><th class="num">p95</th><th class="num">Max</th>'
        '<th class="num">p95÷p50</th><th></th><th class="num">Share</th>'
        '</tr></thead><tbody>'
        + "".join(rows)
        + '</tbody></table>'
    )


def render_cost(token_hot, cache, models, cost_from_trace):
    if not token_hot and not models:
        return "<div class='empty'>No LLM token data available.</div>"
    parts = []
    hit_pct = cache["hit_rate"] * 100
    cache_color = "good" if hit_pct >= 70 else ("warn" if hit_pct >= 30 else "bad")
    est = cost_from_trace if cost_from_trace else cache["est_cost"]
    saved = max(0.0, cache["uncached_cost"] - est)
    cost_source = "trace" if cost_from_trace else "est · opus-4 rate"
    parts.append(
        f'<div class="tk-head">'
        f'<div class="tk-head-cell"><span class="lbl">Input</span>'
        f'<span class="val">{fmt_int(cache["input"])}</span></div>'
        f'<div class="tk-head-cell"><span class="lbl">Output</span>'
        f'<span class="val">{fmt_int(cache["output"])}</span></div>'
        f'<div class="tk-head-cell"><span class="lbl">Cache read</span>'
        f'<span class="val">{fmt_int(cache["cache_read"])}</span></div>'
        f'<div class="tk-head-cell"><span class="lbl">Cache hit</span>'
        f'<span class="val {cache_color}">{hit_pct:.1f}%</span></div>'
        f'<div class="tk-head-cell"><span class="lbl">Cost ({cost_source})</span>'
        f'<span class="val">${est:,.2f}</span></div>'
        f'<div class="tk-head-cell"><span class="lbl">Cache saved</span>'
        f'<span class="val good">${saved:,.2f}</span></div>'
        f'</div>'
    )
    if models:
        parts.append('<div class="tk-models"><span class="lbl">Models:</span>')
        for m in models:
            parts.append(
                f'<span class="tk-model">{esc(m["model"])} '
                f'<span class="dim">· {fmt_int(m["calls"])} calls · {fmt_int(m["tokens"])}t</span>'
                f'</span>'
            )
        parts.append('</div>')
    if token_hot:
        parts.append('<table class="tbl"><thead><tr>'
                     '<th>#</th><th>LLM call</th><th class="num">Tokens</th>'
                     '<th class="num">In</th><th class="num">Out</th>'
                     '<th class="num">Cache</th></tr></thead><tbody>')
        for i, s in enumerate(token_hot, 1):
            m = s.get("metadata") or {}
            in_t = int(m.get("claude.usage.input_tokens", 0) or 0)
            out_t = int(m.get("claude.usage.output_tokens", 0) or 0)
            cr = int(m.get("claude.usage.cache_read_input_tokens", 0) or 0)
            parts.append(
                f'<tr onclick="jumpToSpan(\'{esc(s["span_id"])}\')">'
                f'<td class="dim">{i}</td>'
                f'<td class="name">{esc(s["name"])}</td>'
                f'<td class="num">{fmt_int(s.get("token_count") or 0)}</td>'
                f'<td class="num dim">{fmt_int(in_t)}</td>'
                f'<td class="num dim">{fmt_int(out_t)}</td>'
                f'<td class="num dim">{fmt_int(cr)}</td>'
                f'</tr>'
            )
        parts.append('</tbody></table>')
    return "".join(parts)


def render_errors(err):
    if err["failed_count"] == 0 and err["retried_spans"] == 0:
        return '<div class="empty good-empty">✓ All spans completed. No retries recorded.</div>'
    parts = [
        f'<div class="err-head">'
        f'<div class="err-head-cell"><span class="lbl">Failed spans</span>'
        f'<span class="val bad">{err["failed_count"]}</span></div>'
        f'<div class="err-head-cell"><span class="lbl">Spans with retries</span>'
        f'<span class="val warn">{err["retried_spans"]}</span></div>'
        f'<div class="err-head-cell"><span class="lbl">Total retries</span>'
        f'<span class="val">{err["total_retries"]}</span></div>'
        f'</div>'
    ]
    for c in err["clusters"]:
        parts.append(
            f'<div class="err-cluster">'
            f'<span class="err-count">×{c["count"]}</span>'
            f'<span class="err-msg">{esc(c["message"])}</span>'
            f'<span class="dim err-examples">{esc(", ".join(c["examples"]))}</span>'
            f'</div>'
        )
    return "".join(parts)


def render_handoff(ho):
    if ho["count"] == 0:
        return '<div class="empty">No handoffs recorded.</div>'
    if ho["max_bytes"] == 0:
        return (
            f'<div class="err-head"><div class="err-head-cell">'
            f'<span class="lbl">Handoffs</span>'
            f'<span class="val">{ho["count"]}</span></div></div>'
            f'<div class="empty">Context sizes were not recorded for this trace.</div>'
        )
    series = ho["series"]
    mx = max(series) or 1
    spark = "".join(
        f'<span class="spark-bar" style="height:{int(v/mx*40)+2}px" '
        f'title="handoff #{i+1}: {fmt_int(v)} bytes"></span>'
        for i, v in enumerate(series)
    )
    return (
        f'<div class="ho-head">'
        f'<div class="err-head-cell"><span class="lbl">Handoffs</span>'
        f'<span class="val">{ho["count"]}</span></div>'
        f'<div class="err-head-cell"><span class="lbl">Avg context</span>'
        f'<span class="val">{fmt_int(int(ho["avg_bytes"]))}B</span></div>'
        f'<div class="err-head-cell"><span class="lbl">Max context</span>'
        f'<span class="val warn">{fmt_int(ho["max_bytes"])}B</span></div>'
        f'</div>'
        f'<div class="spark">{spark}</div>'
    )


def render_agent_table(rows):
    if not rows:
        return '<div class="empty">No agents in this trace.</div>'
    head = (
        '<table class="tbl agents-tbl"><thead><tr>'
        '<th>Agent</th><th class="num">Duration</th>'
        '<th class="num">Tools</th><th class="num">Tool wait</th>'
        '<th class="num">LLM calls</th><th class="num">Tokens</th>'
        '<th class="num">Cache hit</th><th class="num">Status</th>'
        '</tr></thead><tbody id="agents-body">'
    )
    body = []
    for r in rows[:80]:
        short = r["name"][:26] + ("…" if len(r["name"]) > 26 else "")
        hit = r["cache_hit"] * 100
        hit_cls = "good" if hit >= 70 else ("warn" if hit >= 30 else ("dim" if hit == 0 else "bad"))
        hit_str = f"{hit:.0f}%" if r["tokens"] > 0 else "—"
        stat_cls = "good" if r["status"] == "completed" else "bad"
        body.append(
            f'<tr onclick="jumpToSpan(\'{esc(r["span_id"])}\')" '
            f'data-name="{esc(r["name"].lower())}">'
            f'<td class="name" title="{esc(r["name"])}">{esc(short)}</td>'
            f'<td class="num">{fmt_dur(r["duration_ms"])}</td>'
            f'<td class="num dim">{r["tools"]}</td>'
            f'<td class="num warn">{fmt_dur(r["tool_wait_ms"])}</td>'
            f'<td class="num dim">{r["llm_calls"]}</td>'
            f'<td class="num">{fmt_int(r["tokens"])}</td>'
            f'<td class="num {hit_cls}">{hit_str}</td>'
            f'<td class="num {stat_cls}">{r["status"]}</td>'
            f'</tr>'
        )
    if len(rows) > 80:
        body.append(
            f'<tr><td colspan="8" class="dim" style="text-align:center">'
            f'… {len(rows) - 80} more agents truncated</td></tr>'
        )
    return head + "".join(body) + "</tbody></table>"


def render_tree(root, primary_children, children_map, dur_total):
    def render_row(s, depth):
        kids = [c for c in children_map.get(s["span_id"], []) if c["span_type"] != "handoff"]
        dur = s.get("duration_ms") or 0
        pct = (dur / dur_total) * 100
        bar_w = max(1.0, min(100.0, pct))
        type_ = s["span_type"]
        kind_label = {"agent": "AGENT", "tool": "TOOL", "llm_call": "LLM"}.get(type_, type_.upper())
        status = s.get("status") or "completed"
        dot = {"completed": "ok", "failed": "err", "running": "warn"}.get(status, "ok")
        tokens = s.get("token_count") or 0
        tok_html = f'<span class="tok">{fmt_int(tokens)}t</span>' if tokens else ""
        caret = '<span class="caret">›</span>' if kids else '<span class="caret ghost">·</span>'
        subtitle = span_subtitle(s)
        sub_html = f'<div class="subtitle">{esc(subtitle)}</div>' if subtitle else ""
        html_ = (
            f'<div class="node" id="node-{esc(s["span_id"])}" '
            f'data-span-id="{esc(s["span_id"])}" data-depth="{depth}" data-expanded="false">'
            f'<div class="row" onclick="toggleNode(this)">'
            f'<span class="pad" style="width:{depth*14}px"></span>'
            f'{caret}'
            f'<span class="dot d-{dot}"></span>'
            f'<span class="kind k-{type_}">{kind_label}</span>'
            f'<div class="row-main"><div class="name">{esc(s["name"])}</div>{sub_html}</div>'
            f'{tok_html}'
            f'<span class="bar-wrap"><span class="bar" style="width:{bar_w:.1f}%"></span></span>'
            f'<span class="dur">{fmt_dur(dur)}</span>'
            f'</div>'
        )
        if kids:
            kids_sorted = sorted(kids, key=lambda x: -(x.get("duration_ms") or 0))
            html_ += '<div class="kids">'
            for c in kids_sorted:
                html_ += render_row(c, depth + 1)
            html_ += '</div>'
        html_ += '</div>'
        return html_

    out = ""
    if root:
        out += render_row(root, 0)
    else:
        for a in sorted(primary_children, key=lambda x: -(x.get("duration_ms") or 0)):
            out += render_row(a, 0)
    return out


# ---------------------------------------------------------------------------
# Interpretation (verdict strip on each card)
# ---------------------------------------------------------------------------


def verdict_hotspots(hot, active_ms):
    if not hot:
        return verdict("info", "Too few measurable spans to rank.")
    top = hot[0]
    pct = ((top.get("duration_ms") or 0) / active_ms * 100) if active_ms else 0
    if pct >= 50:
        return verdict("bad",
            f"<b>{esc(top['name'])}</b> alone consumes {pct:.0f}% of active time — "
            f"this is the single highest-leverage target.")
    if pct >= 20:
        return verdict("warn",
            f"<b>{esc(top['name'])}</b> owns {pct:.0f}% of active time. "
            f"Optimize it before anything else.")
    return verdict("good", "Load is spread across many spans — no single dominant bottleneck.")


def verdict_cpath(path, active):
    if not path:
        return verdict("info", "Path not resolvable.")
    p = active["parallelism"]
    active_ms = active["active_ms"]
    wall_ms = active["wall_ms"]
    idle = wall_ms - active_ms
    tone = "good" if p >= 1.5 else ("warn" if p >= 1.05 else "bad")
    verdict_word = (
        "highly parallel (work overlaps)"
        if p >= 1.5 else
        "mostly serial (waits stack up)" if p <= 1.05 else
        "partially parallel"
    )
    idle_note = ""
    if wall_ms > 60_000 and idle / wall_ms > 0.2:
        idle_note = f" · {fmt_dur(idle)} of idle removed from wall-clock"
    return verdict(tone,
        f"Active time {fmt_dur(active_ms)} across {len(path)} critical-path nodes — "
        f"<b>{p:.2f}×</b> {verdict_word}.{idle_note}")


def verdict_time_dist(rows):
    if not rows:
        return verdict("info", "No tool time recorded.")
    top = rows[0]
    if top["pct"] >= 50:
        return verdict("warn",
            f"<b>{esc(top['label'])}</b> absorbs {top['pct']:.0f}% of tool time — "
            f"parallelizing it or reducing call count is the biggest win.")
    return verdict("good", "Tool time is spread — no single tool dominates.")


def verdict_cost(cache):
    hit = cache["hit_rate"] * 100
    est = cache["est_cost"]
    saved = max(0.0, cache["uncached_cost"] - est)
    if cache["total_input"] == 0:
        return verdict("info", "No LLM token usage reported.")
    if hit >= 70:
        return verdict("good",
            f"Cache hit <b>{hit:.1f}%</b> is saving ~<b>${saved:,.2f}</b> vs uncached — "
            f"prompt caching is working as intended.")
    if hit >= 30:
        return verdict("warn",
            f"Cache hit <b>{hit:.1f}%</b> is low; prompts likely vary across turns. "
            f"Stabilize your system prompt to lift this toward 90%.")
    return verdict("bad",
        f"Cache hit is only <b>{hit:.1f}%</b> — you are paying full price for repeated prompts.")


def verdict_errors(err):
    if err["failed_count"] == 0 and err["retried_spans"] == 0:
        return verdict("good", "Trace is clean — no failures and no retries.")
    if err["failed_count"] == 0:
        return verdict("warn",
            f"No fatal failures, but <b>{err['total_retries']}</b> retries were needed — "
            f"transient instability is present.")
    return verdict("bad",
        f"<b>{err['failed_count']}</b> failed spans in <b>{len(err['clusters'])}</b> "
        f"error clusters — inspect the largest cluster first.")


def verdict_tool_waits(tool_stats):
    if not tool_stats:
        return verdict("info", "No tool calls recorded.")
    worst = max(tool_stats, key=lambda t: (t["p95"] / t["p50"]) if t["p50"] > 0 else 0)
    amp = (worst["p95"] / worst["p50"]) if worst["p50"] > 0 else 0
    if amp >= 50:
        return verdict("bad",
            f"<b>{esc(worst['name'])}</b> has p95/p50 = <b>{amp:.0f}×</b>. "
            f"That profile matches a proxy/plugin intercepting specific calls, not "
            f"the tool itself being slow.")
    if amp >= 10:
        return verdict("warn",
            f"<b>{esc(worst['name'])}</b> has p95/p50 = {amp:.0f}× — occasional long tails.")
    return verdict("good", "All tools return in a tight latency band.")


def verdict_handoffs(ho):
    if ho["count"] == 0:
        return verdict("info", "No handoffs in this trace.")
    if ho["max_bytes"] == 0:
        return verdict("info", "Handoff sizes were not recorded.")
    if ho["max_bytes"] > ho["avg_bytes"] * 5:
        return verdict("warn",
            f"Peak handoff is <b>{fmt_int(ho['max_bytes'])}B</b>, "
            f"~{ho['max_bytes']/max(ho['avg_bytes'],1):.0f}× the average — "
            f"a few subagents inflate context sharply.")
    return verdict("good", "Handoff context sizes look steady — no uncontrolled growth.")


def verdict_agents(rows, active_ms):
    if not rows:
        return verdict("info", "No agents to score.")
    top5_dur = sum(r["duration_ms"] for r in rows[:5])
    total = sum(r["duration_ms"] for r in rows)
    if total == 0:
        return verdict("info", "Agent durations not available.")
    pct = top5_dur / total * 100
    if pct >= 70:
        return verdict("warn",
            f"Top 5 agents account for <b>{pct:.0f}%</b> of all agent time — "
            f"work is concentrated in a few subagents.")
    return verdict("good",
        f"Work is well spread — top 5 agents carry {pct:.0f}% of total agent time.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def build(trace_path, out_path):
    trace = json.loads(Path(trace_path).read_text())
    spans = trace["spans"]
    dur_total = max(trace.get("duration_ms") or 1, 1)

    children_map = defaultdict(list)
    spans_by_id = {}
    for s in spans:
        spans_by_id[s["span_id"]] = s
        if s.get("parent_span_id"):
            children_map[s["parent_span_id"]].append(s)

    agents = [s for s in spans if s["span_type"] == "agent"]
    tools = [s for s in spans if s["span_type"] == "tool"]
    llms = [s for s in spans if s["span_type"] == "llm_call"]
    failed = sum(1 for s in spans if s.get("status") == "failed")

    tool_stats = compute_tool_stats(tools)
    cpath = compute_critical_path(spans, children_map)
    active = compute_active_time(spans)
    cache = compute_cache_stats(spans)
    model_mix = compute_model_mix(spans)
    errors = compute_errors(spans)
    handoffs = compute_handoffs(spans)
    time_dist = compute_time_distribution(spans)
    token_hot = compute_token_hotlist(spans)
    agent_table = compute_agent_table(spans, children_map)
    hot = compute_hotspots(spans, children_map, dur_total)

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

    chips = [
        ("Wall-clock", fmt_dur(dur_total)),
    ]
    if active["active_ms"] > 0 and active["active_ms"] < dur_total * 0.95:
        chips.append(("Active time", fmt_dur(active["active_ms"])))
    chips += [
        ("Agents", fmt_int(len(agents))),
        ("Tools", fmt_int(len(tools))),
        ("LLM calls", fmt_int(len(llms))),
        ("Handoffs", fmt_int(handoffs["count"])),
    ]
    if active["parallelism"] > 0:
        chips.append(("Parallelism", f"{active['parallelism']:.2f}×"))
    if total_tokens:
        chips.append(("Tokens", fmt_int(total_tokens)))
    if cache["total_input"] > 0:
        chips.append(("Cache hit", f"{cache['hit_rate']*100:.1f}%"))
    cost_val = cost_from_trace if cost_from_trace else cache["est_cost"]
    if cost_val:
        cost_suffix = " *" if not cost_from_trace else ""
        chips.append(("Cost", f"${cost_val:,.2f}{cost_suffix}"))
    if failed:
        chips.append(("Failed", str(failed)))

    chips_html = "".join(
        f'<div class="chip"><span class="chip-label">{esc(l)}</span>'
        f'<span class="chip-value">{esc(v)}</span></div>'
        for l, v in chips
    )

    cost_footnote = "" if cost_from_trace else (
        '<div class="footnote">* Cost estimated at Anthropic published '
        'opus-4 rates ($15/$75/$1.5/$18.75 per 1M input/output/cache-read/'
        'cache-creation tokens). The SDK did not populate a canonical figure.</div>'
    )

    task = esc(trace.get("task") or trace.get("trace_id", ""))
    status_ok = failed == 0
    status_label = "PASS" if status_ok else "FAIL"
    status_cls = "pass" if status_ok else "fail"

    Path(out_path).write_text(
        PAGE.format(
            task=task,
            status_label=status_label,
            status_cls=status_cls,
            chips=chips_html,
            cost_footnote=cost_footnote,
            v_hot=verdict_hotspots(hot, active["active_ms"] or dur_total),
            v_cp=verdict_cpath(cpath, active),
            v_td=verdict_time_dist(time_dist),
            v_cost=verdict_cost(cache),
            v_err=verdict_errors(errors),
            v_tw=verdict_tool_waits(tool_stats),
            v_ho=verdict_handoffs(handoffs),
            v_ag=verdict_agents(agent_table, active["active_ms"]),
            hot_rows=render_hotspots(hot, active["active_ms"] or dur_total),
            cpath=render_critical_path(cpath),
            time_dist=render_time_distribution(time_dist),
            cost=render_cost(token_hot, cache, model_mix, cost_from_trace),
            errors=render_errors(errors),
            tool_tbl=render_tool_table(tool_stats, dur_total, spans_by_id),
            handoffs=render_handoff(handoffs),
            agents_tbl=render_agent_table(agent_table),
            tree=render_tree(tree_root, primary_children, children_map, dur_total),
        ),
        encoding="utf-8",
    )


PAGE = """<!DOCTYPE html>
<html lang="en"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AgentGuard — {task}</title>
<style>
:root {{
  --bg: #0b0e14; --surface: #131823; --surface-2: #1a2030; --surface-3: #0f141d;
  --border: #232a3a; --fg: #dde3ef; --dim: #7a8599; --dim-2: #5a6478;
  --accent: #5dd2f3; --warn: #f0b957; --good: #43c57a; --bad: #ef5a5a; --violet: #a48cf5;
}}
* {{ box-sizing: border-box; }}
html, body {{ margin: 0; background: var(--bg); color: var(--fg); }}
body {{ font: 13px/1.55 -apple-system, "Segoe UI", "Inter", system-ui, sans-serif; min-height: 100vh; }}
.wrap {{ max-width: 1280px; margin: 0 auto; padding: 28px 32px 80px; }}

.hdr {{ display: flex; align-items: baseline; gap: 14px; margin-bottom: 6px; }}
.brand {{ font-weight: 700; font-size: 15px; letter-spacing: 0.3px; color: var(--fg); }}
.brand .dot {{ display:inline-block;width:8px;height:8px;border-radius:2px;
  background: var(--accent); margin-right: 8px; transform: translateY(-1px); }}
.sub {{ color: var(--dim); font-size: 11px; letter-spacing: 0.5px; text-transform: uppercase; }}
.pill {{ margin-left: auto; padding: 3px 10px; border-radius: 999px; font-size: 11px;
  font-weight: 600; letter-spacing: 0.4px; text-transform: uppercase; }}
.pill.pass {{ background: rgba(67,197,122,0.15); color: var(--good); }}
.pill.fail {{ background: rgba(239,90,90,0.15); color: var(--bad); }}
h1 {{ font-size: 22px; font-weight: 650; margin: 4px 0 16px; letter-spacing: -0.2px; color: var(--fg); }}

.chips {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 8px; }}
.chip {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 14px; display: flex; flex-direction: column; gap: 2px; min-width: 92px; }}
.chip-label {{ font-size: 10px; color: var(--dim); letter-spacing: 0.5px; text-transform: uppercase; }}
.chip-value {{ font-size: 16px; font-weight: 600; color: var(--fg);
  font-variant-numeric: tabular-nums; font-family: "JetBrains Mono", ui-monospace, monospace; }}
.footnote {{ font-size: 11px; color: var(--dim-2); margin: 6px 0 18px; }}

.grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 18px; margin-bottom: 18px; }}
.grid.one {{ grid-template-columns: 1fr; }}
@media (max-width: 900px) {{ .grid {{ grid-template-columns: 1fr; }} }}
.card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 18px; }}
.card h2 {{ margin: 0 0 4px; font-size: 11px; color: var(--dim); letter-spacing: 1px;
  text-transform: uppercase; font-weight: 600; display: flex; align-items: center; gap: 8px; }}
.card h2 .hint {{ color: var(--dim-2); font-weight: 400; letter-spacing: 0;
  text-transform: none; font-size: 11px; }}

.verdict {{ font-size: 12px; margin: 0 0 12px; padding: 6px 10px; border-radius: 6px;
  border-left: 3px solid var(--dim-2); background: rgba(255,255,255,0.015); color: var(--fg); }}
.verdict b {{ color: var(--fg); font-weight: 600; }}
.verdict.v-good {{ border-left-color: var(--good); }}
.verdict.v-warn {{ border-left-color: var(--warn); }}
.verdict.v-bad {{ border-left-color: var(--bad); }}
.verdict.v-info {{ border-left-color: var(--accent); }}

.empty {{ color: var(--dim-2); font-size: 12px; padding: 8px 0; }}
.empty.good-empty {{ color: var(--good); }}

.hot-row {{ display: grid; grid-template-columns: 30px 50px 1fr auto auto; gap: 12px;
  padding: 7px 6px; border-radius: 6px; align-items: center;
  cursor: pointer; transition: background 0.12s; }}
.hot-row:hover {{ background: var(--surface-2); }}
.hot-rank {{ color: var(--dim-2); font-size: 11px;
  font-variant-numeric: tabular-nums; font-family: "JetBrains Mono", ui-monospace, monospace; }}
.hot-pct {{ color: var(--warn); font-size: 11px;
  font-variant-numeric: tabular-nums; font-family: "JetBrains Mono", ui-monospace, monospace; }}
.hot-name {{ min-width: 0; }}

.subtitle {{ color: var(--dim); font-size: 10.5px; margin-top: 2px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 640px; }}

.cp {{ display: flex; flex-wrap: wrap; gap: 6px; align-items: stretch; }}
.cp-arrow {{ color: var(--dim-2); padding: 0 2px; align-self: center; }}
.cp-node {{ display: inline-flex; align-items: center; gap: 10px; background: var(--surface-2);
  padding: 6px 10px; border-radius: 6px; border: 1px solid var(--border);
  cursor: pointer; transition: all 0.12s; }}
.cp-node:hover {{ border-color: var(--accent); }}
.cp-info {{ display: flex; flex-direction: column; gap: 1px; min-width: 0; }}
.cp-name {{ font-size: 12.5px; }}

.kind {{ font-size: 9.5px; font-weight: 700; letter-spacing: 0.7px; padding: 2px 7px;
  border-radius: 4px; text-align: center;
  font-family: "JetBrains Mono", ui-monospace, monospace; min-width: 44px; display: inline-block; }}
.k-agent {{ background: rgba(93,210,243,0.14); color: var(--accent); }}
.k-tool {{ background: rgba(164,140,245,0.14); color: var(--violet); }}
.k-llm_call, .k-llm {{ background: rgba(240,185,87,0.14); color: var(--warn); }}
.k-handoff {{ background: rgba(122,133,153,0.14); color: var(--dim); }}

.tbl {{ width: 100%; border-collapse: collapse; font-size: 12px; }}
.tbl th {{ text-align: left; padding: 6px 10px; font-size: 10px; color: var(--dim);
  border-bottom: 1px solid var(--border); letter-spacing: 0.5px; text-transform: uppercase; font-weight: 600; }}
.tbl td {{ padding: 7px 10px; border-bottom: 1px solid rgba(35,42,58,0.5); }}
.tbl tbody tr {{ cursor: pointer; transition: background 0.1s; }}
.tbl tbody tr:hover {{ background: var(--surface-2); }}
.tbl .num {{ text-align: right;
  font-family: "JetBrains Mono", ui-monospace, monospace; }}
.tbl td.name {{ color: var(--fg); white-space: nowrap; max-width: 260px;
  overflow: hidden; text-overflow: ellipsis; }}
.tbl .dim {{ color: var(--dim); }} .tbl .warn {{ color: var(--warn); }}
.tbl .bad {{ color: var(--bad); }} .tbl .good {{ color: var(--good); }}
.bar-cell {{ width: 110px; }}
.bar-inline {{ display: block; height: 5px; background: var(--accent); border-radius: 3px; opacity: 0.8; }}

.td-bar {{ display: flex; height: 12px; border-radius: 4px; overflow: hidden;
  background: var(--surface-3); margin-bottom: 10px; }}
.td-seg {{ height: 100%; display: inline-block; }}
.td-legend {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 4px 16px; font-size: 11.5px; }}
.td-leg-row {{ display: grid; grid-template-columns: 12px 1fr auto auto; gap: 8px; align-items: center; }}
.td-sw {{ width: 10px; height: 10px; border-radius: 2px; display: inline-block; }}
.td-leg-row .dim {{ color: var(--dim-2);
  font-family: "JetBrains Mono", ui-monospace, monospace; }}
.td-leg-row .name {{ white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.td-leg-row .dur {{ color: var(--dim); font-size: 11px;
  font-family: "JetBrains Mono", ui-monospace, monospace; }}

.tk-head, .err-head, .ho-head {{ display: flex; gap: 18px; margin-bottom: 10px; flex-wrap: wrap; }}
.tk-head-cell, .err-head-cell {{ display: flex; flex-direction: column; gap: 1px; }}
.lbl {{ font-size: 10px; color: var(--dim); letter-spacing: 0.5px; text-transform: uppercase; }}
.val {{ font-size: 15px; font-weight: 600;
  font-family: "JetBrains Mono", ui-monospace, monospace; }}
.val.good {{ color: var(--good); }} .val.warn {{ color: var(--warn); }}
.val.bad {{ color: var(--bad); }}
.tk-models {{ margin: 8px 0; font-size: 11px; }}
.tk-model {{ display: inline-block; background: var(--surface-2); border: 1px solid var(--border);
  padding: 3px 8px; border-radius: 6px; margin-right: 6px;
  font-family: "JetBrains Mono", ui-monospace, monospace; }}
.tk-models .lbl {{ margin-right: 6px; }}

.err-cluster {{ display: grid; grid-template-columns: 40px 1fr auto; gap: 8px;
  padding: 5px 6px; border-radius: 4px; align-items: center; }}
.err-cluster:hover {{ background: var(--surface-2); }}
.err-count {{ color: var(--bad); font-weight: 600;
  font-family: "JetBrains Mono", ui-monospace, monospace; }}
.err-msg {{ font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11.5px; }}
.err-examples {{ font-size: 10.5px; max-width: 260px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}

.spark {{ display: flex; align-items: flex-end; gap: 2px; height: 48px;
  background: var(--surface-3); border-radius: 4px; padding: 4px; overflow: hidden; }}
.spark-bar {{ flex: 1 1 auto; min-width: 2px; max-width: 6px;
  background: var(--violet); border-radius: 1px; }}

.agents-wrap {{ max-height: 460px; overflow-y: auto; border-radius: 8px; border: 1px solid var(--border); }}
.agents-tbl {{ font-size: 11.5px; }}
.agents-tbl thead th {{ position: sticky; top: 0; background: var(--surface); z-index: 1; }}
.agents-search {{ width: 100%; background: var(--surface-3); border: 1px solid var(--border);
  color: var(--fg); padding: 6px 10px; border-radius: 6px; font-size: 12px; margin-bottom: 8px; }}

.tree-hdr {{ display: flex; align-items: center; gap: 12px; margin: 22px 0 10px; }}
.tree-hdr h2 {{ margin: 0; font-size: 11px; color: var(--dim); letter-spacing: 1px;
  text-transform: uppercase; font-weight: 600; }}
.tree-hdr .actions {{ margin-left: auto; display: flex; gap: 6px; }}
.btn {{ background: var(--surface); border: 1px solid var(--border); color: var(--dim);
  padding: 4px 10px; border-radius: 6px; font-size: 11px; cursor: pointer; transition: all 0.12s; }}
.btn:hover {{ color: var(--fg); border-color: var(--dim-2); }}
.tree {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }}
.node > .kids {{ display: none; }}
.node[data-expanded="true"] > .kids {{ display: block; }}
.node.flash > .row {{ background: rgba(93,210,243,0.15); }}
.row {{ display: grid; grid-template-columns: auto 16px 10px 60px 1fr auto 220px auto;
  gap: 10px; align-items: center; padding: 7px 14px; cursor: pointer;
  border-bottom: 1px solid rgba(35,42,58,0.5); transition: background 0.1s; }}
.row-main {{ min-width: 0; display: flex; flex-direction: column; gap: 1px; }}
.node:last-child > .row {{ border-bottom: none; }}
.row:hover {{ background: var(--surface-2); }}
.caret {{ color: var(--dim-2); width: 16px; text-align: center; font-size: 14px; transition: transform 0.12s; }}
.caret.ghost {{ color: rgba(122,133,153,0.25); }}
.node[data-expanded="true"] > .row > .caret:not(.ghost) {{ transform: rotate(90deg); color: var(--accent); }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; }}
.d-ok {{ background: var(--good); }} .d-err {{ background: var(--bad); }} .d-warn {{ background: var(--warn); }}
.name {{ color: var(--fg); font-size: 12.5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
.tok {{ color: var(--dim); font-size: 10.5px;
  font-family: "JetBrains Mono", ui-monospace, monospace; }}
.bar-wrap {{ height: 6px; background: rgba(35,42,58,0.7); border-radius: 3px; overflow: hidden; width: 220px; }}
.bar {{ display: block; height: 100%;
  background: linear-gradient(90deg, var(--accent), var(--violet)); border-radius: 3px; }}
.dur {{ color: var(--fg);
  font-family: "JetBrains Mono", ui-monospace, monospace; font-size: 11.5px;
  min-width: 58px; text-align: right; }}
.pad {{ display: inline-block; }}
.footer {{ color: var(--dim-2); font-size: 11px; margin-top: 22px; text-align: center; }}
</style>
</head>
<body>
<div class="wrap">

  <div class="hdr">
    <div class="brand"><span class="dot"></span>AgentGuard</div>
    <span class="sub">diagnose · claude_session_import</span>
    <span class="pill {status_cls}">{status_label}</span>
  </div>

  <h1>{task}</h1>

  <div class="chips">{chips}</div>
  {cost_footnote}

  <div class="grid one">
    <div class="card">
      <h2>Top hotspots <span class="hint">— click any row to jump to the span</span></h2>
      {v_hot}
      {hot_rows}
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>Critical path <span class="hint">— longest descent from root</span></h2>
      {v_cp}
      {cpath}
    </div>
    <div class="card">
      <h2>Time distribution <span class="hint">— where tool time went</span></h2>
      {v_td}
      {time_dist}
    </div>
  </div>

  <div class="grid">
    <div class="card">
      <h2>LLM cost &amp; tokens</h2>
      {v_cost}
      {cost}
    </div>
    <div class="card">
      <h2>Failures &amp; retries</h2>
      {v_err}
      {errors}
    </div>
  </div>

  <div class="grid one">
    <div class="card">
      <h2>Tool waits <span class="hint">— tool_use → tool_result latency</span></h2>
      {v_tw}
      {tool_tbl}
    </div>
  </div>

  <div class="grid one">
    <div class="card">
      <h2>Handoffs <span class="hint">— context carried between agents</span></h2>
      {v_ho}
      {handoffs}
    </div>
  </div>

  <div class="grid one">
    <div class="card">
      <h2>Agents <span class="hint">— click a row to jump</span></h2>
      {v_ag}
      <input class="agents-search" placeholder="Filter agents by name…" oninput="filterAgents(this.value)">
      <div class="agents-wrap">{agents_tbl}</div>
    </div>
  </div>

  <div class="tree-hdr">
    <h2>Execution tree</h2>
    <div class="actions">
      <button class="btn" onclick="expandAll(true)">Expand all</button>
      <button class="btn" onclick="expandAll(false)">Collapse all</button>
    </div>
  </div>
  <div class="tree" id="tree">{tree}</div>

  <div class="footer">AgentGuard prototype · v3</div>
</div>

<script>
function toggleNode(rowEl) {{
  var node = rowEl.parentElement;
  if (!node.querySelector(':scope > .kids')) return;
  var now = node.getAttribute('data-expanded') === 'true';
  node.setAttribute('data-expanded', now ? 'false' : 'true');
}}
function expandAll(on) {{
  document.querySelectorAll('#tree .node').forEach(function(n) {{
    if (n.querySelector(':scope > .kids')) {{
      n.setAttribute('data-expanded', on ? 'true' : 'false');
    }}
  }});
}}
(function() {{
  var root = document.querySelector('#tree > .node');
  if (root && root.querySelector(':scope > .kids')) {{
    root.setAttribute('data-expanded', 'true');
  }}
}})();
function jumpToSpan(spanId) {{
  var el = document.getElementById('node-' + spanId);
  if (!el) return;
  var cur = el.parentElement;
  while (cur && cur.classList.contains('kids')) {{
    var parentNode = cur.parentElement;
    if (parentNode) parentNode.setAttribute('data-expanded', 'true');
    cur = parentNode ? parentNode.parentElement : null;
  }}
  el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
  el.classList.add('flash');
  setTimeout(function() {{ el.classList.remove('flash'); }}, 1600);
}}
function filterAgents(q) {{
  q = (q || '').toLowerCase();
  document.querySelectorAll('#agents-body tr').forEach(function(tr) {{
    var name = tr.getAttribute('data-name') || '';
    tr.style.display = (!q || name.indexOf(q) !== -1) ? '' : 'none';
  }});
}}
</script>
</body></html>
"""


if __name__ == "__main__":  # pragma: no cover - CLI convenience
    build(sys.argv[1], sys.argv[2])
