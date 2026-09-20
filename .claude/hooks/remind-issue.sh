#!/bin/sh
# PreToolUse (Bash): keep the tracker honest (CLAUDE.md workflow).
# When Claude creates a feature branch or opens a PR, remind it that the change
# must trace to a GitHub issue and that the PR body must say "Closes #<n>".
# Emits additionalContext ONLY for matching commands — a no-op for every other call.

cmd=$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null)

case "$cmd" in
  *"git switch -c "* | *"git checkout -b "* | *"gh pr create"*)
    python3 - <<'PY'
import json

msg = (
    "Issue-first workflow (CLAUDE.md): this change MUST trace to a GitHub issue. "
    "If none exists, create one NOW — the feature-request skill, or `gh issue create` "
    "with a req:FR-xx / infra / bug label plus a milestone — before the branch or PR. "
    "The PR body must contain \"Closes #<n>\", and the PR template's \"How to validate\" "
    "section is mandatory: exact commands, expected output, acceptance criteria. "
    "Do not open a feature PR without a linked issue."
)
print(json.dumps({
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": msg,
    }
}))
PY
    ;;
esac
exit 0
