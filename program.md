# AgentGuard — Development Program

## Identity
- **Name:** AgentGuard
- **One-liner:** Multi-agent orchestration diagnostics.
- **Repo:** https://github.com/betaHi/AgentGuard
- **License:** MIT | **Language:** Python 3.11+

## The 5 Questions (success criteria)
1. Which agent is the performance bottleneck?
2. Which handoff lost critical information?
3. Which sub-agent's failure started propagating downstream?
4. Which execution path has the highest cost but worst yield?
5. Which orchestration decision caused downstream degradation?

## Design Rules
1. Zero external deps for core/ and sdk/
2. Trace depth > feature breadth
3. README/examples/analysis/viewer tell the same story

## Completed Stories
- [x] Deepen Q4: add cost-yield analysis with tests (analyze_cost_yield + 9 tests)
- [x] Trace replay with assertion (replay_v2.py + TraceReplay + mutate_trace)
- [x] Mermaid flow-graph (flowgraph.py + to_mermaid())
- [x] Guard watch mode (guard.py watch())
- [x] Error recovery example (retry, circuit breaker, graceful degradation)
- [x] Basic trace roundtrip test (write → read)
- [x] Thread context propagation (TraceThread + bind_current_trace_context)

## Current Stories (priority order per current-state-review)

### P0: Viewer ↔ Analysis semantic alignment (current-state-review §2.1)
- [ ] Viewer bottleneck sidebar: support tool-span bottlenecks, not just agent cards
- [ ] Viewer: verify every analysis finding is correctly rendered (no phantom handoffs)

### P1: SDK ergonomics for parallel (current-state-review §2.2)
- [ ] Add TracingExecutor (ThreadPoolExecutor wrapper that propagates trace context)
- [ ] Add async context propagation for asyncio.create_task

### P2: Docs/README consistency (current-state-review §2.3, §2.4)
- [ ] Merge getting-started.md + quickstart.md into one clear onboarding doc
- [ ] Create docs/api-reference.md with all public function signatures + examples
- [ ] Create docs/configuration.md — agentguard.json schema, CLI flags, env vars
- [ ] Audit README claims against actual stable implementation — remove overstatements

### P3: Deepen diagnostics
- [ ] Deepen Q5: refactor analyze_decisions to ≤50 lines with extracted helpers, revert progress.txt
- [ ] Handoff: detect context truncation (compare input size vs what arrived at next agent)
- [ ] Span duration anomaly detection: flag spans 3x slower than historical baseline
- [ ] Viewer: context flow waterfall chart (context size at each handoff as bar)

### P4: Integration & examples
- [ ] Integration test: full record → analyze → export_otel → import → compare roundtrip
- [ ] Add example: multi-model pipeline (GPT-4 + Claude + local model, cost comparison)
- [ ] Improve error_recovery example: add timeout pattern + partial result handling

## Progress Log

- 2026-04-12: Added threaded trace-context propagation helpers (threading.py)
- 2026-04-12: Ralph Loop v7 — production-grade with thorough review + self-improvement
- 2026-04-12: Q4 cost-yield: 9 tests added (718 total), ACCEPTED
- 2026-04-12: Q5 decisions: implemented but needs refactor (>50 line function), SKIPPED
- 2026-04-12: Audited all stories against existing codebase — reorganized by priority
