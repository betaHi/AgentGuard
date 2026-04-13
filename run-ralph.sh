#!/bin/bash
# Launch ralph.sh in tmux — session stays alive even after ralph exits
MAX_ITER=${1:-200}
MAX_HOURS=${2:-10}
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

tmux kill-session -t ralph 2>/dev/null
> "$PROJECT_DIR/.ralph-log.txt"

# Use bash -c with a trap to keep session alive
tmux new-session -d -s ralph "cd $PROJECT_DIR && ./ralph.sh $MAX_ITER $MAX_HOURS; echo ''; echo 'Ralph finished. Session kept alive.'; echo 'Press Enter to close.'; read"

echo "Ralph launched in tmux session 'ralph'"
