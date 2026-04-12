# QuickStart Guide

## Install

```bash
pip install -e .
# or from PyPI (coming soon):
# pip install agentguard
```

## 1. Record a Trace

```python
from agentguard import record_agent, record_tool, record_handoff, mark_context_used
from agentguard.sdk.recorder import init_recorder, finish_recording

# Start recording
init_recorder(task="My Pipeline")

# Use decorators
@record_agent(name="researcher")
def research(topic):
    return {"articles": ["a1", "a2"], "raw": "...", "meta": {}}

@record_agent(name="writer")
def write(articles):
    return {"draft": "# My Blog Post"}

# Execute
data = research("AI agents")
h = record_handoff("researcher", "writer", context=data, summary="2 articles")
mark_context_used(h, used_keys=["articles"])
draft = write(data["articles"])

# Finish
trace = finish_recording()
```

## 2. Analyze

```python
# Score the trace
from agentguard.scoring import score_trace
score = score_trace(trace)
print(f"Score: {score.overall}/100 ({score.grade})")

# Extract metrics
from agentguard.metrics import extract_metrics
m = extract_metrics(trace)
print(f"Agents: {m.agent_count}, Duration p90: {m.agent_duration.p90_ms}ms")

# Failure propagation
from agentguard.propagation import analyze_propagation
prop = analyze_propagation(trace)
print(prop.to_report())

# Flow graph (Mermaid)
from agentguard.flowgraph import build_flow_graph
graph = build_flow_graph(trace)
print(graph.to_mermaid())

# Context flow
from agentguard.context_flow import analyze_context_flow_deep
flow = analyze_context_flow_deep(trace)
print(flow.to_report())

# Natural language summary
from agentguard.summarize import summarize_trace
print(summarize_trace(trace))
```

## 3. CLI

```bash
# Show a trace
agentguard show trace.json

# Score it
agentguard score trace.json

# Timeline view
agentguard timeline trace.json

# Tree view
agentguard tree trace.json

# Dependency graph
agentguard dependencies trace.json --mermaid

# SLA check
agentguard sla trace.json --max-duration 10000 --min-score 70

# Compare two traces
agentguard compare trace_v1.json trace_v2.json
agentguard span-diff trace_v1.json trace_v2.json

# Generate synthetic traces
agentguard generate --count 20 --agents 5

# Run benchmark
agentguard benchmark --traces 50
```

## 4. Advanced: TraceBuilder

```python
from agentguard.builder import TraceBuilder

trace = (TraceBuilder("Content Pipeline")
    .agent("researcher", duration_ms=5000, token_count=2000, cost_usd=0.06)
        .tool("web_search", duration_ms=2000)
        .llm_call("claude", duration_ms=3000, token_count=1500, cost_usd=0.04)
    .end()
    .handoff("researcher", "writer", context_size=2000)
    .agent("writer", duration_ms=8000)
    .end()
    .build())
```

## 5. SLA Checking

```python
from agentguard.sla import SLAChecker

sla = (SLAChecker()
    .max_duration_ms(10000)
    .min_success_rate(0.95)
    .max_cost_usd(1.0)
    .min_score(70))

result = sla.check(trace)
print(result.to_report())
```

## 6. Alert Rules

```python
from agentguard.alerts import AlertEngine, rule_trace_failed, rule_score_below

engine = AlertEngine()
engine.add_rule(rule_trace_failed())
engine.add_rule(rule_score_below(60, severity="critical"))

alerts = engine.evaluate(trace)
for alert in alerts:
    print(f"[{alert.severity}] {alert.message}")
```
