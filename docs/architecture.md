# AgentGuard Architecture

## Overview

AgentGuard is structured as a layered SDK with clear separation of concerns:

```
┌─────────────────────────────────────────────────────────┐
│                    User Application                      │
│  (your agents, tools, workflows)                        │
└──────────────────────┬──────────────────────────────────┘
                       │ integrates via
                       ▼
┌─────────────────────────────────────────────────────────┐
│                    AgentGuard SDK                         │
│                                                          │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────┐ │
│  │  Decorators   │  │Context Managers│  │ Manual API   │ │
│  │ @record_agent │  │ AgentTrace    │  │ ManualTracer │ │
│  │ @record_tool  │  │ ToolContext   │  │              │ │
│  └──────┬───────┘  └──────┬────────┘  └──────┬───────┘ │
│         └──────────────────┼─────────────────-┘         │
│                            ▼                             │
│  ┌──────────────────────────────────────────────────┐   │
│  │              TraceRecorder                        │   │
│  │  Thread-safe span collection + context stack      │   │
│  └──────────────────────┬───────────────────────────┘   │
│                         ▼                                │
│  ┌──────────────────────────────────────────────────┐   │
│  │           Core Data Models                        │   │
│  │  ExecutionTrace  │  Span  │  SpanType             │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────┬───────────────────────────────┘
                          │ writes
                          ▼
┌─────────────────────────────────────────────────────────┐
│                 .agentguard/traces/                       │
│                 (JSON files on disk)                      │
└─────────────────────────┬───────────────────────────────┘
                          │ consumed by
                          ▼
┌────────────┐  ┌────────────┐  ┌──────────┐  ┌─────────┐
│  Eval      │  │  Replay    │  │  Guard   │  │  Export  │
│  Engine    │  │  Engine    │  │  Mode    │  │  (OTel)  │
└────────────┘  └────────────┘  └──────────┘  └─────────┘
       │               │              │             │
       ▼               ▼              ▼             ▼
  eval reports    regression     alerts        JSONL/OTel
                  reports       (stdout,       collectors
                               file, webhook)
```

## Design Principles

### 1. Zero Dependencies for Core
`agentguard/core/` and `agentguard/sdk/` use only Python stdlib.
This means:
- No dependency conflicts
- Works in any Python 3.11+ environment
- Fast import time

### 2. Flat Span Storage, Tree Assembly on Read
Spans are stored as a flat list with `parent_span_id` references.
Tree structure is assembled on-demand via `trace.build_tree()`.
This keeps serialization simple and allows flexible querying.

### 3. File-Based, No Database
Traces are JSON files on disk. This means:
- Zero infrastructure required
- Git-friendly (version control your traces)
- Easy to inspect manually
- Can be loaded into any tool

### 4. Progressive Enhancement
Start with decorators → add eval rules → enable guard mode.
Each layer is independent. You don't need eval to use recording,
and you don't need recording to use the eval engine.

## Integration Points

### For Agent Frameworks
AgentGuard doesn't know about LangChain, CrewAI, or any framework.
Integration happens at the Python function level:
- Wrap agent functions with `@record_agent`
- Wrap tool functions with `@record_tool`
- Or use context managers / manual API

### For Observability Platforms
Use `export.export_otel_spans()` to convert traces to OTel format,
then send to any OTel collector (Jaeger, Zipkin, Grafana Tempo, etc.)

### For CI/CD
Use the replay engine in your test pipeline:
```bash
agentguard eval <trace> --config agentguard.json
```
Exit code 0 = all rules pass, non-zero = failures detected.

## Data Flow

```
Agent runs → Decorator/CM captures spans → TraceRecorder assembles trace
  → JSON file written → eval/replay/guard/export consume it
```

Each step is independent and testable.
