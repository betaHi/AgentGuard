# Contributing to AgentGuard

Thanks for considering contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/betaHi/AgentGuard.git
cd AgentGuard
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

All tests must pass before submitting a PR.

## Code Standards

- **Language:** Python 3.11+ with type hints on all public APIs
- **Docstrings:** Required on all public classes and functions
- **Comments/code:** All in English
- **Dependencies:** Zero external deps for `agentguard/core/` and `agentguard/sdk/`
- **Function length:** ≤ 50 lines (extract helpers if needed)
- **Quality bar:** Production-grade, not demo quality

## Project Direction

Read `GUARDRAILS.md` for the project's non-negotiable principles and the 5 Questions that define success.

Every PR should serve at least one of the 5 Questions (Q1-Q5), or be clearly infrastructure/docs work. Include which Q# your change serves in the PR description.

## Project Structure

```
agentguard/
├── core/           # Data models (zero deps, pure dataclasses)
├── sdk/            # Instrumentation (decorators, context managers, threading, async)
├── eval/           # Evaluation engine (rules, comparison)
├── analysis.py     # Diagnostic analysis (bottleneck, flow, failures, cost-yield, decisions)
├── guard.py        # Continuous monitoring
├── replay.py       # Trace replay with assertions
├── web/            # HTML report generator (viewer)
└── cli/            # Command-line interface
```

## PR Checklist

- [ ] All tests pass (`pytest tests/ -v`)
- [ ] New functions have tests
- [ ] Type hints on public APIs
- [ ] Docstrings on public functions
- [ ] No external deps added to core/sdk
- [ ] Functions ≤ 50 lines
- [ ] PR description states which GUARDRAILS Q# (Q1-Q5) this serves
- [ ] No overstatements in docs/comments

## License

By contributing, you agree that your contributions will be licensed under MIT.
