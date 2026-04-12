# AgentGuard API Reference

Complete reference for all public APIs. See [getting-started.md](getting-started.md) for a guided introduction.

## Recording

### `init_recorder`

```python
from agentguard.sdk.recorder import init_recorder
```

**Start recording a new trace**

```python
init_recorder(task: 'str' = '', trigger: 'str' = 'manual', output_dir: 'str' = '.agentguard/traces') -> 'TraceRecorder'
```

Initialize a new global trace recorder.

### `finish_recording`

```python
from agentguard.sdk.recorder import finish_recording
```

**Finalize and save the current trace**

```python
finish_recording() -> 'ExecutionTrace'
```

Finalize the current recording and return the trace.

### `get_recorder`

```python
from agentguard.sdk.recorder import get_recorder
```

**Get the active recorder**

```python
get_recorder() -> 'TraceRecorder'
```

Get or create the global trace recorder.

---

## Decorators

### `record_agent`

```python
from agentguard.sdk.decorators import record_agent
```

**Record an agent execution**

```python
record_agent(name: 'str', version: 'str' = 'latest', metadata: 'Optional[dict[str, Any]]' = None) -> 'Callable'
```

Decorator to record an agent's execution as a trace span.

### `record_tool`

```python
from agentguard.sdk.decorators import record_tool
```

**Record a tool call**

```python
record_tool(name: 'str', metadata: 'Optional[dict[str, Any]]' = None) -> 'Callable'
```

Decorator to record a tool call as a trace span.

---

## Handoffs & Decisions

### `record_handoff`

```python
from agentguard.sdk.handoff import record_handoff
```

**Record context transfer between agents**

```python
record_handoff(from_agent: 'str', to_agent: 'str', context: 'Any' = None, summary: 'str' = '', metadata: 'Optional[di...
```

Record a handoff event between two agents.

### `mark_context_used`

```python
from agentguard.sdk.handoff import mark_context_used
```

**Track which context keys were used**

```python
mark_context_used(handoff_span: 'Span', used_keys: 'list[str]', received_context: 'Any' = None) -> 'dict'
```

Mark which context keys were actually used by the receiving agent.

### `detect_context_loss`

```python
from agentguard.sdk.handoff import detect_context_loss
```

**Detect lost context in handoffs**

```python
detect_context_loss(sent_context: 'dict', received_input: 'dict', required_keys: 'Optional[list[str]]' = None) -> 'dict'
```

Detect if context was lost during a handoff.

### `record_decision`

```python
from agentguard.sdk.handoff import record_decision
```

**Record orchestration routing decision**

```python
record_decision(coordinator: 'str', chosen_agent: 'str', alternatives: 'Optional[list[str]]' = None, rationale: 'str'...
```

Record an orchestration decision — why the coordinator chose one agent over others.

---

## Context Managers

### `AgentTrace`

```python
from agentguard.sdk.context import AgentTrace
```

**Sync agent context manager**

```python
AgentTrace(name: 'str', version: 'str' = 'latest', metadata: 'Optional[dict]' = None)
```

Context manager for recording an agent execution.

### `AsyncAgentTrace`

```python
from agentguard.sdk.context import AsyncAgentTrace
```

**Async agent context manager**

```python
AsyncAgentTrace(name: 'str', version: 'str' = 'latest', metadata: 'Optional[dict]' = None)
```

Async context manager for recording agent execution.

### `ToolContext`

```python
from agentguard.sdk.context import ToolContext
```

**Tool call context manager**

```python
ToolContext(name: 'str', input_data: 'Any' = None, metadata: 'Optional[dict]' = None)
```

Context manager for recording a single tool call as a trace span.

---

## Parallel Execution

### `TracingExecutor`

```python
from agentguard.sdk.context import TracingExecutor
```

**Thread pool with trace propagation**

```python
TracingExecutor(max_workers: 'Optional[int]' = None) -> 'None'
```

ThreadPoolExecutor wrapper that propagates trace context to workers.

### `traced_task`

```python
from agentguard.sdk.context import traced_task
```

**asyncio.create_task with trace propagation**

```python
traced_task(coro: 'Any', name: 'Optional[str]' = None) -> "'asyncio.Task[Any]'"
```

Create an asyncio task with trace context propagation.

---

## Distributed Tracing

### `inject_trace_context`

```python
from agentguard.sdk.distributed import inject_trace_context
```

**Extract trace context as env vars**

```python
inject_trace_context(recorder: 'Optional[TraceRecorder]' = None, parent_span_id: 'Optional[str]' = None) -> 'dict[str...
```

Extract current trace context as environment variables.

### `init_recorder_from_env`

```python
from agentguard.sdk.distributed import init_recorder_from_env
```

**Initialize recorder from parent env**

```python
init_recorder_from_env() -> 'TraceRecorder'
```

Initialize a recorder from environment variables set by parent process.

### `merge_child_traces`

```python
from agentguard.sdk.distributed import merge_child_traces
```

**Merge child process traces into parent**

```python
merge_child_traces(parent_trace: 'ExecutionTrace', traces_dir: 'str' = '.agentguard/traces', cleanup: 'bool' = True, ...
```

Merge child process traces into the parent trace.

---

## Analysis

### `analyze_failures`

```python
from agentguard.analysis import analyze_failures
```

**Failure propagation analysis**

```python
analyze_failures(trace: 'ExecutionTrace') -> 'FailureAnalysis'
```

Analyze failure propagation in a trace.

### `analyze_bottleneck`

```python
from agentguard.analysis import analyze_bottleneck
```

**Performance bottleneck detection**

```python
analyze_bottleneck(trace: 'ExecutionTrace') -> 'BottleneckReport'
```

Identify the performance bottleneck in a trace.

### `analyze_flow`

```python
from agentguard.analysis import analyze_flow
```

**Agent flow and handoff analysis**

```python
analyze_flow(trace: 'ExecutionTrace') -> 'FlowAnalysis'
```

Analyze the execution flow of a multi-agent trace.

### `analyze_context_flow`

```python
from agentguard.analysis import analyze_context_flow
```

**Context flow anomaly detection**

```python
analyze_context_flow(trace: 'ExecutionTrace') -> 'ContextFlowReport'
```

Analyze how context flows between agents via handoffs.

### `analyze_cost_yield`

```python
from agentguard.analysis import analyze_cost_yield
```

**Cost vs output quality comparison**

```python
analyze_cost_yield(trace: 'ExecutionTrace') -> 'CostYieldReport'
```

Compare token spend per agent vs output quality.

### `analyze_decisions`

```python
from agentguard.analysis import analyze_decisions
```

**Orchestration decision analysis**

```python
analyze_decisions(trace: 'ExecutionTrace') -> 'DecisionAnalysis'
```

Analyze orchestration decisions and their downstream outcomes.

### `analyze_retries`

```python
from agentguard.analysis import analyze_retries
```

**Retry pattern analysis**

```python
analyze_retries(trace: 'ExecutionTrace') -> 'dict'
```

Detect retry patterns in a trace.

### `analyze_cost`

```python
from agentguard.analysis import analyze_cost
```

**Cost distribution analysis**

```python
analyze_cost(trace: 'ExecutionTrace') -> 'dict'
```

Analyze cost distribution across agents and tools.

---

## Scoring

### `score_trace`

```python
from agentguard.scoring import score_trace
```

**Compute quality score (0-100)**

```python
score_trace(trace: 'ExecutionTrace', expected_duration_ms: 'Optional[float]' = None, weights: 'Optional[dict[str, flo...
```

Score a trace on multiple quality dimensions.

---

## Builder

### `TraceBuilder`

```python
from agentguard.builder import TraceBuilder
```

**Fluent trace builder for testing**

```python
TraceBuilder(task: 'str' = '', trigger: 'str' = 'manual')
```

Fluent builder for constructing execution traces.

---

## Replay

### `TraceReplay`

```python
from agentguard.replay_v2 import TraceReplay
```

**Assertion-based trace replay**

```python
TraceReplay() -> 'None'
```

Replay a trace with configurable assertions.

### `replay_golden`

```python
from agentguard.replay_v2 import replay_golden
```

**Compare against golden trace file**

```python
replay_golden(golden_path: 'str', current_trace: 'ExecutionTrace', tolerance_ms: 'float' = 500.0, score_threshold: 'f...
```

Compare a current trace against a golden (known-good) baseline.

### `compare_golden`

```python
from agentguard.replay_v2 import compare_golden
```

**Compare against golden trace (in memory)**

```python
compare_golden(golden: 'ExecutionTrace', current: 'ExecutionTrace', tolerance_ms: 'float' = 500.0, score_threshold: '...
```

Compare current trace against a golden baseline (both in memory).

### `mutate_trace`

```python
from agentguard.replay_v2 import mutate_trace
```

**Create mutated trace for testing**

```python
mutate_trace(trace: 'ExecutionTrace', mutation: 'str' = 'random_failure') -> 'ExecutionTrace'
```

Create a mutated copy of a trace for mutation testing.

---

## Export

### `export_jsonl`

```python
from agentguard.export import export_jsonl
```

**Export to JSONL format**

```python
export_jsonl(trace: 'ExecutionTrace', filepath: 'str') -> 'None'
```

Export trace as JSONL (one span per line).

### `export_otel`

```python
from agentguard.export import export_otel
```

**Export to OpenTelemetry format**

```python
export_otel(trace: 'ExecutionTrace', filepath: 'Optional[str]' = None) -> 'dict'
```

Export trace to OpenTelemetry JSON format (resourceSpans envelope).

---

## Normalization

### `normalize_trace`

```python
from agentguard.normalize import normalize_trace
```

**Fix common trace issues**

```python
normalize_trace(trace: 'ExecutionTrace') -> 'NormalizationResult'
```

Normalize a trace by fixing common issues.

---

## Data Models

### `ExecutionTrace`

```python
from agentguard.core.trace import ExecutionTrace
```

Complete record of a multi-agent task execution.

### `Span`

```python
from agentguard.core.trace import Span
```

A single unit of work within a trace.

### `SpanType`

```python
from agentguard.core.trace import SpanType
```

Type of span in the trace.

### `SpanStatus`

```python
from agentguard.core.trace import SpanStatus
```

Status of a span execution.
