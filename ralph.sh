#!/bin/bash
# AgentGuard Ralph Loop — with proper Evaluator
#
# Architecture:
#   黑虎虾 (heihu)  = Generator (fresh context per story)
#   Evaluator       = separate sub-agent that reviews against docs/goals
#   ralph.sh        = Harness
#
# Usage: ./ralph.sh [max-iterations] [max-hours]

set -e

MAX_ITERATIONS=${1:-100}
MAX_HOURS=${2:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ITERATION=0
START_TIME=$(date +%s)
MAX_SECONDS=$((MAX_HOURS * 3600))
LOG_FILE="$PROJECT_DIR/.ralph-log.txt"

echo "🛡️ AgentGuard Ralph Loop (Generator + Evaluator)" | tee -a "$LOG_FILE"
echo "   Generator: 🐯 黑虎虾 | Evaluator: 🔱 review agent" | tee -a "$LOG_FILE"
echo "   Max: $MAX_ITERATIONS iterations / $MAX_HOURS hours" | tee -a "$LOG_FILE"
echo "   Started: $(date -u)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    
    # Time check
    ELAPSED=$(( $(date +%s) - START_TIME ))
    REMAINING=$(( MAX_SECONDS - ELAPSED ))
    if [ $ELAPSED -ge $MAX_SECONDS ]; then
        echo "⏰ Time limit ($MAX_HOURS hours)" | tee -a "$LOG_FILE"
        break
    fi
    
    # Find next story
    NEXT_STORY=$(grep -m1 '^\- \[ \]' program.md 2>/dev/null | sed 's/^- \[ \] //')
    if [ -z "$NEXT_STORY" ]; then
        echo "✅ All stories complete!" | tee -a "$LOG_FILE"
        break
    fi
    
    echo "━━━ Iteration $ITERATION ($((ELAPSED/60))min elapsed) ━━━" | tee -a "$LOG_FILE"
    echo "📋 Story: $NEXT_STORY" | tee -a "$LOG_FILE"
    
    # Write story spec with project context
    cat > .story-current.md << STORYEOF
# Current Story

## Task
$NEXT_STORY

## Project Context
- Dir: $PROJECT_DIR
- Venv: source $PROJECT_DIR/.venv/bin/activate
- Test: cd $PROJECT_DIR && source .venv/bin/activate && python3 -m pytest tests/ -q --tb=short
- Read CLAUDE.md for project rules
- Read GUARDRAILS.md for constraints
- Read docs/current-state-review-zh.md section 7 for known issues to avoid

## Project Goals (from README + docs)
- AgentGuard = observability for multi-agent orchestration
- Core value: trace schema + low-intrusion SDK + orchestration diagnostics
- NOT a generic LLM observability tool
- Trace depth > feature breadth
- README, examples, analysis, viewer must tell the same story

## Acceptance Criteria
- Implementation matches the story description exactly
- All tests pass (pytest, no regressions)
- Code follows existing patterns (zero external deps for core, English code/docs)
- Changes committed with descriptive message
- Minimal changes — only what the story requires

## Do NOT
- Add new Python modules unless the story explicitly requires it
- Modify program.md or progress.txt
- Change unrelated code
- Overstate capabilities in docs
STORYEOF
    
    # ── GENERATOR: 黑虎虾 ──
    ITER_START=$(date +%s)
    echo "🐯 Generator: 黑虎虾..." | tee -a "$LOG_FILE"
    
    GEN_RESULT=$(openclaw agent \
        --agent heihu \
        --session-id "heihu-gen-$ITERATION-$(date +%s)" \
        --message "Read $PROJECT_DIR/.story-current.md. Implement the story, run tests, commit. Report: what changed, which files, test results." \
        --timeout 300 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    GEN_TEXT=$(echo "$GEN_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for p in data.get('result', {}).get('payloads', []):
        print(p.get('text', ''))
except: print('PARSE_ERROR')
" 2>/dev/null)
    
    echo "$GEN_TEXT" | head -20 | tee -a "$LOG_FILE"
    
    # ── TESTS ──
    echo "" | tee -a "$LOG_FILE"
    source "$PROJECT_DIR/.venv/bin/activate"
    TEST_RESULT=$(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
    echo "🧪 Tests: $TEST_RESULT" | tee -a "$LOG_FILE"
    
    # ── EVALUATOR: separate agent reviews the change ──
    echo "🔱 Evaluator reviewing..." | tee -a "$LOG_FILE"
    
    # Get the diff for review
    DIFF_SUMMARY=$(git diff HEAD~1 --stat 2>/dev/null | tail -5)
    
    EVAL_RESULT=$(openclaw agent \
        --session-id "eval-$ITERATION-$(date +%s)" \
        --message "You are a code review evaluator for AgentGuard. 

Story was: '$NEXT_STORY'

Generator reported: $(echo "$GEN_TEXT" | head -10)

Files changed: $DIFF_SUMMARY

Tests: $TEST_RESULT

Evaluate against these criteria:
1. Does the change match the story spec exactly? (not more, not less)
2. Does it align with project goals? (observability for multi-agent orchestration, not feature sprawl)
3. Does it avoid overstatements or promises the code doesn't deliver?
4. Is the code quality acceptable? (follows existing patterns)

Reply with ONLY one of:
- ACCEPT: [one-line reason]
- REJECT: [one-line reason and what to fix]" \
        --timeout 60 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    EVAL_TEXT=$(echo "$EVAL_RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for p in data.get('result', {}).get('payloads', []):
        print(p.get('text', ''))
except: print('EVAL_ERROR')
" 2>/dev/null)
    
    echo "   $EVAL_TEXT" | tee -a "$LOG_FILE"
    
    ITER_DURATION=$(( $(date +%s) - ITER_START ))
    echo "   ⏱️ ${ITER_DURATION}s" | tee -a "$LOG_FILE"
    
    # ── ACCEPT/REJECT ──
    if echo "$EVAL_TEXT" | grep -qi "ACCEPT"; then
        # Mark story done
        if echo "$TEST_RESULT" | grep -q "passed"; then
            ESCAPED=$(echo "$NEXT_STORY" | sed 's/[&/\\.]/\\&/g')
            sed -i "s/^- \[ \] ${ESCAPED}/- [x] ${ESCAPED}/" program.md
            echo "   ✅ ACCEPTED + marked done" | tee -a "$LOG_FILE"
            git add program.md && git commit -m "mark done: $NEXT_STORY" 2>/dev/null || true
        fi
    else
        echo "   ❌ REJECTED — will retry next iteration" | tee -a "$LOG_FILE"
        # Revert the generator's commit so next iteration can try again
        git revert HEAD --no-edit 2>/dev/null || true
    fi
    
    # Log
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iter $ITERATION (${ITER_DURATION}s): $NEXT_STORY — Tests: $TEST_RESULT — Eval: $EVAL_TEXT" >> progress.txt
    
    git push 2>/dev/null || true
    echo "" | tee -a "$LOG_FILE"
    sleep 2
done

# Summary
TOTAL=$(( $(date +%s) - START_TIME ))
echo "━━━ Done ━━━" | tee -a "$LOG_FILE"
echo "Iterations: $ITERATION | Time: $((TOTAL/60))min | Tests: $(source $PROJECT_DIR/.venv/bin/activate && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1) | Commits: $(git log --oneline | wc -l)" | tee -a "$LOG_FILE"
