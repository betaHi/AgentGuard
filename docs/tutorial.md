# AgentGuard Tutorial

A step-by-step guide to instrumenting, analyzing, and monitoring your
multi-agent systems with AgentGuard.

## Prerequisites

- Python 3.11+
- For application teams: `pip install agentguard`
- For AgentGuard contributors: `pip install -e .`

## Part 1: Your First Trace

### 1.1 Initialize a Project

```bash
agentguard init
```

This creates `.agentguard/traces/`, `.agentguard/knowledge/`, and `agentguard.json`.

Recommended startup in real applications:

```python
import agentguard

agentguard.configure(
    output_dir=".agentguard/traces",
    auto_thread_context=True,
)
```

### 1.2 Instrument Your Agents

AgentGuard uses decorators to record agent and tool executions. Your
code stays unchanged — just add `@record_agent` and `@record_tool`:

```python
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_tool(name="web_search")
def search(query: str) -> list[str]:
    # Your existing code — unchanged
    return ["result1", "result2"]

@record_agent(name="researcher", version="v1.0")
def researcher(topic: str) -> dict:
    results = search(topic)
    return {"topic": topic, "results": results}

# Start recording, run your agent, finish
init_recorder(task="Research Pipeline", trigger="manual")
output = researcher("AI agents")
trace = finish_recording()
print(f"Trace saved: {trace.trace_id}")
```

### 1.3 View the Trace

```bash
agentguard show .agentguard/traces/<id>.json
```

You'll see a tree view of your execution:

```
🤖 researcher (v1.0)  ✓ PASS  150ms
└── 🔧 web_search     ✓ PASS   80ms
```

## Part 2: Multi-Agent Pipelines

### 2.1 Adding Handoffs

When work passes between agents, record the handoff explicitly:

```python
from agentguard import record_agent, record_handoff, mark_context_used
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_agent(name="collector", version="v1.0")
def collector(topic: str) -> dict:
    return {"articles": ["article1", "article2"], "raw_data": "..."}

@record_agent(name="analyst", version="v1.0")
def analyst(data: dict) -> dict:
    return {"summary": f"Analysis of {len(data['articles'])} articles"}

init_recorder(task="Research Pipeline")

data = collector("AI safety")

# Record the handoff with context tracking
h = record_handoff(
    "collector", "analyst",
    context=data,
    summary="Passing 2 articles for analysis",
)

# Mark which keys the receiver actually used
result = analyst(data)
mark_context_used(h, used_keys=["articles"])

trace = finish_recording()
```

### 2.2 Context Managers (Alternative to Decorators)

For more control, use context managers:

```python
from agentguard import AgentTrace
from agentguard.sdk.recorder import init_recorder, finish_recording

init_recorder(task="Pipeline")

with AgentTrace(name="researcher", version="v1.0") as agent:
    with agent.tool("search", input_data={"q": "AI"}) as t:
        results = ["result1", "result2"]
        t.set_output(results)
    agent.set_output({"results": results})

trace = finish_recording()
```

### 2.3 Error Handling and Resilience

AgentGuard tracks failures and whether they were handled:

```python
@record_agent(name="fetcher", version="v1.0")
def fetcher(url: str) -> dict:
    raise ConnectionError("Service unavailable")

@record_agent(name="coordinator", version="v1.0")
def coordinator():
    try:
        return fetcher("https://api.example.com")
    except ConnectionError:
        return {"fallback": True}  # Handled — trace stays COMPLETED
```

## Part 3: Analysis

### 3.1 CLI Analysis

```bash
# Full diagnostics: failures, bottleneck, handoffs, context flow
agentguard analyze .agentguard/traces/<id>.json

# Score the trace on quality dimensions
agentguard score .agentguard/traces/<id>.json

# Natural language summary
agentguard summarize .agentguard/traces/<id>.json

# Tree view
agentguard tree .agentguard/traces/<id>.json
```

### 3.2 Programmatic Analysis

```python
from agentguard.analysis import (
    analyze_failures,
    analyze_bottleneck,
    analyze_flow,
    analyze_context_flow,
)

failures = analyze_failures(trace)
print(f"Resilience: {failures.resilience_score:.0%}")
print(f"Unhandled failures: {failures.unhandled_count}")

bn = analyze_bottleneck(trace)
print(f"Bottleneck: {bn.bottleneck_span} ({bn.bottleneck_pct:.0f}%)")

flow = analyze_flow(trace)
for h in flow.handoffs:
    print(f"  {h.from_agent} → {h.to_agent} ({h.context_size_bytes}B)")
```

### 3.3 Flow Graph (Mermaid)

```bash
agentguard flowgraph .agentguard/traces/<id>.json --mermaid
```

Paste the output into any Mermaid renderer to see your agent DAG.

## Part 4: Comparing and Monitoring

### 4.1 Compare Two Runs

```bash
agentguard compare trace_v1.json trace_v2.json
agentguard span-diff trace_v1.json trace_v2.json
```

### 4.2 SLA Checks

```bash
agentguard sla .agentguard/traces/<id>.json \
  --max-duration 10000 \
  --min-score 70 \
  --max-cost 1.0
```

### 4.3 Continuous Monitoring

```bash
agentguard guard --interval 60 --threshold 3
```

Watches for new traces and alerts on consecutive failures.

### 4.4 Web Report

```bash
agentguard report
# Open .agentguard/report.html in your browser
```

The report includes a Gantt timeline with zoom controls, agent health
cards, diagnostics grid, and failure propagation analysis.

## Part 5: Distributed Tracing

When agents run as separate processes, propagate trace context:

```python
import subprocess, sys, os
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.sdk.distributed import (
    inject_trace_context,
    init_recorder_from_env,
    merge_child_traces,
)

# Parent process
recorder = init_recorder(task="Distributed Pipeline")
child_env = {**os.environ, **inject_trace_context()}

proc = subprocess.Popen(
    [sys.executable, "child_agent.py"],
    env=child_env,
)
proc.wait()

trace = finish_recording()
merged = merge_child_traces(trace, traces_dir=str(recorder.output_dir))
```

```python
# child_agent.py
from agentguard import record_agent
from agentguard.sdk.distributed import init_recorder_from_env
from agentguard.sdk.recorder import finish_recording

recorder = init_recorder_from_env()

@record_agent(name="child-agent", version="v1.0")
def do_work():
    return {"status": "done"}

do_work()
finish_recording()
```

## Part 6: Health Check

```bash
agentguard doctor
```

Verifies Python version, core modules, traces directory, and config.

## Next Steps

- Browse [examples/](../examples/) for realistic pipelines
- See [examples.md](examples.md) for the example catalog
- See [architecture.md](architecture.md) for system design
- See [getting-started.md](getting-started.md) for the onboarding guide
- See [current-state-review-zh.md](current-state-review-zh.md) for the current product status and next tasks
