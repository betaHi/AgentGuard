# Contributing to AgentGuard

Thanks for considering contributing! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/betaHi/AgentGuard.git
cd AgentGuard
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v
```

All tests must pass before submitting a PR.

## Code Style

- Python 3.11+ with type hints on all public APIs
- Docstrings on all public classes and functions
- All code and comments in English
- Zero external dependencies for `agentguard/core/` and `agentguard/sdk/`
- Optional dependencies clearly marked in pyproject.toml

## Project Structure

```
agentguard/
├── core/           # Data models (zero deps, pure dataclasses)
├── sdk/            # Instrumentation (decorators, context managers, manual API)
├── eval/           # Evaluation engine (rules, comparison)
├── guard.py        # Continuous monitoring
├── replay.py       # Replay engine
├── web/            # HTML report generator
└── cli/            # Command-line interface
```

## Adding a New Rule Type

1. Add the function in `agentguard/eval/rules.py`
2. Register it in `RULE_REGISTRY`
3. Add tests in `tests/test_eval.py`
4. Document in README

## Development Philosophy

This project is built using the [Ralph Loop](https://ghuntley.com/ralph/) methodology.
See `program.md` for the current development program and `LOOPS.md` for the
multi-loop architecture.

## License

By contributing, you agree that your contributions will be licensed under MIT.
