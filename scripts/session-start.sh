#!/usr/bin/env bash
# Claude Code SessionStart hook: in cloud sessions the container is fresh each time, so install
# the toolchain once. On a local machine this does nothing (run scripts/setup.* yourself).
cd "$(dirname "$0")/.." || exit 0
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && { [ ! -x .venv/bin/engagent ] || ! command -v ccx >/dev/null 2>&1; }; then
  bash scripts/setup.sh > .setup.log 2>&1 \
    && echo "EngineeringAgent toolchain installed (see .setup.log)." \
    || echo "EngineeringAgent setup did not finish; run 'bash scripts/setup.sh' and read .setup.log."
fi
if [ -x .venv/bin/engagent ] || [ -x .venv/Scripts/engagent.exe ]; then
  U="$(./ea units --json 2>/dev/null | grep -o '"units": *"[a-z]*"' | head -1)"
  [ -n "$U" ] && echo "EngineeringAgent ready. Active $U (toggle: ./ea units metric|imperial)."
else
  echo "EngineeringAgent is not set up on this machine: run scripts/setup.ps1 (Windows) or bash scripts/setup.sh."
fi
exit 0
