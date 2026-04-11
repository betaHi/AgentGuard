<div align="center">

# 🛡️ AgentGuard

**Record, Replay, Evaluate, and Guard your AI Agents.**

*Multi-agent orchestration observability & reliability — the missing engineering layer.*

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

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

## Key Design Decisions

- **Framework-agnostic** — Works with any agent system (LangChain, CrewAI, custom, etc.)
- **Zero dependencies to start** — Core SDK uses only Python stdlib
- **Local-first** — No cloud, no database, no Docker required
- **OTel-compatible** — Follows OpenTelemetry GenAI semantic conventions
- **Not another framework** — We don't build agents. We make sure yours keep working.

## Quick Start

```bash
pip install agentguard
```

### Record

```python
from agentguard import record_agent, record_tool

@record_agent(name="news-collector", version="v1.0")
def collect_news(topic: str) -> list[dict]:
    articles = search_web(topic)
    return summarize(articles)

@record_tool(name="web_search")
def search_web(query: str) -> list[str]:
    # your search logic
    ...
```

### Evaluate

```yaml
# agentguard.yaml
agents:
  - name: news-collector
    tests:
      - name: daily-report-quality
        assertions:
          - type: min_count
            target: articles
            value: 5
          - type: each_has
            target: articles
            fields: [title, date, url]
          - type: recency
            target: articles.date
            within_days: 2
```

```bash
agentguard eval run
```

### Guard

```bash
agentguard guard --watch --alert-on regression
```

## How This Project Is Built

AgentGuard is developed using the [Ralph Loop](https://ghuntley.com/ralph/) methodology combined with [autoresearch](https://github.com/karpathy/autoresearch) principles:

> An AI agent iteratively builds this SDK — writing code, running tests, evaluating results, and improving. The project is its own first user.

See [`program.md`](program.md) for the current development program.

## Positioning

AgentGuard is **not** competing with:
- **Langfuse / Phoenix** — They do LLM-call-level observability (great at it). We do multi-agent orchestration level.
- **LangChain / CrewAI** — They build agents. We make sure agents keep working.
- **OpenTelemetry** — We follow OTel standards. AgentGuard is a consumer of OTel, not a replacement.

AgentGuard sits **above** these tools — the engineering layer between "agent works in dev" and "agent works in production."

## Roadmap

- [x] Project structure & program.md
- [ ] **Sprint 1:** Core schemas + SDK + CLI skeleton
- [ ] **Sprint 2:** Evaluation engine (rules + LLM)
- [ ] **Sprint 3:** Replay + regression detection
- [ ] **Sprint 4:** Guard mode + Web UI

## Contributing

This project is in early development. Star ⭐ the repo to follow progress.

## License

MIT
