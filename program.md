# AgentGuard — Development Program

## Identity
- **Name:** AgentGuard
- **One-liner:** Multi-agent orchestration diagnostics.
- **Repo:** https://github.com/betaHi/AgentGuard
- **License:** MIT | **Language:** Python 3.11+

## The 5 Questions (success criteria)
1. Which agent is the performance bottleneck?
2. Which handoff lost critical information?
3. Which sub-agent's failure started propagating downstream?
4. Which execution path has the highest cost but worst yield?
5. Which orchestration decision caused downstream degradation?

## Design Rules
1. Zero external deps for core/ and sdk/
2. Trace depth > feature breadth
3. README/examples/analysis/viewer tell the same story

## Current Stories

- [ ] Deepen Q4: add cost-yield analysis — compare token spend per agent vs output quality
- [ ] Deepen Q5: add orchestration decision tracking — record why coordinator chose agent A over B
- [ ] Add trace replay with assertion: replay golden trace and verify properties hold
- [ ] Viewer: add mini flow-graph (Mermaid SVG) in diagnostics panel
- [ ] Viewer: add context flow waterfall — context size at each handoff as bar chart
- [ ] Add agentguard watch mode: monitor traces dir, auto-analyze, alert on regressions
- [ ] Improve handoff: detect context truncation (input larger than what arrived)
- [ ] Add span duration anomaly detection: flag spans 3x slower than historical average
- [ ] Create docs/api-reference.md with all public function signatures
- [ ] Update ralph-loop-guide.md to document v6 architecture
- [ ] Merge getting-started.md and quickstart.md into one doc
- [ ] Create docs/configuration.md — agentguard.json schema, CLI flags, env vars
- [ ] Add integration test: record → analyze → export → import → compare roundtrip
- [ ] Improve error_recovery example: add timeout + partial result patterns
- [ ] Add example: multi-model pipeline (GPT-4 + Claude + local, cost comparison)
