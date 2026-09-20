#!/bin/sh
# PostToolUse (Edit|Write): auto-format the touched file.
# Python -> ruff format + ruff check --fix. TypeScript -> eslint --fix.
# Reads the hook JSON on stdin and extracts .tool_input.file_path.

file_path=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("file_path",""))' 2>/dev/null)
root="$CLAUDE_PROJECT_DIR"
[ -n "$root" ] || root=$(dirname "$0")/../..

case "$file_path" in
  *.py)
    cd "$root" || exit 0
    uv run ruff format --quiet "$file_path" 2>/dev/null
    uv run ruff check --fix --quiet "$file_path" 2>/dev/null
    ;;
  *.ts | *.tsx)
    # Skip silently when the frontend has not been installed yet.
    [ -d "$root/frontend/node_modules" ] || exit 0
    cd "$root/frontend" || exit 0
    npm exec --no -- eslint --fix "$file_path" >/dev/null 2>&1
    ;;
esac
exit 0
