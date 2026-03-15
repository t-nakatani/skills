# Claude Code Skills & Extensions

Claude Code のセッション管理・運用支援ツールキット。
スキル、フック、エージェント、Cron レジストリ、ユーティリティスクリプトを収録。

## 構成

```
skills/                          # → .claude/skills/ にコピーして使う
├── session-review/              #   セッション終了時の振り返り・改善提案
├── pause-session/               #   セッション一時停止・復帰（Markdown ベース）
├── session-dig/                 #   過去セッション JSONL 検索
├── spawn-agent/                 #   新しい Terminal タブでエージェント起動
├── cron-manage/                 #   Cron Registry 管理（登録・状態確認・有効化等）
└── codex-review/                #   Codex CLI による外部コードレビュー

agents/                          # → .claude/agents/ にコピーして使う
└── code-reviewer.md             #   コミット・ブランチの技術レビュー

references/                      # → .claude/references/ にコピーして使う
└── loop_skill_design.md         #   /loop 併用スキルの設計原則

claude_platform/                 # Claude Code 運用インフラ
├── hooks/                       #   settings.json に登録して使うフック群
│   ├── README.md                #     フック一覧・ライフサイクル図
│   ├── skill-usage-log.sh       #     スキル使用を JSONL に記録
│   ├── session-capture.sh       #     セッション開始時にメタデータ保存（クラッシュ復旧用）
│   ├── session-cleanup.sh       #     セッション終了時にメタデータ削除
│   ├── session-end-review.sh    #     "close" 入力で自動レビュー → コミット → 終了
│   ├── session-close-on-marker.sh  #  SESSION_CLOSE マーカーで自動終了
│   └── debug-dump.sh            #     フック入力 JSON をファイルにダンプ（開発用）
├── scripts/                     #   CLI ユーティリティ
│   ├── skill-stats.sh           #     スキル使用統計の集計・表示
│   └── spawn-agent.sh           #     新 Terminal タブで Claude Code 起動
└── cron/                        #   Claude Code 定期実行レジストリ
    ├── README.md                #     セットアップ・コマンド詳細
    ├── manage.py                #     全機能統合 CLI（PEP 723 スクリプト）
    ├── registry.yaml            #     ジョブ定義（サンプル）
    └── .env.example             #     環境変数テンプレート
```

## セットアップ

### スキルのインストール

使いたいスキルをプロジェクトの `.claude/skills/` にコピーする:

```bash
# 例: session-review をインストール
cp -r skills/session-review /path/to/project/.claude/skills/

# 全スキルを一括コピー
cp -r skills/* /path/to/project/.claude/skills/
```

### エージェントのインストール

`.claude/agents/` にコピーする:

```bash
cp agents/code-reviewer.md /path/to/project/.claude/agents/
```

### フックの登録

1. `claude_platform/hooks/` をプロジェクト内に配置する
2. `.claude/settings.json` に登録する:

```json
{
  "hooks": {
    "SessionStart": [
      { "type": "command", "command": "claude_platform/hooks/session-capture.sh" }
    ],
    "SessionEnd": [
      { "type": "command", "command": "claude_platform/hooks/session-cleanup.sh" }
    ],
    "UserPromptSubmit": [
      { "type": "command", "command": "claude_platform/hooks/session-end-review.sh" }
    ],
    "Stop": [
      { "type": "command", "command": "claude_platform/hooks/session-close-on-marker.sh" }
    ],
    "PostToolUse": [
      {
        "type": "command",
        "command": "claude_platform/hooks/skill-usage-log.sh",
        "matcher": { "tool_name": "Skill" }
      }
    ]
  }
}
```

### Cron レジストリの導入

`claude_platform/cron/` をプロジェクト内に配置して使う。詳細は [`claude_platform/cron/README.md`](claude_platform/cron/README.md) を参照。

```bash
# 1. 設定
cp claude_platform/cron/.env.example claude_platform/cron/.env
# .env を編集

# 2. registry.yaml にジョブを定義

# 3. 検証 → インストール
uv run claude_platform/cron/manage.py validate
uv run claude_platform/cron/manage.py install
```

## スキル一覧

### session-review

セッション終了時に作業内容を振り返り、改善提案を生成する。
ワークフロー・コード品質・自動化・ドキュメント・技術的負債の観点から提案し、
`.claude/sessions/YYYY-MM-DD_HH-MM_<topic>.md` に保存する。

### pause-session

セッションの一時停止と復帰。コンテキスト（タスク・進捗・判断・未解決事項・次のアクション）を
構造化 Markdown に保存し、別のセッションで復帰できるようにする。
`--resume` の UUID を探す手間を省き、人間が読めるスナップショットで管理する。

### session-dig

過去の Claude Code セッション JSONL を検索・閲覧する。
キーワード AND 検索、最近のセッション一覧、セッション詳細表示をサポート。
Python スクリプト (`scripts/session_search.py`) で高速に全履歴をスキャンする。

### spawn-agent

macOS Terminal の新しいタブで独立した Claude Code エージェントを起動する。
並列作業や別タスクの委任に使用。`-p` モード（自律実行）と対話モードをサポート。

### cron-manage

Claude Cron Registry の管理スキル。ジョブの登録・状態確認・有効化/無効化・ログ確認・手動実行・設定変更・削除を対話的に行う。自然言語のスケジュール指定（「2時間ごと」「毎朝9時」）を cron 式に自動変換する。`claude_platform/cron/manage.py` のラッパー。

### codex-review

Codex CLI (`codex exec`) を使い、コード変更の外部レビューを取得する。
エフェメラルなレビュースペースを `.claude/tmp/reviews/` に作成し、レビュー結果をファイルに保存。
spawned agent のセルフチェックや、異なる AI モデルによるクロスレビューに使える。

## フックの連携図

```
SessionStart → session-capture.sh → .claude/active-sessions/<id> に記録
     ↓
  作業中  → skill-usage-log.sh → .claude/skill-usage.jsonl に記録
     ↓
"close" 入力 → session-end-review.sh → /session-review 実行指示を注入
     ↓
SESSION_CLOSE 出力 → session-close-on-marker.sh → session-cleanup.sh → プロセス終了
     ↓
SessionEnd → session-cleanup.sh → .claude/active-sessions/<id> を削除
```

## Cron レジストリ

Claude Code の定期 headless 実行を YAML レジストリで一元管理する。

特徴:
- **安全ガードレール**: ツールホワイトリスト、コスト上限、ターン上限、タイムアウト
- **並行実行防止**: `fcntl.flock` による排他制御
- **Discord 通知**: 成功/失敗/タイムアウトをステータスのみ通知（生出力は送らない）
- **ログ管理**: 実行ごとに生ログ + 構造化メタデータ JSON を保存

詳細: [`claude_platform/cron/README.md`](claude_platform/cron/README.md)

## 依存関係

- **jq**: フックスクリプトで JSON パースに使用
- **python3**: セッション検索スクリプト、一部フックで使用
- **uv**: Cron レジストリの manage.py 実行に使用
- **git**: パスの自動検出 (`git rev-parse --show-toplevel`)
- **osascript**: spawn-agent（macOS のみ）

## ライセンス

MIT
