#!/bin/bash
# spawn-agent.sh — 新しい Terminal タブで Claude Code エージェントを起動する
#
# Usage:
#   spawn-agent.sh "タスクの説明"
#   spawn-agent.sh --interactive "タスクの説明"
#
# Options:
#   --interactive, -i   対話モードで起動（デフォルトは -p モード）
#   --no-close          実行完了後にタブを閉じない

set -euo pipefail

DIR="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
MODE="-p"
CLOSE="; exit"

# Parse flags
while [[ $# -gt 0 ]]; do
  case "$1" in
    --interactive|-i)
      MODE=""
      shift
      ;;
    --no-close)
      CLOSE=""
      shift
      ;;
    *)
      break
      ;;
  esac
done

PROMPT="${*:?Usage: spawn-agent.sh [--interactive] \"prompt\"}"

# Escape single quotes for osascript
ESCAPED_PROMPT="${PROMPT//\'/\'\\\'\'}"

if [[ -n "$MODE" ]]; then
  CMD="cd '$DIR' && claude --dangerously-skip-permissions $MODE '$ESCAPED_PROMPT'$CLOSE"
else
  CMD="cd '$DIR' && claude --dangerously-skip-permissions '$ESCAPED_PROMPT'$CLOSE"
fi

osascript -e "tell application \"Terminal\" to do script \"$CMD\""
