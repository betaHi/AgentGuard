# Changelog

All notable changes to AgentGuard are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Added
- `bottleneck_agent` field in BottleneckReport — maps tool bottleneck to parent agent (Q1)
- `_are_parallel()` helper — filters false truncation for parallel siblings (Q2)
- SDK noise key filtering (`args`/`kwargs`) in context flow analysis (Q2)
- `py.typed` marker with package-data for PEP 561 support
- `__version__` reads from `importlib.metadata` with fallback
- Pre-commit config with ruff check + format hooks
- GitHub Actions: `actions/checkout@v5`, `fail-fast: false`, ruff format step

### Changed
- Refactored 15+ functions to ≤50 lines: `build_flow_graph`, `analyze_propagation`, `score_trace`, `export_otel`, `suggest_optimizations`, `normalize_trace`, `build_dependency_graph`, `detect_patterns`, `import_otel`, `compare_golden`, `reflect`, `diff_traces`, `generate_trace`, CLI `main()`
- Return type hints on all 518 public functions
- Docstrings with Args/Returns on all public APIs in `analysis.py`, `sdk/`, `core/`
- pyproject.toml classifier Alpha → Beta
- `full_analysis.py` example enriched with failure diversity (correlations + patterns now visible)

### Fixed
- Parallel siblings no longer produce false truncation reports in `context_flow_deep`
- `test_no_zero_spans` no longer false-matches "0 spans" inside "10 spans"

## [0.1.0] — Sprint 1–6

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
