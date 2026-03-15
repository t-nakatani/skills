# Hooks

`.claude/settings.json` に登録されるフックスクリプト。
セッションのライフサイクルやツール使用に応じて自動実行される。

## 一覧

| Hook | Event | Matcher | Description |
|------|-------|---------|-------------|
| session-capture | SessionStart | (all) | セッション開始時に session_id, transcript_path, cwd を `.claude/active-sessions/` に記録。クラッシュリカバリ用 |
| session-cleanup | SessionEnd | (all) | 正常終了時に自セッションの active-sessions/ ファイルを削除。並行セッションには影響しない |
| session-end-review | UserPromptSubmit | (all) | ユーザー入力が "close" の場合、/session-review → コミット → マーカー出力を指示 |
| session-close-on-marker | Stop | (all) | アシスタント出力にマーカーを検出 → session-cleanup → プロセス kill |
| skill-usage-log | PostToolUse | Skill | Skill ツール呼び出しを `.claude/skill-usage.jsonl` に JSONL 記録 |
| debug-dump | (任意) | — | 任意のイベントの stdin JSON を `.claude/tmp/hook-debug/` にダンプ。開発・デバッグ用 |

## セッションライフサイクル

```
SessionStart
  → session-capture.sh: active-sessions/<session_id> に書き出し

  ... セッション中 ...

  ユーザーが "close" と入力
    → session-end-review.sh: /session-review + コミット指示を注入

  アシスタントがマーカーを出力
    → session-close-on-marker.sh: session-cleanup.sh を呼び出し → プロセス kill

SessionEnd（正常終了時）
  → session-cleanup.sh: active-sessions/<session_id> を削除

クラッシュ時
  → SessionEnd が発火しない → ファイルが残る
  → claude --resume <session_id> で復帰
```

## debug-dump の使い方

調べたいイベントの hooks 配列に追加する:

```json
"SessionStart": [
  {
    "matcher": "",
    "hooks": [
      { "type": "command", "command": "claude_platform/hooks/session-capture.sh" },
      { "type": "command", "command": "claude_platform/hooks/debug-dump.sh" }
    ]
  }
]
```

ダンプ先: `.claude/tmp/hook-debug/<event>_<timestamp>.json`

調査が終わったら settings.json から debug-dump の行を削除する。

## settings.json への登録

Hook の追加・変更は `.claude/settings.json` で行う。
スクリプトのパスはプロジェクトに合わせて変更すること。
