#!/bin/sh
# Run the development version of tame on throwaway data, never your real tasks.
# Tasks and settings go to .sandbox/ at the repository root (ignored by git).
# All arguments are passed to tk.
#
#   ./scripts/tk.sh add Call bank +phone due:fri
#   ./scripts/tk.sh
#   ./scripts/tk.sh --reset      # delete the sandbox and start over
root="$(cd "$(dirname "$0")/.." && pwd)"
sandbox="$root/.sandbox"
if [ "$#" -eq 1 ] && [ "$1" = "--reset" ]; then
    rm -rf "$sandbox"
    echo "Sandbox reset: $sandbox"
    exit 0
fi
export TAME_HOME="$sandbox"
export UV_TOOL_BIN_DIR="$sandbox/bin" # tk alias stays in the sandbox too
exec uv run --project "$root" tk "$@"
