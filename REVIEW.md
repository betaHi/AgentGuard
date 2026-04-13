# AgentGuard Code Review Criteria

> Read this ENTIRELY before every review. No exceptions.

## Project Identity
AgentGuard = **multi-agent orchestration diagnostics tool**.
Goal: **production-grade repository**, NOT a demo.

## The 5 Questions (success criteria)
Every change must help answer at least one:
1. Which agent is the performance bottleneck?
2. Which handoff lost critical information?
3. Which sub-agent's failure started propagating downstream?
4. Which execution path has the highest cost but worst yield?
5. Which orchestration decision caused downstream degradation?

If a change doesn't serve any of these → REJECT.

## Design Documents (authoritative — code MUST match these)
- `GUARDRAILS.md` — three lines that must not be crossed
- `docs/current-state-review-zh.md` — latest state review with known issues and priorities
- `program.md` — current stories and progress

Code that contradicts these documents is WRONG, even if tests pass.

## Known Issues (from current-state-review)
1. Viewer bottleneck sidebar shows agent cards but analysis returns tool spans → semantic mismatch
2. Thread context propagation is explicit-only → SDK ergonomics gap
3. examples.md descriptions may not match actual pipeline output → credibility risk
4. README narrative slightly ahead of stable implementation → tighten, don't overstate

## Review Principles

### 1. Every change gets a thorough review — no shortcuts
- Read the FULL diff, not just stat
- Check semantic correctness, not just syntax
- Run the code mentally or actually — construct edge cases
- Never say "looks good" without evidence

### 2. Code must align with design documents
- Check against current-state-review priorities
- Check against GUARDRAILS three lines
- Check against program.md direction
- If code drifts from these → REJECT with specific reference

### 3. Expert-level code quality
- Production patterns, not demo patterns
- Error handling for real failure modes (not just happy path)
- Type hints, docstrings, defensive coding
- Functions ≤ 50 lines unless justified
- Clear task decomposition — each commit solves ONE thing

### 4. Real scenarios, not toy examples
- Examples must use realistic agent counts, data sizes, failure modes
- If a scenario is too simple to be useful → reconstruct it
- Deterministic outputs (fixed seeds) so docs match reality

### 5. Confidence levels required
For every review, state your confidence:
- ✅ **HIGH**: Verified by running code or constructing edge cases
- ⚠️ **MEDIUM**: Logic looks correct but not runtime-verified
- ❓ **LOW**: Cannot verify without more context — flag what's uncertain

### 6. No self-inflation
- Don't assume your own code is correct
- Don't trust "tests pass" as proof of correctness
- If you're not sure, say so explicitly

## Must Pass
- [ ] All tests pass (pytest, no regressions)
- [ ] Change matches story spec exactly — not more, not less
- [ ] Aligns with GUARDRAILS.md and current-state-review priorities
- [ ] No new modules unless story explicitly requires it
- [ ] No overstatements in docs/comments/README
- [ ] Error handling present (no bare exceptions)

## Should Pass
- [ ] Type hints on public API
- [ ] Docstring on public functions
- [ ] Follows existing code patterns
- [ ] New function has at least one test
- [ ] Edge cases considered and handled

## Red Flags (auto-REJECT)
- Adding unrelated features
- Changing GUARDRAILS.md or REVIEW.md
- Modifying program.md (Planner's job)
- Hardcoded values that should be configurable
- Functions > 50 lines without justification
- Import of external packages in core/ or sdk/
- README/docs claiming capabilities that don't exist
- Demo-quality code pretending to be production-quality

## ACCEPT/REJECT Format
```
ACCEPT: [reason] | Confidence: [HIGH/MEDIUM/LOW]
```
or
```
REJECT: [specific issue with doc reference]. Fix: [concrete action]
```
