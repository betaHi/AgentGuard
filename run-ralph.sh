#!/bin/bash
# Robust Ralph runner — survives all disconnections
#
# Uses tmux session that persists independently of:
# - OpenClaw session timeout
# - SSH disconnect  
# - Terminal close
# - Main agent compaction
#
# Usage: ./run-ralph.sh [max-iterations] [max-hours]
# Monitor: tmux attach -t ralph
# Stop: tmux send-keys -t ralph C-c

SESSION="ralph"
MAX_ITER=${1:-100}
MAX_HOURS=${2:-10}

# Kill existing session if any
tmux kill-session -t $SESSION 2>/dev/null

# Start new tmux session running ralph.sh
tmux new-session -d -s $SESSION "cd $(pwd) && ./ralph.sh $MAX_ITER $MAX_HOURS; echo 'RALPH DONE'; sleep 99999"

echo "🐯 Ralph running in tmux session '$SESSION'"
echo ""
echo "Commands:"
echo "  Monitor:  tmux attach -t ralph"
echo "  Status:   tail -f .ralph-log.txt"
echo "  Stop:     tmux send-keys -t ralph C-c"
echo "  Kill:     tmux kill-session -t ralph"
echo ""
echo "This survives: SSH disconnect, OpenClaw session timeout, agent compaction."
