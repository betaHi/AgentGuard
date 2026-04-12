#!/bin/bash
# AgentGuard Ralph Loop v6
#
# Generator: 🐯 黑虎虾 (heihu) — fresh context per story
# Evaluator: 🔱 罗氏虾 (luoshi) — Code Review specialist, persistent session
# Evolve: every 5 iterations
# Recovery: session IDs saved to .ralph-state.json
#
# Usage: ./ralph.sh [max-iterations] [max-hours]
# Resume: ./ralph.sh (reads .ralph-state.json automatically)

set -e

MAX_ITERATIONS=${1:-100}
MAX_HOURS=${2:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$PROJECT_DIR/.ralph-log.txt"
STATE_FILE="$PROJECT_DIR/.ralph-state.json"
START_TIME=$(date +%s)
MAX_SECONDS=$((MAX_HOURS * 3600))

# ── Resume from state file if exists ──
ITERATION=0
if [ -f "$STATE_FILE" ]; then
    SAVED_ITER=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('iteration', 0))" 2>/dev/null || echo 0)
    if [ "$SAVED_ITER" -gt 0 ]; then
        ITERATION=$SAVED_ITER
        echo "📂 Resuming from iteration $ITERATION" | tee -a "$LOG_FILE"
    fi
fi

echo "🛡️ AgentGuard Ralph Loop v6" | tee -a "$LOG_FILE"
echo "   🐯 Generator: 黑虎虾 | 🔱 Evaluator: 罗氏虾" | tee -a "$LOG_FILE"
echo "   Max: $MAX_ITERATIONS iter / $MAX_HOURS hours" | tee -a "$LOG_FILE"
echo "   Started: $(date -u) (iter $ITERATION)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

# ── Save state function ──
save_state() {
    python3 -c "
import json
state = {
    'iteration': $ITERATION,
    'start_time': $START_TIME,
    'pid': $$,
    'last_story': '''$NEXT_STORY''',
    'timestamp': '$(date -u +%Y-%m-%dT%H:%M:%SZ)'
}
with open('$STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null
}

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    
    # Time check
    ELAPSED=$(( $(date +%s) - START_TIME ))
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
    
    # Save state (for recovery)
    save_state
    
    echo "━━━ Iteration $ITERATION ($((ELAPSED/60))min elapsed) ━━━" | tee -a "$LOG_FILE"
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

## Project Goals
- AgentGuard = multi-agent orchestration diagnostics (NOT generic LLM observability)
- Must answer: bottleneck? context loss? failure propagation? cost/yield? degradation?
- Trace depth > feature breadth
- README/examples/analysis/viewer must tell the same story

## Previous Evaluator Feedback
$(cat .evaluator-feedback.txt 2>/dev/null || echo "None")

## Acceptance Criteria
- Matches story spec exactly (not more, not less)
- All tests pass
- Minimal changes
- Committed with descriptive message

## Do NOT
- Add new modules unless story requires it
- Modify program.md or progress.txt
- Overstate capabilities
STORYEOF
    
    # ── GENERATOR: 黑虎虾 (fresh context) ──
    ITER_START=$(date +%s)
    echo "🐯 Generator..." | tee -a "$LOG_FILE"
    
    GEN_RESULT=$(openclaw agent \
        --agent heihu \
        --session-id "heihu-$ITERATION-$(date +%s)" \
        --message "Read $PROJECT_DIR/.story-current.md. Implement, test, commit. Report what changed." \
        --timeout 300 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    GEN_TEXT=$(echo "$GEN_RESULT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for p in d.get('result',{}).get('payloads',[]): print(p.get('text',''))
except: print('GEN_ERROR')
" 2>/dev/null)
    echo "$GEN_TEXT" | head -15 | tee -a "$LOG_FILE"
    
    # ── TESTS ──
    source "$PROJECT_DIR/.venv/bin/activate"
    TEST_RESULT=$(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
    echo "🧪 Tests: $TEST_RESULT" | tee -a "$LOG_FILE"
    
    # ── EVALUATOR: 罗氏虾 (persistent session — remembers context) ──
    echo "🔱 Evaluator (罗氏虾)..." | tee -a "$LOG_FILE"
    
    DIFF_SUMMARY=$(git diff HEAD~1 --stat 2>/dev/null | tail -5)
    DIFF_CONTENT=$(git diff HEAD~1 -- "*.py" 2>/dev/null | head -100)
    
    EVAL_RESULT=$(openclaw agent \
        --agent luoshi \
        --session-id "luoshi-ralph-eval" \
        --message "Code Review for AgentGuard story: '$NEXT_STORY'

Generator report: $(echo "$GEN_TEXT" | head -5)
Files: $DIFF_SUMMARY
Tests: $TEST_RESULT

Code diff (first 100 lines):
$DIFF_CONTENT

Review criteria:
1. Does change match story exactly? (not more, not less)
2. Is code quality acceptable? (patterns, types, docs)
3. Does it avoid feature sprawl? (GUARDRAILS: trace depth > breadth)
4. Are there bugs or missing edge cases?
5. Is any function implemented but NOT tested?

Reply ONLY: ACCEPT: [reason] or REJECT: [what to fix]" \
        --timeout 90 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    EVAL_TEXT=$(echo "$EVAL_RESULT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for p in d.get('result',{}).get('payloads',[]): print(p.get('text',''))
except: print('EVAL_ERROR')
" 2>/dev/null)
    echo "   $EVAL_TEXT" | tee -a "$LOG_FILE"
    
    ITER_DURATION=$(( $(date +%s) - ITER_START ))
    echo "   ⏱️ ${ITER_DURATION}s" | tee -a "$LOG_FILE"
    
    # ── ACCEPT/REJECT ──
    if echo "$EVAL_TEXT" | grep -qi "ACCEPT"; then
        if echo "$TEST_RESULT" | grep -q "passed"; then
            ESCAPED=$(echo "$NEXT_STORY" | sed 's/[&/\\.]/\\&/g')
            sed -i "s/^- \[ \] ${ESCAPED}/- [x] ${ESCAPED}/" program.md
            echo "   ✅ ACCEPTED" | tee -a "$LOG_FILE"
            rm -f .evaluator-feedback.txt
            git add program.md && git commit -m "✅ story done: $NEXT_STORY" 2>/dev/null || true
        fi
    else
        echo "   ❌ REJECTED" | tee -a "$LOG_FILE"
        echo "$EVAL_TEXT" > .evaluator-feedback.txt
    fi
    
    # ── EVOLVE: every 5 iterations ──
    if [ $((ITERATION % 5)) -eq 0 ]; then
        echo "🧬 Evolve: learning from recent traces..." | tee -a "$LOG_FILE"
        python3 -c "
from agentguard.evolve import EvolutionEngine
from agentguard.store import TraceStore
store = TraceStore()
traces = store.query(limit=5)
if traces:
    engine = EvolutionEngine()
    for t in traces:
        engine.learn(t)
    print(f'   Learned from {len(traces)} traces, {len(engine.kb.lessons)} lessons total')
" 2>/dev/null | tee -a "$LOG_FILE"
    fi
    
    # Log + push
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iter $ITERATION (${ITER_DURATION}s): $NEXT_STORY — $TEST_RESULT — $EVAL_TEXT" >> progress.txt
    git push 2>/dev/null || true
    save_state
    
    echo "" | tee -a "$LOG_FILE"
    sleep 2
done

# ── Summary ──
TOTAL=$(( $(date +%s) - START_TIME ))
echo "━━━ Done ━━━" | tee -a "$LOG_FILE"
echo "Iterations: $ITERATION | Time: $((TOTAL/60))min" | tee -a "$LOG_FILE"
echo "Tests: $(source $PROJECT_DIR/.venv/bin/activate && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)" | tee -a "$LOG_FILE"
echo "Commits: $(git log --oneline | wc -l)" | tee -a "$LOG_FILE"

# Clean state file on completion
rm -f "$STATE_FILE"
