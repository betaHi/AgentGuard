# AgentGuard — Project Guardrails

> These are the lines we must not cross. Revisit before every major decision.

## Three Lines to Hold

1. **Never overlap with generic LLM observability.** We don't do tokens, latency, cost dashboards. That's Langfuse territory. We stay above that layer.

2. **Never inflate the roadmap into a broad reliability suite.** Eval, replay, guard are secondary. The moment they start driving product direction over trace depth, we've lost focus.

3. **Always deepen multi-agent orchestration: handoff, failure propagation, context flow.** This is the only axis that matters. Every feature must serve this axis or wait.

## The Real Bar

The project succeeds not when it can show a pretty timeline, but when it can **reliably answer these five questions**:

1. Which agent is the performance bottleneck?
2. Which handoff lost critical information?
3. Which sub-agent's failure started propagating downstream?
4. Which execution path has the highest cost but worst yield?
5. Which orchestration decision caused downstream degradation?

Once it can answer these, it's not an "Agent visualization tool" — it's a **multi-agent system diagnostic tool**. The difference in value is enormous.

## Summary Judgment

- Direction is right. Worth continuing.
- The cut is correct — much stronger than a generic AI platform play.
- The biggest risk is not technical — it's **product boundary drift**.
- Success depends not on UI, but on **orchestration semantics and diagnostic capability**.
- Keep pushing. But hold the three lines.
