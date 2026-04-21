---
name: list-sessions
description: List Claude sessions across all projects, grouped by project directory, so the user can find a session id to diagnose.
---

# List Claude Sessions

Run this and paste the raw stdout back to the user. Do not summarize, reformat, or truncate.

```bash
${CLAUDE_PLUGIN_ROOT}/bin/agentguard list-claude-sessions --limit 20 --group-by-project
```

If the user explicitly asks for "all", "every", "full list", or "全部", swap `--limit 20` for `--all`.

## Rules

- Print the command output verbatim. No commentary unless the user asks.
- Do not invent session ids.
- Do not auto-pick a session. Let the user choose.

