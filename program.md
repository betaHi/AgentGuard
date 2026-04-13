# AgentGuard — Sprint 3: Production Depth

## Goals
1. Make every analysis module answer its Question with real diagnostic value
2. Ensure viewer, CLI, and examples all tell the same accurate story
3. Harden SDK for real-world adoption
4. Comprehensive test coverage for edge cases

## Design Docs (authoritative)
- GUARDRAILS.md — 5 Questions + 3 Lines
- docs/current-state-review-zh.md — known issues
- REVIEW.md — review criteria

## Current Stories

### P0: Analysis depth — make diagnostics genuinely useful
- [x] Q1: bottleneck report should rank agents by "own work time" excluding child spans, with percentage breakdown
- [x] Q2: handoff analyzer should detect dropped keys — compare context keys sent vs keys received
- [x] Q3: failure propagation report should include timeline visualization (ASCII) showing failure spread over time
- [S] Q4: cost-yield should identify the "most wasteful" agent (highest cost, lowest output quality) with actionable recommendation (SKIPPED: 3x REJECT)
- [x] Q5: decision analysis should detect "repeated bad decisions" — same agent chosen despite prior failures

### P1: Viewer ↔ Analysis full alignment
- [x] HTML viewer: diagnostics panel should render ALL analysis outputs (bottleneck, flow, failures, cost-yield, decisions) — verify no analysis result is missing from viewer
- [x] HTML viewer: add trace metadata header (task name, total duration, agent count, span count, overall status)
- [S] CLI: `agentguard analyze` should output structured JSON matching exactly what viewer renders (SKIPPED: 3x REJECT)

### P2: Examples tell real stories
- [x] Audit all 18 examples: run each, capture output, verify README/docs descriptions match actual output
- [x] Add example: debugging a real failure — trace shows agent B failed because agent A dropped context key "user_id"
- [x] Add example: performance optimization — trace shows parallel pipeline is 3x faster than sequential, with cost comparison

### P3: SDK real-world readiness
- [x] Add `@record_agent` decorator error handling: if recording fails, the decorated function should still work (fail-open)
- [x] Add trace size limits: warn if trace exceeds 10MB, truncate span metadata if needed
- [x] Add `agentguard.configure()` for global settings (output dir, max trace size, sampling rate)

### P4: Test edge cases
- [ ] Test: trace with 0 spans (empty trace through full pipeline)
- [ ] Test: trace with duplicate agent names (same agent called multiple times)
- [ ] Test: trace with circular handoffs (A→B→A)
- [ ] Test: Unicode agent names, emoji in metadata, very long strings
- [ ] Test: concurrent recording from multiple threads simultaneously

## Progress Log
- 2026-04-13: Sprint 3 started — focus on production depth, not feature breadth
