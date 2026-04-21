#!/usr/bin/env bash
# AgentGuard auto-bootstrap.
#
# Ensures `agentguard` is importable/runnable on the current machine without
# asking the user to run pip themselves. Called from:
#   - the SessionStart hook (one-shot, silent on success)
#   - the `bin/agentguard` launcher as a last-resort fallback
#
# Strategy (first success wins):
#   1. If agentguard is already resolvable, do nothing.
#   2. `pipx install` from the upstream git repo (puts it on PATH globally).
#      Also `pipx inject` claude-agent-sdk so live-capture works.
#   3. `python3 -m pip install --user` as a fallback.
#
# Honors:
#   - AGENTGUARD_AUTO_INSTALL=0   disables this bootstrap entirely
#   - AGENTGUARD_GIT_REF          branch/tag/commit to install (default: main)
#   - AGENTGUARD_PKG_SPEC         full pip spec override
#     (e.g. AGENTGUARD_PKG_SPEC="agentguard==0.2.0")
#
# Emits a one-time sentinel so repeated sessions don't re-trigger the install.
set -u

if [ "${AGENTGUARD_AUTO_INSTALL:-1}" = "0" ]; then
  exit 0
fi

# Already installed? Nothing to do.
if command -v agentguard >/dev/null 2>&1; then
  exit 0
fi
if command -v python3 >/dev/null 2>&1 && python3 -c "import agentguard" >/dev/null 2>&1; then
  exit 0
fi

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/agentguard"
mkdir -p "$state_dir" 2>/dev/null || true
sentinel="$state_dir/bootstrap.attempted"
log_file="$state_dir/bootstrap.log"

# One attempt per machine unless the user forces a retry.
if [ -f "$sentinel" ] && [ "${AGENTGUARD_FORCE_INSTALL:-0}" != "1" ]; then
  exit 0
fi
touch "$sentinel" 2>/dev/null || true

ref="${AGENTGUARD_GIT_REF:-main}"
spec="${AGENTGUARD_PKG_SPEC:-git+https://github.com/betaHi/AgentGuard.git@${ref}}"

{
  printf '[%s] AgentGuard bootstrap starting (spec=%s)\n' "$(date -Is)" "$spec"
} >>"$log_file" 2>&1 || true

# Route 1: pipx (best UX — isolated venv, goes on PATH).
if command -v pipx >/dev/null 2>&1; then
  if pipx install "$spec" >>"$log_file" 2>&1; then
    pipx inject agentguard claude-agent-sdk >>"$log_file" 2>&1 || true
    printf '[%s] pipx install succeeded\n' "$(date -Is)" >>"$log_file" 2>&1 || true
    exit 0
  fi
  printf '[%s] pipx install failed, falling back to pip --user\n' "$(date -Is)" >>"$log_file" 2>&1 || true
fi

# Route 2: pip install --user.
if command -v python3 >/dev/null 2>&1; then
  if python3 -m pip install --user --quiet "$spec" >>"$log_file" 2>&1; then
    python3 -m pip install --user --quiet claude-agent-sdk >>"$log_file" 2>&1 || true
    printf '[%s] pip --user install succeeded\n' "$(date -Is)" >>"$log_file" 2>&1 || true
    exit 0
  fi
fi

printf '[%s] bootstrap failed — see %s\n' "$(date -Is)" "$log_file" >&2
exit 1
