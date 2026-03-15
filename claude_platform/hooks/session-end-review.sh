#!/bin/bash
# UserPromptSubmit hook: detect exit-intent and inject /session-review instruction
# stdin receives JSON with the user's prompt
#
# settings.json example:
#   { "event": "UserPromptSubmit", "hooks": [{ "type": "command", "command": "hooks/session-end-review.sh" }] }

input=$(cat)

# Extract prompt from JSON
if echo "$input" | grep -q '"prompt"'; then
  prompt=$(echo "$input" | python3 -c "import sys,json; print(json.load(sys.stdin).get('prompt',''))" 2>/dev/null)
else
  prompt="$input"
fi

# Match "close"
if echo "$prompt" | grep -qiE '^close$'; then
  cat <<'INSTRUCTION'
ユーザーがセッション終了を希望しています。以下の手順を順番に実行してください:
1. /session-review スキルを実行してセッションレビューを完了する
2. セッション中に作成・変更したファイルを git commit する（git status で差分を確認し、関連ファイルを add してコミット。コミットメッセージは作業内容を簡潔に記述する。push は不要）
3. 最後に必ず「SESSION_CLOSE」というマーカーテキストを出力する（Stop hookが検出してセッションを自動終了します）
INSTRUCTION
fi

exit 0
