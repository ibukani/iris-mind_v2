# ADR 0010: Runtime Learning / Delivery / Conversation History Boundary

## Status

Accepted.

## Context

Iris の companion runtime では、会話応答、proactive delivery、長期記憶、関係性更新、transcript persistence が同じ会話データから派生する。しかし、これらを同期 cognitive hot path に混ぜると、次の状態が曖昧になる。

```text
生成された output
実際にユーザーへ届いた output
短期会話履歴として次ターンへ渡してよい output
長期記憶へ保存してよい inferred fact
監査・削除対象となる raw transcript
```

特に external adapter / Discord / proactive delivery では、`PresentedOutput` が生成されても delivery safety、client failure、network failure、provider-side block によりユーザーへ届かない場合がある。届いていない assistant output を通常の assistant turn として confirmed conversation history に入れると、Iris が「言っていないこと」を次ターンの文脈として扱う。

## Decision

Runtime は次の境界を分けて扱う。

- short-term conversation history: 次の cognitive turn に渡す process-local window。
- persistent transcript: 将来の raw/summarized transcript store。`MemoryStore` とは分ける。
- long-term memory: user/account/actor に紐づく durable memory。raw transcript ではない。
- relationship / affect state: memory ではなく専用 store の current state。
- delivery state: outbox と `ActionResult` が所有する external side-effect lifecycle。
- learning jobs: `ActionResult` 後に enqueue / run される post-result work。

`LearningHookRunner` は、名前は learning hook だが、runtime の action-result hook boundary としても使う。delivery-aware conversation history finalization は learning.enabled では無効化しない。これは学習推論ではなく、delivery result を見た後の履歴確定だからである。

Delivery item は `source_observation_id` を nullable に持つ。Scheduler / proactive path は enqueue 時に元 observation を保存し、`ReportActionResult` 受理後に生成される `LearningEvent` へ伝搬する。

Confirmed conversation history の扱いは次の通り。

```text
inline SubmitObservation response
→ sendable actor message の場合のみ user + assistant turn を記録する

outbox delivery ActionStatus.SUCCEEDED
→ delivered assistant turn だけを confirmed history に追加する

outbox delivery ActionStatus.BLOCKED / FAILED / CANCELLED
→ confirmed assistant history に追加しない
```

Delivery success で追加する assistant turn は、`DeliveryTarget` から actor/account/session と space を解決し、actor/account がある場合だけ space で分離する。session fallback では space を conversation key に含めない。

## Non-decisions

- raw transcript persistence はこの ADR では実装しない。
- transcript retention / deletion policy はこの ADR では確定しない。
- LLM-based implicit memory extraction はこの ADR では実装しない。
- conversation summarization はこの ADR では実装しない。
- failed delivery を監査ログへ残すかどうかは activity/transcript policy 側で扱う。

## Consequences

Blocked / failed / cancelled delivery は、学習イベントとして観測可能だが、通常の assistant turn として次ターンへ漏れない。

Proactive output は、生成時点ではなく successful delivery report 後にだけ confirmed conversation history へ入る。

Implicit learning は `LearningEvent.source_observation_id` を使って traceability を持てる。ただし、implicit candidate を long-term memory に直接書くかどうかは別 policy で決める。

SQLite delivery outbox は nullable `source_observation_id` を保存する。既存 DB migration は現 phase では扱わず、fresh schema creation を対象にする。

## Implementation anchors

- `iris/contracts/delivery.py`
- `iris/contracts/learning.py`
- `iris/runtime/delivery/broker.py`
- `iris/runtime/conversation.py`
- `iris/runtime/state/conversation.py`
- `iris/runtime/scheduler/runner.py`
- `iris/runtime/wiring/runtime.py`
- `iris/adapters/persistence/sqlite/schema/delivery.py`
- `iris/adapters/persistence/sqlite/stores/delivery_outbox.py`
