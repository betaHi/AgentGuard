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

- **6 explicit handoffs** with context size tracking
- **Graceful fallback:** vector_search may fail → keyword_search takes over
- **Unhandled failure:** notifier may fail (Slack rate limit simulation), creating an unhandled tail failure
- **Bottleneck:** LLM calls (especially in code-generator) are typically the slowest spans
- **Conditional flow:** deployer only runs if review approved AND tests passed
- **Consistent resilience:** vector_search fails (fallback to keyword_search), notifier always fails (Slack rate limit), yielding 50% resilience

Note: The demo uses a fixed random seed for reproducible output.
Every run produces the same trace structure, diagnostics, and "deployed" result.

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

**Scenario:** A coordinator runs a news collector then an analyst sequentially.

**Agents:** coordinator → news-collector → analyst (sequential)

**What this demonstrates:**
- Simple multi-agent orchestration (sequential execution)
- Basic tool calls (web_search, github_api, summarize)
- Getting started with AgentGuard in < 30 lines
- Note: agents run sequentially under the coordinator, not in parallel

---

## Example 3: Async Agents

**File:** [`examples/async_demo.py`](../examples/async_demo.py)

**Scenario:** Async agents using `asyncio.gather` for concurrent execution.

**What this demonstrates:**
- `@record_agent_async` and `@record_tool_async` decorators
- `asyncio.gather` with multiple agents running concurrently
- Trace correctly captures parent-child relationships in async context

---

## Example 4: Parallel Research Pipeline

**File:** [`examples/parallel_pipeline.py`](../examples/parallel_pipeline.py)

**Scenario:** Three researchers run in parallel under one coordinator, then a merger, analyst, and writer continue sequentially.

**What this demonstrates:**
- Product-style startup with `agentguard.configure(output_dir=".agentguard/traces", auto_thread_context=True)`
- Standard `threading.Thread` usage with automatic trace context propagation
- Real timing overlap across sibling agents under one coordinator span
- HTML report output that matches the README viewer style: Gantt timeline, diagnostics cards, and handoff badges

---

## Example 5: Parallel Coding Pipeline

**File:** [`examples/parallel_coding.py`](../examples/parallel_coding.py)

**Scenario:** Code review, security scan, and test execution run concurrently after code generation.

**What this demonstrates:**
- The easiest threaded integration path for product code: configure once, keep standard threads
- Parallel review branches flowing back into a single fixer handoff
- Viewer output aligned with the README screenshots via the generated HTML report

---

## Example 6: Subprocess / Spawned Agents

**File:** [`examples/subprocess_demo.py`](../examples/subprocess_demo.py)

**Scenario:** Agents launched as separate processes (subprocess, multiprocessing).

**What this demonstrates:**
- `inject_trace_context()` to propagate trace context via env vars
- `init_recorder_from_env()` to join parent trace in child process
- API for cross-process trace correlation
- Note: the demo simulates subprocess behavior inline; for true subprocess usage, pass env vars to `subprocess.run()`

---

## Example 7: Handoff Tracking

**File:** [`examples/demo_with_handoffs.py`](../examples/demo_with_handoffs.py)

**Scenario:** Pipeline with explicit handoff recording between agents.

**What this demonstrates:**
- `record_handoff()` to capture context transfer between agents
- Context size tracking at each handoff point
- Handoff visualization in CLI and web report

---

## Example 8: Real-World Full Pipeline

**File:** [`examples/real_world.py`](../examples/real_world.py)

**Scenario:** Research pipeline with recording → evaluation → replay baseline → HTML report.

**What this demonstrates:**
- Complete AgentGuard workflow: record → eval → replay → report
- Rule-based evaluation (min_count, each_has, no_duplicates, contains, range)
- Saving replay baselines for future regression comparison
- HTML report generation

---


---

## Example 9: Customer Support Pipeline

**File:** [`examples/support_pipeline.py`](../examples/support_pipeline.py)

**Scenario:** Customer sends a billing dispute. Agents classify intent, search knowledge base, generate response, and check escalation rules.

**Agents:** support-coordinator → classifier → knowledge-retriever → responder → escalation-checker

**What this demonstrates:**
- Intent classification → knowledge retrieval → response generation flow
- Escalation decision with email notification
- 5 agents, 5 tools, 3 handoffs

---

## Example 10: Data ETL Pipeline

**File:** [`examples/data_pipeline.py`](../examples/data_pipeline.py)

**Scenario:** Monthly transaction data processing — extract CSV, validate schema, clean/aggregate, load to database, generate report.

**Agents:** data-coordinator → extractor → validator → transformer → loader → reporter

**What this demonstrates:**
- Linear pipeline with strict ordering
- Validation gate (schema check before transform)
- 6 agents, 6 tools, 4 handoffs


---

## Example 11: Security Scanning Pipeline

**File:** [`examples/security_pipeline.py`](../examples/security_pipeline.py)

**Scenario:** Automated security audit — SAST scan, dependency check, analyze findings, auto-fix exploitable issues, verify fixes.

**Agents:** security-coordinator → scanner → analyzer → remediator → verifier

---

## Example 12: Content Creation Pipeline

**File:** [`examples/content_pipeline.py`](../examples/content_pipeline.py)

**Scenario:** Blog post creation — research topic, create outline, write sections, edit, publish.

**Agents:** content-coordinator → researcher → outliner → writer → editor → publisher

---

## Example 13: Multi-Hop RAG Pipeline

**File:** [`examples/multi_hop_rag_pipeline.py`](../examples/multi_hop_rag_pipeline.py)

**Scenario:** A five-hop RAG workflow moves from retrieval to reranking, generation, fact-checking, and synthesis while context degrades across hops.

**What this demonstrates:**
- A realistic sequential RAG chain instead of a toy two-step retriever→generator demo
- Context loss that the existing handoff analysis can actually detect
- A fact-check stage removing an unsupported claim introduced after evidence shrinkage
- Viewer/HTML output for a product-relevant RAG-with-verification workflow

## Example 14: Evolution Loop

**File:** [`examples/evolution_loop.py`](../examples/evolution_loop.py)

**Scenario:** The same orchestration pattern runs multiple times so the evolution engine can accumulate recurring lessons, detect trends, and draft an improvement PRD.

**What this demonstrates:**
- Repeated learning across multiple runs instead of one-off reflection output
- Knowledge accumulation in `.agentguard/knowledge/` semantics without relying on viewer state
- High-confidence recurring failure and bottleneck suggestions
- Trend detection and PRD generation for product-style follow-up work

## Example 15: MVP HTML Prototype

**File:** [`examples/mvp_html_prototype.py`](../examples/mvp_html_prototype.py)

**Scenario:** A coordinator chooses a deeper but slower reviewer, that decision degrades downstream quality via failure and context loss, a stable reviewer exists as the counterfactual alternative, and the final HTML report includes evolution insights.

**What this demonstrates:**
- A viewer demo generated by the current codebase rather than a hand-written static mock
- Decision impact, context loss, bottleneck, workflow pattern, and evolution panels in one trace
- A product-facing artifact you can open directly at `.agentguard/prototypes/mvp-prototype.html`
- A better MVP inspection example than a minimal happy-path pipeline

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
```

### 2.5 Optional: one-time product setup

```python
import agentguard

agentguard.configure(
  output_dir=".agentguard/traces",
  auto_thread_context=True,
)
```

Use this when your application starts standard threads and you want the
recorded topology and HTML report to match the orchestration view shown in
the README screenshots.

### 2.6 Add tools

```python
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
