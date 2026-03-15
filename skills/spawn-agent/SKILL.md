---
name: spawn-agent
description: 新しい Terminal タブで独立した Claude Code エージェントを起動する。並列作業や別タスクの委任に使う。
---

# Spawn Agent

新しい macOS Terminal タブで Claude Code エージェント (`claude --dangerously-skip-permissions`) を起動するスキル。

## 使い方

ユーザーからタスクの説明を受け取り、このスキルと同階層の `scripts/spawn-agent.sh` を実行する。

```bash
bash scripts/spawn-agent.sh "タスクの説明"
```

インタラクティブモード（対話型セッション）で起動したい場合:

```bash
bash scripts/spawn-agent.sh --interactive "タスクの説明"
```

## ワークフロー

1. ユーザーからタスク内容を確認する（引数 `$ARGUMENTS` があればそれを使う）
2. タスク内容をプロンプトとして `spawn-agent.sh` に渡す
3. 新しい Terminal タブが開き、Claude Code が `-p` モードでタスクを実行する
4. ユーザーに「新しいタブでエージェントを起動しました」と報告する

## ルール

- プロンプトにはタスクの目的・対象ファイル・期待する結果を具体的に含める
- シングルクォートのエスケープはスクリプト側で処理するので、プロンプトはそのまま渡してよい
- 複数エージェントを同時に起動する場合は、それぞれ別の `spawn-agent.sh` 呼び出しを行う
