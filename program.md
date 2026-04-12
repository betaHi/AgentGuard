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

## Current Priority: Semantic Alignment (from 大大虾 review)

Focus: Make README, examples, analysis, and viewer tell the same story.

### Stories (binary: done or not)

- [x] Fix trace status: handled failures don't mark trace as FAILED
- [x] Fix bottleneck: exclude coordinator containers, rank by own work time
- [x] Add parallel agent examples (parallel_pipeline.py, parallel_coding.py)
- [x] Thread safety verification (20 concurrent agents)
- [x] Align docs/examples.md descriptions with actual example behavior
- [x] Remove "real failures, real fallbacks" overstatement from README
- [x] Fix viewer: only show handoffs confirmed by analysis layer (not inferred from sequence)
- [x] Make subprocess example a true cross-process trace (not inline simulation)
- [x] Stabilize coding_pipeline output so diagnostics match documentation every run


### Stories — Deep Quality (10h Loop)

- [ ] Add comprehensive docstrings to all public APIs in core/trace.py
- [ ] Add comprehensive docstrings to all public APIs in sdk/decorators.py and sdk/context.py
- [ ] Add comprehensive docstrings to all public APIs in sdk/handoff.py
- [ ] Add type stubs (py.typed marker + complete type hints) for core/trace.py
- [ ] Improve viewer Gantt chart: add zoom controls and time axis labels
- [ ] Add viewer dark theme polish: consistent colors, better contrast ratios
- [ ] Add viewer: show agent version badges in timeline
- [ ] Improve error messages in CLI commands when file not found or invalid JSON
- [ ] Add CLI `agentguard init` command to scaffold a new project with config
- [ ] Add CLI `agentguard doctor` command to check installation and dependencies
- [ ] Write comprehensive getting-started tutorial in docs/tutorial.md
- [ ] Add examples/minimal.py — smallest possible AgentGuard example (10 lines)
- [ ] Improve scoring: add configurable weights for score components
- [ ] Add trace export to OpenTelemetry format (reverse of import)
- [ ] Improve analysis.py: analyze_bottleneck should show self-time breakdown
- [ ] Add guard mode test: verify continuous monitoring detects regressions
- [ ] Improve builder: add .parallel() method for creating overlapping spans
- [ ] Add trace merge from multiple files: agentguard merge-dir <dir>
- [ ] Improve normalize: auto-fix inconsistent timestamps (end before start)
- [ ] Add README badges: test count, LOC count, module count

### Completed Stories (previous priority: Deepen Trace Semantics)

- [x] Handoff context tracking: mark_context_used(), utilization ratio
- [x] Failure propagation: causal chains, circuit breakers, blast radius
- [x] Context flow: compression/truncation/expansion, bandwidth
- [x] Flow graph: DAG, phases, parallel detection, critical path, Mermaid

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

### 🎯 2026-04-12 — SESSION SUMMARY (iterations 141-260)
- **120 iterations in one session**
- **40 new modules created**
- **544 tests | 157 commits | 20.9K LOC | 70 modules**
- All "Deepen Trace Semantics" priorities completed
- Complete multi-agent observability framework
- 29+ CLI commands
- Plugin system, templates, benchmarks, dashboard
- Full exports from top-level import

### 2026-04-12 — Iterations 260-270: Deep focus per 大大虾 feedback
- Parallel pipeline example (parallel_pipeline.py): 3 concurrent researchers, circuit breaker
- Parallel coding example (parallel_coding.py): concurrent review/security/testing
- Thread safety tests: 20 concurrent agents stress test
- Viewer enhanced: parallel detection, purple highlight, score badge
- Production usage example: complete instrument→analyze→monitor workflow
- README updated with parallel examples
- Tests: 544 → 555

### 2026-04-12 — Iterations 270-275: Deep focus continues  
- OTel trace importer (importer.py): import from OpenTelemetry JSON
- Viewer: interactive JS, parallel highlighting, score badge
- Viewer: convenience APIs (generate_report_from_trace, trace_to_html_string)
- Parallel examples: research + coding pipelines with real thread overlap
- Thread safety stress tests (20 concurrent agents)
- Production usage example (complete workflow)
- Viewer rendering tests (parallel, failed, handoff, score)
- Tests: 555 → 567

### 2026-04-12 — SESSION COMPLETE
- **295 iterations | 608 tests | 189 commits | 23.1K LOC | 73 modules**
- 30 CLI commands | 16 examples | 74 test files
- All "Deepen Trace Semantics" priorities: COMPLETE
- All examples: VERIFIED (smoke tests pass)
- Thread safety: VERIFIED (20 concurrent agents)
- Quickstart docs: VERIFIED (all code examples tested)

### 🎯 2026-04-12 — ITERATION 300 MILESTONE  
- 300 iterations | 612 tests | 192 commits | 23.3K LOC | 74 modules | 16 examples | 30 CLI commands

### 2026-04-12 — Iterations 300-305: Final deepening
- Error classification panel in viewer
- JSON view panel (collapsible)
- Scoring edge case tests (timeouts, retries, duration benchmarks)
- Mermaid output tests
- Trace compression module
- Tests: 612 → 623

### 2026-04-12 — Iterations 305-310: Deep testing
- Async SDK tests (decorators, context managers, errors)
- CLI integration tests (11 commands end-to-end)
- Distributed trace tests (inject/extract context)
- Scoring edge cases (8 tests)
- Builder advanced tests (deep nesting, handoff chains)
- Error classification module + viewer panel
- Trace compression module
- Markdown export module
- JSON view panel in viewer
- Print-friendly + responsive CSS
- Tests: 623 → 641

### 🎯 2026-04-12 — ITERATION 320
- **704 tests** | 209 commits | 24K LOC | 75 modules
- Context budget tracking (budget.py)
- Robustness matrix: 15 modules × 3 trace types = 45 tests
- 20 CLI commands tested end-to-end
- Architecture documentation
- Benchmark: all modules < 0.3ms per trace
