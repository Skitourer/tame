#!/bin/sh
# TAME installer for Linux. Installs uv (which brings its own Python) if needed, then TAME.
# Usage:  curl -LsSf https://skitourer.github.io/tame/install.sh | sh
# Run it again to update.
set -eu
package="tame-tasks"

if ! command -v uv >/dev/null 2>&1; then
    echo "Installing uv, the tool that installs TAME and its Python..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
fi

# Installs made before the package was named tame-tasks own the tk command: remove them.
if uv tool list 2>/dev/null | grep -q '^tame v'; then
    uv tool uninstall tame
fi

echo "Installing TAME..."
uv tool install --upgrade "$package"

if command -v tk >/dev/null 2>&1; then
    printf '\nDone! Type: tk\n'
else
    uv tool update-shell || true
    printf '\nDone! Open a new terminal and type: tk\n'
fi
