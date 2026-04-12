#!/bin/bash
# AgentGuard Ralph Loop v7
# Agent IDs (heihu=generator, luoshi=reviewer) are OpenClaw internal config.
#
# Changes from v6:
# - Reviewer reads FULL diff (not truncated) + design docs
# - Self-improvement review every 5 iterations
# - Skip story after 3 consecutive REJECTs
# - Confidence levels in review output
# - Production-grade focus
#
# Usage: ./ralph.sh [max-iterations] [max-hours]

set -e

MAX_ITERATIONS=${1:-100}
MAX_HOURS=${2:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_FILE="$PROJECT_DIR/.ralph-log.txt"
STATE_FILE="$PROJECT_DIR/.ralph-state.json"
START_TIME=$(date +%s)
MAX_SECONDS=$((MAX_HOURS * 3600))
MAX_REJECTS=3

# Resume
ITERATION=0
REJECT_COUNT=0
CURRENT_STORY=""
if [ -f "$STATE_FILE" ]; then
    ITERATION=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('iteration', 0))" 2>/dev/null || echo 0)
    REJECT_COUNT=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('reject_count', 0))" 2>/dev/null || echo 0)
    CURRENT_STORY=$(python3 -c "import json; print(json.load(open('$STATE_FILE')).get('current_story', ''))" 2>/dev/null || echo "")
    [ "$ITERATION" -gt 0 ] && echo "📂 Resuming from iteration $ITERATION (reject_count=$REJECT_COUNT)" | tee -a "$LOG_FILE"
fi

echo "🛡️ AgentGuard Ralph Loop v7 (production-grade)" | tee -a "$LOG_FILE"
echo "   Generator + Reviewer agents | Self-improvement every 5 iter" | tee -a "$LOG_FILE"
echo "   Max: $MAX_ITERATIONS iter / $MAX_HOURS hours | Skip after $MAX_REJECTS REJECTs" | tee -a "$LOG_FILE"
echo "   Started: $(date -u) (iter $ITERATION)" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

cd "$PROJECT_DIR"

save_state() {
    python3 -c "
import json
state = {
    'iteration': $ITERATION,
    'reject_count': $REJECT_COUNT,
    'current_story': '''$CURRENT_STORY''',
    'start_time': $START_TIME,
    'pid': $$,
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
    
    # Track reject count per story
    if [ "$NEXT_STORY" != "$CURRENT_STORY" ]; then
        REJECT_COUNT=0
        CURRENT_STORY="$NEXT_STORY"
    fi
    
    # Skip after MAX_REJECTS
    if [ $REJECT_COUNT -ge $MAX_REJECTS ]; then
        echo "⏭️ Skipping story after $MAX_REJECTS REJECTs: $NEXT_STORY" | tee -a "$LOG_FILE"
        echo "   Moving to next story. Feedback saved for manual review." | tee -a "$LOG_FILE"
        ESCAPED=$(echo "$NEXT_STORY" | sed 's/[&/\\.]/\\&/g')
        sed -i "s/^- \[ \] ${ESCAPED}/- [S] ${ESCAPED} (SKIPPED: ${MAX_REJECTS}x REJECT)/" program.md
        REJECT_COUNT=0
        CURRENT_STORY=""
        git add program.md && git commit -m "⏭️ skip: $NEXT_STORY (${MAX_REJECTS}x REJECT)" 2>/dev/null || true
        continue
    fi
    
    save_state
    
    echo "━━━ Iteration $ITERATION ($((ELAPSED/60))min elapsed) ━━━" | tee -a "$LOG_FILE"
    echo "📋 Story: $NEXT_STORY (attempt $((REJECT_COUNT + 1))/$MAX_REJECTS)" | tee -a "$LOG_FILE"
    
    # Write story spec with full context
    cat > .story-current.md << STORYEOF
# Current Story

## Task
$NEXT_STORY

## Project Context
- Run tests: python3 -m pytest tests/ -q --tb=short
- Read CLAUDE.md for development rules
- Read GUARDRAILS.md for lines that must not be crossed
- Read docs/current-state-review-zh.md for known issues and priorities

## Quality Bar: PRODUCTION-GRADE
This is NOT a demo. Every function must handle real failure modes.
- Error handling for edge cases
- Type hints on all public APIs
- Docstrings explaining WHY, not just WHAT
- Functions ≤ 50 lines
- Deterministic examples (fixed seeds)

## MANDATORY: Design Document Alignment
Before writing ANY code, you MUST:
1. Read GUARDRAILS.md — state which Q# (Q1-Q5) this story serves
2. Read docs/current-state-review-zh.md — state which section is relevant
3. If your code contradicts either document, STOP and reconsider

## Task Decomposition
Before writing code, decompose this story into concrete steps:
1. Which GUARDRAILS Question does this serve? (Q1-Q5 or infra/docs)
2. What exactly needs to change?
3. Which files need modification?
4. What edge cases exist?
5. What tests are needed?

## Previous Evaluator Feedback
$(cat .evaluator-feedback.txt 2>/dev/null || echo "None — first attempt")

## Do NOT
- Add unrelated features
- Modify program.md, progress.txt, REVIEW.md, or GUARDRAILS.md (these are Planner-owned files)
- Overstate capabilities in docs
- Write demo-quality code
- Import external packages in core/ or sdk/
STORYEOF
    
    # ── GENERATOR (agent: heihu) ──
    ITER_START=$(date +%s)
    BASELINE_COMMIT=$(git rev-parse HEAD)
    echo "🔧 Generator..." | tee -a "$LOG_FILE"
    
    GEN_RESULT=$(openclaw agent \
        --agent heihu \
        --session-id "gen-$ITERATION-$(date +%s)" \
        --message "Read $(pwd)/.story-current.md. 

CRITICAL RULES:
1. Read .story-current.md COMPLETELY — especially 'Previous Evaluator Feedback'
2. If there is feedback, you MUST address every point. Do NOT resubmit the same code.
3. Do NOT modify program.md or progress.txt (Planner's files — auto-REJECT)
4. Read GUARDRAILS.md — identify which of the 5 Questions this story serves
5. Read docs/current-state-review-zh.md — check known issues and priorities
6. Decompose the task: what files, what edge cases, what tests
7. Functions must be ≤ 50 lines — extract helpers
8. Quality bar: production-grade, NOT demo
9. Run tests, commit.

YOUR OUTPUT MUST INCLUDE:
- GUARDRAILS alignment: which Q# (Q1-Q5) this serves, or 'infra/docs'
- current-state-review: which section is relevant
- Task decomposition: concrete steps before coding
- What changed, which edge cases handled" \
        --timeout 300 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    GEN_TEXT=$(echo "$GEN_RESULT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for p in d.get('result',{}).get('payloads',[]): print(p.get('text',''))
except: print('GEN_ERROR')
" 2>/dev/null)
    echo "$GEN_TEXT" | head -20 | tee -a "$LOG_FILE"
    
    # ── AUTO-REVERT PLANNER FILES (generator should not touch these) ──
    git checkout $BASELINE_COMMIT -- progress.txt 2>/dev/null || true
    git checkout $BASELINE_COMMIT -- program.md 2>/dev/null || true
    git checkout $BASELINE_COMMIT -- REVIEW.md 2>/dev/null || true
    git checkout $BASELINE_COMMIT -- GUARDRAILS.md 2>/dev/null || true
    # Re-add and amend if anything was reverted
    if ! git diff --cached --quiet 2>/dev/null || ! git diff --quiet -- progress.txt program.md REVIEW.md GUARDRAILS.md 2>/dev/null; then
        git add progress.txt program.md REVIEW.md GUARDRAILS.md 2>/dev/null || true
        git commit --amend --no-edit 2>/dev/null || true
    fi
    
    # ── TESTS ──
    source "$PROJECT_DIR/.venv/bin/activate"
    TEST_RESULT=$(python3 -m pytest tests/ -q --tb=short 2>&1 | tail -3)
    TEST_SUMMARY=$(echo "$TEST_RESULT" | tail -1)
    echo "🧪 Tests: $TEST_SUMMARY" | tee -a "$LOG_FILE"
    
    # ── REVIEWER (agent: luoshi) (full diff, design doc alignment) ──
    echo "🔍 Reviewer..." | tee -a "$LOG_FILE"
    
    # Diff against baseline (before generator ran), not HEAD~1
    # Exclude planner-owned files from diff to avoid false REJECTs
    DIFF_STAT=$(git diff $BASELINE_COMMIT --stat -- . ':!progress.txt' ':!program.md' ':!REVIEW.md' ':!GUARDRAILS.md' 2>/dev/null)
    DIFF_FULL=$(git diff $BASELINE_COMMIT -- "*.py" "*.md" ':!progress.txt' ':!program.md' ':!REVIEW.md' ':!GUARDRAILS.md' 2>/dev/null | head -300)
    
    # If no changes (excluding planner files), generator did nothing
    if [ -z "$DIFF_STAT" ]; then
        echo "   ⚠️ Generator made no changes" | tee -a "$LOG_FILE"
        REJECT_COUNT=$((REJECT_COUNT + 1))
        echo "   ❌ NO CHANGES ($REJECT_COUNT/$MAX_REJECTS)" | tee -a "$LOG_FILE"
        echo "Generator did not produce any code changes. Implement the story from scratch." > .evaluator-feedback.txt
        echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iter $ITERATION (0s): $NEXT_STORY — NO CHANGES" >> progress.txt
        git add -A && git push 2>/dev/null || true
        save_state
        sleep 2
        continue
    fi
    
    EVAL_RESULT=$(openclaw agent \
        --agent luoshi \
        --session-id "rev-$ITERATION-$(date +%s)" \
        --message "REVIEW for AgentGuard. Read $(pwd)/REVIEW.md first.

Story: '$NEXT_STORY'
Attempt: $((REJECT_COUNT + 1))/$MAX_REJECTS

Generator report:
$(echo "$GEN_TEXT" | head -10)

Files changed:
$DIFF_STAT

Tests: $TEST_SUMMARY

Full diff:
$DIFF_FULL

REQUIRED STEPS (do ALL):
1. Read $(pwd)/REVIEW.md checklist — walk through every item
2. Read $(pwd)/GUARDRAILS.md — verify change serves at least one of the 5 Questions
3. Read $(pwd)/docs/current-state-review-zh.md — check against known issues and priorities
4. Verify production quality (error handling, types, edge cases)
5. State confidence level: HIGH/MEDIUM/LOW

YOUR REPLY MUST INCLUDE:
- Which of the 5 GUARDRAILS Questions this change serves (Q1-Q5, or 'infra/docs')
- Whether it aligns with current-state-review priorities (cite specific section)
- Specific evidence for ACCEPT/REJECT (not just 'looks good')

Format:
ACCEPT: [reason] | GUARDRAILS: [Q1-Q5 or infra] | Review: [section ref] | Confidence: [level]
or:
REJECT: [issue + doc reference]. Fix: [action] | Confidence: [level]" \
        --timeout 120 \
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
        if echo "$TEST_SUMMARY" | grep -q "passed"; then
            ESCAPED=$(echo "$NEXT_STORY" | sed 's/[&/\\.]/\\&/g')
            sed -i "s/^- \[ \] ${ESCAPED}/- [x] ${ESCAPED}/" program.md
            echo "   ✅ ACCEPTED" | tee -a "$LOG_FILE"
            rm -f .evaluator-feedback.txt
            REJECT_COUNT=0
            git add -A && git commit -m "✅ done: $NEXT_STORY" 2>/dev/null || true
        fi
    else
        REJECT_COUNT=$((REJECT_COUNT + 1))
        echo "   ❌ REJECTED ($REJECT_COUNT/$MAX_REJECTS)" | tee -a "$LOG_FILE"
        echo "$EVAL_TEXT" > .evaluator-feedback.txt
    fi
    
    # ── SELF-IMPROVEMENT: every 5 iterations ──
    if [ $((ITERATION % 5)) -eq 0 ]; then
        echo "🔄 Self-improvement review..." | tee -a "$LOG_FILE"
        
        RECENT_LOG=$(tail -50 "$LOG_FILE")
        
        IMPROVE_RESULT=$(openclaw agent \
            --session-id "self-improve-$ITERATION" \
            --message "You are reviewing the last 5 iterations of the AgentGuard development loop.

Recent log:
$RECENT_LOG

Questions to answer:
1. What patterns are causing REJECTs? How to fix the root cause?
2. Are stories well-decomposed or too vague?
3. Is code quality trending up or down?
4. Are we drifting from GUARDRAILS.md direction?
5. What should change in the next 5 iterations?

Be specific and actionable. No generic advice." \
            --timeout 90 \
            --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
        
        IMPROVE_TEXT=$(echo "$IMPROVE_RESULT" | python3 -c "
import sys,json
try:
    d=json.load(sys.stdin)
    for p in d.get('result',{}).get('payloads',[]): print(p.get('text',''))
except: print('IMPROVE_ERROR')
" 2>/dev/null)
        echo "   Improvement notes:" | tee -a "$LOG_FILE"
        echo "$IMPROVE_TEXT" | head -15 | tee -a "$LOG_FILE"
    fi
    
    # Log + push
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iter $ITERATION (${ITER_DURATION}s): $NEXT_STORY — $TEST_SUMMARY — $(echo "$EVAL_TEXT" | head -1)" >> progress.txt
    git add -A && git push 2>/dev/null || true
    save_state
    
    echo "" | tee -a "$LOG_FILE"
    sleep 2
done

# Summary
TOTAL=$(( $(date +%s) - START_TIME ))
echo "━━━ Done ━━━" | tee -a "$LOG_FILE"
echo "Iterations: $ITERATION | Time: $((TOTAL/60))min" | tee -a "$LOG_FILE"
echo "Tests: $(source $PROJECT_DIR/.venv/bin/activate && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)" | tee -a "$LOG_FILE"
echo "Commits: $(git log --oneline | wc -l)" | tee -a "$LOG_FILE"

rm -f "$STATE_FILE"
