#!/usr/bin/env bash
# EngineeringAgent setup for Linux and macOS (also used by Claude Code cloud sessions).
#   bash scripts/setup.sh
# Creates .venv, installs the Python packages and the CalculiX solver, runs the benchmark.
set -euo pipefail
cd "$(dirname "$0")/.."
ROOT="$(pwd)"
echo "== EngineeringAgent setup =="

PY=""
for c in python3.12 python3.13 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then
    v="$("$c" -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
    case "$v" in 3.10|3.11|3.12|3.13) PY="$c"; break ;; esac
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10-3.13 not found. Install Python 3.12 and re-run."; exit 1
fi
echo "Python: $($PY --version)"

if [ ! -x .venv/bin/python ]; then
  if command -v uv >/dev/null 2>&1; then uv venv --python "$PY" .venv -q; else "$PY" -m venv .venv; fi
fi
echo "Installing Python packages (build123d, gmsh, ...)"
if command -v uv >/dev/null 2>&1; then
  uv pip install -q --python .venv/bin/python -e ".[mcp,dev]"
else
  .venv/bin/python -m pip install -q --upgrade pip
  .venv/bin/python -m pip install -q -e ".[mcp,dev]"
fi

if ! command -v ccx >/dev/null 2>&1 && [ -z "${ENGAGENT_CCX:-}" ]; then
  echo "Installing the CalculiX solver ..."
  SUDO=""; [ "$(id -u)" -ne 0 ] && SUDO="sudo"
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update -qq || true
    $SUDO apt-get install -y -qq calculix-ccx libglu1-mesa libgl1 libxrender1 libxcursor1 libxft2 libxinerama1 \
      || echo "apt install failed: install 'calculix-ccx' manually."
  elif command -v dnf >/dev/null 2>&1; then
    $SUDO dnf install -y calculix mesa-libGLU || echo "dnf install failed: install CalculiX manually."
  elif command -v brew >/dev/null 2>&1; then
    brew install calculix-ccx || echo "brew install failed: install CalculiX manually."
  else
    echo "No supported package manager found. Install CalculiX (ccx) and put it on PATH, or set ENGAGENT_CCX."
  fi
fi

echo
.venv/bin/engagent doctor --full && {
  echo
  echo "Setup complete. Start Claude Code in this folder and ask for a part or an analysis."
  echo "Command line:  ./ea units     ./ea fea new jobs/01-my-part -a static"
  echo "MCP server for other AI clients:  $ROOT/.venv/bin/engagent-mcp   (see docs/mcp.md)"
}
