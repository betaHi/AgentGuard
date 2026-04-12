#!/bin/bash
# AgentGuard Ralph Loop — 黑虎虾 🐯 as Generator
#
# Architecture:
#   基围小小虾 (main) = Planner + Evaluator (only needed for direction changes)
#   黑虎虾 (heihu)    = Generator (fresh context per story)
#   ralph.sh          = Harness (runs independently, no agent context needed)
#
# Usage: ./ralph.sh [max-iterations] [max-hours]
# Example: ./ralph.sh 100 10    # max 100 iterations or 10 hours

set -e

MAX_ITERATIONS=${1:-100}
MAX_HOURS=${2:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ITERATION=0
START_TIME=$(date +%s)
MAX_SECONDS=$((MAX_HOURS * 3600))
LOG_FILE="$PROJECT_DIR/.ralph-log.txt"

echo "🛡️ AgentGuard Ralph Loop" | tee -a "$LOG_FILE"
echo "   Generator: 🐯 黑虎虾 (heihu agent)" | tee -a "$LOG_FILE"
echo "   Max iterations: $MAX_ITERATIONS" | tee -a "$LOG_FILE"
echo "   Max hours: $MAX_HOURS" | tee -a "$LOG_FILE"
echo "   Started: $(date -u)" | tee -a "$LOG_FILE"
echo "   Log: $LOG_FILE" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    
    # Check time limit
    ELAPSED=$(( $(date +%s) - START_TIME ))
    ELAPSED_MIN=$((ELAPSED / 60))
    ELAPSED_HR=$((ELAPSED / 3600))
    REMAINING=$(( MAX_SECONDS - ELAPSED ))
    
    if [ $ELAPSED -ge $MAX_SECONDS ]; then
        echo "⏰ Time limit reached ($MAX_HOURS hours)" | tee -a "$LOG_FILE"
        break
    fi
    
    # Find next unchecked story
    NEXT_STORY=$(grep -m1 '^\- \[ \]' program.md 2>/dev/null | sed 's/^- \[ \] //')
    
    if [ -z "$NEXT_STORY" ]; then
        echo "✅ All stories complete!" | tee -a "$LOG_FILE"
        break
    fi
    
    echo "━━━ Iteration $ITERATION/$MAX_ITERATIONS (${ELAPSED_MIN}min elapsed, ${REMAINING}s remaining) ━━━" | tee -a "$LOG_FILE"
    echo "📋 Story: $NEXT_STORY" | tee -a "$LOG_FILE"
    
    # Write story spec
    cat > .story-current.md << STORYEOF
# Current Story

## Task
$NEXT_STORY

## Project
- Dir: $PROJECT_DIR
- Venv: source $PROJECT_DIR/.venv/bin/activate
- Test: cd $PROJECT_DIR && source .venv/bin/activate && python3 -m pytest tests/ -q --tb=short
- Read CLAUDE.md for project rules
- Read GUARDRAILS.md for constraints

## Acceptance Criteria
- Implementation matches the story description exactly
- All tests pass (no regressions)
- Changes committed with descriptive message
- Minimal code changes — only what the story requires

## Do NOT
- Add new Python modules unless the story explicitly requires it
- Modify program.md or progress.txt
- Change unrelated code
STORYEOF
    
    # Spawn 黑虎虾 (fresh context = context reset)
    ITER_START=$(date +%s)
    echo "🐯 Dispatching to 黑虎虾..." | tee -a "$LOG_FILE"
    
    RESULT=$(openclaw agent \
        --agent heihu \
        --session-id "heihu-ralph-$ITERATION-$(date +%s)" \
        --message "Read $PROJECT_DIR/.story-current.md for your task. Implement it, run tests, commit, and report what you did." \
        --timeout 300 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    ITER_DURATION=$(( $(date +%s) - ITER_START ))
    
    # Show result
    echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for p in data.get('result', {}).get('payloads', []):
        text = p.get('text', '')
        print(text[:800])
        if len(text) > 800: print('...')
    print(f'Status: {data.get(\"status\", \"unknown\")}')
except Exception as e:
    print(f'Parse error: {e}')
" 2>/dev/null | tee -a "$LOG_FILE"
    
    # Verify tests
    echo "" | tee -a "$LOG_FILE"
    echo "🧪 Evaluator verifying..." | tee -a "$LOG_FILE"
    source "$PROJECT_DIR/.venv/bin/activate"
    TEST_RESULT=$(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
    echo "   Tests: $TEST_RESULT" | tee -a "$LOG_FILE"
    echo "   Iteration took: ${ITER_DURATION}s" | tee -a "$LOG_FILE"
    
    # Log progress (append-only)
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iter $ITERATION (${ITER_DURATION}s): $NEXT_STORY — $TEST_RESULT" >> progress.txt
    
    # Push changes from sub-agent
    git push 2>/dev/null || true
    
    echo "" | tee -a "$LOG_FILE"
    sleep 2
done

# Final summary
TOTAL_ELAPSED=$(( $(date +%s) - START_TIME ))
TOTAL_MIN=$((TOTAL_ELAPSED / 60))
TOTAL_HR=$((TOTAL_ELAPSED / 3600))

echo "" | tee -a "$LOG_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"
echo "🛡️ Ralph Loop Complete" | tee -a "$LOG_FILE"
echo "   Iterations: $ITERATION" | tee -a "$LOG_FILE"
echo "   Total time: ${TOTAL_MIN}min (${TOTAL_HR}h ${TOTAL_MIN}min)" | tee -a "$LOG_FILE"
echo "   Started: $(date -u -d @$START_TIME 2>/dev/null || date -r $START_TIME -u)" | tee -a "$LOG_FILE"
echo "   Ended: $(date -u)" | tee -a "$LOG_FILE"
echo "   Tests: $(source $PROJECT_DIR/.venv/bin/activate && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)" | tee -a "$LOG_FILE"
echo "   Commits: $(git log --oneline | wc -l)" | tee -a "$LOG_FILE"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━" | tee -a "$LOG_FILE"
