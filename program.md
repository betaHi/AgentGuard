# AgentGuard — Development Program

> This file drives the Ralph Loop. The agent reads this, executes, evaluates, and iterates.
> Humans edit this file to steer direction. The agent edits code.

## Project Identity

- **Name:** AgentGuard
- **One-liner:** Record, Replay, Evaluate, and Guard your AI Agents.
- **Repo:** https://github.com/betaHi/AgentGuard
- **License:** MIT
- **Language:** Python 3.11+

## Design Principles

1. **Zero/minimal dependencies** — Core uses only stdlib. Optional deps for extras.
2. **Low intrusion** — Users should NOT need to restructure their code. A decorator or context manager is enough.
3. **Framework-agnostic** — Works with any agent system. No LangChain/CrewAI lock-in.
4. **Generic examples** — No project-specific branding in README. Use generic agent names.
5. **Local-first** — Works without cloud, DB, or Docker.

## Sprint Plan

### Sprint 1: Foundation ✅ DONE
- Core trace schema (ExecutionTrace, Span)
- SDK decorators (@record_agent, @record_tool)  
- TraceRecorder with context propagation
- CLI: show, list
- 11 tests passing

### Sprint 2: Evaluation Engine
- Rule-based assertions (min_count, each_has, recency, no_duplicates, contains, regex, custom)
- EvaluationResult schema
- YAML config (agentguard.yaml) for test definitions
- CLI: `agentguard eval`
- Agent config versioning
- Tests for all rule types

### Sprint 3: Replay + Regression
- Fixed-input replay mechanism
- Version comparison (diff two runs)
- LLM evaluator (optional, requires API key)
- Regression detection across multiple runs
- CLI: `agentguard replay`, `agentguard diff`, `agentguard regression`
- Regression report (Markdown)

### Sprint 4: Guard + Polish
- Continuous monitoring mode (watch)
- Alert mechanism (webhook, stdout, file)
- Context manager API (alternative to decorators for less intrusion)
- Async support
- Web UI: multi-agent timeline viewer (simple HTML, no React needed)
- Comprehensive README with generic examples
- PyPI-ready packaging

## Development Rules

1. Every change must have tests.
2. Zero external deps for core/sdk/eval. Optional deps clearly marked.
3. Type hints everywhere.
4. Docstrings on all public APIs.
5. Generic examples only — no project-specific branding.
6. Low intrusion: decorator OR context manager OR manual API. User's choice.

## Progress Log

### 2026-04-11 — Sprint 1 Complete ✅
- Core schemas, SDK decorators, CLI, 11 tests
### 2026-04-11 — Multi-Loop architecture designed
- LOOPS.md, progress files for parallel development
