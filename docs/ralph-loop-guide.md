# How to Run Ralph Loop on AgentGuard

## What is Ralph Loop?

A simple bash loop that repeatedly feeds a task to an AI coding agent until completion. 
Named after Ralph Wiggum — "I may fail a lot, but I keep trying."

## Method 1: Claude Code + Ralph Plugin (Recommended)

```bash
# Install Claude Code
npm install -g @anthropic/claude-code

# Install Ralph Loop plugin
claude /plugin install ralph-loop@claude-plugins-official

# Start the loop
cd /path/to/AgentGuard
claude /ralph-loop:ralph-loop "Read CLAUDE.md and program.md. Pick the next priority item, implement it with tests, commit, and continue." --completion-promise "SPRINT_COMPLETE" --max-iterations 20
```

The loop will:
1. Read CLAUDE.md → program.md → GUARDRAILS.md
2. Pick the highest priority unfinished task
3. Write code + tests
4. Run pytest
5. Commit
6. Repeat until SPRINT_COMPLETE or max iterations

## Method 2: Manual Bash Loop (No Claude Code)

```bash
# Simple loop using any LLM CLI tool
cd /path/to/AgentGuard

while true; do
  cat CLAUDE.md program.md | your-llm-cli --prompt "Execute the next task"
  
  # Run tests
  python -m pytest tests/ -v
  if [ $? -ne 0 ]; then
    echo "Tests failed — loop will retry"
    continue
  fi
  
  # Commit
  git add -A && git commit -m "Ralph Loop iteration $(date +%H%M)"
  
  # Check completion
  if grep -q "SPRINT_COMPLETE" /tmp/last_output.txt; then
    echo "Sprint complete!"
    break
  fi
done
```

## Method 3: OpenClaw Cron (What We Actually Use)

Since AgentGuard is developed inside OpenClaw, we can use cron jobs:

```bash
# Create a cron job that runs the development loop every 30 minutes
openclaw cron create ralph-dev \
  --schedule "*/30 * * * *" \
  --agent main \
  --prompt "Read CLAUDE.md and program.md in the AgentGuard repo at /tmp/AgentGuard. Pick the next priority item, implement it with tests, run pytest, commit and push. If all current priorities are done, reply SPRINT_COMPLETE." \
  --delivery none \
  --max-iterations 1
```

## Method 4: GitHub Actions (Automated)

```yaml
# .github/workflows/ralph-loop.yml
name: Ralph Loop
on:
  workflow_dispatch:
  schedule:
    - cron: '0 */2 * * *'  # every 2 hours

jobs:
  iterate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: pip install pytest
      
      # Feed to Claude API
      - name: Run iteration
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: |
          # Call Claude API with CLAUDE.md + program.md as context
          # Parse response for code changes
          # Apply changes, run tests, commit if passing
          echo "TODO: implement API call"
      
      - name: Run tests
        run: python -m pytest tests/ -v
      
      - name: Commit if tests pass
        run: |
          git config user.name "Ralph Loop"
          git config user.email "ralph@agentguard.dev"
          git add -A
          git diff --cached --quiet || git commit -m "Ralph Loop: $(date -u +%Y-%m-%dT%H:%M)"
          git push
```

## Key Files the Loop Reads

| File | Purpose |
|------|---------|
| `CLAUDE.md` | Instructions for the AI agent (what to do, rules, completion promise) |
| `program.md` | Project direction, priorities, sprint plan |
| `GUARDRAILS.md` | Lines not to cross (prevents scope drift) |
| `.loops/sdk-progress.md` | SDK module progress (for scoped context) |
| `.loops/eval-progress.md` | Eval module progress |

## Multi-Loop Setup

For parallel development, run multiple loops with scoped context:

```bash
# Loop 1: SDK development
claude /ralph-loop:ralph-loop "Focus on agentguard/sdk/ and agentguard/core/. Read .loops/sdk-progress.md for context." --max-iterations 10

# Loop 2: Analysis development (separate terminal)
claude /ralph-loop:ralph-loop "Focus on agentguard/analysis.py. Read .loops/eval-progress.md for context." --max-iterations 10
```

Each loop only loads its relevant files to stay within context limits.

## Stop Conditions

The loop stops when:
1. Completion promise is found in output (`SPRINT_COMPLETE`)
2. Max iterations reached
3. Tests fail 3 consecutive times (safety net)
4. Manual cancellation (`/ralph-loop:cancel-ralph`)
