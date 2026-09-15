#!/bin/bash
set -euo pipefail

# Only needed in Claude Code on the web - the container is ephemeral, so
# tools installed in a previous session don't carry over.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# uv gives us an isolated tool env for the headroom CLI without touching
# the repo's own Python environment/dependencies.
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

# Idempotent: re-running just confirms the tool is already installed.
uv tool install --python 3.13 "headroom-ai[all]"

echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$CLAUDE_ENV_FILE"
