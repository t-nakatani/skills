#!/bin/bash
# Skill usage statistics viewer
# Usage: skill-stats.sh [days]  (default: all time)
#
# Reads from .claude/skill-usage.jsonl (written by hooks/skill-usage-log.sh)

PROJECT_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
LOG_FILE="${PROJECT_ROOT}/.claude/skill-usage.jsonl"

if [[ ! -f "$LOG_FILE" ]]; then
  echo "No skill usage data yet."
  exit 0
fi

DAYS="${1:-}"

if [[ -n "$DAYS" ]] && ! [[ "$DAYS" =~ ^[0-9]+$ ]]; then
  echo "Usage: skill-stats.sh [days]"
  exit 1
fi

if [[ -n "$DAYS" ]]; then
  SINCE=$(date -u -v-"${DAYS}"d '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date -u -d "${DAYS} days ago" '+%Y-%m-%dT%H:%M:%SZ')
  DATA=$(jq -r --arg since "$SINCE" 'select(.timestamp >= $since)' "$LOG_FILE")
  HEADER="=== Skill Usage (last ${DAYS} days) ==="
else
  DATA=$(cat "$LOG_FILE")
  HEADER="=== Skill Usage (all time) ==="
fi

TOTAL=$(echo "$DATA" | jq -s 'length')

echo "$HEADER"
echo "Total invocations: $TOTAL"
echo ""
echo "By skill:"
echo "$DATA" | jq -r '.skill' | sort | uniq -c | sort -rn | while read -r count name; do
  printf "  %-30s %4d\n" "$name" "$count"
done

echo ""
echo "By date:"
echo "$DATA" | jq -r '.timestamp[:10]' | sort | uniq -c | sort | while read -r count date; do
  printf "  %s  %4d\n" "$date" "$count"
done

echo ""
echo "Recent (last 10):"
echo "$DATA" | jq -s '.[-10:][] | "\(.timestamp[:19])  \(.skill)"' -r
