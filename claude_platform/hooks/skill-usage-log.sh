#!/bin/bash
# PostToolUse hook: Log skill usage to JSONL for statistics
# Matches: Skill tool only
#
# settings.json example:
#   { "event": "PostToolUse", "hooks": [{ "type": "command", "command": "hooks/skill-usage-log.sh" }], "matcher": { "tool_name": "Skill" } }

INPUT=$(cat)

SKILL_NAME=$(echo "$INPUT" | jq -r '.tool_input.skill // empty')
if [[ -z "$SKILL_NAME" ]]; then
  exit 0
fi

SESSION_ID=$(echo "$INPUT" | jq -r '.session_id // empty')
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ')

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG_FILE="${PROJECT_ROOT}/.claude/skill-usage.jsonl"

jq -nc --arg skill "$SKILL_NAME" --arg ts "$TIMESTAMP" --arg sid "$SESSION_ID" \
  '{skill: $skill, timestamp: $ts, session_id: $sid}' >> "$LOG_FILE"

exit 0
