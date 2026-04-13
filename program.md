# AgentGuard — Sprint 4: Polish & Depth

## Current Stories

### P0: Deepen the 5 Questions further
- [x] Q1: bottleneck should detect "false bottleneck" — agent that appears slow but is actually waiting on a dependency
- [x] Q2: handoff should track context transformation — not just keys sent/received but semantic changes (summarization, filtering)
- [x] Q3: failure propagation should distinguish recoverable vs fatal failures in the causal chain
- [x] Q4: cost-yield should support custom cost models (not just token count) — allow user-defined cost functions
- [x] Q5: decision analysis should suggest optimal agent selection based on historical performance

### P1: Viewer & CLI polish
- [x] Viewer: add collapsible sections in diagnostics panel (expand/collapse each analysis)
- [x] Viewer: add trace search/filter — find spans by agent name, status, or duration range
- [x] CLI: add `agentguard diff trace1.json trace2.json` — compare two traces with colored output
- [x] CLI: add `agentguard summary` — one-line summary of trace health (like git status)

### P2: SDK production hardening
- [x] SDK: add sampling — record only N% of traces in production (configurable)
- [x] SDK: add span annotations — user can attach arbitrary key-value metadata to spans
- [x] SDK: add trace correlation ID — link related traces across service boundaries
- [x] SDK: add batch export — accumulate spans and flush periodically (reduce I/O)

### P3: Advanced testing
- [x] Test: replay a trace, mutate one agent's timing, verify analysis changes correctly
- [x] Test: generate adversarial traces (contradictory timestamps, missing parents) — verify graceful handling
- [x] Test: verify all CLI commands work end-to-end with real trace files
- [x] Test: verify HTML viewer renders correctly with 50+ agent traces

### P4: Documentation & best practices
- [x] Update docs/best-practices.md with Sprint 3 lessons
- [x] Create docs/faq.md — common questions and troubleshooting
- [x] Update README with Sprint 3 features (1000+ tests, new analysis capabilities)
