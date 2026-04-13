# AgentGuard Development Best Practices

> Lessons learned building a production-grade multi-agent diagnostics tool with AI-assisted development.

## Repository Standards (Reference: FastAPI, Pydantic, LangChain, Ruff)

### Must-Have for Open Source
| Item | Why | Reference |
|------|-----|-----------|
| `pyproject.toml` only (no setup.py) | Modern Python packaging standard | PEP 621, Ruff, Polars |
| CI on 3.11/3.12/3.13 | Ensure compatibility | FastAPI, Pydantic |
| Ruff for lint + format | Fastest, replaces flake8+isort+black | Ruff, Polars, FastAPI |
| `py.typed` marker | PEP 561 — enables downstream type checking | Pydantic, httpx |
| SECURITY.md | Responsible disclosure policy | GitHub recommended |
| Issue/PR templates | Consistent contributions | All major projects |
| CHANGELOG.md | User-facing change history | Keep a Changelog spec |
| CONTRIBUTING.md with PR checklist | Lower barrier to entry | FastAPI pattern |

### Code Quality
| Practice | Rule | Why |
|----------|------|-----|
| Functions ≤ 50 lines | Extract helpers | Readability, testability |
| Zero deps for core | `agentguard/core/` and `agentguard/sdk/` | Minimal install footprint |
| Type hints on public API | `def func(x: str) -> int:` | IDE support, documentation |
| Docstrings on public functions | Explain WHY, not just WHAT | Auto-generated docs |
| Deterministic examples | Fixed seeds, no random output | Docs match reality |

### Testing
| Practice | Tool | Why |
|----------|------|-----|
| Unit tests per module | pytest | Catch regressions |
| Integration roundtrip | pytest | Verify full pipeline |
| Property-based tests | hypothesis | Find edge cases humans miss |
| Stress tests | pytest + timing | Ensure analysis scales |
| Viewer fidelity tests | pytest + HTML parsing | Viewer matches analysis |

### AI-Assisted Development Loop (Ralph Loop)
| Principle | Implementation |
|-----------|---------------|
| Design docs are authoritative | GUARDRAILS.md, current-state-review — code must match |
| Every change gets thorough review | Reviewer reads REVIEW.md checklist, cites GUARDRAILS Q# |
| Generator must cite design docs | State Q# alignment before coding |
| Self-improvement every N iterations | Analyze REJECT patterns, adjust approach |
| Skip after 3 REJECTs | Prevent infinite loops; flag for human review |
| Auto-revert planner files | Generator can't modify program.md/progress.txt |
| Smoke test on startup | Verify first iteration before hands-off |

### Lessons Learned

1. **"Tests pass" ≠ "code is correct"** — Semantic correctness requires checking against design docs. Automated tests catch regressions but not direction drift.

2. **Fresh context agents forget feedback** — When using stateless generator agents, evaluator feedback must be explicitly injected into the next prompt. "Already done" is the most common false positive.

3. **Concurrent repo edits break the loop** — Never manually commit to the repo while the automated loop is running. The diff baseline becomes stale.

4. **Auto-revert must use baseline commit, not HEAD** — After generator commits, HEAD includes generator's changes. Reverting from HEAD is a no-op.

5. **Reviewer diff must exclude planner-owned files** — Otherwise, planner's own commits appear as generator changes and get auto-REJECTed.

6. **tmux sessions exit when the process exits** — Add a `read` or `sleep infinity` after the main process to keep the session alive for inspection.

7. **Production-grade ≠ feature count** — 15 well-tested modules > 40 shallow modules. Trace depth > feature breadth.

8. **Design doc contradictions cause 100% REJECT** — CLAUDE.md said "update program.md", REVIEW.md said "don't modify program.md" → every attempt was rejected. Check for contradictions before running.

9. **OpenClaw log cap breaks JSON parsing** — `[openclaw] log file size cap reached` prefix corrupts `--json` output. Filter it with grep.

10. **Gitignored files get re-tracked** — When a generator agent creates or modifies a gitignored file, `git add -A` re-tracks it. Keep dev tooling in the repo or use `git add --ignore-errors`.
