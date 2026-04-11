#!/bin/bash
# AgentGuard Ralph Loop — self-iterating development loop
# 
# This script implements the Ralph Wiggum method:
# A simple loop that repeatedly feeds the program to an AI agent
# until the completion promise is met.
#
# Usage: ./ralph.sh [--max-iterations N]

set -e

MAX_ITERATIONS=${1:-50}
COMPLETION_PROMISE="LOOP_COMPLETE"
ITERATION=0
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🛡️ AgentGuard Ralph Loop starting"
echo "   Max iterations: $MAX_ITERATIONS"
echo "   Completion promise: $COMPLETION_PROMISE"
echo "   Project dir: $PROJECT_DIR"
echo ""

cd "$PROJECT_DIR"

while [ $ITERATION -lt $MAX_ITERATIONS ]; do
    ITERATION=$((ITERATION + 1))
    echo "━━━ Iteration $ITERATION/$MAX_ITERATIONS ━━━"
    
    # Run tests first
    PYTHONPATH="$PROJECT_DIR" python3 -m pytest tests/ -q 2>&1 || true
    
    # Check if there's work to do based on program.md
    # The agent reads program.md and decides what to do next
    
    # For now, we can trigger specific improvement tasks
    # In production, this would feed to an LLM agent
    
    echo "   Tests: $(PYTHONPATH=$PROJECT_DIR python3 -m pytest tests/ -q 2>&1 | tail -1)"
    echo "   Files: $(find agentguard -name '*.py' | wc -l) Python files"
    echo "   Lines: $(find agentguard -name '*.py' -exec cat {} + | wc -l) lines of code"
    
    # Check completion
    if grep -q "$COMPLETION_PROMISE" program.md 2>/dev/null; then
        echo "✅ Completion promise found. Loop complete."
        break
    fi
    
    sleep 2
done

echo ""
echo "🛡️ Ralph Loop finished after $ITERATION iterations"
