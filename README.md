<div align="center">

# 🛡️ AgentGuard

**Record, Replay, Evaluate, and Guard your AI Agents.**

*The missing engineering layer between "agent works in dev" and "agent works in production."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-68%20passed-brightgreen.svg)]()

</div>

---

## The Problem

Building an agent is easy. Running one reliably in production is hard.

There are dozens of frameworks to *build* agents. But once deployed:

- **Silent degradation** — your agent gets worse and no one notices until a user complains
- **No version control** — you change a prompt and can't tell if things improved or regressed  
- **Multi-agent black box** — agents collaborate but you can't see who did what
- **No CI/CD** — no tests, no regression detection, no quality gates

AgentGuard gives you engineering tools for agents that are already running.

## What It Does

```
Record  →  Replay  →  Evaluate  →  Guard
```

| | What | Why |
|---|---|---|
| **Record** | Capture multi-agent execution traces | See what actually happened |
| **Replay** | Re-run with fixed inputs, compare versions | Know if changes helped or hurt |
| **Evaluate** | Rule + LLM quality assessment | Define and enforce "good output" |
| **Guard** | Continuous monitoring with alerts | Catch degradation automatically |

## Quick Start

```bash
pip install agentguard
```

### Option 1: Decorators (2 lines of code)

```python
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording

@record_tool(name="web_search")
def search(query: str) -> list[str]:
    return call_search_api(query)

@record_agent(name="researcher", version="v1.3")
def research(topic: str) -> dict:
    results = search(topic)
    return {"results": results, "count": len(results)}

# Record a session
init_recorder(task="Research Report", trigger="cron")
research("AI agents")
trace = finish_recording()
# → saved to .agentguard/traces/<id>.json
```

### Option 2: Context Managers (zero decoration needed)

```python
from agentguard import AgentTrace
from agentguard.sdk.recorder import init_recorder, finish_recording

init_recorder(task="Research Report")

with AgentTrace(name="researcher", version="v1.3") as agent:
    with agent.tool("web_search") as t:
        results = search(query)
        t.set_output(results)
    agent.set_output({"results": results})

trace = finish_recording()
```


### Option 3: Spawned / Multi-Process Agents

For agents launched via `subprocess`, `multiprocessing`, or any spawn mechanism:

```python
import subprocess, os
from agentguard.sdk.recorder import init_recorder, finish_recording
from agentguard.sdk.distributed import inject_trace_context

# Parent process: start recording and propagate context
recorder = init_recorder(task="Distributed Research", trigger="api")
env = inject_trace_context()

# Spawn child agents — trace context propagated via env vars
subprocess.run(["python", "agent_a.py"], env={**os.environ, **env})
subprocess.run(["python", "agent_b.py"], env={**os.environ, **env})

trace = finish_recording()
```

```python
# agent_a.py (child process)
from agentguard import AgentTrace
from agentguard.sdk.distributed import init_recorder_from_env
from agentguard.sdk.recorder import finish_recording

init_recorder_from_env()  # automatically joins parent trace

with AgentTrace(name="agent-a", version="v1") as agent:
    result = do_work()
    agent.set_output(result)

finish_recording()
```

All spawned agents appear in the same trace tree, properly nested under the parent.

### Option 4: Async Agents

```python
from agentguard import record_agent_async, record_tool_async, AsyncAgentTrace

@record_tool_async(name="search")
async def search(query: str) -> list:
    return await api.search(query)

@record_agent_async(name="researcher", version="v1.0")
async def researcher(topic: str) -> dict:
    results = await search(topic)
    return {"results": results}

# Or with async context manager:
async with AsyncAgentTrace(name="agent", version="v1") as agent:
    async with agent.tool("search") as t:
        results = await search(query)
        t.set_output(results)
```

### View Traces

```bash
python -m agentguard.cli.main show .agentguard/traces/<id>.json
```

```
════════════════════════════════════════════════════════════
  🛡️  AgentGuard Trace Report
════════════════════════════════════════════════════════════

  Trace ID:    7f3cb929-ab53-41
  Task:        AI Agent Research Report
  Trigger:     manual
  Status:       ✓ PASS
  Duration:    1.0s
  Agents:      3
  Tool calls:  5
  Total spans: 8

  Execution Timeline
  ──────────────────────────────────────────────────
  🤖 coordinator (v1.0)   ✓ PASS   1.0s
  ├── 🤖 news-collector (v1.3)   ✓ PASS   551ms
  │   ├── 🔧 web_search   ✓ PASS   159ms
  │   ├── 🔧 github_api   ✓ PASS   141ms
  │   └── 🔧 summarize   ✓ PASS   251ms
  └── 🤖 analyst (v2.0)   ✓ PASS   474ms
      ├── 🔧 web_search   ✓ PASS   137ms
      └── 🔧 summarize   ✓ PASS   337ms

════════════════════════════════════════════════════════════
```

### Evaluate

Define quality rules in YAML:

```yaml
# agentguard.yaml
agents:
  - name: news-collector
    version: v1.3
    tests:
      - name: output-quality
        assertions:
          - type: min_count
            target: articles
            value: 5
          - type: each_has
            target: articles
            fields: [title, url, date]
          - type: recency
            target: articles.date
            within_days: 2
          - type: no_duplicates
            target: articles.url
```

Or evaluate programmatically:

```python
from agentguard.eval.rules import evaluate_rules

output = {"articles": [...]}
rules = [
    {"type": "min_count", "target": "articles", "value": 5},
    {"type": "each_has", "target": "articles", "fields": ["title", "url"]},
]
results = evaluate_rules(output, rules)
# → [RuleResult(verdict=PASS), RuleResult(verdict=FAIL, detail="...")]
```

**Built-in rule types:** `min_count`, `max_count`, `each_has`, `recency`, `no_duplicates`, `contains`, `regex`, `range`

### Compare Versions

```python
from agentguard.eval.compare import compare_evals

result = compare_evals(baseline_eval, candidate_eval)
print(result.to_report())
# → Shows what improved, what regressed, deploy recommendation
```

### Guard (Continuous Monitoring)

```python
from agentguard.guard import Guard, StdoutAlert, FileAlert, WebhookAlert

guard = Guard(
    traces_dir=".agentguard/traces",
    alert_handlers=[
        StdoutAlert(),
        FileAlert(".agentguard/alerts.jsonl"),
        WebhookAlert("https://hooks.slack.com/..."),
    ],
    fail_threshold=3,  # alert after 3 consecutive failures
)

guard.watch(interval=300)  # check every 5 minutes
```

### Web Report

```python
from agentguard.web.viewer import generate_timeline_html

generate_timeline_html()  # → .agentguard/report.html
```

Opens a standalone HTML page with dark-theme timeline visualization — no JS frameworks, no build step.


### Option 5: Manual API (maximum control)

For event-driven, callback-based, or complex architectures:

```python
from agentguard.sdk.manual import ManualTracer

tracer = ManualTracer(task="Pipeline Run")

agent_id = tracer.start_agent("processor", version="v1")
tool_id = tracer.start_tool("database_query", parent=agent_id, input_data={"sql": "SELECT ..."})
tracer.end_tool(tool_id, output=rows)
tracer.end_agent(agent_id, output={"processed": len(rows)})

trace = tracer.finish()
```

### Replay & Regression Testing

```python
from agentguard.replay import ReplayEngine

engine = ReplayEngine()

# Save a baseline
engine.save_baseline("daily-report", input_data={"topic": "AI"}, 
                     output_data={"articles": [...]},
                     rules=[{"type": "min_count", "target": "articles", "value": 5}])

# Later: compare new output against baseline
result = engine.compare("daily-report", candidate_output=new_output)
print(result.verdict)  # "improved", "regressed", or "neutral"

# Or run full regression suite
results = engine.run_regression(my_agent_fn)
```


## CLI Reference

```bash
agentguard show <trace.json>                    # Display trace tree
agentguard list [--dir .agentguard/traces]      # List all traces
agentguard eval <trace.json> [--config cfg.json] # Evaluate against rules
agentguard report [--dir DIR] [--output FILE]   # Generate HTML report
agentguard guard [--dir DIR] [--interval 60]    # Continuous monitoring
                 [--threshold 3] [--log FILE]
```

## Design Principles

| Principle | Implementation |
|---|---|
| **Low intrusion** | Decorator OR context manager OR manual API — your choice |
| **Framework-agnostic** | Works with LangChain, CrewAI, AutoGen, custom agents, anything |
| **Zero dependencies** | Core SDK uses only Python stdlib |
| **Local-first** | No cloud, no database, no Docker. Files on disk. |
| **OTel-aligned** | Follows OpenTelemetry GenAI semantic conventions |

## Architecture

```
agentguard/
├── core/               # Data models (zero deps)
│   ├── trace.py        # ExecutionTrace, Span
│   ├── eval_schema.py  # EvaluationResult, RuleResult
│   └── config.py       # AgentConfig, GuardConfig
├── sdk/                # Instrumentation (zero deps)
│   ├── decorators.py   # @record_agent, @record_tool
│   ├── context.py      # AgentTrace, ToolContext
│   └── recorder.py     # TraceRecorder
├── eval/               # Evaluation engine
│   ├── rules.py        # 8 built-in rule types
│   └── compare.py      # Version diff & regression
├── guard.py            # Continuous monitoring + alerts
├── web/
│   └── viewer.py       # Standalone HTML report
└── cli/
    └── main.py         # CLI interface
```

## Positioning

AgentGuard is **not** competing with:

| Tool | Their Focus | Our Relationship |
|---|---|---|
| **Langfuse / Phoenix** | LLM call-level tracing | We sit above — orchestration layer |
| **LangChain / CrewAI** | Building agents | We ensure they keep working |
| **OpenTelemetry** | Observability standard | We follow OTel conventions |

## Built With

This project is developed using the [Ralph Loop](https://ghuntley.com/ralph/) methodology — an AI agent iteratively builds the SDK, runs tests, and improves. See [`program.md`](program.md).

## Roadmap

- [x] Core trace schema with multi-agent span trees
- [x] SDK: decorators + context managers
- [x] 8 built-in evaluation rules
- [x] Version comparison & regression detection
- [x] Guard mode with alerts (stdout, file, webhook)
- [x] Standalone HTML timeline viewer
- [x] 41 tests passing
- [x] Async agent/tool support (decorators + context managers)
- [x] PyPI-ready packaging with entry point
- [ ] LLM-based evaluation (pairwise compare)
- [ ] Interactive web dashboard
- [ ] OTel exporter
- [ ] GitHub Actions integration

## Contributing

This project is in early development. Star ⭐ to follow progress.

Issues and PRs welcome.

## License

MIT
