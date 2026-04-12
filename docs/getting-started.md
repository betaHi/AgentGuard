# Getting Started with AgentGuard

## Install

```bash
pip install agentguard
```

## 1. Instrument Your Agents (30 seconds)

Add `@record_agent` and `@record_tool` to your existing functions:

```python
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_tool(name="search")
def search(query):
    return call_your_api(query)  # your code, unchanged

@record_agent(name="researcher", version="v1.0")
def researcher(topic):
    return search(topic)  # your code, unchanged

# Start recording
init_recorder(task="My Pipeline", trigger="manual")
researcher("AI agents")
trace = finish_recording()
```

## 2. View the Trace

```bash
agentguard show .agentguard/traces/<id>.json
```

## 3. Run Diagnostics

```bash
agentguard analyze .agentguard/traces/<id>.json
```

Shows: failure propagation, bottleneck, handoffs, context flow.

## 4. Generate Web Report

```bash
agentguard report
# Open .agentguard/report.html
```

## 5. Self-Reflection (Learn from Traces)

```bash
agentguard evolve --learn --suggest
```

AgentGuard learns from your traces and suggests improvements.

## 6. Continuous Monitoring

```bash
agentguard guard --interval 300
```

Watches for new traces and alerts on failures.

## Alternative: Context Managers (Zero Decorators)

```python
from agentguard import AgentTrace

with AgentTrace(name="my-agent", version="v1") as agent:
    results = your_function()
    agent.set_output(results)
```

## Alternative: Wrap Third-Party Code

```python
from agentguard.sdk.middleware import wrap_agent

traced = wrap_agent(third_party_fn, name="external", version="v1")
traced(args)
```

## Next Steps

- See [examples/](../examples/) for realistic multi-agent pipelines
- See [docs/examples.md](examples.md) for example catalog
- See [docs/architecture.md](architecture.md) for system design
