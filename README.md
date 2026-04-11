<div align="center">

# 🛡️ AgentGuard

**Record, Replay, Evaluate, and Guard your AI Agents.**

*Multi-agent orchestration observability & reliability — the missing engineering layer.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-11%20passed-brightgreen.svg)]()

</div>

---

## The Problem

Building an agent is easy. Running one reliably in production is hard.

There are dozens of frameworks to *build* agents. But what happens after?

- Your agent silently degrades — and you don't know until a human notices
- You change a prompt and can't tell if it made things better or worse
- Multiple agents collaborate but you can't see what each one actually did
- There's no CI/CD for agents — no tests, no regression detection, no version control

**AgentGuard fills this gap.**

## What It Does

```
Record  →  Replay  →  Evaluate  →  Guard
```

| Verb | What | Why |
|------|------|-----|
| **Record** | Capture multi-agent execution traces | See what actually happened |
| **Replay** | Re-run with fixed inputs, compare versions | Know if changes helped or hurt |
| **Evaluate** | Rule + LLM quality assessment | Define what "good" looks like |
| **Guard** | Continuous monitoring & regression alerts | Catch degradation before users do |

## Demo

### ✅ Multi-Agent Success Trace

```
════════════════════════════════════════════════════════════
  🛡️  AgentGuard Trace Report
════════════════════════════════════════════════════════════

  Trace ID:    7d3b7fe1-71d1-41
  Task:        AI Agent Daily Report
  Trigger:     cron
  Status:       ✓ PASS
  Duration:    1.2s
  Agents:      3
  Tool calls:  5
  Total spans: 8

  Execution Timeline
  ──────────────────────────────────────────────────
  🤖 基围小小虾 🦐 (v1.0)   ✓ PASS   1.2s
  ├── 🤖 北极虾 ❄️ (v1.3)   ✓ PASS   547ms
  │   ├── 🔧 web_search   ✓ PASS   115ms
  │   ├── 🔧 github_trending   ✓ PASS   152ms
  │   └── 🔧 summarize   ✓ PASS   281ms
  └── 🤖 皮皮虾 👊 (v2.0)   ✓ PASS   632ms
      ├── 🔧 web_search   ✓ PASS   272ms
      └── 🔧 summarize   ✓ PASS   360ms

════════════════════════════════════════════════════════════
```

### ❌ Failure Detection & Error Propagation

```
════════════════════════════════════════════════════════════
  🛡️  AgentGuard Trace Report
════════════════════════════════════════════════════════════

  Trace ID:    251d1a2e-ad6e-49
  Task:        AI Daily Report (with failures)
  Trigger:     cron
  Status:       ✗ FAIL
  Duration:    251ms
  Agents:      3
  Tool calls:  3
  Total spans: 6

  Execution Timeline
  ──────────────────────────────────────────────────
  🤖 基围小小虾 🦐 (v1.0)   ✓ PASS   250ms
  ├── 🤖 北极虾 ❄️ (v1.3)   ✓ PASS   150ms
  │   ├── 🔧 web_search   ✗ FAIL   100ms
  │   │      ⚠ ConnectionError: Search API timeout after 10s
  │   └── 🔧 cache_lookup   ✓ PASS   50ms
  └── 🤖 皮皮虾 👊 (v2.0)   ✗ FAIL   100ms
         ⚠ ConnectionError: Search API timeout after 10s
      └── 🔧 web_search   ✗ FAIL   100ms
             ⚠ ConnectionError: Search API timeout after 10s

════════════════════════════════════════════════════════════
```

> Notice: 北极虾 gracefully fell back to cache, while 皮皮虾 propagated the failure upward. AgentGuard makes this visible.

## Quick Start

```bash
pip install agentguard
```

### Record

```python
from agentguard import record_agent, record_tool
from agentguard.sdk.recorder import init_recorder, finish_recording

# Initialize a recording session
recorder = init_recorder(task="Daily Report", trigger="cron")

@record_agent(name="news-collector", version="v1.3")
def collect_news(topic: str) -> list[dict]:
    results = search_web(topic)
    return summarize(results)

@record_tool(name="web_search")
def search_web(query: str) -> list[str]:
    # your search logic
    ...

# Run your agents
collect_news("AI developments")

# Save the trace
trace = finish_recording()
# → .agentguard/traces/<trace_id>.json
```

### View Traces

```bash
# Show a specific trace
python -m agentguard.cli.main show .agentguard/traces/<trace_id>.json

# List all traces
python -m agentguard.cli.main list
```

## Key Design Decisions

- **Framework-agnostic** — Works with any agent (LangChain, CrewAI, custom, etc.)
- **Zero dependencies** — Core SDK uses only Python stdlib
- **Local-first** — No cloud, no database, no Docker required
- **OTel-compatible** — Follows OpenTelemetry GenAI semantic conventions
- **Not another framework** — We don't build agents. We make sure yours keep working.

## How This Project Is Built

AgentGuard is developed using the [Ralph Loop](https://ghuntley.com/ralph/) methodology:

> A simple loop that repeatedly lets an AI agent execute → evaluate → improve, turning predictable failures into progress.

Combined with [Karpathy's autoresearch](https://github.com/karpathy/autoresearch) principles — the agent modifies code, humans edit [`program.md`](program.md).

## Positioning

| Tool | Focus | Relationship |
|------|-------|-------------|
| **Langfuse** | LLM call-level tracing | AgentGuard sits above — orchestration level |
| **LangChain / CrewAI** | Building agents | AgentGuard ensures they keep working |
| **OpenTelemetry** | Observability standard | AgentGuard follows OTel conventions |

## Roadmap

- [x] **Sprint 1:** Core schemas + SDK decorators + CLI trace viewer
- [ ] **Sprint 2:** Rule-based evaluation engine + config versioning
- [ ] **Sprint 3:** Replay + LLM evaluator + regression detection
- [ ] **Sprint 4:** Guard mode + Web UI

## Contributing

This project is in early development. Star ⭐ the repo to follow progress.

## License

MIT
