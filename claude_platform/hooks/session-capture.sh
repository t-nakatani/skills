#!/bin/bash
# SessionStart hook: capture active session info for crash recovery
# Writes per-session file to .claude/active-sessions/<session_id>
#
# settings.json example:
#   { "event": "SessionStart", "hooks": [{ "type": "command", "command": "hooks/session-capture.sh" }] }

input=$(cat)

session_id=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('session_id',''))" 2>/dev/null)
transcript_path=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('transcript_path',''))" 2>/dev/null)
cwd=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('cwd',''))" 2>/dev/null)

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"

if [ -n "$session_id" ]; then
  mkdir -p "${PROJECT_ROOT}/.claude/active-sessions"
  cat > "${PROJECT_ROOT}/.claude/active-sessions/${session_id}" <<EOF
{"session_id":"${session_id}","transcript_path":"${transcript_path}","cwd":"${cwd}","captured_at":"$(date '+%Y-%m-%d %H:%M:%S')"}
EOF
fi

exit 0
