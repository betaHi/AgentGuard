#!/bin/bash
# Launch ralph.sh in tmux with startup verification
#
# Usage: ./run-ralph.sh [max-iterations] [max-hours]

MAX_ITER=${1:-100}
MAX_HOURS=${2:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Kill existing
tmux kill-session -t ralph 2>/dev/null

# Clear old logs
> "$PROJECT_DIR/.ralph-log.txt"

# Start in tmux
tmux new-session -d -s ralph "cd $PROJECT_DIR && ./ralph.sh $MAX_ITER $MAX_HOURS"

echo "🛡️ Ralph v7 launched in tmux session 'ralph'"
echo ""
echo "⏳ Waiting for first iteration to complete (smoke test)..."
echo ""

# SMOKE TEST: wait for first iteration result
TIMEOUT=300
ELAPSED=0
while [ $ELAPSED -lt $TIMEOUT ]; do
    sleep 10
    ELAPSED=$((ELAPSED + 10))
    
    # Check if first iteration completed
    if grep -q "Iteration 1.*━━━" "$PROJECT_DIR/.ralph-log.txt" 2>/dev/null && \
       (grep -q "ACCEPTED\|REJECTED" "$PROJECT_DIR/.ralph-log.txt" 2>/dev/null); then
        echo "━━━ First iteration result ━━━"
        # Show first iteration
        sed -n '/Iteration 1/,/Iteration 2\|━━━ Done/p' "$PROJECT_DIR/.ralph-log.txt" | head -30
        echo ""
        
        if grep -q "REJECTED" "$PROJECT_DIR/.ralph-log.txt" 2>/dev/null; then
            echo "⚠️  FIRST ITERATION REJECTED — review the feedback above."
            echo "   If this looks like a systemic issue, STOP and fix before continuing."
            echo ""
            echo "   Stop:  tmux send-keys -t ralph C-c"
            echo "   Logs:  tail -f .ralph-log.txt"
        else
            echo "✅ First iteration ACCEPTED — loop is healthy."
            echo ""
            echo "   Monitor: tmux attach -t ralph"
            echo "   Logs:    tail -f .ralph-log.txt"
            echo "   Stop:    tmux send-keys -t ralph C-c"
        fi
        exit 0
    fi
    
    echo "   ... waiting (${ELAPSED}s / ${TIMEOUT}s)"
done

echo "⏰ Timeout: first iteration didn't complete in ${TIMEOUT}s"
echo "   Check: tail -20 .ralph-log.txt"
