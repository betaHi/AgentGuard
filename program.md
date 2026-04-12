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

## Completed (Sprint 1)
- [x] All P0-P4 stories from previous sprint (19 stories)
- [x] 786 tests, 15K+ LOC, 18 examples, 11 docs

## Current Stories (Sprint 2: Production Hardening)

### P0: Deepen core diagnostics (current-state-review §2.1)
- [ ] Q1 deep: bottleneck analysis should distinguish CPU-bound vs IO-bound vs waiting — add span category classification
- [ ] Q2 deep: handoff analyzer should compute information retention ratio (bytes_out / bytes_in per handoff)
- [ ] Q3 deep: failure propagation should build a causal chain (root → intermediate → final) with confidence scores
- [ ] Q5 deep: decision tracker should compare "what happened" vs "what could have happened" (counterfactual analysis)

### P1: Viewer production-grade (current-state-review §2.1, §2.4)
- [ ] Viewer: add comparison mode — side-by-side two traces with diff highlighting
- [ ] Viewer: bottleneck panel should show tool-level drill-down (click agent → see tool breakdown)
- [ ] Viewer: add export to PDF/PNG for sharing diagnostics reports

### P2: SDK hardening (current-state-review §2.2)
- [ ] SDK: add automatic context propagation for concurrent.futures.ProcessPoolExecutor
- [ ] SDK: add OpenTelemetry bridge — import OTel spans into AgentGuard trace format
- [ ] SDK: add middleware for popular frameworks (LangChain, CrewAI, AutoGen)

### P3: Testing & reliability
- [ ] Add property-based tests (hypothesis) for trace serialization roundtrip
- [ ] Add stress test: 1000-span trace with deep nesting — verify analysis doesn't degrade
- [ ] Add fuzz test: random span attributes — verify no crashes in analysis/viewer

### P4: Documentation
- [ ] Write docs/architecture.md — system design, data model, analysis pipeline
- [ ] Update current-state-review-zh.md with Sprint 2 findings
- [ ] Add CONTRIBUTING.md with code standards, PR process, testing requirements

## Progress Log

- 2026-04-12: Sprint 1 complete — 19 stories, 786 tests
- 2026-04-12: Sprint 2 started — focus on production hardening, deeper diagnostics
