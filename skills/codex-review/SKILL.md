---
name: codex-review
description: Codex CLI にコードレビューを依頼する。エフェメラルなレビュースペースをプロジェクト内に作成し、codex exec でレビュー結果をファイルに保存する。spawned agent が自分の作業成果をレビューしてもらいたいときに使う。「codex レビュー」「外部レビュー」「レビュー依頼」「codex review」などのリクエストで使用。
---

# Codex Review

codex CLI の `codex exec` を使い、コード変更の外部レビューを取得する。
spawned agent が作業完了後にセルフチェックとして使うことを想定している。

`codex review` ではなく `codex exec` を使う理由: `codex review --uncommitted` はリポジトリ全体の未コミット変更を対象にしてしまい、レビュー対象を絞れない。`codex exec` ならプロンプトで対象ファイルを明示できる。

## ワークフロー

### 1. レビュースペースを作成する

```bash
REVIEW_DIR=".claude/tmp/reviews/review-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$REVIEW_DIR"
```

### 2. codex exec でレビューを実行する

```bash
codex exec -m gpt-5.4 -c 'reasoning.effort="high"' \
  -o "$REVIEW_DIR/review_round_1.md" \
  "以下のファイルをレビューしてください: path/to/file1.rs path/to/file2.rs"
```

- `-o` で最終メッセージをファイルに出力する
- プロンプトにレビュー対象のファイルパスを列挙する
- プロンプトは簡素に。過剰なコンテキストはレビュアーの先入観になる

### 3. レビュー結果を読んで対応する

`review_round_1.md` を読み、指摘に対応する。
納得できるもののみ修正して、そうでないものは理由を述べて拒否する。

### 4. 追加ラウンド（必要な場合のみ）

観点を変えて再実行:

```bash
codex exec -m gpt-5.4 -c 'reasoning.effort="high"' \
  -o "$REVIEW_DIR/review_round_2.md" \
  "具体的な観点"
```

## 注意事項

- `codex exec` は非インタラクティブ。`-o` で最終メッセージをファイルに保存する
- レビュースペースは自動削除しない（後から参照可能）
