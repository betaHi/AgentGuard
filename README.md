<div align="center">

# 🛡️ AgentGuard

**Record, Replay, Evaluate, and Guard your AI Agents.**

*The missing engineering layer between "agent works in dev" and "agent works in production."*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-41%20passed-brightgreen.svg)]()

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
- [ ] Async agent/tool support
- [ ] PyPI package publishing
- [ ] LLM-based evaluation (pairwise compare)
- [ ] Interactive web dashboard
- [ ] OTel exporter
- [ ] GitHub Actions integration

## Contributing

This project is in early development. Star ⭐ to follow progress.

Issues and PRs welcome.

## License

MIT
