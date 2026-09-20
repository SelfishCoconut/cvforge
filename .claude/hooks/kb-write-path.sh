#!/bin/sh
# PostToolUse (Edit|Write). The logic lives in kb_write_path.py.
# Thin wrapper for the same reason as guard-private-data.sh.
exec python3 "$(dirname "$0")/kb_write_path.py"
