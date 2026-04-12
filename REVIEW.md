# AgentGuard Code Review Criteria

> 罗氏虾 🔱 reads this before every review. This is the single source of truth for what "good" means.

## Project Identity
AgentGuard = **multi-agent orchestration diagnostics tool** (NOT generic LLM observability).

## The 5 Questions (from GUARDRAILS.md)
Every change should help answer at least one of these:
1. Which agent is the performance bottleneck?
2. Which handoff lost critical information?
3. Which sub-agent's failure started propagating downstream?
4. Which execution path has the highest cost but worst yield?
5. Which orchestration decision caused downstream degradation?

If a change doesn't serve any of these, it's probably feature sprawl.

## Known Issues to Watch (from 大大虾 review)
- Viewer must NOT show handoffs that aren't confirmed by analysis layer
- Bottleneck must NOT identify coordinator/container nodes as bottleneck
- Trace status must correctly handle: handled failure ≠ trace failed
- README/examples/docs must not overstate what the code actually does
- Examples must be deterministic (use fixed seeds) so docs match output

## Review Checklist
For every change, check:

### Must Pass
- [ ] Tests pass (pytest, no regressions)
- [ ] Change matches story spec exactly — not more, not less
- [ ] No new modules added unless story explicitly requires it
- [ ] No overstatements in docs/comments
- [ ] Error handling present (no bare exceptions swallowing errors)

### Should Pass
- [ ] Type hints on public API
- [ ] Docstring on public functions
- [ ] Follows existing code patterns (look at neighboring code)
- [ ] New function has at least one test

### Red Flags (auto-REJECT)
- Adding unrelated features ("while I'm here, I also added...")
- Changing GUARDRAILS.md or REVIEW.md
- Modifying program.md or progress.txt (Planner's job)
- Hardcoded values that should be configurable
- Functions > 50 lines without clear reason
- Import of external packages in core/ or sdk/ (zero-dep rule)

## ACCEPT/REJECT Format
```
ACCEPT: [one-line reason why this change is good]
```
or
```
REJECT: [specific issue]. Fix: [concrete action to take]
```
