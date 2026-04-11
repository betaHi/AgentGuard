# Changelog

All notable changes to AgentGuard will be documented in this file.

## [0.1.0] — 2026-04-11

### Core
- ExecutionTrace and Span data models with JSON serialization
- Span types: agent, tool, llm_call, handoff
- Parent-child span relationships (tree assembly)
- Handoff tracking fields: handoff_from, handoff_to, context_passed, context_size_bytes
- Failure tracking fields: caused_by, failure_handled

### SDK (6 integration styles)
- `@record_agent` / `@record_tool` sync decorators
- `@record_agent_async` / `@record_tool_async` async decorators
- `AgentTrace` / `ToolContext` sync context managers
- `AsyncAgentTrace` / `AsyncToolContext` async context managers
- `ManualTracer` explicit span API
- `wrap_agent()` / `wrap_tool()` / `patch_method()` middleware
- `inject_trace_context()` / `init_recorder_from_env()` for spawned processes
- `merge_child_traces()` with persist + cleanup
- `record_handoff()` explicit handoff recording
- `detect_context_loss()` handoff validation

### Analysis
- `analyze_failures()`: root cause identification, blast radius, resilience score
- `analyze_flow()`: handoff detection, critical path, parallel groups
- `analyze_bottleneck()`: agent rankings, bottleneck identification
- `analyze_context_flow()`: context loss/bloat detection across handoffs
- `diff_traces()`: side-by-side trace comparison

### Evaluation
- 8 built-in rule types: min_count, max_count, each_has, recency, no_duplicates, contains, regex, range
- EvaluationResult with Markdown report generation
- LLM pairwise evaluator (OpenAI-compatible API)

### Replay
- ReplayEngine: save baselines, compare candidates, run regression suites

### Guard
- Continuous monitoring with configurable check interval
- Alert handlers: stdout, file (JSONL), webhook
- Consecutive failure escalation (warning → critical)
- Agent-only failure tracking (tool failures don't escalate)

### Export
- JSON (native)
- JSONL (for log aggregation)
- OTel-compatible span format
- Trace statistics

### CLI (7 commands)
- `agentguard show` — display trace tree
- `agentguard list` — list traces
- `agentguard eval` — evaluate against rules
- `agentguard diff` — compare two traces
- `agentguard analyze` — failure propagation + bottleneck + flow + context
- `agentguard report` — generate HTML report
- `agentguard guard` — continuous monitoring

### Web
- Standalone HTML report with dark theme
- Diagnostic badges from analysis layer (single source of truth)
- Timeline bars, handoff indicators, failure propagation
- Prototype Gantt-style orchestration panel (docs/prototype.html)

### Documentation
- Architecture guide
- Quick start tutorial
- Examples catalog (6 examples including coding pipeline)
- Ralph Loop setup guide
- GUARDRAILS.md (project boundary protection)
- Contributing guide

### Tests
- 106 tests covering: trace schema, decorators, context managers, async,
  distributed, eval rules, replay, guard, analysis, diff, web, edge cases
