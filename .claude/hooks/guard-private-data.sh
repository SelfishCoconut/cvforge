#!/bin/sh
# PreToolUse (Bash|Write|Edit). The logic lives in guard_private_data.py.
#
# This file is deliberately a three-line wrapper. The Python used to live in a
# heredoc here, and that cost the project a bricked repository: an unterminated
# `$(` left every Bash/Write/Edit call in this repo failing until the file was
# repaired from outside Claude Code. A hook that gates every tool call earns the
# least fragile invocation available, and a .py file is lintable and testable.
exec python3 "$(dirname "$0")/guard_private_data.py"
