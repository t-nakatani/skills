#!/bin/bash
# Claude Code ステータスライン — cwd | git branch | model | ctx% | cost | time
# .claude/settings.json の Notification hook として登録して使う

input=$(cat)

# Parse JSON fields
cwd=$(echo "$input" | jq -r '.workspace.current_dir // .cwd')
cwd_display=$(echo "$cwd" | sed "s|^$HOME|~|")
model=$(echo "$input" | jq -r '.model.display_name // "?"')
ctx_pct=$(echo "$input" | jq -r '.context_window.used_percentage // 0')
cost=$(echo "$input" | jq -r '.cost.total_cost_usd // 0')

# Git info
git_seg=''
if git -C "$cwd" rev-parse --git-dir >/dev/null 2>&1; then
  branch=$(git -C "$cwd" rev-parse --abbrev-ref HEAD 2>/dev/null)
  if [ -n "$branch" ]; then
    dirty=''
    if ! git -C "$cwd" diff --no-lock-index --quiet 2>/dev/null || \
       ! git -C "$cwd" diff --no-lock-index --cached --quiet 2>/dev/null; then
      dirty='*'
    fi
    git_seg="${branch}${dirty}"
  fi
fi

# Format values
ctx_int=$(printf '%.0f' "$ctx_pct")
cost_fmt=$(printf '$%.2f' "$cost")
time_now=$(date +%H:%M:%S)

# Output
printf '\033[36m%s\033[0m \033[31m%s\033[0m \033[32m%s\033[0m \033[35mctx:%s%%\033[0m \033[34m%s\033[0m \033[33m%s\033[0m\n' \
  "$cwd_display" "$git_seg" "$model" "$ctx_int" "$cost_fmt" "$time_now"
