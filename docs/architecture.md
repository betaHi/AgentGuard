# AgentGuard Architecture

## Module Map

```
agentguard/
├── core/
│   ├── trace.py          — ExecutionTrace + Span data model
│   ├── config.py         — Configuration
│   └── eval_schema.py    — Evaluation schema
│
├── sdk/                  — Instrumentation (7 integration styles)
│   ├── decorators.py     — @record_agent, @record_tool
│   ├── async_decorators  — Async versions
│   ├── context.py        — AgentTrace, ToolContext context managers
│   ├── manual.py         — Manual API
│   ├── middleware.py      — Middleware/wrap pattern
│   ├── distributed.py    — Cross-process trace propagation
│   ├── handoff.py        — Handoff recording + context tracking
│   ├── hooks.py          — Span lifecycle callbacks
│   └── recorder.py       — TraceRecorder (thread-safe)
│
├── analysis/             — Trace analysis (Tier 1)
│   ├── analysis.py       — 7 analysis functions
│   ├── propagation.py    — Failure causal chains, circuit breakers
│   ├── flowgraph.py      — DAG, phases, critical path, Mermaid
│   ├── context_flow.py   — Compression/truncation/expansion
│   ├── correlation.py    — Fingerprints, patterns
│   ├── timeline.py       — Chronological event stream
│   └── tree.py           — Span tree utilities
│
├── extensions/           — Built on traces (Tier 2)
│   ├── scoring.py        — 5-component quality score (A-F)
│   ├── annotations.py    — Structured span tags
│   ├── aggregate.py      — Multi-trace trends
│   ├── filter.py         — Composable query DSL
│   ├── ab_test.py        — A/B testing
│   ├── metrics.py        — Duration percentiles, Prometheus
│   ├── alerts.py         — Declarative alert rules
│   ├── sla.py            — SLA checking
│   ├── dependency.py     — Agent dependency graph
│   ├── profile.py        — Per-agent performance profiles
│   ├── optimize.py       — Optimization suggestions
│   ├── budget.py         — Token budget tracking
│   ├── errors.py         — Error classification
│   ├── comparison.py     — Rich trace comparison
│   ├── diff.py           — Trace diff
│   ├── span_diff.py      — Span-level diff
│   └── summarize.py      — Natural language summaries
│
├── tools/
│   ├── builder.py        — Fluent trace builder
│   ├── generate.py       — Synthetic trace generator
│   ├── templates.py      — Pipeline templates
│   ├── store.py          — File-based storage
│   ├── search.py         — Full-text search
│   ├── manipulate.py     — Clone, slice, anonymize, merge
│   ├── compress.py       — Trace compression
│   ├── normalize.py      — Trace cleanup
│   ├── benchmark.py      — Performance benchmarks
│   └── importer.py       — OTel import
│
├── eval/                 — Rule evaluation
│   ├── rules.py          — Built-in eval rules
│   ├── compare.py        — Comparison evaluators
│   └── llm.py            — LLM-based evaluation
│
├── web/
│   └── viewer.py         — HTML report generator
│
├── cli/
│   └── main.py           — 30 CLI commands
│
├── plugin.py             — Plugin registry
├── stats.py              — Statistical utilities
├── compat.py             — Schema versioning
├── schema.py             — JSON Schema validation
├── markdown.py           — Markdown export
├── ascii_viz.py          — Terminal visualizations
├── dashboard.py          — Dashboard data
└── export*.py            — JSON/JSONL/OTel/CSV export
```

## Data Flow

```
Your Code (agents, tools)
    │
    ▼ instrumentation (decorators/context managers)
    │
TraceRecorder (thread-safe)
    │
    ▼ finish_recording()
    │
ExecutionTrace (spans, relationships)
    │
    ├──▶ Analysis (scoring, flow, propagation, ...)
    ├──▶ Export (JSON, CSV, OTel, Prometheus, HTML, Markdown)
    ├──▶ Storage (file store, query, prune)
    ├──▶ Monitoring (SLA, alerts, guard mode)
    └──▶ Comparison (diff, A/B test, aggregate)
```

## Key Design Decisions

1. **Zero external dependencies** for core/ and sdk/
2. **Thread-safe** recorder using thread-local span stacks
3. **Flat span list** with parent_span_id (tree assembled on demand)
4. **Analysis consumes trace** — modules are pure functions on ExecutionTrace
5. **Viewer = single HTML file** — no server, no JS framework, just one file
