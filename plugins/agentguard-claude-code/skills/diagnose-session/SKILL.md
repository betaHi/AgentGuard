---
name: diagnose-session
description: Diagnose a Claude session with AgentGuard. If no session id is given, list recent sessions for the current project and ask the user to pick one.
---

# Diagnose Claude Session

`$ARGUMENTS` is an optional Claude session id.

## If $ARGUMENTS is empty

Run and paste the output verbatim, then ask the user to pick one:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/agentguard list-claude-sessions --limit 10 --project .
```

Wait for the user's choice. Do NOT auto-pick. If no sessions are listed, offer to run the `list-sessions` skill to look across all projects.

## If $ARGUMENTS is a session id

Run and paste the output verbatim:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/agentguard diagnose-claude-session "$ARGUMENTS" --output .agentguard/traces/"$ARGUMENTS".json
```

The `[artifacts]` block in the output lists a trace JSON and a companion HTML report that is generated automatically. Do not add any summary unless the user asks.

## Rules

- Never fabricate a session id.
- Never auto-pick when the user did not specify one.
- Paste command output verbatim. No commentary unless asked.