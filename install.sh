#!/usr/bin/env bash
# AgentGuard one-line installer.
#
#   curl -sSL https://raw.githubusercontent.com/betaHi/AgentGuard/main/install.sh | bash
#
# Resolution order (first success wins):
#   1. pipx install git+https://github.com/betaHi/AgentGuard.git (recommended)
#   2. python3 -m pip install --user
#
# Also installs claude-agent-sdk so live capture works out of the box.
#
# Honors:
#   AGENTGUARD_GIT_REF    branch/tag/commit to install (default: main)
#   AGENTGUARD_PKG_SPEC   full pip spec override
#   AGENTGUARD_NO_SDK=1   skip claude-agent-sdk
set -eu

ref="${AGENTGUARD_GIT_REF:-main}"
spec="${AGENTGUARD_PKG_SPEC:-git+https://github.com/betaHi/AgentGuard.git@${ref}}"

say() { printf '\033[36m[agentguard]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[agentguard]\033[0m %s\n' "$*" >&2; exit 1; }

if command -v agentguard >/dev/null 2>&1; then
  say "already installed: $(command -v agentguard)"
  say "run: agentguard --help"
  exit 0
fi

# Route 1: pipx.
if command -v pipx >/dev/null 2>&1; then
  say "installing via pipx ($spec)…"
  pipx install "$spec"
  if [ "${AGENTGUARD_NO_SDK:-0}" != "1" ]; then
    pipx inject agentguard claude-agent-sdk || true
  fi
  say "done — try: agentguard list-claude-sessions --limit 5"
  exit 0
fi

# Route 2: pip --user.
if command -v python3 >/dev/null 2>&1; then
  say "pipx not found; falling back to pip --user ($spec)…"
  python3 -m pip install --user "$spec"
  if [ "${AGENTGUARD_NO_SDK:-0}" != "1" ]; then
    python3 -m pip install --user claude-agent-sdk || true
  fi
  user_bin="$(python3 -c 'import site,sys; print(site.getuserbase()+"/bin")' 2>/dev/null || echo "")"
  case ":$PATH:" in
    *":$user_bin:"*) : ;;
    *) say "note: $user_bin is not on PATH; add it to use the 'agentguard' command." ;;
  esac
  say "done — try: agentguard list-claude-sessions --limit 5"
  exit 0
fi

die "need either pipx or python3 on PATH"
