---
name: diagnose-trace
description: Diagnose an existing AgentGuard trace file.
---

# Diagnose AgentGuard Trace

`$ARGUMENTS` is a path to a trace JSON file. Run this and paste the output verbatim:

```bash
${CLAUDE_PLUGIN_ROOT}/bin/agentguard diagnose "$ARGUMENTS"
```

The `[artifacts]` block lists the trace path and a companion HTML report generated next to it. Do not add any summary unless the user asks.
