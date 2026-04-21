#!/usr/bin/env bash
# AgentGuard SessionEnd hook: run a dense diagnosis for the just-ended Claude
# session in the background, so it never blocks the terminal and always lands
# as artifacts the user can open later.
set -u

launcher="${CLAUDE_PLUGIN_ROOT:-$(dirname "$0")/..}/bin/agentguard"
if [ ! -x "$launcher" ]; then
  # Degrade to whatever is on PATH so the hook never crashes a session exit.
  launcher="$(command -v agentguard 2>/dev/null || true)"
fi

# Skip silently when agentguard truly cannot be resolved.
if [ -z "$launcher" ] || [ ! -x "$launcher" ]; then
  exit 0
fi

payload=$(cat || true)
session_id=$(
  printf '%s' "$payload" | python3 -c '
import json, sys
try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(0)
sid = data.get("session_id") or ""
print(sid)
' 2>/dev/null || true
)

if [ -z "${session_id}" ]; then
  exit 0
fi

reports_dir=".agentguard/reports"
traces_dir=".agentguard/traces"
mkdir -p "$reports_dir" "$traces_dir"

log_file="${reports_dir}/${session_id}.txt"
trace_file="${traces_dir}/${session_id}.json"
html_file="${reports_dir}/${session_id}.html"

nohup "$launcher" diagnose-claude-session "$session_id" \
  --output "$trace_file" \
  --report-output "$html_file" \
  >"$log_file" 2>&1 &

exit 0
