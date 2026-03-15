---
name: session-dig
description: Claude Code の過去セッション履歴を検索・探索する。「前に話した」「以前のセッション」「セッション検索」「過去の会話」「session dig」「履歴を探して」「あのときの会話」「セッション掘り出し」「あの作業いつやった」などのリクエストで使用。ユーザーが過去に Claude Code で行った作業を思い出したいとき、特定トピックのセッションを見つけたいときに必ず使う。
---

# Session Dig

過去の Claude Code セッション JSONL を検索・閲覧する。
コンパクト（context compression）後もオリジナルメッセージは JSONL に全て残っているため、完全な会話履歴を復元できる。

## スクリプト

Base directory: このファイルと同階層の `scripts/session_search.py`

### キーワード検索

```bash
python scripts/session_search.py search <keyword1> [keyword2 ...]
```

複数キーワードは AND 検索。ユーザーメッセージのみを対象にする。
日本語・英語どちらでも検索可能。

### 最近のセッション一覧

```bash
python scripts/session_search.py list [--recent N]
```

### セッション詳細（ユーザーメッセージ一覧）

```bash
python scripts/session_search.py show <session-id>
```

メッセージは以下に分類される:
- `user`: 通常のユーザー発言
- `summary`: コンパクト時のサマリー挿入
- `task-notification`: バックグラウンドタスク通知
- `command`: スキル呼び出し
- `interrupted`: ユーザーによる中断

## ワークフロー

1. ユーザーの要望からキーワードを推測して `search` を実行
2. マッチしたセッション一覧を提示（session_id、日時、サイズ、最初のマッチ文）
3. ユーザーが特定のセッションを指定したら `show` で詳細表示
4. 必要に応じて JSONL を直接 Read してさらに深掘り（アシスタント応答の確認等）

### 検索のコツ

- AND 検索なので、キーワードが多すぎるとヒットしない。まず単一キーワードで広く探し、必要なら絞る
- ユーザーの言い回しと実際のメッセージが一致するとは限らない。同義語・関連語で複数パターン試す
  - 例: 「トレーダー追跡」→ `search トレーダー`, `search 追跡`, `search leaderboard` を別々に試す
- 日本語と英語の両方を試す（ユーザーがどちらで入力したか不明なため）

## 補足

- セッションディレクトリは cwd から自動検出される
- `--dir` で明示指定も可能
- 大きなセッション（100MB超）でもユーザーメッセージだけをスキャンするため数秒で完了する
