# Changelog

All notable changes to AgentGuard are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

## [0.1.0] — Real-session hardening & release prep (2026-04-22)

### Added
- **Claude session import: subagent naming**. `Task` tool dispatches now surface the real `subagent_type` (e.g. `Task(general-purpose)`) instead of collapsing into an opaque `tool:Agent` label, so the bottleneck and critical-path outputs point at something actionable on real multi-agent runs.
- **Cost roll-up for subtree-attached spend**. When Claude (or any runtime) attaches cost/tokens to leaf LLM / tool spans instead of to the orchestrating agent, per-agent `CostYieldEntry` now rolls up subtree cost and tokens. Previously every per-agent entry collapsed to `$0.0000` on a real 6458-span session while the total was still correct.
- **Leaf-agent preference in cost-yield summaries**. `highest_cost_agent` / `most_wasteful_agent` now prefer agents with no agent descendants, so reporting stops defaulting to the root container (tautological).
- **End-to-end regression fixture** (`tests/test_real_session_e2e.py`). Builds a structurally-complete Claude JSONL session (user → Task tool_use → tool_result → final assistant) and locks in cost roll-up, Task naming, and bottleneck labeling.
- **Claude SDK version range validation**. Doctor check + error messages pin a supported range (`>=0.1.0,<0.2.0`).
- **Pricing table freshness** with a built-in `_BUILTIN_PRICING_DATE` surfaced by the cost-yield panel and doctor check (warns at 365d).
- **Critical-key decision provenance** (`ContextFlowPoint.critical_key_source`: `explicit` / `learned` / `heuristic`) — rendered in the viewer as "why flagged".
- **Doctor plugin-presence check** and a CLI-contract test that parses `bin/agentguard …` invocations out of plugin skill docs.
- **SECURITY.md privacy section**: no network, no telemetry, input/output paths, sharing guidance, pricing-override mechanism. Linked from README.
- **P2.10 importer error messages audit** — every `_call_sdk_helper` failure now includes the helper name, the failed directory, a pip-install hint, and a fork-mismatch warning.

### Changed
- **Failure attribution walks DOWN** the causal chain to the deepest failed span (tool-first), not UP to the first failed-with-non-failed-parent span. This flips Q3 from "something under X failed" to "X failed and propagated".
- **`analyze_cost_yield` total-cost** now sums direct span cost (or leaf entries when a custom `cost_fn` is supplied) so roll-up never double-counts.
- **Empty-panel messaging** in the CLI diagnose output — failures / handoffs / decisions panels each print a one-line all-clear on healthy sessions instead of going silent.
- **Cost recommendations** no longer emit tautological "costs $X/success — consider batching" advice for whole-session container agents. Generic cost-per-success advice is restricted to leaf agents.
- Extra `[claude]` pinned to `claude-agent-sdk>=0.1.0,<0.2.0` (real PyPI range).

### Fixed
- `diagnose-claude-session` on real Claude sessions no longer reports `$0.0000` for every per-agent entry while the total is `$401.17`.
- Cost roll-up preserves explicit per-agent cost when present and does not descend into nested agents (no double count).
- Parallel siblings no longer produce false truncation reports in `context_flow_deep`.
- `test_no_zero_spans` no longer false-matches "0 spans" inside "10 spans".

### Previously added during the same release window
- `bottleneck_agent` field in `BottleneckReport` — maps tool bottleneck to parent agent (Q1)
- `_are_parallel()` helper — filters false truncation for parallel siblings (Q2)
- SDK noise key filtering (`args`/`kwargs`) in context flow analysis (Q2)
- `py.typed` marker with package-data for PEP 561 support
- `__version__` reads from `importlib.metadata` with fallback
- Pre-commit config with ruff check + format hooks
- Return type hints on all 518 public functions
- Docstrings with Args/Returns on all public APIs in `analysis.py`, `sdk/`, `core/`
- pyproject.toml classifier Alpha → Beta
- Refactored 15+ functions to ≤50 lines

## [0.0.x] — Sprint 1–6

### Added — Sprint 1: Foundation
- Core trace model: `ExecutionTrace`, `Span`, `SpanType`, `SpanStatus`
- CLI trace viewer with tree display
- SDK decorators: `@record_agent`, `@record_tool`
- JSON trace serialization

### Added — Sprint 2: Evaluation
- Rule-based evaluation engine (8 rule types)
- `agentguard eval` CLI command
- Duration, error rate, and custom rule support

### Added — Sprint 3: Replay & Regression
- Replay engine with golden trace comparison
- Context manager API for manual instrumentation
- Assertion-based replay results

### Added — Sprint 4: Guard & Web UI
- Continuous monitoring (`agentguard guard`)
- Web viewer with Gantt timeline, sidebar, diagnostics grid
- Auto-learning from trace patterns

### Added — Sprint 5: Deep Analysis
- Failure propagation analysis (Q3) — causal chains, circuit breakers
- Flow graph with critical path detection (Q1/Q5)
- Context flow analysis — loss/bloat/mutation detection (Q2)
- Bottleneck analysis with own-duration ranking (Q1)
- Handoff as first-class primitive with context tracking
- Cost/yield analysis (Q4)
- Decision quality analysis (Q5)
- OTel export/import, JSONL export, trace statistics

### Added — Sprint 6: Evolution & Polish
- Self-reflection + learning engine (`evolve`)
- Trend detection across trace history
- TraceBuilder fluent API
- Span correlation and pattern detection
- 20+ CLI commands, 20+ examples
- Trace diff, search, aggregate, SLA checks
- HTML report generation
- 1330+ tests, zero external dependencies for core
