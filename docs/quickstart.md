# Quick Start: Instrument Your First Agent in 5 Minutes

## 1. Install

```bash
pip install agentguard
```

## 2. Add Two Lines to Your Agent

Before:
```python
def my_agent(task: str) -> dict:
    results = search(task)
    return {"results": results}

def search(query: str) -> list:
    # your search logic
    return [...]
```

After:
```python
from agentguard import record_agent, record_tool

@record_agent(name="my-agent", version="v1.0")
def my_agent(task: str) -> dict:
    results = search(task)
    return {"results": results}

@record_tool(name="search")
def search(query: str) -> list:
    # your search logic (unchanged)
    return [...]
```

That's it. Two decorators, zero code changes to your logic.

## 3. Record a Run

```python
from agentguard.sdk.recorder import init_recorder, finish_recording

init_recorder(task="Daily Report", trigger="cron")
my_agent("AI news")
trace = finish_recording()
# → .agentguard/traces/<id>.json
```

## 4. View the Trace

```bash
agentguard show .agentguard/traces/<id>.json
```

You'll see a tree like:
```
🤖 my-agent (v1.0)   ✓ PASS   1.2s
└── 🔧 search   ✓ PASS   800ms
```

## 5. Add Quality Rules

Create `agentguard.json`:
```json
{
  "agents": [{
    "name": "my-agent",
    "tests": [{
      "name": "basic-check",
      "assertions": [
        {"type": "min_count", "target": "results", "value": 3},
        {"type": "each_has", "target": "results", "fields": ["title", "url"]}
      ]
    }]
  }]
}
```

Evaluate:
```bash
agentguard eval .agentguard/traces/<id>.json --config agentguard.json
```

## 6. Set Up Monitoring

```bash
agentguard guard --interval 300  # check every 5 minutes
```

## Next Steps

- Add more agents and tools with `@record_agent` / `@record_tool`
- Use context managers if decorators don't fit: `with AgentTrace(...) as agent:`
- Use `async` variants for async code
- Set up replay baselines for regression testing
- Export to OTel for integration with your observability stack
