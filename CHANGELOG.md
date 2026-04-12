# Changelog

All notable changes to AgentGuard will be documented in this file.


## [Unreleased]

### Added
- **Evolution Engine** (`agentguard/evolve.py`): Self-reflection and learning
  - `reflect()`: Extract lessons from traces (failures, bottlenecks, handoffs)
  - `learn()`: Persist lessons to Zettelkasten-style knowledge base
  - `suggest()`: High-confidence improvement suggestions
  - `detect_trends()`: Recurring failure, persistent bottleneck detection
  - Knowledge accumulates across runs, confidence increases with repetition
- **Guard auto-learn**: `Guard(auto_learn=True)` learns from every monitored trace
- **Trace Validator** (`agentguard/validate.py`): Check trace integrity
  - Orphan spans, duplicate IDs, circular references, missing fields
- **Trace Diff** (`agentguard/diff.py`): Side-by-side trace comparison
  - Status changes, duration changes, added/removed spans
- **Trace Query** (`agentguard/query.py`): Filter and aggregate traces
  - TraceStore with filter by task/trigger/status/agent/duration
  - Per-agent and per-tool statistics
- **Health Reports** (`agentguard/health.py`): Aggregate agent health
- **Context Flow Analysis**: Detect context loss/bloat at handoffs
- **Bottleneck Analysis**: Critical path, agent rankings
- **Web Panel**: Upgraded to Gantt-style timeline + sidebar + diagnostics grid
- **CLI**: 9 commands (added validate, diff, analyze, evolve)
- **Deterministic demo**: `random.seed(42)` for reproducible screenshots
- 16 integration tests covering full user workflows
- Duration percentiles (p50/p95/p99) in trace statistics
- Context compression detection (shrinkage > 50%)
- `python -m agentguard` module entry point
- PEP 561 py.typed marker
- Span timing analysis (gaps, overlaps, utilization)
- Cost analysis (per-agent/tool token + USD breakdown)
- Retry pattern detection
- Span tags for custom filtering
- Token count + estimated cost fields
- Security scanning pipeline example
- Content creation pipeline example
- 10 examples covering 6 domains
- Full experimental field serialization roundtrip

### Changed
- Web viewer now consumes `analysis.py` (single source of truth)
- Handoffs in viewer only show analysis-confirmed handoffs
- README screenshots are actual viewer output (not prototypes)

### Fixed
- Distributed trace: child processes write separate files + merge + cleanup
- Guard: tool failures don't escalate as agent failures
- HTML XSS: all user-controlled fields escaped
- Viewer handoff: no longer shows unconfirmed handoffs

## [0.1.0] — 2026-04-11

### Core
- ExecutionTrace and Span data models with JSON serialization
- Span types: agent, tool, llm_call, handoff
- Parent-child span relationships (tree assembly)
- Handoff tracking fields: handoff_from, handoff_to, context_passed, context_size_bytes
- Failure tracking fields: caused_by, failure_handled

### SDK (6 integration styles)
- `@record_agent` / `@record_tool` sync decorators
- `@record_agent_async` / `@record_tool_async` async decorators
- `AgentTrace` / `ToolContext` sync context managers
- `AsyncAgentTrace` / `AsyncToolContext` async context managers
- `ManualTracer` explicit span API
- `wrap_agent()` / `wrap_tool()` / `patch_method()` middleware
- `inject_trace_context()` / `init_recorder_from_env()` for spawned processes
- `merge_child_traces()` with persist + cleanup
- `record_handoff()` explicit handoff recording
- `detect_context_loss()` handoff validation

### Analysis
- `analyze_failures()`: root cause identification, blast radius, resilience score
- `analyze_flow()`: handoff detection, critical path, parallel groups
- `analyze_bottleneck()`: agent rankings, bottleneck identification
- `analyze_context_flow()`: context loss/bloat detection across handoffs
- `diff_traces()`: side-by-side trace comparison

### Evaluation
- 8 built-in rule types: min_count, max_count, each_has, recency, no_duplicates, contains, regex, range
- EvaluationResult with Markdown report generation
- LLM pairwise evaluator (OpenAI-compatible API)

### Replay
- ReplayEngine: save baselines, compare candidates, run regression suites

### Guard
- Continuous monitoring with configurable check interval
- Alert handlers: stdout, file (JSONL), webhook
- Consecutive failure escalation (warning → critical)
- Agent-only failure tracking (tool failures don't escalate)

### Export
- JSON (native)
- JSONL (for log aggregation)
- OTel-compatible span format
- Trace statistics

### CLI (7 commands)
- `agentguard show` — display trace tree
- `agentguard list` — list traces
- `agentguard eval` — evaluate against rules
- `agentguard diff` — compare two traces
- `agentguard analyze` — failure propagation + bottleneck + flow + context
- `agentguard report` — generate HTML report
- `agentguard guard` — continuous monitoring

### Web
- Standalone HTML report with dark theme
- Diagnostic badges from analysis layer (single source of truth)
- Timeline bars, handoff indicators, failure propagation
- Prototype Gantt-style orchestration panel (docs/prototype.html)

### Documentation
- Architecture guide
- Quick start tutorial
- Examples catalog (6 examples including coding pipeline)
- Ralph Loop setup guide
- GUARDRAILS.md (project boundary protection)
- Contributing guide

### Tests
- 106 tests covering: trace schema, decorators, context managers, async,
  distributed, eval rules, replay, guard, analysis, diff, web, edge cases

## [Unreleased] — 2026-04-12

### Added — Deep Trace Semantics

#### Handoff Enhancements
- `mark_context_used()` — track which context keys the receiver actually used
- Context utilization ratio (0-1) measuring how much of passed context was consumed
- `context_received`, `context_used_keys`, `context_dropped_keys` fields on Span
- Handoff chain analysis (`analyze_handoff_chains`) — detect progressive context degradation

#### Failure Propagation (new module: `propagation.py`)
- `analyze_propagation()` — full causal chain analysis with circuit breaker detection
- `hypothetical_failure()` — what-if analysis for blast radius estimation
- `compute_context_integrity()` — overall trace health score combining utilization, loss, and resilience

#### Flow Graph (new module: `flowgraph.py`)
- `build_flow_graph()` — dependency DAG with true parallel/sequential detection
- Execution phase detection (groups of concurrent spans)
- Critical path via topological sort + longest path
- Mermaid diagram output (`graph.to_mermaid()`)
- Sequential fraction metric

#### Context Flow (new module: `context_flow.py`)
- `analyze_context_flow_deep()` — compression/truncation/expansion event detection
- Bandwidth analysis (bytes/second between agents)
- Context bottleneck detection
- Per-transition classification: stable, compression, truncation, expansion, transformation

#### Span Correlation (new module: `correlation.py`)
- `analyze_correlations()` — combined fingerprint + causal + pattern analysis
- `fingerprint_span()` — structural fingerprint for cross-trace pattern matching
- `correlate_failures_to_handoffs()` — causal links between handoffs and failures
- `detect_patterns()` — repeated failures, retry storms, slow agents

#### Enhanced Diff
- `diff_flow_graphs()` — compare parallelism, phases, critical path between traces
- `diff_context_flow()` — compare compression ratios, truncation events, bottlenecks

#### CLI
- `agentguard propagation <file>` — failure propagation report
- `agentguard flowgraph <file> [--mermaid]` — flow graph / Mermaid diagram
- `agentguard context-flow <file>` — context flow analysis

### Fixed
- `pyproject.toml` build-backend corrected to `setuptools.build_meta`
