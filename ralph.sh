#!/bin/bash
# AgentGuard Ralph Loop — using OpenClaw sub-agents
#
# Each iteration:
# 1. Read program.md for next unchecked story
# 2. Spawn a fresh sub-agent (context reset) to implement it
# 3. Evaluate the result
# 4. Update checklist + progress.txt
# 5. Repeat
#
# Usage: ./ralph.sh [max-iterations]

set -e

MAX_ITERATIONS=${1:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
ITERATION=0

echo "🛡️ AgentGuard Ralph Loop (OpenClaw sub-agents)"
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
    echo ""
    
    # Write story spec
    cat > .story-current.md << STORYEOF
# Current Story

## Task
$NEXT_STORY

## Context
- Project: AgentGuard (multi-agent observability framework)
- Dir: $PROJECT_DIR
- Read CLAUDE.md for project rules
- Read GUARDRAILS.md for constraints

## Acceptance Criteria
- Implementation matches the story description
- All tests pass: python3 -m pytest tests/ -q
- Changes committed with descriptive message

## Rules
- Only modify files relevant to this story
- Do NOT add new modules unless the story requires it
- Run tests before committing
STORYEOF
    
    # Spawn sub-agent (fresh context)
    echo "🤖 Spawning sub-agent..."
    RESULT=$(openclaw agent \
        --session-id "ralph-iter-$ITERATION" \
        --message "You are a coding agent. Read /home/azureuser/AgentGuard/.story-current.md for your task. Read CLAUDE.md and GUARDRAILS.md for rules. Implement the story, run tests, and commit. Report what you did." \
        --timeout 300 \
        --json 2>&1 | grep -v "Config warnings\|plugins\|Registered")
    
    echo "$RESULT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    status = data.get('status', 'unknown')
    for p in data.get('result', {}).get('payloads', []):
        print(p.get('text', '')[:500])
    print(f'\nStatus: {status}')
except:
    print('Failed to parse result')
" 2>/dev/null
    
    # Run tests to verify
    echo ""
    echo "🧪 Verifying..."
    TEST_RESULT=$(cd "$PROJECT_DIR" && python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)
    echo "   Tests: $TEST_RESULT"
    
    # Append to progress
    echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Iteration $ITERATION: $NEXT_STORY — Tests: $TEST_RESULT" >> progress.txt
    
    echo ""
    sleep 2
done

echo ""
echo "🛡️ Ralph Loop finished after $ITERATION iterations"
echo "   Tests: $(python3 -m pytest tests/ -q --tb=no 2>&1 | tail -1)"
echo "   Commits: $(git log --oneline | wc -l)"
