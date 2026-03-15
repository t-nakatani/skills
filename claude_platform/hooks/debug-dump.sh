#!/bin/bash
# Debug hook: dump stdin JSON payload to file for inspection
# Usage: Register on any hook event in settings.json to capture its payload
#
# Output: .claude/tmp/hook-debug/<event>_<timestamp>.json
#
# settings.json example:
#   { "event": "PostToolUse", "hooks": [{ "type": "command", "command": "hooks/debug-dump.sh" }] }

input=$(cat)

event=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('hook_event_name','unknown'))" 2>/dev/null)

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
DUMP_DIR="${PROJECT_ROOT}/.claude/tmp/hook-debug"
mkdir -p "$DUMP_DIR"

echo "$input" | python3 -c "import sys,json; json.dump(json.load(sys.stdin), sys.stdout, indent=2, ensure_ascii=False)" \
  > "$DUMP_DIR/${event}_$(date +%Y%m%d_%H%M%S).json" 2>/dev/null

exit 0
