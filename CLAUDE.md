# AgentGuard Development Instructions

Read program.md for project direction and current priorities.
Read GUARDRAILS.md for lines that must not be crossed.
Read REVIEW.md for code review criteria.

## Your task

You are developing AgentGuard, an observability layer for multi-agent orchestration.

Every iteration:
1. Read the story spec (.story-current.md) carefully
2. Read any previous evaluator feedback — address ALL points
3. Decompose the task into concrete steps before coding
4. Implement (code + tests)
5. Run `python -m pytest tests/ -v` — all tests must pass
6. Commit with a descriptive message

## Rules
- All code and comments in English
- Zero external dependencies for core/sdk
- Type hints and docstrings on public APIs
- Every change must have tests
- Functions ≤ 50 lines (extract helpers if needed)
- Trace depth > feature breadth (per GUARDRAILS.md)
- Production-grade quality, NOT demo quality

## DO NOT
- Modify program.md (Planner's job)
- Modify progress.txt (Planner's job)
- Modify REVIEW.md or GUARDRAILS.md
- Add modules unless the story explicitly requires it
- Ignore evaluator feedback — if feedback says "fix X", you MUST fix X
