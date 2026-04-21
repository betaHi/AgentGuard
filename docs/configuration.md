# AgentGuard Configuration

## agentguard.json

Project-level config created by `agentguard init`. Placed in your project root.

```json
{
  "traces_dir": ".agentguard/traces",
  "knowledge_dir": ".agentguard/knowledge",
  "report_output": ".agentguard/report.html",
  "agents": [
    {
      "name": "my-agent",
      "tests": [
        {
          "assertions": [
            {"type": "min_count", "target": "output_data", "value": 1, "name": "has-output"}
          ]
        }
      ]
    }
  ]
}
```

### Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `traces_dir` | string | `.agentguard/traces` | Directory for trace JSON files |
| `knowledge_dir` | string | `.agentguard/knowledge` | Directory for evolution knowledge |
| `report_output` | string | `.agentguard/report.html` | HTML report output path |
| `agents` | array | `[]` | Per-agent evaluation rules |
| `agents[].name` | string | — | Agent name to match |
| `agents[].tests[].assertions` | array | — | Eval rules (used by `agentguard eval`) |

## Environment Variables

Used for distributed tracing (cross-process context propagation).
Set automatically by `inject_trace_context()`, read by `init_recorder_from_env()`.

| Variable | Description | Example |
|----------|-------------|---------|
| `AGENTGUARD_TRACE_ID` | Parent trace ID | `a1b2c3d4-e5f6-7a` |
| `AGENTGUARD_PARENT_SPAN_ID` | Parent span ID for nesting | `x1y2z3` |
| `AGENTGUARD_TASK` | Task description | `My Pipeline` |
| `AGENTGUARD_TRIGGER` | Trigger type | `api`, `manual`, `cron` |
| `AGENTGUARD_OUTPUT_DIR` | Trace output directory | `.agentguard/traces` |

### Usage

```python
# Parent process
from agentguard.sdk.distributed import inject_trace_context
env = inject_trace_context()
subprocess.Popen(["python", "child.py"], env={**os.environ, **env})

# Child process
from agentguard.sdk.distributed import init_recorder_from_env
recorder = init_recorder_from_env()  # reads env vars automatically
```

## CLI Commands

### Project Setup

| Command | Description |
|---------|-------------|
| `agentguard init` | Create `.agentguard/traces/` and `agentguard.json` |
| `agentguard doctor` | Verify installation, modules, config |
| `agentguard version` | Show version |

### Viewing Traces

| Command | Description |
|---------|-------------|
| `agentguard show <file>` | Display trace as tree |
| `agentguard list [--dir DIR]` | List recorded traces |
| `agentguard tree <file>` | Indented tree view |
| `agentguard timeline <file> [--max N]` | Chronological event timeline |
| `agentguard report [--dir DIR] [--output PATH]` | Generate HTML report |

### Analysis

| Command | Description |
|---------|-------------|
| `agentguard analyze <file>` | Failure propagation + flow analysis |
| `agentguard learn <file>` | Learn recurring lessons from a trace |
| `agentguard suggest` | Show high-confidence learned suggestions |
| `agentguard trends` | Show recurring evolution trends |
| `agentguard prd` | Draft an improvement PRD from recurring issues |
| `agentguard auto-apply <file>` | Generate or apply config patches from learned issues |
| `agentguard score <file> [--expected-ms N]` | Quality score (0-100) |
| `agentguard summarize <file> [--brief]` | Natural language summary |
| `agentguard flowgraph <file> [--mermaid]` | Agent flow graph |
| `agentguard context-flow <file>` | Context flow analysis |
| `agentguard propagation <file>` | Failure propagation chains |
| `agentguard dependencies <file> [--mermaid]` | Agent dependency graph |
| `agentguard annotate <file>` | Auto-annotate trace |
| `agentguard correlate <file>` | Span correlation analysis |
| `agentguard metrics <file> [--prometheus]` | Extract metrics |

### Comparison

| Command | Description |
|---------|-------------|
| `agentguard diff <a> <b>` | Compare two traces |
| `agentguard span-diff <a> <b>` | Span-level diff |
| `agentguard compare <a> <b>` | Comprehensive comparison |

### Evaluation & SLA

| Command | Description |
|---------|-------------|
| `agentguard eval <file> [--config PATH]` | Evaluate against rules |
| `agentguard sla <file>` | SLA check |
| `agentguard validate <file>` | Trace integrity check |

SLA flags: `--max-duration MS`, `--min-score N`, `--max-cost USD`, `--max-error-rate N`

### Operations

| Command | Description |
|---------|-------------|
| `agentguard search [--name N] [--type T] [--failed]` | Search spans |
| `agentguard merge <file> [--keep]` | Merge child traces |
| `agentguard merge-dir <dir> [--output PATH]` | Merge all traces in dir |
| `agentguard generate [--count N] [--agents N] [--failure-rate F]` | Generate synthetic traces |
| `agentguard aggregate [--dir DIR]` | Aggregate analysis |
| `agentguard benchmark [--traces N] [--agents N]` | Performance benchmark |
| `agentguard guard [--interval S] [--threshold N] [--log PATH]` | Continuous monitoring |
| `agentguard schema` | Print trace JSON schema |

## SDK Defaults

| Setting | Default | Set via |
|---------|---------|---------|
| Traces directory | `.agentguard/traces` | `agentguard.configure(output_dir=...)` or `init_recorder(output_dir=...)` |
| Auto thread context | `False` | `agentguard.configure(auto_thread_context=True)` |
| Trigger type | `"manual"` | `init_recorder(trigger=...)` |
| Score weights | success=0.30, performance=0.20, context=0.20, resilience=0.15, efficiency=0.15 | `score_trace(weights={...})` |
| Knowledge base | `.agentguard/knowledge/` | `EvolutionEngine(knowledge_dir=...)` |
| Guard interval | 60s | `guard.watch(interval=...)` |
| Guard fail threshold | 3 | `Guard(fail_threshold=...)` |
