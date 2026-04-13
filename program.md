# AgentGuard — Sprint 6: Production Hardening & Deep Quality

## Current Stories

### Phase 1: CI & Code Quality (fix the broken build first)

- [x] Fix: ruff lint — done manually by planner (3066 errors fixed, all checks passed)
- [x] Fix: ruff remaining manual fixes — done with autofix pass (all resolved)
- [x] Fix: consolidate 3 redundant example test files (test_examples_smoke.py, test_examples_no_misleading.py, test_examples_integration.py) into one test_examples.py with parametrized checks. Currently running all examples 3x (~3min wasted). Single file, all 4 check types (exit code, output, no traceback, no import error)
- [x] Fix: remove duplicate modules — merge export_v2.py into export.py (keep best of both), merge replay_v2.py into replay.py (keep best of both). Update all imports. Remove _v2 files. No functionality loss

### Phase 2: Code Architecture (>50-line function refactoring)

- [x] Refactor: analysis.py — break analyze_failures (103 lines) into helpers: _find_root_causes(), _compute_blast_radius(), _compute_resilience(). Each ≤50 lines
- [x] Refactor: analysis.py — break analyze_flow (100 lines) into helpers: _extract_handoffs(), _compute_flow_metrics(). Each ≤50 lines
- [x] Refactor: analysis.py — break analyze_bottleneck (86 lines) into helpers: _find_critical_path(), _rank_bottlenecks(). Each ≤50 lines
- [x] Refactor: analysis.py — break analyze_context_flow (110 lines) into helpers: _trace_context_points(), _detect_anomalies(). Each ≤50 lines
- [x] Refactor: analysis.py — break analyze_cost_yield (90 lines) into helpers: _compute_agent_costs(), _compute_yield_scores(), _generate_recommendations(). Each ≤50 lines
- [x] Refactor: viewer.py — break _build_full_html (229 lines) into ≤50-line helpers: _build_head(), _build_styles(), _build_scripts(), _build_body_layout(). Extract CSS/JS into separate string constants
- [x] Refactor: viewer.py — break _build_diagnostics (159 lines) into per-panel helpers: _panel_failures(), _panel_bottleneck(), _panel_handoffs(), _panel_context(), _panel_cost(), _panel_retries(), _panel_errors(), _panel_decisions(), _panel_propagation(). Each ≤50 lines
- [x] Refactor: viewer.py — break _build_sidebar (93 lines) and _build_gantt (91 lines) and _render_gantt_rows (81 lines) into ≤50-line helpers each
- [x] Refactor: flowgraph.py — break build_flow_graph (207 lines!) into helpers: _extract_nodes(), _extract_edges(), _detect_phases(), _find_critical_path(), _build_mermaid(). Each ≤50 lines
- [x] Refactor: propagation.py — break analyze_propagation (123 lines) and analyze_handoff_chains (99 lines) into ≤50-line helpers
- [x] Refactor: scoring.py — break score_trace (156 lines) into per-dimension helpers: _score_performance(), _score_reliability(), _score_handoff_quality(), _score_cost_efficiency(), _score_decision_quality(). Each ≤50 lines
- [x] Refactor: context_flow.py — break analyze_context_flow_deep (153 lines) into helpers: _build_snapshots(), _detect_transitions(), _compute_bandwidth(). Each ≤50 lines. Also fix false positive: parallel agents should NOT report truncation between independent siblings (currently parallel_pipeline.py output still shows false truncation from this module even though analysis.py is fixed)
- [x] Refactor: cli/main.py — break main() (168 lines) into subcommand dispatch table + per-command small functions. Extract common patterns (load trace, print error) into helpers
- [x] Refactor: remaining >60-line functions — normalize.py normalize_trace(100), optimize.py suggest_optimizations(113), dependency.py build_dependency_graph(96), correlation.py detect_patterns(92), evolve.py reflect(82), diff.py diff_traces(81)+diff_flow_graphs(69), export.py export_otel(127), generate.py generate_trace(81), guard.py check_new_traces(79), importer.py import_otel(90), ab_test.py ab_test(79), aggregate.py aggregate_traces(80), budget.py analyze_budget(72), comparison.py compare_traces(72), replay_v2.py compare_golden(99), sdk/handoff.py record_handoff(74)+mark_context_used(64)+record_decision(82), timeline.py build_timeline(81), search.py search_traces(70), schema.py validate_trace_dict(67), markdown.py trace_to_markdown(67), metrics.py extract_metrics(62)

### Phase 3: Type Hints & Docstrings (production quality)

- [x] Fix: add return type hints to all 35 public CLI functions (cmd_show, cmd_list, cmd_eval etc.) — all should return None or int
- [ ] Fix: add return type hints to remaining 15 public functions without them (outside CLI)
- [ ] Audit: verify all public API functions have docstrings with Args/Returns sections. Add missing ones. Focus on agentguard/analysis.py, agentguard/sdk/, agentguard/core/

### Phase 4: Semantic Issues (from review)

- [ ] Fix: parallel_pipeline.py console output still shows false truncation from context_flow_deep — the deep module reports "web_researcher → academic_researcher: -85% truncation" for independent parallel agents. Fix analyze_context_flow_deep to detect parallel siblings (same parent, overlapping timestamps) and exclude them from sequential analysis
- [ ] Fix: viewer bottleneck sidebar shows agent cards but analyze_bottleneck returns tool spans — semantic mismatch between viewer and analysis. Viewer should map tool bottleneck back to parent agent, or show both agent and tool level
- [ ] Fix: context_flow_deep "Keys removed/added" reports args/kwargs for every transition — this is SDK noise (decorator argument passing), not real context loss. Filter out args/kwargs from transition analysis
- [ ] Fix: full_analysis.py shows "Correlations: 0, Patterns: 0" on every run — correlation analysis should find patterns in a complex trace with 10+ spans, mixed failures, and different agent types. If single-trace correlation is inherently limited, improve the algorithm or show a better example
- [ ] Fix: README claims "1170+ tests" but actual count is 1374 (collected) — update README test count. Also verify all feature claims in README match reality by running each example and checking

### Phase 5: Production Hardening

- [ ] Add: pyproject.toml — add proper entry points, classifiers update to "4 - Beta", add project.urls for Documentation
- [ ] Add: py.typed marker file for PEP 561 type checking support
- [ ] Add: __version__ attribute in agentguard/__init__.py that reads from pyproject.toml
- [ ] Fix: GitHub Actions — update to actions/checkout@v5 and actions/setup-python@v5 with FORCE_JAVASCRIPT_ACTIONS_TO_NODE24=true to fix Node.js deprecation warnings. Add matrix fail-fast: false so all Python versions run even if one fails. Add ruff format check
- [ ] Add: pre-commit config (.pre-commit-config.yaml) with ruff check + ruff format hooks
- [ ] Add: CHANGELOG.md — proper Keep a Changelog format documenting Sprint 1-6 changes
- [ ] Fix: .agentguard/ traces directory cleanup — examples accumulate traces on disk. Add max_traces option to TraceStore.save() and auto-prune old traces (keep last 100)

### Phase 6: Deep Analysis Improvements (GUARDRAILS Q1-Q5)

- [ ] Q1 improve: bottleneck analysis should distinguish between "agent is slow because its LLM call is slow" vs "agent is slow because it's waiting for a dependency" — add wait_time vs work_time breakdown per agent span
- [ ] Q2 improve: handoff analysis should track not just bytes but semantic richness — count unique information units (distinct facts/entities) rather than just key counts. Use a heuristic: count unique leaf values in the output dict
- [ ] Q3 improve: failure propagation should detect retry storms — when an agent retries 3+ times and each retry triggers downstream work, flag as "retry storm" with total wasted cost
- [ ] Q4 improve: cost-yield analysis should support custom cost models — allow users to pass a cost_fn(span) -> float function instead of only reading span.estimated_cost_usd. Document with example
- [ ] Q5 improve: counterfactual analysis — when a coordinator chose agent A over agent B, and A failed, compute "if B had been chosen instead" based on B's historical success rate from previous traces

### Phase 7: Testing Depth

- [ ] Test: add edge case tests for empty traces, traces with 1 span, traces with 1000 spans, traces with circular parent references, traces with orphan spans (parent_span_id points to nonexistent span)
- [ ] Test: add concurrency stress test — 50 threads each recording a separate trace simultaneously, verify no data corruption or cross-trace leaks
- [ ] Test: add serialization roundtrip property test (fix the hypothesis import issue from Sprint 5 — use pytest.importorskip). Generate random traces with hypothesis, verify from_dict(to_dict(trace)) == trace
- [ ] Test: add CLI integration test — run every CLI command against a real trace file and verify exit code 0 + output contains expected keywords
- [ ] Test: add viewer HTML validation — generate report, check valid HTML structure, all panels present, no broken references
- [ ] Test: add cross-version compatibility test — create a trace with v0.1.0 schema, verify it loads correctly. Test forward/backward compat

### Phase 8: Examples & Documentation

- [ ] New example: multi-hop RAG pipeline — retriever → reranker → generator → fact-checker → synthesizer, demonstrating context degradation across 5 hops (realistic RAG-with-verification scenario)
- [ ] New example: auto-recovery pipeline — agents that detect their own failures and retry with different strategies (exponential backoff, different model, simplified prompt), demonstrating retry analysis
- [ ] New example: human-in-the-loop — pipeline that pauses for human approval at a gate agent, demonstrating long-duration traces and decision analysis
- [ ] Improve: all existing examples should print their GUARDRAILS Q# alignment (which of the 5 questions this example demonstrates)
- [ ] Docs: add troubleshooting.md — common issues (trace too large, circular dependencies, missing handoffs, viewer not showing data)
- [ ] Docs: update architecture.md to reflect actual module layout (current doc doesn't match — modules are flat in agentguard/, not in subdirectories like analysis/ or extensions/)

### Phase 9: Advanced Features (deep work)

- [ ] Feature: trace diffing with alignment — when comparing two traces of the same pipeline, align spans by name+type (not just position), compute per-span deltas (duration change, status change, cost change), visualize as a colored diff tree
- [ ] Feature: trace replay simulator — given a recorded trace, simulate re-execution with injected failures (e.g., "what if tool X failed?") and predict how the pipeline would behave differently. Use existing failure propagation logic to simulate cascade
- [ ] Feature: pipeline health dashboard data API — aggregate traces over time windows (1h, 24h, 7d), compute trend lines for: total duration, failure rate, cost, bottleneck stability. Return structured data for external dashboards (Grafana JSON API compatible)
- [ ] Feature: span tagging taxonomy — define a standard set of span tags (category, tier, criticality, retry_policy) with validation. Use these tags in analysis to provide more nuanced bottleneck and cost recommendations
- [ ] Feature: trace sampling strategies — implement 3 sampling modes: (1) always (default), (2) rate-based (1-in-N), (3) error-only (only record if any span fails). Configurable via TraceRecorder constructor
- [ ] Feature: trace anonymization — strip all output_data/input_data content but keep structure (key names, sizes, types). For sharing traces without leaking business data. Add CLI command `agentguard anonymize <trace.json>`
- [ ] Feature: OTel import improvements — import from OTel JSON files and reconstruct AgentGuard traces. Map OTel span kinds to AgentGuard SpanTypes. Handle nested spans correctly. Add test with real OTel export data
- [ ] Feature: Markdown report generator — `agentguard report --format markdown` generates a Markdown file instead of HTML. Useful for pasting into GitHub issues/PRs. Include all 9 diagnostic sections
- [ ] Feature: trace compression — implement a compact binary format for traces (msgpack-style) that's 5-10x smaller than JSON. Add `agentguard export --format compact` and `agentguard import --format compact`
- [ ] Feature: plugin system — allow users to register custom analysis functions via entry_points. Plugin receives a trace, returns a diagnostic dict. Viewer renders plugin diagnostics in a "Custom" panel

### Phase 10: Viewer Upgrades (make it production-worthy)

- [ ] Viewer: add collapsible panels — each diagnostic panel should be collapsible/expandable. Default: failures + bottleneck expanded, others collapsed. Save state in localStorage
- [ ] Viewer: add span detail popup — clicking a span in the Gantt chart opens a detail popup showing: all span fields, input/output data (truncated), parent chain, child spans, timing breakdown
- [ ] Viewer: add keyboard navigation — arrow keys to navigate spans, Enter to expand detail, Escape to close, / to focus search. Accessible focus indicators
- [ ] Viewer: add trace comparison mode — side-by-side view of two traces. Aligned by span name. Color-coded deltas (green=faster, red=slower). Toggle between overlay and split view
- [ ] Viewer: add export options — "Copy as Markdown" button, "Download JSON" button, "Share URL" (base64-encoded trace in URL hash for small traces)
- [ ] Viewer: add dark/light theme toggle — currently dark only. Add a toggle that saves preference in localStorage. Light theme should be readable and professional
- [ ] Viewer: responsive design — viewer should work on mobile/tablet screens. Sidebar collapses to hamburger menu. Gantt chart scrolls horizontally. Diagnostics stack vertically
- [ ] Viewer: add real-time mode — if pointed at a traces directory, auto-refresh when new traces appear. WebSocket-free polling approach (check mtime every 5s)
