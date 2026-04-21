---
name: agentguard-diagnose-session
description: Diagnose a Claude session with AgentGuard from this repository checkout.
---

# AgentGuard Diagnose Session

Use this local standalone skill while iterating on the plugin.

1. If `$ARGUMENTS` contains a Claude session id, use it.
2. Otherwise run `agentguard list-claude-sessions --limit 10 --project .`.
3. Run `agentguard diagnose-claude-session <session-id> --output .agentguard/traces/<session-id>.json`. The dense output's `[artifacts]` block lists both the saved trace JSON path and a companion HTML report path; include both in your summary.
4. Only pass `--report-output` when the user wants the HTML written to a non-default location.
5. Lead with the dense terminal diagnosis, then mention the HTML report path for deeper inspection.