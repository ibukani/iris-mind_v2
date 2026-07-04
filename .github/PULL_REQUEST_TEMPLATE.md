## Linked Issues

<!--
直接解決するIssueだけ Closes を使う。
前提・順序制約は Depends on、文脈共有は Related、後続を止める場合は Blocks。
該当なしは N/A と書く。
-->

- Closes: N/A
- Depends on: N/A
- Related: N/A
- Blocks: N/A

## 概要

<!--
何を、なぜ変更したか。
Issueの目的・acceptance criteriaとの対応が分かるように書く。
-->

-

## 変更点

<!--
必要な項目だけ残す。
-->

- Code:
- Tests:
- Docs / ADR:
- Config / schema / proto:
- Other:

## Issue 要件との対応

<!--
Issue本文の acceptance criteria / checklist / review comment と対応させる。
未対応がある場合は理由と後続Issueを書く。
-->

- [ ] 要件1:
- [ ] 要件2:
- [ ] 要件3:

## アーキテクチャ影響

<!--
Iris runtime の境界を壊していないか確認する。
該当なしでも N/A だけにせず、影響なしと判断した理由を書く。
-->

Touched layers:

- [ ] contracts
- [ ] core
- [ ] cognitive
- [ ] features
- [ ] adapters
- [ ] presentation
- [ ] safety
- [ ] runtime
- [ ] docs / ADR
- [ ] tests
- [ ] scripts / AI harness

Boundary checks:

- [ ] `cognitive/` から `adapters/`, `runtime/`, `features/` へ依存していない
- [ ] `contracts/` から `cognitive/`, `adapters/`, `runtime` へ依存していない
- [ ] feature-specific data を `WorkspaceFrame` に広げていない
- [ ] `FeatureDefinition` を迂回して cognitive internals を直接変更していない
- [ ] service locator / global mutable registry / temporary compatibility shim を追加していない
- [ ] internal boundary に `dict[str, Any]` / `dict[str, object]` を追加していない
- [ ] 新しい `action: str` dispatcher branch を追加していない

Notes:

-

## Runtime / Safety 影響

<!--
runtime, scheduler, delivery, ingress, safety, presenter, proactive behavior に触る場合は必須。
触らない場合も「影響なし」と書く。
-->

- No-action semantics:
- Safety gate / presenter / output boundary:
- Ingress trust boundary:
- Persistence / activity journal / memory impact:
- Observability / diagnostics impact:

## 検証

<!--
実行したものだけチェック。
実行できない場合は、理由と代替確認を書く。
-->

- [ ] `make ai-quick`
- [ ] `make quick`
- [ ] `make ai-check`
- [ ] `make check`
- [ ] Targeted pytest: `uv run pytest ...`
- [ ] Docs-only review
- [ ] Not run

Results:

```text
# paste concise command results here
```

Commands not run:

-

## レビュー観点

<!--
レビュアーに特に見てほしい観点。
例: architecture boundary, persistence policy, no-action semantics, docs/ADR drift, test coverage.
-->

-

## リスク・後続作業

<!--
残リスクがなければ「なし」。
後続Issueが必要なら Related / Blocks と揃える。
-->

- Risk:
- Follow-up:
