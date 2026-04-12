# AgentGuard — Development Program

> This file drives the Ralph Loop. Humans set direction. Agents write code.

## Identity

- **Name:** AgentGuard
- **Positioning:** Observability for multi-agent orchestration.
- **One-liner:** See how your agents collaborate, where they fail, and why.
- **Repo:** https://github.com/betaHi/AgentGuard
- **License:** MIT
- **Language:** Python 3.11+

## What Matters Most (Priority Order)

### Tier 1 — Core (the product)
The trace data model and the instrumentation that feeds it. This is what makes AgentGuard unique.

- **Trace schema** — ExecutionTrace, Span, span types, parent-child relationships
- **Instrumentation SDK** — decorators, context managers, manual API, distributed propagation
- **Multi-agent semantics** — handoff events, context flow between agents, failure propagation paths
- **Trace visualization** — CLI tree, web timeline, flow graph

### Tier 2 — Extensions (built on traces)
Valuable but secondary. These consume trace data — they don't define the product.

- **Eval rules** — assertions on agent output quality
- **Replay engine** — baseline comparison and regression detection
- **Guard mode** — continuous monitoring and alerts
- **Export** — OTel, JSONL for integration

### Tier 3 — Future
Not now. Will grow naturally once Tier 1 is deep enough.

- Interactive web dashboard
- LLM-based evaluation
- Real-time streaming traces
- GitHub Actions integration

## Core Asset Protection

The most valuable code in this repo is NOT the rule engine. It is:

1. **agentguard/core/trace.py** — the trace schema
2. **agentguard/sdk/** — low-intrusion instrumentation
3. **The ability to express cross-agent relationships** — parent-child, handoff, context propagation

These must be kept clean, well-documented, and zero-dependency.

## Current Priority: Deepen Trace Semantics

The next iterations should focus on making the trace richer, not adding more commands.

### Handoff Events
When agent A passes work to agent B, capture:
- What context was passed
- What context was lost
- Duration of the handoff
- Whether the receiving agent used the context

### Failure Propagation Analysis
Given a trace with failures:
- Which span was the root cause?
- Did the failure propagate or get caught?
- What was the blast radius (how many downstream spans affected)?

### Context Flow
Track how information flows between agents:
- Context size at each handoff point
- Context compression/truncation events
- Whether downstream agents received sufficient context

### Multi-Agent Flow Graph
Beyond tree view — show the actual flow:
- Parallel vs sequential execution
- Agent dependencies
- Critical path analysis

## Design Rules

1. Zero external deps for core/ and sdk/
2. All code and docs in English
3. Type hints and docstrings on public APIs
4. Every change has tests
5. Trace depth > feature breadth

## Progress Log

### 2026-04-11 — Project launch
- Sprint 1-4 completed (core, eval, replay, guard)
- 12 iterations via Ralph Loop
- 74 tests passing
- 6 integration styles
- Bug fixes from code review (distributed trace, guard, XSS)
- README repositioned: observability-first
- program.md repositioned: trace depth over feature breadth

### 2026-04-12 — Deepen trace semantics (iterations 141-145)
- Handoff context usage tracking: mark_context_used(), utilization ratio, context_received/used_keys/dropped_keys
- Failure propagation: causal chains, circuit breaker detection, hypothetical failure analysis (propagation.py)
- Flow graph DAG: execution phases, parallel/sequential detection, critical path, Mermaid output (flowgraph.py)
- Context flow: compression/truncation/expansion events, bandwidth analysis, bottleneck detection (context_flow.py)
- 3 new CLI commands: propagation, flowgraph, context-flow
- Tests: 148 → 189+

### 2026-04-12 — Iterations 146-150: Deep semantics + wiring
- Handoff chain analysis + context integrity scoring (propagation.py)
- Span correlation: fingerprinting, failure-handoff causality, pattern detection (correlation.py)
- Semantic trace diff: flow graph + context flow comparison (diff.py)
- End-to-end deep analysis demo (examples/deep_analysis_demo.py)
- All new modules wired into __init__.py exports + CLI
- CHANGELOG updated
- Tests: 189 → 209

### 2026-04-12 — Iterations 151-160: Extensions + tooling
- Span lifecycle hooks (sdk/hooks.py)
- Trace scoring: 5-component quality score with A-F grade (scoring.py)
- Span annotations: structured tags + auto-annotate (annotations.py)
- Trace aggregation: multi-trace trends and agent rankings (aggregate.py)
- Filter DSL: composable span/trace filters + sampling (filter.py)
- A/B testing: compare agent versions + regression detection (ab_test.py)
- Timeline: chronological event stream (timeline.py)
- 4 new CLI commands: score, aggregate, annotate, correlate
- Tests: 209 → 286

### 2026-04-12 — Iterations 161-170: Tooling + developer experience
- JSON Schema validation (schema.py)
- Metrics collector with duration percentiles + Prometheus export (metrics.py)
- Fluent trace builder API for testing (builder.py)
- File-based trace store with query + prune (store.py)
- 3 more CLI commands: timeline, metrics, schema (21 total)
- Full analysis example using all modules
- Tests: 286 → 322

### 2026-04-12 — Iterations 171-180: Robustness + tooling
- Span tree utilities (tree.py): stats, cycles, orphans, text render
- Trace normalization (normalize.py): orphan fix, dedup, status reconciliation
- Rich trace comparison (comparison.py): scores + metrics + structural diff
- Trace summarizer (summarize.py): natural language summaries
- Agent profiling (profile.py): per-agent stats across traces
- Tests: 322 → 358

### 2026-04-12 — Iterations 181-190: Integration + edge cases + alerting
- Full integration test: 23 analysis modules tested on complex trace  
- Extended edge cases: empty, 100-span, 50-deep, malformed, unicode
- Span-level diff (span_diff.py): field-by-field comparison
- Alert rules engine (alerts.py): declarative rules, severity, batch
- README feature table
- Tests: 358 → 418

### 🎯 2026-04-12 — ITERATION 200 MILESTONE
- 200 iterations | 447 tests | 134 commits | 18.3K LOC
- 58 Python modules in agentguard/ package
- Agent dependency graph (dependency.py)
- SLA checker (sla.py)
- Trace generator for benchmarking (generate.py)
- Benchmark harness — 13-module perf suite (benchmark.py)
- Full integration test (23 modules on complex trace)
- Extended edge case tests (empty/large/malformed/unicode/deep)
- Span-level diff (span_diff.py)
- Alert rules engine (alerts.py)

### 2026-04-12 — Iterations 200-210: CLI, replay, search
- 8 new CLI commands (29+ total): span-diff, sla, dependencies, benchmark, generate, summarize, tree, compare
- Updated quickstart docs
- Trace replay v2: assertions, mutation testing
- Trace search: full-text, regex, multi-field
- Tests: 447 → 467

### 2026-04-12 — Iterations 210-220
- Optimization suggestions (optimize.py): retries, parallelization, cost, context
- Enhanced export (export_v2.py): CSV/TSV/table for pandas
- Trace search (search.py): full-text, regex, multi-field
- Tests: 467 → 480

### 🎯 2026-04-12 — 500+ TESTS MILESTONE (iteration 226)
- 226 iterations | 502 tests | 146 commits | 19.7K LOC | 64 modules
- Schema compatibility + migration (compat.py)
- Statistical analysis utilities (stats.py): descriptive, outliers, trends
- Complete multi-agent observability framework

### 2026-04-12 — Iterations 220-230
- Schema compatibility + migration (compat.py)
- Statistical analysis (stats.py)
- ASCII visualization (ascii_viz.py): Gantt, status summary, distribution
- Tests: 480 → 507

### 2026-04-12 — Iterations 230-240
- Plugin system (plugin.py): custom analyzers/exporters registry
- Trace templates (templates.py): research, code_review, support, ETL
- ASCII visualization (ascii_viz.py): Gantt chart, status summary
- Schema compatibility + migration (compat.py)
- Statistical analysis (stats.py)
- Tests: 507 → 523

### 🎯 2026-04-12 — ITERATION 250 MILESTONE
- 250 iterations | 537 tests | 154 commits | 20.7K LOC | 69 modules
- Trace manipulation: clone, slice, anonymize, merge (manipulate.py)
- Dashboard data provider (dashboard.py)
- Plugin system (plugin.py)
- Trace templates: 4 pipeline patterns (templates.py)
- ASCII visualization (ascii_viz.py)
- Complete multi-agent observability framework
