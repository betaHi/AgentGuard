# AgentGuard Development Instructions

## MANDATORY: Read These First (every time)
1. GUARDRAILS.md — the 5 Questions and 3 Lines that must not be crossed
2. docs/current-state-review-zh.md — current known issues and priorities
3. REVIEW.md — what the reviewer will check (your code must pass all items)
4. .story-current.md — your current task and evaluator feedback

## Your Task

You are developing AgentGuard, a multi-agent orchestration diagnostics tool.

Every iteration:
1. Read .story-current.md — especially Previous Evaluator Feedback
2. If feedback exists: FIX every issue. Do NOT resubmit unchanged code.
3. State which GUARDRAILS Q# (Q1-Q5) your task serves
4. Decompose into concrete steps before coding
5. Implement (code + tests)
6. Run `python -m pytest tests/ -v` — all must pass
7. Commit with descriptive message

## Rules
- All code and comments in English
- Zero external dependencies for core/sdk
- Type hints and docstrings on public APIs
- Every change must have tests
- Functions ≤ 50 lines (extract helpers if needed)
- Trace depth > feature breadth (per GUARDRAILS.md)
- Production-grade quality, NOT demo quality

## DO NOT
- Modify program.md or progress.txt (Planner-owned)
- Modify REVIEW.md or GUARDRAILS.md
- Add modules unless story explicitly requires it
- Ignore evaluator feedback
- Overstate capabilities in docs/comments
