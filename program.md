# AgentGuard — Development Program

> This file drives the Ralph Loop. Humans set direction. Agents write code.

## Identity

- **Name:** AgentGuard
- **Positioning:** Observability for multi-agent orchestration.
- **One-liner:** See how your agents collaborate, where they fail, and why.
- **Repo:** https://github.com/betaHi/AgentGuard
- **License:** MIT
- **Language:** Python 3.11+

## What Matters Most (Priority Order)

### Tier 1 — Core (the product)
The trace data model and the instrumentation that feeds it. This is what makes AgentGuard unique.

- **Trace schema** — ExecutionTrace, Span, span types, parent-child relationships
- **Instrumentation SDK** — decorators, context managers, manual API, distributed propagation
- **Multi-agent semantics** — handoff events, context flow between agents, failure propagation paths
- **Trace visualization** — CLI tree, web timeline, flow graph

### Tier 2 — Extensions (built on traces)
Valuable but secondary. These consume trace data — they don't define the product.

- **Eval rules** — assertions on agent output quality
- **Replay engine** — baseline comparison and regression detection
- **Guard mode** — continuous monitoring and alerts
- **Export** — OTel, JSONL for integration

### Tier 3 — Future
Not now. Will grow naturally once Tier 1 is deep enough.

- Interactive web dashboard
- LLM-based evaluation
- Real-time streaming traces
- GitHub Actions integration

## Core Asset Protection

The most valuable code in this repo is NOT the rule engine. It is:

1. **agentguard/core/trace.py** — the trace schema
2. **agentguard/sdk/** — low-intrusion instrumentation
3. **The ability to express cross-agent relationships** — parent-child, handoff, context propagation

These must be kept clean, well-documented, and zero-dependency.

## Current Priority: Deepen Trace Semantics

The next iterations should focus on making the trace richer, not adding more commands.

### Handoff Events
When agent A passes work to agent B, capture:
- What context was passed
- What context was lost
- Duration of the handoff
- Whether the receiving agent used the context

### Failure Propagation Analysis
Given a trace with failures:
- Which span was the root cause?
- Did the failure propagate or get caught?
- What was the blast radius (how many downstream spans affected)?

### Context Flow
Track how information flows between agents:
- Context size at each handoff point
- Context compression/truncation events
- Whether downstream agents received sufficient context

### Multi-Agent Flow Graph
Beyond tree view — show the actual flow:
- Parallel vs sequential execution
- Agent dependencies
- Critical path analysis

## Design Rules

1. Zero external deps for core/ and sdk/
2. All code and docs in English
3. Type hints and docstrings on public APIs
4. Every change has tests
5. Trace depth > feature breadth

## Progress Log

### 2026-04-11 — Project launch
- Sprint 1-4 completed (core, eval, replay, guard)
- 12 iterations via Ralph Loop
- 74 tests passing
- 6 integration styles
- Bug fixes from code review (distributed trace, guard, XSS)
- README repositioned: observability-first
- program.md repositioned: trace depth over feature breadth

### 2026-04-12 — Deepen trace semantics (iterations 141-145)
- Handoff context usage tracking: mark_context_used(), utilization ratio, context_received/used_keys/dropped_keys
- Failure propagation: causal chains, circuit breaker detection, hypothetical failure analysis (propagation.py)
- Flow graph DAG: execution phases, parallel/sequential detection, critical path, Mermaid output (flowgraph.py)
- Context flow: compression/truncation/expansion events, bandwidth analysis, bottleneck detection (context_flow.py)
- 3 new CLI commands: propagation, flowgraph, context-flow
- Tests: 148 → 189+
