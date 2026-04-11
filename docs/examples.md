# AgentGuard Examples

> Realistic multi-agent scenarios that demonstrate AgentGuard's orchestration observability.
> Each example can be run directly and serves as a template for your own pipelines.

---

## Example 1: AI Coding Pipeline

**File:** [`examples/coding_pipeline.py`](../examples/coding_pipeline.py)

**Scenario:** A user requests a new API endpoint. Multiple agents collaborate to plan, implement, review, test, and deploy it — the architecture behind tools like Cursor, Copilot Workspace, and Claude Code.

**Agents:**

| Agent | Version | Role | Notable Behavior |
|-------|---------|------|-----------------|
| coding-pipeline | v4.0 | Coordinator | Orchestrates all phases, catches notification failure |
| planner | v2.1 | Planning | LLM breaks request into subtasks |
| code-searcher | v1.4 | Context gathering | Vector search with keyword fallback |
| code-generator | v3.0 | Implementation | LLM generates code (slow — bottleneck candidate) |
| code-reviewer | v2.3 | Quality gate | LLM review + static analysis |
| test-runner | v1.2 | Validation | Executes tests, reports coverage |
| deployer | v1.5 | Deployment | Creates PR, triggers CI |
| notifier | v1.0 | Notification | Slack alerts (may fail — unhandled) |

**Pipeline flow:**

```
user request
    │
    ▼
planner ──[handoff: plan]──► code-searcher ──[handoff: context]──► code-generator
                                                                        │
                                                                  [handoff: code]
                                                                        │
                                                                        ▼
                                                              code-reviewer
                                                                        │
                                                                  [handoff: review]
                                                                        │
                                                                        ▼
                                                              test-runner
                                                                        │
                                                                  [handoff: results]
                                                                        │
                                                                        ▼
                                                              deployer ──► notifier
```

**What this demonstrates:**

- **6 explicit handoffs** with context size tracking (0.3KB → 1.2KB → 0.8KB...)
- **Graceful fallback:** vector_search fails → keyword_search takes over, researcher still succeeds
- **Unhandled failure:** notifier crashes (Slack rate limit), coordinator catches it but notification is lost
- **Bottleneck:** code-generator and code-reviewer are LLM-heavy (slow)
- **Conditional flow:** deployer only runs if review approved AND tests passed
- **Resilience score:** ~50% (1 handled failure + 1 unhandled)

**Run it:**

```bash
python examples/coding_pipeline.py
```

**Observe it:**

```bash
agentguard show .agentguard/traces/<id>.json
agentguard analyze .agentguard/traces/<id>.json
agentguard report
```

---

## Example 2: Basic Multi-Agent Research

**File:** [`examples/demo.py`](../examples/demo.py)

**Scenario:** A coordinator dispatches a news collector and an analyst to research a topic.

**Agents:** coordinator → news-collector + analyst

**What this demonstrates:**
- Simple multi-agent orchestration
- Parallel agent execution under a coordinator
- Basic tool calls (web_search, github_api, summarize)
- Getting started with AgentGuard in < 30 lines

---

## Example 3: Async Agents

**File:** [`examples/async_demo.py`](../examples/async_demo.py)

**Scenario:** Async agents using `asyncio.gather` for concurrent execution.

**What this demonstrates:**
- `@record_agent_async` and `@record_tool_async` decorators
- `asyncio.gather` with multiple agents running concurrently
- Trace correctly captures parent-child relationships in async context

---

## Example 4: Subprocess / Spawned Agents

**File:** [`examples/subprocess_demo.py`](../examples/subprocess_demo.py)

**Scenario:** Agents launched as separate processes (subprocess, multiprocessing).

**What this demonstrates:**
- `inject_trace_context()` in parent process
- `init_recorder_from_env()` in child process
- Cross-process trace correlation
- `merge_child_traces()` to combine results

---

## Example 5: Handoff Tracking

**File:** [`examples/demo_with_handoffs.py`](../examples/demo_with_handoffs.py)

**Scenario:** Pipeline with explicit handoff recording between agents.

**What this demonstrates:**
- `record_handoff()` to capture context transfer between agents
- Context size tracking at each handoff point
- Handoff visualization in CLI and web report

---

## Example 6: Real-World Full Pipeline

**File:** [`examples/real_world.py`](../examples/real_world.py)

**Scenario:** Research pipeline with recording → evaluation → replay baseline → HTML report.

**What this demonstrates:**
- Complete AgentGuard workflow: record → eval → replay → report
- Rule-based evaluation (min_count, each_has, no_duplicates, contains, range)
- Saving replay baselines for future regression comparison
- HTML report generation

---

## Creating Your Own Example

To create a scenario for your agent system:

### 1. Identify your agents and tools

```python
# Who are the agents? What tools do they use?
agents = ["coordinator", "researcher", "analyst", "writer"]
tools = ["web_search", "llm_call", "database_query"]
```

### 2. Add instrumentation (2 lines per function)

```python
from agentguard import record_agent, record_tool

@record_agent(name="researcher", version="v1.0")
def researcher(topic):
    # your existing code, unchanged
    ...

@record_tool(name="web_search")
def search(query):
    # your existing code, unchanged
    ...
```

### 3. Record handoffs (optional but valuable)

```python
from agentguard import record_handoff

# After agent A completes, before agent B starts:
record_handoff("researcher", "analyst", 
               context=research_results,
               summary="5 articles about AI")
```

### 4. Record and analyze

```python
from agentguard.sdk.recorder import init_recorder, finish_recording

init_recorder(task="My Pipeline", trigger="manual")
run_pipeline()
trace = finish_recording()

# View
# agentguard show .agentguard/traces/<id>.json
# agentguard analyze .agentguard/traces/<id>.json
```

### 5. Define evaluation rules

```json
{
  "agents": [{
    "name": "researcher",
    "tests": [{
      "name": "output-quality",
      "assertions": [
        {"type": "min_count", "target": "articles", "value": 5},
        {"type": "each_has", "target": "articles", "fields": ["title", "url"]}
      ]
    }]
  }]
}
```

---

## Example Ideas for Different Domains

| Domain | Pipeline | Key Agents |
|--------|----------|------------|
| **Coding** | Plan → Search → Generate → Review → Test → Deploy | planner, code-gen, reviewer, tester |
| **Research** | Search → Collect → Analyze → Synthesize → Write | searcher, analyst, writer |
| **Customer Support** | Classify → Route → Respond → Escalate → Follow-up | classifier, responder, escalator |
| **Data Pipeline** | Extract → Validate → Transform → Load → Report | extractor, validator, transformer |
| **Content Creation** | Research → Outline → Write → Edit → Publish | researcher, writer, editor |
| **Security** | Scan → Analyze → Triage → Remediate → Verify | scanner, analyzer, remediator |

Each of these is a multi-agent orchestration scenario that AgentGuard can observe.
