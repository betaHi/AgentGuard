# FAQ & Troubleshooting

## General

### What is AgentGuard?
AgentGuard is a diagnostics toolkit for multi-agent AI systems. It records execution traces, analyzes them for bottlenecks, context loss, failure propagation, cost waste, and bad orchestration decisions, then presents actionable insights.

### What are the 5 Questions?
AgentGuard is built around 5 diagnostic questions (see GUARDRAILS.md):
1. **Q1:** Which agent is the performance bottleneck?
2. **Q2:** Which handoff lost critical information?
3. **Q3:** Which sub-agent's failure started propagating downstream?
4. **Q4:** Which execution path has the highest cost but worst yield?
5. **Q5:** Which orchestration decision caused downstream degradation?

### Does it require external dependencies?
No. Core analysis (`agentguard/core/`, `agentguard/sdk/`) has zero external dependencies. Optional YAML config requires `pyyaml`.

## SDK

### How do I instrument my agents?
```python
from agentguard import record_agent, record_tool

@record_agent(name="my-agent", version="v1")
def my_agent(task):
    result = my_tool("query")
    return result

@record_tool(name="search")
def my_tool(query):
    return ["result1", "result2"]
```

### Will AgentGuard crash my application?
No. All decorators are **fail-open** — if recording fails, your function still runs normally. Errors are logged at DEBUG level only.

### How do I reduce overhead in production?
```python
import agentguard
agentguard.configure(sampling_rate=0.1)  # record ~10% of traces
```
Sampling is per-trace (not per-span), so you always get complete traces or nothing.

### How do I attach custom metadata to spans?
```python
from agentguard import annotate
annotate("model_version", "gpt-4")
annotate("temperature", 0.7)
```

### How do I link traces across microservices?
```python
from agentguard import set_correlation_id
set_correlation_id(request.headers["X-Correlation-ID"])
```

### How do I batch trace writes?
```python
from agentguard.sdk.exporter import BatchExporter
exporter = BatchExporter(batch_size=10, output_dir="./traces")
exporter.add(completed_trace)
# Auto-flushes every 10 traces, or call exporter.flush()
```

## Analysis

### Why does the bottleneck analysis show a tool instead of an agent?
Bottleneck analysis targets **work spans** (tools, LLM calls) on the critical path, not container agents. If `db_query` is the bottleneck, optimize the query — the parent agent is just waiting.

### What is a "false bottleneck"?
An agent that appears slow (high wall time) but is actually waiting on its children. AgentGuard detects this when an agent has ≤20% own work time. The fix is to optimize its children, not the agent itself.

### How does context transformation tracking work?
AgentGuard compares output data from one agent with input data of the next. It detects:
- **Summarization:** string shrunk >50%
- **Filtering:** list shortened
- **Type change:** e.g., string `"42"` → integer `42`
- **Key rename:** lost key + new key with same value

### What's the difference between recoverable and fatal failures?
- **Recoverable:** contained by a circuit breaker, or trace succeeded despite the failure
- **Fatal:** propagated 2+ levels deep and trace failed, or affected >50% of spans

### Can I use custom cost models?
```python
from agentguard.analysis import analyze_cost_yield
result = analyze_cost_yield(trace,
    cost_fn=lambda span: span.duration_ms / 1000,  # cost = seconds
    yield_fn=lambda span: 100.0 if span.token_count > 50 else 0.0
)
```

## CLI

### What commands are available?
Run `agentguard --help` for the full list. Key commands:
- `agentguard summary trace.json` — one-line health check
- `agentguard analyze trace.json` — full analysis (add `--json` for structured output)
- `agentguard diff a.json b.json` — compare two traces
- `agentguard score trace.json` — quality score with grade
- `agentguard report trace.json -o report.html` — HTML report

## Troubleshooting

### Traces are too large (>10MB warning)
```python
agentguard.configure(max_trace_size_mb=20)  # raise threshold
# Or truncate automatically:
trace.to_json(truncate=True)
```
Span data fields (input_data, output_data, metadata) are truncated at 100KB each.

### Tests fail with "module not found"
Ensure you're in the project directory and the package is importable:
```bash
cd AgentGuard
python -m pytest tests/ -q
```

### HTML viewer shows blank page
Check that the trace file has valid JSON. Run `agentguard validate trace.json` to check.

### Sampling doesn't seem to work
Sampling is decided per `TraceRecorder` instance. If you're using the global recorder, call `agentguard.configure(sampling_rate=0.5)` before any recording starts.
