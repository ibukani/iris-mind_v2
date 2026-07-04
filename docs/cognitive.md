# Cognitive Cycle と拡張設計

## 認知サイクル

Iris の中核は `cognitive/` にあり、認知サイクル、記憶、感情、行動選択を担当する。

中心は `CognitiveCycle`。

```python
class CognitiveCycle:
    async def run(self, observation: Observation) -> CycleResult:
        ...
```

`CognitiveCycle` は God Service ではなく pipeline coordinator として実装する。

### 実装済み PipelineStep

| Step | ソース | 役割 |
|---|---|---|
| `SimplePerceptionStep` | `cognitive/perception/basic.py` | Observation からテキスト抽出 |
| `MemoryRetrievalStep` | `cognitive/memory/retrieval.py` | MemoryStore からの関連記憶検索 |
| `AppraisalStep` | `cognitive/affect/appraisal.py` | 感情評価 (mood, arousal, valence, dominance) |
| `RelationshipStep` | `cognitive/affect/relationship.py` | 関係性スナップショット更新 (affinity, trust, familiarity) |
| `PolicyInhibitionStep` | `cognitive/policy/inhibition.py` | 発話抑制・行動制約 |
| `ResponseGenerationStep` | `cognitive/action/response.py` | LLM 応答生成 → ActionPlan |

### 利用可能な配線

`runtime/wiring/cognitive.py` に4種類の配線:

1. `wire_text_response_cognitive_cycle` — Perception → ResponseGeneration
2. `wire_memory_aware_text_response_cognitive_cycle` — Perception → MemoryRetrieval → ResponseGeneration
3. `wire_affect_memory_aware_text_response_cognitive_cycle` — Perception → (memory) → Appraisal → Relationship → ResponseGeneration
4. `wire_policy_affect_memory_aware_text_response_cognitive_cycle` — Perception → (memory) → Appraisal → Relationship → PolicyInhibition → ResponseGeneration

### 拡張予定（未実装）

- `MotivationStep` — `MotivationResult` 型と `FrameBuilder` の対応は既存、step 実装は未着手
- `PlanningStep` — 将来の目標計画ステップ

基本フロー（最大構成）:

```text
Observation
→ SimplePerceptionStep
→ MemoryRetrievalStep
→ AppraisalStep
→ RelationshipStep
→ PolicyInhibitionStep
→ ResponseGenerationStep
→ ActionPlan
```

重要ルール。

- cognitive module 同士は直接呼び合わない。
- `CognitiveCycle` が順序制御する。
- 各 PipelineStep は `WorkspaceFrame` を直接 mutate しない。
- 各 PipelineStep は typed result を返す。
- `FrameBuilder` が typed result を `WorkspaceFrame` に統合する。

悪い例。

```text
memory → affect を直接呼ぶ
affect → policy を直接呼ぶ
policy → action を直接呼ぶ
```

良い例。

```text
CognitiveCycle → memory step
CognitiveCycle → affect step
CognitiveCycle → motivation step
CognitiveCycle → policy step
CognitiveCycle → action step
```

---

## Workspace

1ターン中の状態を集約する。

`WorkspaceFrame` は frozen dataclass。実際のフィールド:

- `observation: Observation`
- `interpreted_input: InterpretedInput | None`
- `memory_summary: MemorySummary`
- `affect: AffectSnapshot`
- `relationship: RelationshipSnapshot`
- `goals: tuple[GoalCandidate, ...]`
- `constraints: tuple[PolicyConstraint, ...]`
- `action_preferences: tuple[ActionPreference, ...]`
- `policy_summary: str | None`
- `candidate_action_plans: tuple[ActionPlan, ...]`
- `actor_context: ActorContextSnapshot`
- `space_context: SpaceContextSnapshot`
- `situation_context: SituationContextSnapshot`

入れてはいけないもの。

- storeそのもの
- adapterそのもの
- manager参照
- 過去ログ全体
- 巨大な `dict[str, Any]`
- LLM prompt 文字列だけの巨大 context

`SituationContextSnapshot` はランタイム state から 1 ターン用に組み立てられた snapshot。

- `latest_activity: ActivityEventRecord | None`
- `presence: PresenceSnapshot | None`
- `space_occupancy: SpaceOccupancySnapshot | None`
- `availability: AvailabilitySnapshot | None`

`availability` は `AvailabilityResolver` が `PresenceSnapshot` / 直近 activity / 時刻から決定論的に導出する。
`WorkspaceContextAssembler` が `ActivityProjectionStore` / `PresenceStore` / `SpaceOccupancyStore` を読み、`SituationContextSnapshot` を作る。
認知サイクルはこの snapshot を読み取って応答判断に使うが、store へのアクセスは `runtime` 層に委ねる。

`WorkspaceFrame` は「何でも入る箱」にしない。

---

## Typed Observation Ingress

runtime境界が受け付けるtyped observationは次の4種類。

- `ActorMessageObservation`: actorのテキストmessage。
- `IdleTickObservation`: runtime内部のidle tick。
- `ActivityEventObservation`: 非message外部activity event。
- `PresenceSignalObservation`: provider/clientが観測したactor presence signal。

`ActivityEventObservation` はtext messageを表さず、`PresenceSignalObservation` はvoice channel在室状態を表さない。中核意味はtyped fieldとenumで表し、metadataはprovider固有の補助情報だけに使う。

`ActorMessageObservation` はactor text messageの唯一のtyped ingress。typing開始/終了、voice join/leaveなどactor-scoped activityと、すべてのpresence signalは解決済みactorまたはaccount subjectを必須とする。`SYSTEM_INTERACTION` などsystem-level activityはsubjectなしを許可する。

両観測は外部sourceからの報告・claimであり、Iris内部stateの更新commandではない。runtime boundaryが `ObservationEnvelope.ingress` に `ObservationIngressContext` を付与し、`ObservationTrustPolicy` は認証済みingress capabilityだけを検査する。`ObservationContext.source` や user-controlled metadata だけでtrustを決めない。

```text
ActivityEventObservation
→ ObservationTrustPolicy
→ ActivityIntegrator
→ ActivityJournal
→ ActivityProjectionStore

PresenceSignalObservation
→ ObservationTrustPolicy
→ PresenceIntegrator
→ PresenceStore

ActivityEventObservation(VOICE_JOINED / VOICE_LEFT)
→ ObservationTrustPolicy
→ SpaceOccupancyIntegrator
→ SpaceOccupancyStore
```

`ActivityEventRecord` は受理済みruntime eventであり、長期記憶ではない。`ActivityJournal` はデフォルトでbounded runtime journalで、永続conversation historyやmemory candidate storageとして扱わない。`ActivityProjectionStore` はactor/spaceごとのlatest activity projectionだけを持つ。Presenceからvoice occupancyを推論しない。`InteractionSpace` にparticipantsを戻さない。

`SpaceOccupant` は actor-level の現在在室メンバーシップのみを表す。account_id / device_id は `IdentityResolver` / `AccountStore` / `Identity` 層が所有する。`ActivityEventRecord` や `PresenceSnapshot` は provenance として account_id / device_id を保持してよいが、`SpaceOccupant` では identity-link を重複して持たない。

state-onlyのactivity/presence observationはintegration後に `PresentedOutput(text=None)` を返し、通常のtext response生成へ流さない。ただし、trusted `ActivityEventObservation` のうち `EventReactionPolicy` で許可された kind / availability の組み合わせに対しては、`EventReactionRunner` が決定論的な `PresentedOutput` を返す。これはtext response pipelineではなく、runtime層のcontext-local reactionである。

現在の runtime state は、current-state projection と durable state を分ける。`state.backend = "memory"` では全runtime stateが process-local。`state.backend = "sqlite"` では `ActivityJournal`、account / memory / relationship / affect、delivery outbox、scheduler target store、safety audit journal、runtime learning background jobs、memory candidate review lifecycle を SQLite に永続化する。Transcript は privacy-sensitive state として `conversation.transcript.enabled = true` の場合だけ SQLite に保存する。Activity projection、presence、space occupancy、ephemeral space binding、learning dispatch、short-term conversation history は process-local のままにする。

memory extraction は raw `ActivityEventRecord` から直接行わず、`RuntimeLearningEvent` / `MemoryCandidate` と review lifecycle を通す。availability と workspace context assembly、event reaction、scheduler / delivery outbox / state persistence / runtime learning foundation は実装済み。

未実装または後続拡張は Proactive text generation の高度化、production safety policy、Transcript 管理 API / export、Control Plane UI である。

---


## Small Model Ports

Iris は large LLM を最終応答生成に使い、小型モデルを intent / safety / salience / memory admission /
retrieval / reranking / response policy selection に使えるようにする。ただし、runtime や cognitive step が
特定 provider へ直接依存してはならない。

#89 では次の port を定義する。

- `TextClassifier`: `ClassificationRequest` から `ClassificationResult` を返す。結果は `label`、`confidence`、`reason`、`ModelInvocationMetadata`、`latency_ms` を持つ。
- `EmbeddingClient`: `EmbeddingRequest` / `EmbeddingBatchRequest` から metadata 付き embedding result を返す。既存の `EmbeddingModel` は memory vector index 互換性のため維持する。
- `Reranker`: `RerankRequest` から `RerankResult` を返す。候補 ID、rank、score、reason、model metadata を typed contract として扱う。

Fake / rule implementation は `iris/adapters/` に閉じる。`cognitive/` は実装 adapter を import せず、必要な場合は
constructor injection された port だけを見る。runtime 側では `Budgeted*` wrapper が #88 の call budget に接続し、
`Observable*` wrapper が #90 の latency / call count observability に接続する。実 runtime wiring で両方を使う場合は
`compose_observable_budgeted_*` helper により `Observable(Budgeted(adapter))` の順序で合成し、budget denial も観測対象にする。

この時点では特定 production model、training dataset、evaluation dashboard、#94 retrieval pipeline 本体は実装しない。
#91 の prompt section budget が未適用の間、classifier / retrieval / reranker output を prompt に重く統合しない。

## Learning と BackgroundJob（実装済み skeleton）

Learning は ActionResult / runtime outcome 後に行う。生成された output、実際に delivery された output、blocked / failed / cancelled を分けて観測し、cognitive hot path で重い学習を実行しない。

```text
ActionPlan
→ Presentation
→ SafetyGate
→ Adapter / Runtime outcome
→ ActionResult / RuntimeLearningEvent
→ LearningHook / RuntimeLearningHook
→ BackgroundJobQueue
```

実装済みの境界。
- `LearningHookRunner` / `RuntimeLearningHookRunner` は hook failure を user-facing path へ伝搬しない。
- `BackgroundJobQueue` は runtime learning work を hot path 外で実行する queue 境界として実装済み。`state.backend = "sqlite"` では durable queue、`state.backend = "memory"` では process-local queue を使う。
- 明示メモリ保存は `MemoryBackgroundJobPayload` から `MemoryStore` へ保存できる。
- implicit conversation learning は保守的抽出器で `MemoryCandidateReviewStore` に review-required candidate として保存する。`MemoryCandidate` の durable contract は `iris/contracts/memory_candidates.py` が所有し、SQLite adapter は cognitive 内部 model を import しない。`state.backend = "sqlite"` では review lifecycle と promotion metadata は再起動後も保持される。
- approved implicit candidate だけが `ApprovedMemoryCandidatePromoter` 経由で durable `MemoryStore` に昇格できる。
- promotion 済み metadata と canonical `MemoryStore` の欠損は `promoted_memory_missing` として通常の冪等 promotion と区別する。

未実装または後続作業。
- LLM-based implicit extraction。
- Transcript 管理 API / export。
- LLM-based transcript summarization。
- persona patch / relationship / internal-state worker。

Conversation context は `ConversationHistoryPolicy` で bounded window にする。recent records は raw user/assistant turns として残し、古い records は deterministic summary として `ConversationWindow.summary` に畳む。Summary は prompt context 専用であり、durable memory へ自動保存しない。

Transcript persistence は opt-in で、`conversation.transcript.enabled = true` かつ `state.backend = "sqlite"` のときだけ confirmed inline response / successful delivery を `TranscriptStore` に保存する。Blocked / failed / cancelled delivery は normal transcript として保存しない。Transcript deletion は既定で canonical memory、review candidate、delivery state へ伝搬しない。

---

## Proactive Scheduler / Delivery Foundation（基盤実装済み）

Proactive は内部 Observation から始まる CognitiveCycle として実装されている。Scheduler は外部送信 client を呼ばず、runtime service に typed internal observation を投入する。送信可能な output だけが delivery safety と outbox を通り、外部 client は `PollAppActions` で pull して `ReportActionResult` を返す。

```text
Scheduler (runtime)
→ IdleTickObservation
→ CognitiveCycle (with proactive steps)
→ WorkspaceFrame
→ ActionPlan
→ Presenter
```

`features/proactive_talk/` に実装:

| モジュール | 役割 |
|---|---|
| `scoring.py` | SalienceScorer（発話重要度スコアリング） |
| `goals.py` | GoalProposer（会話目標提案） |
| `policy.py` | プロアクティブ発話のポリシー制約 |
| `models.py` | プロアクティブ専用型 |
| `definition.py` | FeatureDefinition 登録 |

`IdleTickObservation` は基底 `Observation.context` に actor / account / device / space 情報を持つ。
直接 `Observation.actor` / `Observation.space_id` は使わない。
`features/proactive_talk/` が直接 memory や policy の内部実装を改造してはいけない。

実装済みの foundation。

- `IdleTickSource` / `SchedulerRunner`: due target から `IdleTickObservation` を生成し、runtime service へ投入する。
- `SchedulerTargetStore`: `state.backend = "sqlite"` では `SQLiteSchedulerTargetStore` により restart 越しに保持する。
- `DeliverySafetyGate`: quiet hours、availability、strict safety policy、同一targetの直近block履歴を評価する。
- `DeliveryOutbox`: `state.backend = "sqlite"` では `SQLiteDeliveryOutbox` により lease / retry / idempotent report state を保持する。
- `SafetyAuditJournal`: raw textを保存せず、output / delivery safety decision metadata と recent block count を保持する。
- pull-based delivery API: `PollAppActions` / `ReportActionResult` で external client が送信結果を確定する。

未実装または後続作業。

- LLM-based proactive text generation refinement。
- production safety policy / moderation policy の完成。
- provider/channel 別の自律配送ポリシー。
- Control Plane UI からの scheduler / delivery / transcript 管理。

---


## 関連ドキュメント

- architecture.md: 全体構造、各層の責務、依存方向
- rules.md: 認知サイクルに関する Do/Don't
## Space Context Rule

Cognitive flow は memory、relationship、persona semantics の主スコープとして `actor_id` を使う。`space_id` は observation が発生した外部contextの補助scope。

Default runtime は `SpaceBinding` を永続化しない。Space に conversation history や persona state を紐づけない。

`InteractionSpace` は安定したロケーション識別情報とコンテキストのみを表し、現在の在室者を保持しない。在室者の正本は `SpaceOccupancyStore`。

## Prompt budget と context compression

User-facing response generation は `ResponsePrompt` をそのまま巨大な prompt 文字列へ変換しない。`runtime/prompting` の assembler が section 単位に分け、`prompt_budget` profile の deterministic policy を適用してから `LLMRequest` を作る。

Prompt section は次の trust boundary を持つ。

- `trusted`: system instruction、runtime safety guardrails、将来の persona section。
- `internal_derived`: affect / relationship summary、policy constraints、goals、conversation summary。
- `external_context`: memory / project context / retrieval result。
- `user_input`: recent conversation と latest user message。

trusted sections と external context は provider message role 上でも混ぜない。`SYSTEM` role message には trusted instruction / runtime guardrails のみを入れ、internal-derived context と external context は separate context message として渡す。latest user message は system message に入れず、最後の `USER` role message として渡す。短期会話履歴は `recent_conversation` section budget の対象になり、古い record から deterministic に落とす。

`local_low` / `local_balanced` / `local_quality` / `proactive_short` profile は `RuntimePromptBudgetConfig` が source of truth になる。#94 の retrieval top-k は profile の `user_memory` / `project_memory` section budget を参照する。#98 の persona や #78 の proactive prompt は section metadata と budget accounting を通して接続する。
