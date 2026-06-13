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

state-onlyのactivity/presence observationはintegration後に `PresentedOutput(text=None)` を返し、通常のtext response生成へ流さない。EventReactionは未実装。

現在のstoreはin-memoryのみ。将来の永続activity logは別adapterで実装し、memory extractionはraw `ActivityEventRecord` ではなく明示的な `MemoryCandidate` eventから行う。PR4 で availability と workspace context assembly を実装済み。event reaction、delivery target、persistenceは未実装。

---

## Learning と BackgroundJob（未実装）

Learning は ActionResult 後に行う設計だが、現状未実装。

```text
ActionPlan
→ Presentation
→ SafetyGate
→ Adapter
→ ActionResult
→ LearningHook       ← 未実装
```

理由。
- 送信成功したか
- 失敗したか
- safety で blocked されたか

を見てから記憶や関係性を更新する必要がある。

### LearningHook（予定）

hot path で実行する軽量処理。
- 会話ログの追加
- working memory 更新
- relationship の軽い更新
- background job の enqueue

### BackgroundJob（予定）

hot path から外す重い処理。
- 長期記憶抽出
- LangMem extraction
- persona patch proposal
- episodic → semantic promotion
- 重い reflection

---

## Proactive（実装済み）

Proactive は内部 Observation から始まる CognitiveCycle として実装されている。

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

---


## 関連ドキュメント

- architecture.md: 全体構造、各層の責務、依存方向
- rules.md: 認知サイクルに関する Do/Don't
## Space Context Rule

Cognitive flow は memory、relationship、persona semantics の主スコープとして `actor_id` を使う。`space_id` は observation が発生した外部contextの補助scope。

Default runtime は `SpaceBinding` を永続化しない。Space に conversation history や persona state を紐づけない。

`InteractionSpace` は安定したロケーション識別情報とコンテキストのみを表し、現在の在室者を保持しない。在室者の正本は `SpaceOccupancyStore`。
