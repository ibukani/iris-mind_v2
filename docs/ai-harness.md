# AI Harness ガイド

このリポジトリは、Codex・OpenCode などのコーディングエージェントを操作・監査しやすくするために、厳格な品質ゲートとリポジトリレベルのエージェント指示を採用している。

## 共通のソースオブトゥルース

- `AGENTS.md` はルートの指示ファイルである。
- `.agents/rules/` には再利用可能なルールを配置する。
- `.agents/workflows/` にはタスク別の運用手順を配置する。
- `Makefile` と `scripts/verify.py` は決定的な検証エントリポイントである。
- `opencode.json` は OpenCode のスラッシュコマンドと本リポジトリの harness コマンドを対応付ける。

## コマンド階層

```bash
make ai-test-target TARGET=tests/path_or_file.py
make ai-arch
make ai-quick
make ai-check
make check
```

小規模な変更を反復している間は `make ai-test-target` を使う。広い範囲の編集を報告する前は `make ai-quick` を使う。可能であれば引き継ぎ前に `make ai-check` を使う。正規のフルゲートとして `make check` を使う。

## Codex の使い方

Codex はリポジトリルートから起動し、`AGENTS.md` を読み込ませる。専門タスクではプロンプトにワークフローのパスを含める。例:

```text
Goal: fix pyright failures in runtime wiring.
Read: AGENTS.md, .agents/workflows/test-fix.md, .agents/rules/typing.md.
Test: make ai-quick, then make ai-check if feasible.
Report: Japanese.
```

## OpenCode の使い方

OpenCode はプロジェクト指示を `AGENTS.md` から読む。コミット済みの `opencode.json` も AI harness ルールを参照し、`/ai-quick`、`/ai-check`、`/ai-arch`、`/ai-report`、`/ai-review` などのコマンドを提供する。

## 失敗ポリシー

失敗したゲートは有用なシグナルである。設定の弱体化、テストのスキップ、広範な ignore の追加、`Any` による typed 境界の置き換えで失敗を隠蔽しない。

コマンドが失敗した場合、正確なコマンド、最初に失敗したファイルまたはテスト、次の最小修正を報告する。
