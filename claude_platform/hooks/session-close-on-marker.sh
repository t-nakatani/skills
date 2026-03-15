#!/bin/bash
# Stop hook: detect SESSION_CLOSE marker in last_assistant_message and kill Claude Code process
#
# settings.json example:
#   { "event": "Stop", "hooks": [{ "type": "command", "command": "hooks/session-close-on-marker.sh" }] }

input=$(cat)

# Prevent infinite loop
is_active=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('stop_hook_active', False))" 2>/dev/null)
if [ "$is_active" = "True" ]; then
  exit 0
fi

# Check if last_assistant_message contains SESSION_CLOSE marker
has_marker=$(echo "$input" | python3 -c "
import sys, json
data = json.load(sys.stdin)
msg = data.get('last_assistant_message', '')
if isinstance(msg, str):
    text = msg
elif isinstance(msg, list):
    text = ' '.join(
        b.get('text', '') for b in msg
        if isinstance(b, dict) and b.get('type') == 'text'
    )
else:
    text = str(msg)
print('yes' if 'SESSION_CLOSE' in text else 'no')
" 2>/dev/null)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "$has_marker" = "yes" ]; then
  echo "$input" | "${SCRIPT_DIR}/session-cleanup.sh"
  kill $PPID 2>/dev/null
  grandparent=$(ps -o ppid= -p $PPID 2>/dev/null | tr -d ' ')
  if [ -n "$grandparent" ] && [ "$grandparent" != "1" ]; then
    kill "$grandparent" 2>/dev/null
  fi
fi

exit 0
