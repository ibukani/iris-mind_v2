# ADR 0006: Proactive Scheduler / Delivery Outbox / Delivery Safety

## Status

Accepted.

## Context

Iris の proactive behavior は、scheduler が直接 LLM や外部送信 client を呼ぶ形にしない。外部副作用は、認知サイクル、既存 safety/presentation path、delivery safety、outbox を通過した後、信頼済み local/internal client が pull して実行する。

## Decision

正式な proactive delivery path を次に固定する。

```text
Scheduler
→ typed internal Observation
→ IrisRuntimeService
→ CognitiveCycle
→ ActionPlan
→ ActionSafetyGate
→ Presenter
→ PresentedOutput
→ OutputSafetyGate
→ DeliverySafetyGate
→ DeliveryOutbox
→ external client polling
→ ActionResult
→ learning/audit hooks
```

Scheduler は typed observation だけを発行する。proactive talk は `IdleTickObservation` から開始する。Scheduler は LLM client、presenter、Discord/CLI/voice などの外部送信 client を呼ばない。

Delivery は sender ではなく outbox boundary とする。`DeliveryEnvelope` は `DeliveryStatus` による明示状態を持つ。`PENDING` は lease 可能、`LEASED` は lease 一致時だけ完了可能、期限切れ lease は再 lease 可能、`SUCCEEDED` / `FAILED_PERMANENT` / `CANCELLED` / `BLOCKED` は terminal とする。`ReportActionResult` は同一結果の再報告を安全に扱う idempotent API とする。同一性は `delivery_id`、`lease_id`、`action_id`、`correlation_id`、`status`、`external_message_id`、`error_reason` で判定する。`FAILED` のみ retry 可能とし、`CANCELLED` / `BLOCKED` は terminal completion として扱う。競合する再報告は `DeliveryOutboxError` を送出する。`lease_due` / `PollAppActions` は `LEASED` 状態の item のみ返す。terminal item は返さない。

Learning / audit hook は `ActionResult` 後にだけ実行する。`ActionPlan` が提案された時点、または delivery item が enqueue された時点では durable memory を更新しない。

Scheduler lifecycle は default disabled とする。現 phase の outbox / target store は in-memory でよいが、contracts、state machine、lease、idempotency key は SQLite 等の durable 実装へ置換できる public model にする。

`PollAppActions` / `ReportActionResult` はこの phase では信頼済み local/internal client 前提である。public network に unauthenticated で公開してはならない。provider-level authorization は out of scope。

`SchedulerRunner` は `DeliveryAvailabilityProvider` protocol を通じて `DeliverySafetyGate` へ `AvailabilitySnapshot` を渡す。`IrisRuntimeService` に situation context を追加せず、availability safety を runtime scheduler path で有効にする。BUSY / UNAVAILABLE は enqueue を block する。

`DeliverySafetyGate` の runtime-level rate limit は現 phase では未実装とする。プロアクティブ送信頻度は `IdleTickSource` が `min_interval_per_target_seconds` で制御する。`delivery.rate_limit_window_seconds` は送信rate limitには使わず、strict policyが同一targetの直近blockを数える時間窓として使う。

`safety.mode = "strict"` は決定論的な配送安全規則を追加する。包括的なproduction moderationを意味しない。`IdleTickObservation` によるproactive配送では、`sensitive_safety_context`、BUSY / UNAVAILABLE、quiet hours、同一targetの直近反復blockを配送blockとする。通常のuser-initiated応答は、`sensitive_safety_context`の存在だけではblockしない。decisionはreason、risk level、not-before、raw contentを含まないaudit metadataを保持する。

現MVPの `proactive_sensitive_safety_context` は、同じ認知処理結果から `PresentedOutput.policy_constraint_names` へ明示伝播された `sensitive_safety_context` だけを評価する。`IdleTickObservation` は過去のuser textを再解釈せず、最近のuser messageにsensitive語があったという理由だけで後続idle tickを自動blockしない。過去turnを跨ぐtyped safety provenanceは後続phaseとする。

Output safetyとdelivery safetyのblock reasonはscheduler結果とruntime safety auditに保持する。Auditにはuser textや生成output本文を保存しない。

現MVPのsafety audit journalとblocked historyはprocess-localである。`state.backend = "sqlite"` でも `InMemorySafetyAuditJournal` を使用し、output/delivery safety reasonはruntime inspection用には保持するがrestartを越えて永続化しない。SQLite safety auditのdurable実装は意図的に後続phaseへ延期する。

## Forbidden Paths

```text
Scheduler → direct LLM call → direct external message send
Scheduler → Discord / CLI / voice SDK send
DeliveryOutbox → IrisApp / CognitiveCycle / external client send
features/proactive_talk → runtime.delivery / runtime.scheduler / safety
```

`NoAction` は外部副作用なしを意味するため、delivery outbox へ入れない。sendable ではない `PresentedOutput` と delivery safety で block された output も outbox へ入れない。

## Consequences

Runtime は orchestration、lifecycle、dependency wiring を所有する。認知 business logic、proactive salience、delivery safety policy、provider-specific send logic は所有しない。

gRPC adapter は DTO mapping と `AppActionBroker` protocol 呼び出しだけを行う。concrete runtime delivery implementation は import しない。

Retry 可能な `FAILED` は `PENDING` へ戻して `not_before` に retry 時刻、`last_error_reason` に失敗理由を保持する。最大試行後のみ `FAILED_PERMANENT` へ遷移する。
