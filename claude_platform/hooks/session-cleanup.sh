#!/bin/bash
# Clean up active session file on normal exit
# Called from: SessionEnd hook (stdin JSON), session-close-on-marker.sh (stdin JSON)
# Deletes only its own session file — safe for parallel sessions
#
# settings.json example:
#   { "event": "SessionEnd", "hooks": [{ "type": "command", "command": "hooks/session-cleanup.sh" }] }

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if [ -n "$1" ]; then
  session_id="$1"
else
  input=$(cat)
  session_id=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
fi

if [ -n "$session_id" ]; then
  rm -f "${PROJECT_ROOT}/.claude/active-sessions/${session_id}"
fi

exit 0
