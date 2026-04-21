#!/usr/bin/env bash
# AgentGuard one-line installer.
#
#   curl -sSL https://raw.githubusercontent.com/betaHi/AgentGuard/main/install.sh | bash
#
# Requires `uv` (https://docs.astral.sh/uv). Install it first with:
#
#   curl -LsSf https://astral.sh/uv/install.sh | sh
#
# Also installs claude-agent-sdk so live capture works out of the box.
#
# Honors:
#   AGENTGUARD_GIT_REF    branch/tag/commit to install (default: main)
#   AGENTGUARD_PKG_SPEC   full pip/uv spec override
#   AGENTGUARD_NO_SDK=1   skip claude-agent-sdk
set -eu

ref="${AGENTGUARD_GIT_REF:-main}"
spec="${AGENTGUARD_PKG_SPEC:-git+https://github.com/betaHi/AgentGuard.git@${ref}}"

say() { printf '\033[36m[agentguard]\033[0m %s\n' "$*"; }
die() { printf '\033[31m[agentguard]\033[0m %s\n' "$*" >&2; exit 1; }

if command -v agentguard >/dev/null 2>&1; then
  say "already installed: $(command -v agentguard)"
  exit 0
fi

uv_bin=""
if command -v uv >/dev/null 2>&1; then
  uv_bin="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  uv_bin="$HOME/.local/bin/uv"
fi

if [ -z "$uv_bin" ]; then
  die "uv is required. Install it first:
  curl -LsSf https://astral.sh/uv/install.sh | sh"
fi

say "installing via uv ($spec)…"
if [ "${AGENTGUARD_NO_SDK:-0}" = "1" ]; then
  "$uv_bin" tool install "$spec"
else
  "$uv_bin" tool install "$spec" --with claude-agent-sdk
fi

say "done — try: agentguard list-claude-sessions --limit 5"
say "(ensure ~/.local/bin is on your PATH)"
