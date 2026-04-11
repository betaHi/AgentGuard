# AgentGuard — Development Program

> This file drives the Ralph Loop. The agent reads this, executes, evaluates, and iterates.
> Humans edit this file to steer direction. The agent edits code.

## Project Identity

- **Name:** AgentGuard
- **One-liner:** Record, Replay, Evaluate, and Guard your AI Agents.
- **Repo:** https://github.com/betaHi/AgentGuard
- **License:** MIT
- **Language:** Python 3.11+
- **Philosophy:** Zero external dependencies to start. `pip install agentguard` and go.

## Core Concepts

AgentGuard is NOT another Agent framework. It's engineering infrastructure for agents already in production.

Four verbs define the product:

1. **Record** — Capture multi-agent execution traces (who did what, when, with what result)
2. **Replay** — Re-run agents with fixed inputs to compare versions
3. **Evaluate** — Rule-based + LLM-based quality assessment of agent outputs
4. **Guard** — Continuous monitoring with automatic regression detection and alerts

## Architecture

```
agentguard/
├── core/           # Data models (trace, evaluation, regression schemas)
│   ├── trace.py    # Execution trace schema
│   ├── eval.py     # Evaluation result schema
│   └── config.py   # Agent configuration & versioning
├── sdk/            # Instrumentation SDK
│   ├── decorators.py   # @record_agent, @record_tool
│   ├── recorder.py     # Trace collection engine
│   └── context.py      # Multi-agent context propagation
├── eval/           # Evaluation engine
│   ├── rules.py    # Rule-based assertions
│   ├── llm.py      # LLM-based evaluation
│   └── compare.py  # Version comparison & diff
├── cli/            # Command-line interface
│   └── main.py     # CLI entry point
└── __init__.py
```

## Current Sprint

### Sprint 1: Foundation (NOW)
**Goal:** Core data models + basic SDK + CLI skeleton

- [ ] Define `ExecutionTrace` schema (trace.py)
- [ ] Define `EvaluationResult` schema (eval.py)  
- [ ] Define `AgentConfig` schema (config.py)
- [ ] Implement `@record_agent` decorator (decorators.py)
- [ ] Implement `@record_tool` decorator (decorators.py)
- [ ] Implement trace recorder with JSON output (recorder.py)
- [ ] Basic CLI: `agentguard record`, `agentguard show`
- [ ] Write tests for all above
- [ ] Write README.md

### Sprint 2: Evaluate
- [ ] Rule-based assertions (count, format, recency, duplicates)
- [ ] Agent config versioning
- [ ] `agentguard eval` command
- [ ] Comparison between two versions

### Sprint 3: Replay + Regression
- [ ] Fixed-input replay mechanism
- [ ] LLM evaluator (pairwise compare)
- [ ] Regression detection
- [ ] `agentguard replay`, `agentguard regression` commands

### Sprint 4: Guard + UI
- [ ] Continuous monitoring mode
- [ ] Alert mechanism
- [ ] Web UI for multi-agent timeline

## Development Rules

1. **Every change must have tests.** No untested code.
2. **Zero external dependencies for core.** Only stdlib for core/ and sdk/.
   - eval/llm.py may use httpx or similar for LLM API calls
   - cli/ may use click or typer
3. **Type hints everywhere.** This is a typed Python project.
4. **Docstrings on all public APIs.**
5. **Keep it simple.** If a feature can wait, it waits.

## Completion Criteria for Sprint 1

The sprint is COMPLETE when:
- [ ] All schemas defined with type hints and docstrings
- [ ] @record_agent captures: agent_id, start/end time, status, spans
- [ ] @record_tool captures: tool name, input, output, duration, errors
- [ ] Multi-agent traces correctly nest (parent_span_id linkage)
- [ ] Traces serialize to JSON and can be loaded back
- [ ] CLI `agentguard show <trace_file>` renders a readable trace
- [ ] All tests pass
- [ ] README.md explains what AgentGuard is and how to use it

## Progress Log

<!-- Agent appends progress here after each iteration -->

### 2026-04-11 — Project initialized
- Created repo structure
- Wrote program.md
- Starting Sprint 1

### 2026-04-11 — Sprint 1 Complete ✅
- Core trace schema: ExecutionTrace, Span (agent/tool/llm_call/handoff)
- SDK decorators: @record_agent, @record_tool with automatic nesting
- TraceRecorder: thread-safe, parent-child context propagation
- CLI: `agentguard show` with colored tree view, `agentguard list`
- Demo: multi-agent workflow (orchestrator → news collector → tech analyst)
- Demo: failure detection with error propagation visualization
- Tests: 11/11 passing
- README: with demo output screenshots
- Zero external dependencies for core
