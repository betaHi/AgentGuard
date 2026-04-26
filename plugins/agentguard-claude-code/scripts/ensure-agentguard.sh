#!/usr/bin/env bash
# AgentGuard auto-bootstrap.
#
# Ensures `agentguard` is runnable on the current machine. Called from:
#   - the SessionStart hook (one-shot, silent on success)
#   - the `bin/agentguard` launcher as a last-resort fallback
#
# Strategy:
#   1. Read the plugin version from ``plugin.json`` and use it to key the
#      sentinel file. A plugin update from the marketplace bumps that
#      version, invalidates the sentinel, and re-runs the install once.
#   2. Run ``uv tool install --force`` with the upstream git spec so an
#      already-installed-but-stale CLI is replaced cleanly.
#
# uv is the only supported auto-installer because it is the one method that
# works identically across Linux/macOS/Windows, is a single static binary, and
# does not depend on whatever state the system python / pip / distutils are in.
# If uv is missing, print a clear instruction and exit non-zero. The README
# lists uv as a prerequisite.
#
# Honors:
#   AGENTGUARD_AUTO_INSTALL=0    disables this bootstrap entirely
#   AGENTGUARD_GIT_REF           branch/tag/commit (default: main)
#   AGENTGUARD_PKG_SPEC          full pip/uv spec override
#   AGENTGUARD_FORCE_INSTALL=1   retry even after a previous attempt
set -u

if [ "${AGENTGUARD_AUTO_INSTALL:-1}" = "0" ]; then
  exit 0
fi

# Resolve the plugin version so that an updated plugin (e.g. installed via
# /plugin marketplace) can trigger a CLI upgrade even when ``agentguard``
# is already on PATH. The sentinel below is keyed on this string; bumping
# ``plugin.json``'s ``version`` invalidates the old sentinel and runs
# ``uv tool install --reinstall`` once on the next session start.
plugin_json="$(dirname "$0")/../.claude-plugin/plugin.json"
plugin_version="unknown"
if [ -r "$plugin_json" ]; then
  plugin_version="$(
    sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "$plugin_json" \
      | head -n1
  )"
  [ -z "$plugin_version" ] && plugin_version="unknown"
fi

state_dir="${XDG_STATE_HOME:-$HOME/.local/state}/agentguard"
mkdir -p "$state_dir" 2>/dev/null || true
sentinel="$state_dir/bootstrap.${plugin_version}.attempted"
log_file="$state_dir/bootstrap.log"

# Already installed AND already bootstrapped for this plugin version?
# Nothing to do — the launcher will exec the on-PATH binary.
if command -v agentguard >/dev/null 2>&1 \
   && [ -f "$sentinel" ] \
   && [ "${AGENTGUARD_FORCE_INSTALL:-0}" != "1" ]; then
  exit 0
fi

# One attempt per (machine, plugin version) unless the user forces a retry.
if [ -f "$sentinel" ] && [ "${AGENTGUARD_FORCE_INSTALL:-0}" != "1" ]; then
  exit 0
fi
touch "$sentinel" 2>/dev/null || true

# Older sentinels (without a plugin-version suffix or for previous
# versions) are stale once we get here; clean them so the directory
# does not grow without bound.
find "$state_dir" -maxdepth 1 -type f -name 'bootstrap.*.attempted' \
  ! -name "bootstrap.${plugin_version}.attempted" -delete 2>/dev/null || true
[ -f "$state_dir/bootstrap.attempted" ] && rm -f "$state_dir/bootstrap.attempted"

ref="${AGENTGUARD_GIT_REF:-main}"
spec="${AGENTGUARD_PKG_SPEC:-git+https://github.com/betaHi/AgentGuard.git@${ref}}"

{
  printf '[%s] AgentGuard bootstrap starting (spec=%s)\n' "$(date -Is)" "$spec"
} >>"$log_file" 2>&1 || true

# Resolve uv: on PATH, or in the default astral install location.
uv_bin=""
if command -v uv >/dev/null 2>&1; then
  uv_bin="$(command -v uv)"
elif [ -x "$HOME/.local/bin/uv" ]; then
  uv_bin="$HOME/.local/bin/uv"
fi

if [ -z "$uv_bin" ]; then
  cat >&2 <<'MSG'
AgentGuard needs `uv` to install itself. Run:

  curl -LsSf https://astral.sh/uv/install.sh | sh

…then start a new Claude Code session. (See README for details.)
MSG
  printf '[%s] uv not found on PATH or ~/.local/bin\n' "$(date -Is)" >>"$log_file" 2>&1 || true
  exit 1
fi

if "$uv_bin" tool install --force "$spec" --with claude-agent-sdk >>"$log_file" 2>&1; then
  printf '[%s] uv tool install (--force) succeeded for plugin v%s\n' \
    "$(date -Is)" "$plugin_version" >>"$log_file" 2>&1 || true
  exit 0
fi

printf '[%s] uv tool install failed — see %s\n' "$(date -Is)" "$log_file" >&2
exit 1
