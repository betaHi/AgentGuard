# Getting Started with AgentGuard

## Install

```bash
pip install -e .
```

Initialize your project:

```bash
agentguard init
agentguard doctor  # verify installation
```

## 1. Instrument Your Agents (30 seconds)

Add `@record_agent` and `@record_tool` to your existing functions.
Your code stays unchanged — AgentGuard wraps it transparently:

```python
from agentguard import record_agent, record_tool, record_handoff, mark_context_used
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_tool(name="search")
def search(query):
    return call_your_api(query)  # your code, unchanged

@record_agent(name="researcher", version="v1.0")
def researcher(topic):
    return search(topic)

@record_agent(name="writer", version="v1.0")
def writer(articles):
    return {"draft": "# My Blog Post"}

# Start recording
init_recorder(task="My Pipeline", trigger="manual")

# Run your agents
data = researcher("AI agents")
h = record_handoff("researcher", "writer", context=data, summary="2 articles")
mark_context_used(h, used_keys=["articles"])
writer(data)

# Finish — trace is saved to .agentguard/traces/
trace = finish_recording()
```

### Alternative: Context Managers

For cases where decorators don't fit:

```python
from agentguard import AgentTrace
from agentguard.sdk.recorder import init_recorder, finish_recording

init_recorder(task="Pipeline")
with AgentTrace(name="my-agent", version="v1") as agent:
    with agent.tool("search") as t:
        results = do_search("query")
        t.set_output(results)
    agent.set_output(results)
trace = finish_recording()
```

## 2. View and Analyze

### CLI

```bash
# View execution tree
agentguard show .agentguard/traces/<id>.json

# Full diagnostics: failures, bottleneck, handoffs, context flow
agentguard analyze .agentguard/traces/<id>.json

# Quality score
agentguard score .agentguard/traces/<id>.json

# Natural language summary
agentguard summarize .agentguard/traces/<id>.json

# Timeline and tree views
agentguard timeline .agentguard/traces/<id>.json
agentguard tree .agentguard/traces/<id>.json
```

### Web Report

```bash
agentguard report
# Open .agentguard/report.html — Gantt timeline + diagnostics panel
```

### Programmatic Analysis

```python
from agentguard.analysis import analyze_failures, analyze_bottleneck, analyze_flow

failures = analyze_failures(trace)
print(f"Resilience: {failures.resilience_score:.0%}")

bn = analyze_bottleneck(trace)
print(f"Bottleneck: {bn.bottleneck_span} ({bn.bottleneck_pct:.0f}%)")

flow = analyze_flow(trace)
for h in flow.handoffs:
    print(f"  {h.from_agent} → {h.to_agent} ({h.context_size_bytes}B)")
```

## 3. Compare and Monitor

```bash
# Compare two runs
agentguard compare trace_v1.json trace_v2.json

# SLA checks
agentguard sla .agentguard/traces/<id>.json --max-duration 10000 --min-score 70

# Continuous monitoring
agentguard guard --interval 60

# Flow graph (paste into Mermaid renderer)
agentguard flowgraph .agentguard/traces/<id>.json --mermaid
```

## 4. Advanced

### TraceBuilder (for testing/benchmarking)

```python
from agentguard.builder import TraceBuilder

trace = (TraceBuilder("Content Pipeline")
    .agent("researcher", duration_ms=5000, token_count=2000, cost_usd=0.06)
        .tool("web_search", duration_ms=2000)
    .end()
    .handoff("researcher", "writer", context_size=2000)
    .agent("writer", duration_ms=8000)
    .end()
    .build())
```

### SLA Checking

```python
from agentguard.sla import SLAChecker

result = (SLAChecker()
    .max_duration_ms(10000)
    .min_score(70)
    .max_cost_usd(1.0)
    .check(trace))
print(result.to_report())
```

### Parallel Agents (Thread / Async)

```python
from agentguard.sdk.context import TracingExecutor, traced_task

# Threads
with TracingExecutor(max_workers=4) as executor:
    futures = [executor.submit(my_agent, task) for task in tasks]

# Async
task_a = traced_task(agent_a())
task_b = traced_task(agent_b())
await asyncio.gather(task_a, task_b)
```

## Next Steps

- [Tutorial](tutorial.md) — full walkthrough with distributed tracing
- [Examples](examples.md) — realistic multi-agent pipelines
- [Architecture](architecture.md) — system design
