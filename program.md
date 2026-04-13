# AgentGuard — Sprint 2

## Already Done (from Generator's previous commits)
- [x] Q1: span category classification (CPU/IO/waiting)
- [x] Q2: information retention ratio
- [x] architecture.md (110 lines)
- [x] OTel export/import bridge (export.py)

## Stories To Implement (NOT yet in codebase)

### P0: Core diagnostics depth
- [x] Q3: failure propagation causal chain — build root→intermediate→final chain with confidence scores per link
- [x] Q5: counterfactual decision analysis — compare actual outcome vs best alternative path

### P1: Viewer enhancements
- [x] Viewer comparison mode: render two traces side-by-side, highlight differences in timing/status/flow
- [x] Viewer tool drill-down: clicking an agent bottleneck expands to show individual tool timings

### P2: SDK
- [x] ProcessPoolExecutor trace propagation (like TracingExecutor but for multiprocessing)
- [x] Framework middleware: LangChain callback handler that auto-records agent/tool spans

### P3: Testing
- [S] Property-based test: hypothesis strategy for random traces, verify serialization roundtrip (SKIPPED: 3x REJECT)
- [S] Stress test: generate 1000-span trace, verify analyze_bottleneck/flow/failures complete in <5s (SKIPPED: 3x REJECT)

### P4: Docs
- [S] CONTRIBUTING.md enhancement: add architecture overview, PR review criteria (SKIPPED: 3x REJECT)
