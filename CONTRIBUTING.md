# Contributing to AgentGuard

Thanks for considering contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/betaHi/AgentGuard.git
cd AgentGuard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

All tests must pass before submitting a PR.

## Architecture Overview

AgentGuard has four layers, each with strict dependency rules:

```
┌─────────────────────────────────────────────────┐
│  CLI / Web Viewer / Examples                    │  ← User-facing
├─────────────────────────────────────────────────┤
│  Analysis Layer                                 │  ← Diagnostics
│  analysis.py  propagation.py  scoring.py        │
│  ascii_viz.py  eval/                            │
├─────────────────────────────────────────────────┤
│  SDK Layer                                      │  ← Instrumentation
│  sdk/recorder.py  sdk/context.py                │
│  sdk/decorators.py  integrations/               │
├─────────────────────────────────────────────────┤
│  Core Layer                                     │  ← Data models
│  core/trace.py  core/eval_schema.py             │
│  export.py  importer.py  builder.py             │
└─────────────────────────────────────────────────┘
```

**Dependency rules:**
- **Core** → zero external dependencies, pure dataclasses
- **SDK** → depends on Core only, zero external deps
- **Analysis** → depends on Core, may import SDK for recorder access
- **Integrations** → may use optional external deps (langchain, etc.), lazy imports only
- **CLI/Web/Examples** → may use anything

### Data Flow

```
User code → @record_agent/@record_tool decorators → TraceRecorder → ExecutionTrace
    → Analysis modules (bottleneck, flow, failures, cost-yield, decisions, propagation)
    → Reports (ASCII, HTML, OTel export)
```

### The 5 Questions

Every feature must serve at least one of these (from `GUARDRAILS.md`):

| Q# | Question | Primary Module |
|----|----------|----------------|
| Q1 | Which agent is the performance bottleneck? | `analyze_bottleneck()` |
| Q2 | Which handoff lost critical information? | `analyze_flow()`, `analyze_context_flow()` |
| Q3 | Which sub-agent's failure started propagating? | `analyze_failures()`, `analyze_propagation()` |
| Q4 | Which path has highest cost but worst yield? | `analyze_cost_yield()` |
| Q5 | Which orchestration decision caused degradation? | `analyze_decisions()`, `analyze_counterfactual()` |

## Code Standards

- **Language:** Python 3.11+ with type hints on all public APIs
- **Docstrings:** Required on all public classes and functions — explain WHY, not just WHAT
- **Comments/code:** All in English
- **Dependencies:** Zero external deps for `agentguard/core/` and `agentguard/sdk/`
- **Function length:** ≤ 50 lines (extract helpers if needed)
- **Quality bar:** Production-grade, not demo quality
- **Determinism:** Examples must use fixed seeds (`random.seed(42)`)

## PR Review Criteria

PRs are evaluated on these dimensions (in priority order):

### 1. Correctness
- Does the code do what it claims?
- Are edge cases handled (empty traces, zero durations, missing data)?
- Do all existing tests still pass?

### 2. GUARDRAILS Alignment
- Which Q# (Q1-Q5) does this serve? Must be stated in PR description.
- If "infra/docs", explain why it's necessary.
- Changes that don't serve any Q# or infrastructure need will be rejected.

### 3. Test Coverage
- Every new function needs tests.
- Tests must cover: happy path, edge cases, error conditions.
- Property-based tests (`hypothesis`) encouraged for serialization/roundtrip.
- Performance-sensitive code needs benchmark tests (e.g., <5s for 1000 spans).

### 4. Code Quality
- Functions ≤ 50 lines — no exceptions.
- Type hints on all public APIs.
- Docstrings explaining WHY the code exists, not just what it does.
- No `# type: ignore` without a comment explaining why.

### 5. Dependency Discipline
- Core/SDK: absolutely zero external deps.
- Integrations: lazy imports only, clear error messages if missing.
- Tests: external test deps (hypothesis, etc.) must use `pytest.importorskip()`.

### 6. Design Document Consistency
- Code must not contradict `GUARDRAILS.md` or `docs/current-state-review-zh.md`.
- If a design change is needed, update the docs in the same PR.

## Common Rejection Reasons

- ❌ No tests for new functionality
- ❌ Functions exceeding 50 lines
- ❌ Missing type hints or docstrings
- ❌ External dependency added to core/sdk
- ❌ PR description doesn't state which Q# it serves
- ❌ Overstatements in docs ("blazing fast", "production-ready" without evidence)
- ❌ Demo-quality code (no error handling, no edge cases)

## Project Structure

```
agentguard/
├── core/           # Data models (zero deps, pure dataclasses)
│   ├── trace.py    # ExecutionTrace, Span, SpanType, SpanStatus
│   └── eval_schema.py  # EvaluationResult, RuleResult
├── sdk/            # Instrumentation (decorators, context, threading, async)
│   ├── recorder.py # TraceRecorder — span stack, context capture
│   ├── context.py  # TracingExecutor, TracingProcessExecutor, traced_task
│   └── decorators.py  # @record_agent, @record_tool, @record_handoff
├── integrations/   # Framework adapters (optional deps)
│   └── langchain.py  # LangChain callback handler
├── eval/           # Evaluation engine
│   ├── engine.py   # Rule evaluation
│   └── compare.py  # Version comparison, regression detection
├── analysis.py     # All diagnostic analysis functions
├── propagation.py  # Failure propagation, causal chains
├── scoring.py      # Trace scoring (0-100)
├── ascii_viz.py    # Terminal visualizations (gantt, comparison, drill-down)
├── export.py       # OTel export
├── importer.py     # OTel import
├── builder.py      # TraceBuilder for test fixtures
├── guard.py        # Continuous monitoring
├── replay.py       # Trace replay with assertions
├── web/            # HTML report generator
└── cli/            # Command-line interface
tests/              # All tests (pytest)
examples/           # Runnable examples with deterministic output
docs/               # Design documents and reviews
```

## PR Checklist

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] New functions have tests (happy path + edge cases)
- [ ] Type hints on all public APIs
- [ ] Docstrings on public functions (explain WHY)
- [ ] Functions ≤ 50 lines
- [ ] No external deps added to core/sdk
- [ ] PR description states which GUARDRAILS Q# (Q1-Q5) this serves
- [ ] No overstatements in docs/comments
- [ ] Examples are deterministic (fixed seeds)
- [ ] Design docs consulted and consistent

## License

By contributing, you agree that your contributions will be licensed under MIT.


## Updating Screenshots

README screenshots are generated from live HTML reports and CLI output.

    # Install dependencies (one-time)
    pip install playwright
    playwright install chromium

    # Regenerate all 8 screenshots
    python scripts/generate_screenshots.py

Output goes to docs/screenshots/. The script generates HTML report
screenshots via Playwright and CLI output captures as text files
(convert to PNG with termshot or carbon-now-cli).
