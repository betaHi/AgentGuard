# AgentGuard Architecture

## Product Boundary

AgentGuard is a diagnostics SDK for multi-agent orchestration.

It is built to answer five core questions from one execution trace:

1. Which agent is the bottleneck?
2. Which handoff lost critical information?
3. Which failure started propagating downstream?
4. Which execution path cost the most but yielded the least?
5. Which orchestration decision degraded the run?

The product boundary is therefore:

- capture runtime evidence as a trace
- normalize that evidence into a stable trace model
- run orchestration diagnostics on the trace
- deliver the result through CLI, HTML, and structured outputs

AgentGuard does not aim to be a general LLM observability platform or an agent framework.

## Main Runtime Path

The main runtime path is Claude-native.

```text
Claude Agent SDK
    -> agentguard.runtime.claude
    -> ExecutionTrace / Span
    -> agentguard.diagnostics
    -> CLI / HTML report / structured output
```

This path currently includes:

- live Claude runtime capture through `wrap_claude_client(...)`
- Claude session import through `import_claude_session(...)`
- context usage, task, tool, assistant, result, and rate-limit evidence capture

## Compatibility Runtime Paths

For existing Python agent systems, AgentGuard still supports:

- decorators
- context managers
- async wrappers
- middleware wrapping
- distributed trace propagation
- manual tracing

These remain valid integration paths, but they are compatibility surfaces rather than the primary product story.

## Layering

The architecture is easiest to reason about as four layers:

```text
runtime
    -> trace model
    -> diagnostics
    -> delivery
```

### Runtime

Runtime code collects evidence from Claude or existing Python agent systems.

Rules:

- runtime produces trace facts only
- runtime should not contain diagnostic policy
- runtime should preserve source evidence instead of collapsing it early

### Trace Model

The stable model is still centered on `ExecutionTrace` and `Span` in [agentguard/core/trace.py](../agentguard/core/trace.py).

Rules:

- diagnostics consume model objects, not runtime-specific types
- runtime-specific metadata is allowed, but it must remain attached as data, not behavior

### Diagnostics

Diagnostics are the core value layer.

Current major surfaces include:

- bottleneck
- context flow
- failure propagation
- cost-yield
- decisions and counterfactuals
- scoring, timeline, tree, and correlation helpers

The compatibility import surface for this layer lives in [agentguard/diagnostics/__init__.py](../agentguard/diagnostics/__init__.py).

### Delivery

Delivery turns diagnostics into consumable artifacts.

Current delivery surfaces include:

- CLI
- single-file HTML report
- JSON-style structured output

## Current Repository Shape

The repository is still broader than the desired long-term public surface.

What should remain central:

- `agentguard.runtime.claude`
- `agentguard.diagnostics`
- trace model
- CLI and HTML report

What should gradually shrink as public surface:

- very broad top-level exports in `agentguard.__init__`
- long-tail instrumentation-first documentation
- old utility-first product framing

## Data Flow

```text
Runtime event source
    -> Trace capture
    -> ExecutionTrace
    -> Diagnostics
    -> Report / CLI / Export
```

For Claude live runs, the event source is the Claude Agent SDK message and hook stream.
For imported sessions, the event source is the Claude SDK session transcript helpers.

## Design Decisions

1. Claude runtime is the strongest primary path.
2. Diagnostics remain the product core.
3. The trace model is the contract between capture and analysis.
4. Repository and API surface should get smaller, not larger.
5. Delivery stays local-first and easy to inspect.
