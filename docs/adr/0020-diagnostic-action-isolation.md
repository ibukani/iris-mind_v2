# ADR 0020: diagnostic action isolation

Status: Accepted

## Context

`basic_action` は入力テキストをそのまま `ActionPlan` に載せる echo-like な開発・診断用 behavior である。これは runtime の最小疎通確認には便利だが、production-like companion response として扱うと、persona-aware chat path や event reaction path を迂回し、ユーザー入力をそのまま通常応答として返す危険がある。

Issue #107 では、この diagnostic echo behavior を production-like runtime の通常応答候補から分離する。ただし Runtime Config v2 までは、新しい diagnostic flag、mode config field、schema/template、Control Plane manifest 更新は追加しない。

## Decision

- `basic_action` は `FeatureKind.DIAGNOSTIC` の feature として定義する。
- `basic_action` は `DiagnosticEchoActionSelectionStep` のみを所有し、汎用 `ActionPlan` presenter は所有しない。
- 汎用 presenter は `presentation` 層の `DefaultActionPlanPresenter` として提供する。
- 標準 runtime feature catalog は既存の `safety.mode` だけを参照する。
  - `development`: `basic_action` を有効 feature として登録する。
  - `basic` / `strict` / future production-like mode: `basic_action` を通常応答候補から除外し、typed disabled reason を記録する。
- `feature-selection` diagnostics は runtime mode、enabled feature、disabled feature reason を観測可能にする。

## Consequences

- development runtime では従来の echo diagnostic flow を明示的な diagnostic feature として維持できる。
- production-like runtime では diagnostic echo が persona-aware chat / event reaction / proactive response path を上書きしない。
- Runtime Config v2 以前に public config surface を増やさないため、Control Plane schema や template の互換性リスクを避けられる。
- Runtime Config v2 で診断用 flag を公開する場合は、compact user config と typed effective config の設計に合わせて別途追加する。

## Verification

- `wire_runtime_features(RuntimeFeatureSelectionOptions(safety_mode="development"))` は `basic_action` を enabled に含める。
- `wire_runtime_features(RuntimeFeatureSelectionOptions(safety_mode="basic"))` と `strict` は `basic_action` を disabled metadata に含める。
- `wire_presentation_suite()` は feature-specific presenters の後ろに `DefaultActionPlanPresenter` を追加し、専用 presenter の優先順位を維持する。
