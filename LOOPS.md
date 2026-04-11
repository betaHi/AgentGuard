# AgentGuard — Multi-Loop Development Architecture

> Solving single-loop context exhaustion + enabling parallel development

## Problem

A single Ralph Loop has three bottlenecks:
1. **Limited context window** — one session cannot hold the entire project
2. **Serial inefficiency** — SDK and Eval can be developed in parallel
3. **Knowledge loss** — next session doesn't know what the previous one did

## Solution: Multi-Loop + Handoff Protocol

### Architecture

```
program.md (human-edited — overall direction)
    │
    ├── Loop-1: SDK Loop ──────── sdk-progress.md
    ├── Loop-2: Eval Loop ─────── eval-progress.md
    ├── Loop-3: CLI Loop ──────── cli-progress.md
    └── Loop-4: Docs Loop ─────── docs-progress.md
    
    Each Loop:
    ┌──────────────────────────────────────────┐
    │  1. Read program.md (direction)           │
    │  2. Read {module}-progress.md (status)    │
    │  3. Read relevant code files              │
    │  4. Execute one sprint                    │
    │  5. Run tests                             │
    │  6. Update {module}-progress.md           │
    │  7. Check context budget                  │
    │     - Sufficient → continue next round    │
    │     - Tight → write handoff → new session │
    └──────────────────────────────────────────┘
```

### Context Management Strategies

#### Strategy 1: Scoped Context
Each Loop only loads files it needs:

```
SDK Loop needs:
  - program.md (direction)
  - sdk-progress.md (progress)
  - agentguard/core/*.py
  - agentguard/sdk/*.py
  - tests/test_trace.py, tests/test_decorators.py

Eval Loop needs:
  - program.md
  - eval-progress.md
  - agentguard/core/trace.py (read-only)
  - agentguard/eval/*.py
  - tests/test_eval.py
```

#### Strategy 2: Handoff Protocol
When context is nearly full, the Loop writes a handoff file for the next session:

```markdown
# Handoff: SDK Loop Session 3 → Session 4

## Completed
- @record_agent and @record_tool implemented and tested
- TraceRecorder supports multi-threading
- JSON serialization/deserialization passing

## Remaining
- [ ] Context propagation across async calls
- [ ] Trace export to OTel format

## Current State
- Tests: 15/15 passing
- No known bugs

## Next Steps
1. Implement async decorator variants
2. Add OTel exporter

## Key Design Decisions (DO NOT CHANGE)
- Spans stored as flat list + parent_span_id, not nested
- trace_id = uuid4()[:16]
```

#### Strategy 3: Progress Files
Each module has a persistent progress file — the "memory" between Loops:

```
.loops/
├── sdk-progress.md
├── eval-progress.md
├── cli-progress.md
├── docs-progress.md
└── handoffs/
    ├── sdk-session-3-to-4.md
    └── eval-session-1-to-2.md
```

#### Strategy 4: Context Budget Check
Estimate context usage at the start of each Loop:

```
Rule of thumb:
- Each .py file ≈ 100-300 tokens
- program.md ≈ 500 tokens
- progress.md ≈ 200 tokens
- Test output ≈ 200 tokens

If a Loop operates on 5 .py files:
  5 × 200 + 500 + 200 + 200 = ~2000 tokens input
  After 3-5 conversation turns, consider handing off
```

### Parallel Loop Definitions

#### Loop 1: SDK Loop
```
Scope: agentguard/core/ + agentguard/sdk/
Input: program.md, sdk-progress.md
Output: code + tests + sdk-progress.md
Sprint cycle: 1-2 features
```

#### Loop 2: Eval Loop
```
Scope: agentguard/eval/
Input: program.md, eval-progress.md, core/trace.py (read-only)
Output: code + tests + eval-progress.md
Depends on: SDK Loop completing core schemas
Sprint cycle: 1 evaluator
```

#### Loop 3: CLI Loop
```
Scope: agentguard/cli/
Input: program.md, cli-progress.md, core/ + sdk/ + eval/ (read-only)
Output: CLI code + cli-progress.md
Depends on: SDK Loop + Eval Loop
Sprint cycle: 1-2 commands
```

#### Loop 4: Docs Loop
```
Scope: README.md, docs/, examples/
Input: program.md, docs-progress.md, all code (read-only)
Output: docs + examples + docs-progress.md
Independent — can run anytime
```

### Cross-Loop Communication Rules

1. **File-only communication** — no shared memory, no shared context
2. **progress.md is the single source of state** — each Loop writes its own, reads others'
3. **Code is shared output** — code written by one Loop can be read by another
4. **No cross-boundary edits** — SDK Loop doesn't modify eval/ code, and vice versa
5. **Decouple via interfaces** — Eval Loop depends on core/trace.py schema, not SDK implementation

### Dogfooding

AgentGuard's multi-loop development process is itself a multi-agent collaboration scenario.

We can use AgentGuard to record and observe its own development Loops:
- Loop 1 = Agent "SDK-Dev"
- Loop 2 = Agent "Eval-Dev"  
- Their execution, handoffs, and dependencies can be traced with AgentGuard itself.

**Using the tool you're building to observe the process of building that tool.** Meta-dogfooding.

---

_This architecture is a living document. Update as we learn._
