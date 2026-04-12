#!/bin/bash
# AgentGuard Ralph Loop — 黑虎虾 🐯 as Generator
#
# Architecture:
#   基围小小虾 (main) = Planner + Evaluator
#   黑虎虾 (heihu)    = Generator (fresh context per story)
#
# Each iteration:
# 1. Read program.md for next unchecked story
# 2. Write story spec to .story-current.md
# 3. Spawn 黑虎虾 (fresh context) to implement it
# 4. Verify tests pass
# 5. Update progress.txt
# 6. Repeat

set -e

MAX_ITERATIONS=${1:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ITERATION=0

echo "🛡️ AgentGuard Ralph Loop"
echo "   Generator: 🐯 黑虎虾 (heihu agent)"
echo "   Max iterations: $MAX_ITERATIONS"
echo "   Project: $PROJECT_DIR"
echo ""

cd "$PROJECT_DIR"

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    
    # Find next unchecked story
    NEXT_STORY=$(grep -m1 '^\- \[ \]' program.md 2>/dev/null | sed 's/^- \[ \] //')
    
    if [ -z "$NEXT_STORY" ]; then
        echo "✅ All stories complete!"
        break
    fi
    
    echo "━━━ Iteration $ITERATION/$MAX_ITERATIONS ━━━"
    echo "📋 Story: $NEXT_STORY"
    
    # Write story spec
    cat > .story-current.md << STORYEOF
# Current Story

## Task
$NEXT_STORY

## Project
- Dir: $PROJECT_DIR
- Venv: source $PROJECT_DIR/.venv/bin/activate
- Test: cd $PROJECT_DIR && python3 -m pytest tests/ -q --tb=short
- Read CLAUDE.md for project rules

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
    echo "🐯 Dispatching to 黑虎虾..."
    RESULT=$(openclaw agent \
        --agent heihu \
        --session-id "heihu-ralph-$ITERATION-$(date +%s)" \
        --message "Read $PROJECT_DIR/.story-current.md for your task. Implement it, run tests, commit, and report what you did." \
        --timeout 300 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    # Show result
    echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for p in data.get('result', {}).get('payloads', []):
        text = p.get('text', '')
        # Show first 600 chars
        print(text[:600])
        if len(text) > 600: print('...')
    print(f'Status: {data.get(\"status\", \"unknown\")}')
except Exception as e:
    print(f'Parse error: {e}')
" 2>/dev/null
    
    # Verify tests
    echo ""
    echo "🧪 Evaluator verifying..."
    source "$PROJECT_DIR/.venv/bin/activate"
    TEST_RESULT=$(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
    echo "   Tests: $TEST_RESULT"
    
    # Log progress
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iter $ITERATION: $NEXT_STORY — $TEST_RESULT" >> progress.txt
    
    echo ""
    sleep 2
done

echo ""
echo "━━━ Ralph Loop Complete ━━━"
echo "   Iterations: $ITERATION"
echo "   Tests: $(source $PROJECT_DIR/.venv/bin/activate && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)"
echo "   Commits: $(git log --oneline | wc -l)"
