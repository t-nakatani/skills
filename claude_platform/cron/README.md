# Claude Cron Registry

Claude Code CLI (`claude -p`) を crontab で定期実行するための管理システム。
YAML レジストリで全ジョブを一元管理し、安全ガードレール + Discord 通知 + ログで可視性を確保する。

## Quick Start

```bash
cd /path/to/your-project

# 構文・依存チェック
uv run claude_platform/cron/manage.py validate

# crontab に反映
uv run claude_platform/cron/manage.py install

# 手動で 1 回実行（テスト用）
uv run claude_platform/cron/manage.py run example-health-check

# 状態確認
uv run claude_platform/cron/manage.py status
```

## コマンド一覧

| コマンド | 説明 |
|---------|------|
| `run <job>` | ジョブを 1 回実行（cron + 手動テスト兼用） |
| `install` | registry.yaml → crontab に反映 |
| `uninstall` | crontab から managed block を削除 |
| `status` | 全ジョブの enabled/schedule + 直近実行結果 |
| `validate` | registry 構文 + 依存コマンド + ディレクトリチェック |
| `enable <job>` | ジョブ有効化 + crontab 自動更新 |
| `disable <job>` | ジョブ無効化 + crontab 自動更新 |
| `delete <job>` | ジョブを registry から削除 + crontab 自動更新 |
| `logs <job> [-n N]` | 直近 N 件のログ表示（デフォルト 3） |

## 新しいジョブの追加

### 1. registry.yaml にジョブを定義

```yaml
jobs:
  my-new-job:
    schedule: "0 9 * * *"           # 毎日 9:00
    description: "ジョブの説明"
    prompt: "/some-skill"            # スキル名 or 自由テキスト
    timeout_sec: 300                 # 5 分でタイムアウト
    model: sonnet                    # sonnet / opus / haiku
    max_turns: 20                    # 会話ターン上限
    max_budget_usd: 0.50             # コスト上限
    allowed_tools:                   # ツール制限（ホワイトリスト）
      - Read
      - Bash
      - Grep
      - Glob
      - Skill
    enabled: true
```

### 2. validate → install

```bash
uv run claude_platform/cron/manage.py validate
uv run claude_platform/cron/manage.py install
crontab -l  # 確認
```

### 3. 手動テスト

```bash
uv run claude_platform/cron/manage.py run my-new-job
uv run claude_platform/cron/manage.py status
```

## registry.yaml リファレンス

### defaults セクション

全ジョブに適用されるデフォルト値。ジョブ側の設定で上書き可能。

| フィールド | 型 | デフォルト | 説明 |
|-----------|---|-----------|------|
| `timeout_sec` | int | 300 | タイムアウト（秒） |
| `model` | string | sonnet | Claude モデル |
| `max_turns` | int | 20 | 会話ターン上限 |
| `max_budget_usd` | float | 0.50 | コスト上限（USD） |
| `no_session_persistence` | bool | true | セッション保存を無効化 |
| `notify.on_success` | bool | true | 成功時に Discord 通知 |
| `notify.on_failure` | bool | true | 失敗時に Discord 通知 |
| `log_retention_days` | int | 14 | ログ保持日数 |

### jobs セクション

| フィールド | 必須 | 説明 |
|-----------|------|------|
| `schedule` | yes | 5 フィールド cron 式 |
| `prompt` | yes | Claude に渡すプロンプト（`/skill` 名 or テキスト） |
| `description` | no | ジョブの説明（status 表示用） |
| `allowed_tools` | no | 許可ツールのリスト。未指定時は全ツール許可 |
| `enabled` | no | `false` で無効化（crontab に書かない） |
| その他 | no | defaults のフィールドを上書き |

### ジョブ名のルール

- `[a-z0-9-]` のみ（ロックファイルパスに使うため）
- 例: `health-check`, `daily-data-sync`

## 安全ガードレール

| 機構 | 説明 |
|------|------|
| `--allowedTools` | ジョブごとにツールをホワイトリスト制限 |
| `--max-budget-usd` | ジョブあたりのコスト上限 |
| `--max-turns` | 会話ターン上限 |
| `timeout_sec` | タイムアウトで強制停止 |
| `fcntl.flock` | 同一ジョブの並行実行を防止 |
| Discord 通知 | ステータスのみ送信（生出力は送らない。シークレット漏洩防止） |

## Discord 通知の設定

`.env` ファイルに Webhook URL を設定:

```bash
cp .env.example .env
# .env を編集して CLAUDE_CRON_DISCORD_WEBHOOK を設定
```

通知フォーマット:
```
🟢 my-job 完了 (2m 34s, $0.12, sonnet)
🔴 my-job 失敗 (exit 1, 45s, $0.08)
🟡 my-job タイムアウト (5m 上限, $0.30)
⚪ my-job スキップ (already_running)
```

## 認証（setup-token）

cron ジョブは headless モード (`claude -p`) で実行されるため、`setup-token` を使うことで安定稼働する。

### セットアップ

```bash
# 1. ブラウザ認証でトークンを発行（1 年有効）
claude setup-token

# 2. .env に追加
echo 'CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-...' >> .env
```

manage.py が `.env` を自動読み込みし、`CLAUDE_CODE_OAUTH_TOKEN` を環境変数として cron 実行プロセスに渡す。

### 注意事項

- トークンは **サブスクリプション枠**を消費する（API 従量課金ではない）
- 有効期限は 1 年。失効前に `claude setup-token` で再発行し `.env` を更新すること
- `ANTHROPIC_API_KEY` と同時に設定しないこと（競合する）

## トラブルシュート

### "Not logged in" エラー

`setup-token` の期限切れ、または `.env` に `CLAUDE_CODE_OAUTH_TOKEN` が未設定。上記「認証」セクションを参照。

### cron が動かない

```bash
# crontab に登録されているか確認
crontab -l | grep CLAUDE-CRON

# 手動実行でエラーを確認
uv run claude_platform/cron/manage.py run <job>

# cron の stderr ログを確認
cat claude_platform/cron/logs/cron-stderr.log
```

### スキルが失敗する

`allowed_tools` にスキルが内部で使うツールが含まれていない可能性がある。
ログで `permission denied` 等を確認し、不足ツールを追加する。

### ロックが残っている

`fcntl.flock` はプロセス終了で自動解放される。
プロセスが残っている場合は `ps aux | grep manage.py` で確認。

## ファイル構成

```
claude_platform/cron/
├── manage.py            # 全機能統合 CLI（PEP 723 スクリプト）
├── registry.yaml        # ジョブ定義
├── .env                 # Webhook URL + トークン（gitignore 対象）
├── .env.example         # .env テンプレート
├── logs/                # 実行ログ（gitignore 対象）
│   └── {job}/
│       ├── {run_id}.log
│       └── {run_id}.result.json
└── locks/               # flock ファイル（gitignore 対象）
```
