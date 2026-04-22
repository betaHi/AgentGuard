# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅        |

## Reporting a Vulnerability

If you discover a security vulnerability, please report it responsibly:

1. **Do not** open a public issue.
2. Email: [security contact TBD] or use GitHub's private vulnerability reporting.
3. Include: description, reproduction steps, potential impact.

We will acknowledge within 48 hours and provide a fix timeline within 7 days.

## Scope

AgentGuard is a diagnostics library — it reads trace data but does not execute agent code. Security concerns are primarily around:
- Trace data serialization/deserialization (pickle, JSON)
- File system access (trace storage, HTML report generation)
- CLI command injection (user-provided paths)

## Data handling & privacy

AgentGuard operates **entirely locally**. The core and SDK have zero external dependencies; the only optional dependency is `claude-agent-sdk`, which is itself a local-only client library.

- **No network calls.** The library never uploads traces, prompts, tool calls, or any session content. There is no telemetry and no phone-home.
- **Input surfaces.** When you run `agentguard diagnose-claude-session`, the tool reads `~/.claude/projects/<slug>/<id>.jsonl` — the same file Claude Code wrote to your disk. These JSONL files typically contain your prompts, tool outputs, and file contents. Treat every AgentGuard trace/report as being at least as sensitive as the original session.
- **Output surfaces.** Two files are produced, both written to paths you control:
  - A trace JSON (defaults under `.agentguard/traces/`).
  - An HTML report (same directory as the trace unless overridden with `--report-output`).
  Neither file is compressed or obfuscated — open them in a text editor to see exactly what would be shared if you emailed them to a colleague.
- **Sharing reports.** Before passing a report outside your machine, remember it may contain:
  - The first/last prompts of the session.
  - Tool inputs/outputs (filenames, shell commands, code snippets, API responses).
  - Model ids, token counts, and timing.
  If you need to scrub sensitive fields, redact the source JSONL before importing.
- **Pricing & cost numbers.** Cost figures are computed locally from the pricing table declared in `agentguard/runtime/claude/session_import.py::_BUILTIN_PRICING`. Override with `AGENTGUARD_PRICING_FILE=/path/to/pricing.json` if you need region- or contract-specific rates. No rates are fetched from the network.
- **Running against shared / CI machines.** Treat `.agentguard/traces/` and any generated HTML as build artifacts: exclude them from git, or rely on the `.gitignore` patterns the `agentguard init` command sets up.
