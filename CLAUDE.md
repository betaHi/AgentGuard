# AgentGuard Development Instructions

Read program.md for project direction and current priorities.
Read GUARDRAILS.md for lines that must not be crossed.

## Your task

You are developing AgentGuard, an observability layer for multi-agent orchestration.

Every iteration:
1. Read program.md to understand current priorities
2. Pick the highest-priority unfinished item
3. Implement it (code + tests)
4. Run `python -m pytest tests/ -v` — all tests must pass
5. Commit with a descriptive message
6. Update program.md progress log
7. Move to the next item

## Rules
- All code and comments in English
- Zero external dependencies for core/sdk
- Type hints and docstrings on public APIs
- Every change must have tests
- Trace depth > feature breadth (per GUARDRAILS.md)

## Completion Promise
When all items in program.md "Current Priority" section are done, output:
<promise>SPRINT_COMPLETE</promise>
