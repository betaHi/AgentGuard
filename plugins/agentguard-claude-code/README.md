# AgentGuard Claude Code Plugin

This plugin gives Claude Code a direct AgentGuard workflow for diagnosing Claude sessions in the terminal first and exporting HTML only when deeper inspection is needed.

Prerequisites:

- `agentguard` installed in the current Python environment
- `claude-agent-sdk` installed when diagnosing Claude sessions

Local development:

```bash
claude --plugin-dir ./plugins/agentguard-claude-code
```

Then reload inside Claude Code with:

```text
/reload-plugins
```

Key skills:

- `/agentguard:list-sessions` — list every Claude session across all projects, grouped by working directory. Useful when you can't remember which project a session belonged to.
- `/agentguard:diagnose-session [session-id]` — session id is optional. If omitted, the skill lists recent Claude sessions for the current project and asks you to pick one before running the diagnosis.
- `/agentguard:diagnose-trace <trace-path>`

The terminal view is intentionally dense. Export HTML only when the user asks for a deeper report or when the diagnosis shows severe risk.

Automatic post-session diagnosis:

On `SessionEnd`, the plugin runs `agentguard diagnose-claude-session` in the
background for the session that just ended and writes artifacts under
`.agentguard/` in the working directory:

- `.agentguard/traces/<session-id>.json` — captured trace
- `.agentguard/reports/<session-id>.html` — full HTML report
- `.agentguard/reports/<session-id>.txt` — dense terminal diagnosis log

The hook exits immediately and never blocks the session. If `agentguard` is not
installed in the session environment, the hook is a no-op.