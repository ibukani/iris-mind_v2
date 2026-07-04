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

Scheduler lifecycle は default disabled とする。`state.backend = "memory"` では outbox / target store は process-local、`state.backend = "sqlite"` では `SQLiteDeliveryOutbox` と `SQLiteSchedulerTargetStore` が delivery state と scheduler targets を永続化する。contracts、state machine、lease、idempotency key は backend に依存しない public model として維持する。

`PollAppActions` / `ReportActionResult` は local development では local/internal client 前提で扱える。ただし public network に unauthenticated で公開してはならない。remote / public bind では runtime auth boundary が delivery polling / reporting scope と provider ownership を検査する。

`SchedulerRunner` は `DeliveryAvailabilityProvider` protocol を通じて `DeliverySafetyGate` へ `AvailabilitySnapshot` を渡す。`IrisRuntimeService` に situation context を追加せず、availability safety を runtime scheduler path で有効にする。BUSY / UNAVAILABLE は enqueue を block する。

`DeliverySafetyGate` は送信rate limitそのものを所有しない。プロアクティブ送信頻度は `IdleTickSource` が `min_interval_per_target_seconds` で制御する。`delivery.rate_limit_window_seconds` は送信rate limitには使わず、strict policyが同一targetの直近blockを数える時間窓として使う。直近block履歴は `SafetyAuditJournal.recent_block_count()` から取得し、`state.backend = "sqlite"` では restart 越しに参照できる。

`safety.mode = "strict"` は決定論的な配送安全規則を追加する。包括的なproduction moderationを意味しない。`IdleTickObservation` によるproactive配送では、`sensitive_safety_context`、BUSY / UNAVAILABLE、quiet hours、同一targetの直近反復blockを配送blockとする。通常のuser-initiated応答は、`sensitive_safety_context`の存在だけではblockしない。decisionはreason、risk level、not-before、raw contentを含まないaudit metadataを保持する。

High-risk context classification は Config v2 完了前に user-editable config として公開しない。Core cognitive cycle 内の常時有効な internal boundary として、policy enforcement 前に deterministic / provider-free な typed safety context を生成する。検出された `SafetyContext` は category、severity、source、confidence、reason code、response directive を持ち、raw user text を metadata に含めない。User-initiated な支援文脈は `allow_support` として通常応答を継続し、危険な手順要求は deterministic safe redirect / refusal を優先する。Proactive delivery では同じ typed context が `PresentedOutput` から `DeliverySafetyGate` へ伝播され、high severity context を配送 block として扱う。Configurable detector thresholds、enablement flags、schema/template changes、Control Plane manifest changes は Runtime Config v2 後の後続Issueで扱う。

現MVPの `proactive_sensitive_safety_context` は、同じ認知処理結果から `PresentedOutput.policy_constraint_names` へ明示伝播された `sensitive_safety_context` だけを評価する。`IdleTickObservation` は過去のuser textを再解釈せず、最近のuser messageにsensitive語があったという理由だけで後続idle tickを自動blockしない。過去turnを跨ぐtyped safety provenanceは後続phaseとする。

Output safetyとdelivery safetyのblock reasonはscheduler結果とruntime safety auditに保持する。Auditにはuser textや生成output本文を保存しない。

`state.backend = "memory"` の safety audit journal と blocked history は process-local である。`state.backend = "sqlite"` では `SQLiteSafetyAuditJournal` を使用し、output/delivery safety reason と同一targetの直近block履歴を restart 越しに参照する。Audit schema は raw user text / generated output body を保存しない。MVP retention policy として `retention_until` に90日後の削除境界を保存するが、自動削除 job は後続phaseで扱う。

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

## Implementation anchors

- `iris/runtime/scheduler/idle_tick.py`
- `iris/runtime/scheduler/runner.py`
- `iris/runtime/delivery/outbox.py`
- `iris/runtime/delivery/in_memory.py`
- `iris/adapters/persistence/sqlite/stores/delivery_outbox.py`
- `iris/adapters/persistence/sqlite/stores/scheduler_targets.py`
- `iris/runtime/state/safety_audit.py`
- `iris/adapters/persistence/sqlite/stores/safety_audit.py`
- `iris/runtime/wiring/scheduler.py`
- `iris/runtime/wiring/delivery.py`
- `iris/runtime/wiring/state.py`
- `docs/runtime-api.md`
