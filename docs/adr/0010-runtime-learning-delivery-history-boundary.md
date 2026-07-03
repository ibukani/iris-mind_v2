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
- persistent transcript: 明示的に有効化された confirmed transcript store。short-term conversation history と `MemoryStore` とは分ける。
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

Transcript persistence は `conversation.transcript.enabled` で明示的に有効化し、`state.backend = "sqlite"` を使う場合だけ使う。`state.backend = "sqlite"` でも raw/confirmed transcript は privacy-sensitive な state として opt-in にし、default では `NullTranscriptStore` を使う。

Confirmed transcript の扱いは confirmed conversation history と揃える。

```text
inline SubmitObservation response
→ sendable actor message の場合のみ user + assistant transcript を記録する

outbox delivery ActionStatus.SUCCEEDED
→ delivered assistant transcript だけを記録する

outbox delivery ActionStatus.BLOCKED / FAILED / CANCELLED
→ normal transcript に記録しない
```

Transcript record は `iris/contracts/transcript.py` の durable boundary contract が所有する。これは `ConversationRecord` や `MemoryRecord` と別型であり、prompt window、raw/confirmed transcript、long-term memory を型レベルで混同しない。Retention は `conversation.transcript.retention_days` と store-level pruning policy で扱う。削除方針は `TranscriptDeletionPolicy` で明示し、transcript cleanup は既定で canonical `MemoryStore`、review candidate、delivery state へ伝搬しない。

Long conversation context は、recent records を raw user/assistant turns として保持し、古い records は deterministic summary として `ConversationWindow.summary` に畳む。Summary は prompt context 専用であり、assistant/user turn として履歴に混ぜず、`MemoryStore` に自動保存しない。

## Non-decisions

- LLM-based implicit memory extraction はこの ADR では実装しない。
- LLM-based transcript summarization はこの ADR では実装しない。
- Transcript export / management API はこの ADR では実装しない。
- failed delivery を監査ログへ残すかどうかは activity policy 側で扱う。

## Consequences

Blocked / failed / cancelled delivery は、学習イベントとして観測可能だが、通常の assistant turn として次ターンへ漏れない。

Proactive output は、生成時点ではなく successful delivery report 後にだけ confirmed conversation history へ入る。

Implicit learning は `LearningEvent.source_observation_id` を使って traceability を持てる。Implicit conversation candidate は review-required として `MemoryCandidateReviewStore` に保存し、long-term memory へは直接書かない。`MemoryCandidate` / source / reason / confidence / retention / sensitivity は `iris/contracts/memory_candidates.py` の durable boundary contract として所有し、SQLite adapter は cognitive package を import せずこの contract を永続化する。`MemoryCandidateReviewService` は `iris/contracts/review_candidates.py` の `ReviewCandidateSummary` / `ReviewCandidateDetail` / `ReviewDecisionResult` を返し、runtime 内部の store record を service 境界の外へ公開しない。`MemoryCandidateReviewService` で approved になった candidate だけが `ApprovedMemoryCandidatePromoter` 経由で durable `MemoryStore` に昇格できる。昇格時も source / reason / confidence / retention / review metadata を保持し、credential-like / sensitive profile / unsafe candidate は promotion policy で再拒否する。

Review candidate は `candidate_type` を持つ。現実装の promotion 対象は `memory` だが、review contract は `shared_episodic_memory`、`persona_patch`、`relationship`、`internal_state`、`consolidation` を同じ list / read / approve / reject / discard lifecycle で扱える。`shared_episodic_memory` は `ReviewSharedEpisodicMemoryCandidatePayload` を使い、profile / preference memory 用の `ReviewMemoryCandidatePayload` と混ぜない。Shared episodic candidate は actor/account/space、1件以上の source event ID / observation ID / timestamp、confidence、reason、review-required admission policy、sensitive/private/embarrassing/secret-like risk を保持する。Local AI / classifier 由来 candidate は model name/version、classifier name/version、confidence、reason、source event IDs、scope を metadata として保持する。Rejected candidate の metadata と review reason は将来の suppression signal として使えるが、suppression 実行 policy はこの ADR では実装しない。

`state.backend = "sqlite"` では `BackgroundJobQueue` と `MemoryCandidateReviewStore` も durable runtime learning state として SQLite に保存する。これにより、queued learning jobs、retry / lease state、pending review、approved / rejected / discarded lifecycle、promotion metadata は再起動後も保持される。`state.backend = "memory"` では process-local のままである。Promotion は `MemoryStore.update()` 後に review record の `promoted_memory_id` を更新する二段階処理であり、既に promotion 済みの `promoted_memory_id` が canonical `MemoryStore` で見つからない場合は通常の冪等 hit ではなく `promoted_memory_missing` として診断可能にする。

SQLite delivery outbox は nullable `source_observation_id` を保存する。`memory_candidate_reviews` は v4 migration で `candidate_type` を追加する。既存 review record は既定で `memory` candidate として扱う。

## Implementation anchors

- `iris/contracts/delivery.py`
- `iris/contracts/learning.py`
- `iris/contracts/memory_candidates.py`
- `iris/contracts/review_candidates.py`
- `iris/runtime/delivery/broker.py`
- `iris/runtime/conversation.py`
- `iris/runtime/state/conversation.py`
- `iris/runtime/state/transcript.py`
- `iris/contracts/transcript.py`
- `iris/runtime/scheduler/runner.py`
- `iris/runtime/wiring/runtime.py`
- `iris/adapters/persistence/sqlite/schema/delivery.py`
- `iris/adapters/persistence/sqlite/stores/delivery_outbox.py`
- `iris/adapters/persistence/sqlite/stores/background_jobs.py`
- `iris/adapters/persistence/sqlite/stores/memory_candidate_reviews.py`
- `iris/adapters/persistence/sqlite/stores/transcript.py`
