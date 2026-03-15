---
name: cron-manage
description: |
  Claude Cron Registry の管理スキル。Claude Code の定期 headless 実行ジョブの登録・状態確認・有効化/無効化・ログ確認・手動実行・設定変更・削除を行う。
  ユーザーが「cron に登録したい」「定期実行を追加して」「cron の状態を見せて」「あのジョブ止めて」「cron ログ見せて」と言ったときに使う。
  「定期実行」「スケジュール」「cron」「ジョブ」に関する操作は全てこのスキルで対応する。
  「ジョブ削除」「スケジュール変更」「頻度変えて」「次いつ実行される」「cron 一覧」などの表現にも対応する。
---

# Cron Manage

Claude Cron Registry (`claude_platform/cron/`) を操作するスキル。
manage.py のラッパーとして、ユーザーの意図に応じて適切なサブコマンドを呼び出す。

## ツールパス

manage.py の場所をプロジェクトに合わせて設定する。
デフォルトは `claude_platform/cron/manage.py`。

```
MANAGE_PY=claude_platform/cron/manage.py
```

全コマンドは `uv run $MANAGE_PY <subcommand>` で実行する。

## 操作ルーティング

ユーザーの意図を判断し、以下のいずれかを実行する。

---

### 1. ジョブ登録（新規追加）

ユーザーが「〜を定期実行したい」「cron に追加して」と言った場合。

#### ヒアリング項目

以下を AskUserQuestion で確認する。会話から読み取れる情報は確認を省略してよい。

| 項目 | 必須 | 例 |
|------|------|-----|
| 何を実行するか | yes | `/your-skill`, 自由テキスト |
| スケジュール | yes | 「2時間ごと」「毎朝9時」 |
| 許可ツール | no | デフォルト: Read, Bash, Grep, Glob, Skill, WebFetch |
| タイムアウト | no | デフォルト: 5分 |
| コスト上限 | no | デフォルト: $0.50 |
| モデル | no | デフォルト: sonnet |

#### スケジュール変換

自然言語を cron 式に変換する:

| 自然言語 | cron 式 |
|---------|---------|
| 毎時 | `0 * * * *` |
| 2時間ごと | `0 */2 * * *` |
| 毎朝9時 | `0 9 * * *` |
| 毎日5:30 | `30 5 * * *` |
| 平日の朝8時 | `0 8 * * 1-5` |
| 6時間ごと | `0 */6 * * *` |

#### ジョブ名の生成

ユーザーの説明から `[a-z0-9-]` のジョブ名を生成する。
例: 「ヘルスチェックを2時間ごと」→ `health-check`、「データを毎朝同期」→ `daily-data-sync`

#### 登録手順

1. registry.yaml を読み込む
2. 同名ジョブが存在しないことを確認
3. ジョブ定義を registry.yaml の `jobs:` セクション末尾に追記
4. `uv run $MANAGE_PY validate` で構文チェック
5. validate 失敗時は修正して再実行
6. `uv run $MANAGE_PY install` で crontab に反映
7. 登録結果をユーザーに報告

#### registry.yaml への追記テンプレート

```yaml
  <job-name>:
    schedule: "<cron-expression>"
    description: "<説明>"
    prompt: "<prompt-or-skill>"
    timeout_sec: <seconds>
    model: <model>
    max_turns: <turns>
    max_budget_usd: <budget>
    allowed_tools:
      - Read
      - Bash
      - Grep
      - Glob
      - Skill
      - WebFetch
    enabled: true
```

#### 登録後の確認

登録完了後、テスト実行するか AskUserQuestion で確認する。
テスト実行する場合は `uv run $MANAGE_PY run <job-name>` を実行し、結果を報告。

---

### 2. 状態確認

ユーザーが「cron の状態」「ジョブ一覧」「定期実行どうなってる」と言った場合。

```bash
uv run $MANAGE_PY status
```

---

### 3. 有効化 / 無効化

ユーザーが「〜を止めて」「〜を無効化」「〜を再開して」と言った場合。

```bash
# 無効化
uv run $MANAGE_PY disable <job-name>

# 有効化
uv run $MANAGE_PY enable <job-name>
```

ジョブ名が曖昧な場合は `status` を実行して一覧を見せ、AskUserQuestion で選択させる。

---

### 4. ログ確認

ユーザーが「ログ見せて」「最近の実行結果」と言った場合。

```bash
uv run $MANAGE_PY logs <job-name> -n <count>
```

デフォルトは直近 3 件。

---

### 5. 手動実行

ユーザーが「今すぐ実行して」「テスト実行」と言った場合。

```bash
uv run $MANAGE_PY run <job-name>
```

実行には数分かかる。タイムアウトとコスト上限は registry.yaml の設定に従う。

---

### 6. 設定変更

ユーザーが「スケジュール変えたい」「頻度を変更」「allowed_tools を追加して」と言った場合。

1. `status` で現在の設定を確認・表示
2. 変更内容を AskUserQuestion で確認（スケジュール変更の場合は変換テーブルで cron 式を提示）
3. registry.yaml の該当フィールドを編集
4. `uv run $MANAGE_PY validate` で構文チェック
5. `uv run $MANAGE_PY install` で crontab に反映
6. 結果を報告

---

### 7. ジョブ削除

ユーザーが「このジョブ消して」「削除して」「もう使わない」と言った場合。

1. `status` で対象ジョブを確認
2. ジョブ名が曖昧な場合は AskUserQuestion で選択させる
3. 削除を実行:

```bash
uv run $MANAGE_PY delete <job-name>
```

registry.yaml からジョブを除去し、crontab も自動更新される。

---

### 8. crontab 管理

```bash
# crontab に反映（registry.yaml の変更後）
uv run $MANAGE_PY install

# crontab から全ジョブを除去
uv run $MANAGE_PY uninstall
```

---

## 注意事項

registry.yaml を直接編集した場合（設定変更・ジョブ削除）は、必ず最後に `validate` → `install` を実行すること。
install を忘れると crontab に反映されない。

## 参考ドキュメント

詳細な仕様は `claude_platform/cron/README.md` を参照。
