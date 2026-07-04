# Iris Cognitive Runtime Architecture

## 目的

Iris は、AIコンパニオン / Neuro-sama 的な自発性・記憶・関係性・突飛さを持つ AI Runtime として再設計する。

破壊的変更を許可し、既存構造との後方互換よりも、以下を優先する。

- AIコーディングエージェントが実装場所を迷わない
- ツギハギ実装を構造的に防ぐ
- Proactive / Memory / Relationship / PersonaPatch を拡張しやすくする
- Discord / Voice / Twitch / Avatar など外部アプリと疎結合にする
- 脳科学を参考にしつつ、ソフトウェアとして扱いやすい認知サイクルに落とし込む
- MVPを小さく作り、段階的に機能拡張できるようにする

---

## 基本思想

Iris は「脳の部位を直接模倣するシステム」ではなく、**脳科学を参考にした認知サイクルを実行する AI コンパニオン Runtime** として設計する。

脳科学の概念は、以下のように機能へ翻訳して扱う。

| 脳科学的な参考 | Irisでの設計単位 |
|---|---|
| 作業記憶 | `WorkspaceFrame` |
| 海馬 / エピソード記憶 | `cognitive/memory/episodic` |
| 意味記憶 | `cognitive/memory/semantic` |
| 扁桃体 / 価値評価 | `cognitive/affect/appraisal` |
| 気分 | `cognitive/affect/mood` |
| 関係性評価 | `cognitive/affect/relationship` |
| 動機づけ | `cognitive/motivation` |
| 行動選択 | `cognitive/policy` |
| 抑制 | `cognitive/policy/inhibition` |
| 行動実行 | `cognitive/action` |
| 学習・記憶統合 | `cognitive/learning` + `BackgroundJob` |

中心となる流れは以下。

```text
External App
→ Observation
→ AppGateway
→ CognitiveCycle
→ typed PipelineStep results
→ WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presentation
→ PresentedOutput
→ OutputSafetyGate
→ AppAction
→ External App
→ ActionResult
→ LearningHook
→ BackgroundJob
```

---

## ディレクトリ構成

```text
iris/
├── core/
│   └── ids.py
│
├── contracts/
│   ├── observations.py
│   ├── actions.py
│   ├── identity.py
│   ├── spaces.py
│   ├── memory.py
│   ├── policy.py
│   ├── availability.py
│   └── external_refs.py
│
├── runtime/
│   ├── app.py
│   ├── service.py
│   ├── server.py
│   ├── config/
│   ├── wiring/
│   ├── ingress/
│   ├── state/
│   ├── scheduler/
│   ├── delivery/
│   ├── learning/
│   ├── lifecycle/
│   └── observability/
│
├── cognitive/
│   ├── cycle/
│   │   ├── service.py
│   │   ├── pipeline.py
│   │   ├── frame_builder.py
│   │   └── models.py
│   │
│   ├── workspace/
│   │   └── frame.py
│   │
│   ├── perception/
│   │   └── basic.py
│   │
│   ├── memory/
│   │   └── retrieval.py
│   │
│   ├── affect/
│   │   ├── appraisal.py
│   │   ├── mood.py
│   │   └── relationship.py
│   │
│   ├── policy/
│   │   └── inhibition.py
│   │
│   └── action/
│       ├── basic.py
│       └── response.py
│
├── presentation/
│   ├── presenter.py
│   └── event_reaction.py
│
├── features/
│   ├── proactive_talk/
│   │   ├── definition.py
│   │   ├── goals.py
│   │   ├── models.py
│   │   ├── policy.py
│   │   └── scoring.py
│   └── event_reaction/
│       ├── planner.py
│       ├── policy.py
│       └── templates.py
│
├── adapters/
│   ├── persistence/
│   │   └── sqlite/
│   │       └── stores/
│   ├── app_gateway/
│   │   ├── ingress.py
│   │   ├── identity_resolver.py
│   │   ├── ports.py
│   │   ├── space_resolver.py
│   │   └── stable_ids.py
│   ├── llm/
│   │   ├── fake.py
│   │   ├── ollama.py
│   │   ├── openai.py
│   │   └── ports.py
│   └── memory/
│       ├── fake.py
│       ├── langchain.py
│       ├── ports.py
│       └── vector.py
│
└── safety/
    ├── action_gate.py
    └── output_filter.py
```

`iris/admin` は現在のアクティブ構成には含めない。過去構想や廃止済み構造は `docs/legacy.md` に隔離し、実装時に再作成しない。

実装済み / 方針採択済みの runtime foundation:

- `runtime/scheduler/` — `IdleTickSource` と `SchedulerRunner` による typed internal observation 発行。詳細は ADR 0006。
- `runtime/delivery/` — pull-based delivery outbox、lease、idempotent `ReportActionResult`。詳細は ADR 0006。
- `runtime/observability/` — runtime trace context、safe lifecycle logs、LLM request observer、startup diagnostics、runtime doctor。詳細は ADR 0008。
- `runtime/state/` — runtime-owned state ports、activity projection、presence、space occupancy、workspace context assembly。SQLite backend の永続化範囲は ADR 0002、schema migration / backup / recovery は ADR 0012。
- `runtime/learning/` — action-result 後の learning hook、background job queue、implicit memory candidate review / promotion 境界。詳細は ADR 0010。
- `runtime/lifecycle/` — scheduler lifecycle task と background job loop の起動・停止境界。
- `safety/policy_engine.py` — LLM/APIを使わない決定論的strict safety policy。

Deferred / future phase:

- `cognitive/motivation/` — MotivationStep の実装（`MotivationResult` 型と `FrameBuilder` 対応は既存）
- LLM-based implicit extraction / transcript summarization
- `features/memory_consolidation/`, `features/relationship_update/`, `features/persona_patch/`
- `adapters/tools/`, `adapters/embeddings/`

---

## 各層の責務

### `core/`

最下層の共通基盤。

置いてよいもの。

- 共通ID
- 時刻
- Result型
- 共通エラー
- 型ユーティリティ

置いてはいけないもの。

- 記憶処理
- 会話処理
- LLM処理
- Adapter処理
- Feature共通処理

`core/` は便利箱にしない。

### `contracts/`

層間で共享する型を置く。データモデルの型安全と実行時バリデーションを強化するため、境界モデルから Pydantic V2 の `BaseModel` を段階的に導入する。ただし標準の `dataclass` を全廃するわけではない。

主な責務。

- `Observation`
- `Action` / `ActionPlan`
- `Identity` (actor-centered)
- `InteractionSpace`
- `Memory` / `MemorySearchResult`
- `Policy` / `ActionPreference` / `PolicyConstraint`
- `AppraisalSignal` / `AppraisalSemantics`

`Identity` は人間・デバイス・サービス・システム・Iris 自身を区別する `ActorKind` を持つ。
`AccountId` / `DeviceId` は任意の関連リンクで、認証・権限はここで扱わない。

注意点。

- 全体をまとめた巨大な `contracts/ports.py` は作らない。
- 安定したドメインレコードと、それに直結する安定したドメインストアのプロトコル（例: `MemoryStore`, `RelationshipStore`, `AffectStore`）は `contracts/<domain>.py` または `contracts/<domain>/` に配置してよい。
- `WorkspaceFrame` 自体は `contracts` には移さず、機能間で共有が必要な「最小限の context 型」だけを `contracts/` に切り出して一元管理する。
- 特定のユースケースに特化した Runtime / Application port は、それを利用するモジュールの近く（consuming layer）に置く。
- EventBus 的な逃げ道は作らない。

Port の配置例。

```text
cognitive/action/ports.py
cognitive/memory/ports.py
presentation/ports.py
safety/ports.py
adapters/app_gateway/ports.py
```

### `runtime/`

アプリケーション起動、構成、ライフサイクル、スケジューリング、配送、観測 ingress、依存配線、可観測性、runtime state ports / stores を担当する。

主な責務。

- アプリ起動
- 設定読み込み
- dependency wiring
- lifecycle
- scheduler
- delivery outbox / delivery lifecycle
- ingress orchestration
- observability
- runtime state ports / stores

注意点。

- `runtime/composition.py` 1ファイルにすべて詰め込まない。
- `runtime/wiring/` に分割する。
- `runtime/wiring/` は constructor injection に限定する。DI コンテナ（dependency-injector 等）は導入せず、手動配線でシンプルさと構成の明確さを維持する。
- `runtime/wiring/` に業務ロジックや認知ロジックを書かない。
- `runtime/ingress/` は trust check、観測統合、runtime handler 呼び出し、safety gate などの orchestration に限定する。
- `runtime/state/` は activity journal/projection、presence、space occupancy、scheduler target、availability、workspace context assembly など runtime-owned state とその port を置く。volatile store は process-local、durable backend は `runtime/wiring/state.py` が明示的に adapter を注入する。`ActivityJournal` port は consuming runtime state module の近くに置く。
- `runtime/state/` は当面 flat に保つ。大きくなった場合だけ state family ごとに `runtime/state/activity/`、`runtime/state/presence/`、`runtime/state/space_occupancy/`、`runtime/state/scheduler_targets/` へ分割する。複数ファイルが同じ family に溜まるまで、美観だけで nested package を作らない。
- feature 固有の policy、planning、scoring、candidate generation、template は `features/` に置く。
- domain/action/reaction candidate から `PresentedOutput` への変換は `presentation/` に置く。

`runtime` だけが全体を知ってよい。

### `cognitive/`

Iris の中核。認知サイクル、記憶、感情、動機、行動選択、学習を担当する。

中心は `CognitiveCycle`。

```python
class CognitiveCycle:
    async def run(self, observation: Observation) -> CycleResult:
        ...
```

ただし、`CognitiveCycle` は God Service にしない。
処理本体ではなく pipeline coordinator として実装する。

基本フロー（実装済み）。

```text
Observation
→ SimplePerceptionStep
→ MemoryRetrievalStep (optional)
→ AppraisalStep (optional)
→ RelationshipStep (optional)
→ PolicyInhibitionStep (optional)
→ ResponseGenerationStep
→ ActionPlan
```

利用可能な配線（`runtime/wiring/cognitive.py`）:

| 配線関数 | ステップ順序 |
|---|---|
| `wire_text_response_cognitive_cycle` | Perception → ResponseGeneration |
| `wire_memory_aware_text_response_cognitive_cycle` | Perception → MemoryRetrieval → ResponseGeneration |
| `wire_affect_memory_aware_text_response_cognitive_cycle` | Perception → (MemoryRetrieval) → Appraisal → Relationship → ResponseGeneration |
| `wire_policy_affect_memory_aware_text_response_cognitive_cycle` | Perception → (MemoryRetrieval) → Appraisal → Relationship → PolicyInhibition → ResponseGeneration |

拡張予定（未実装）:

- MotivationStep — `MotivationResult` 型と `FrameBuilder` の対応は既存、step 実装は未着手
- PlanningStep — 将来の目標計画ステップ

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

### `workspace/`

1ターン中の状態を集約する。

`WorkspaceFrame` は、会話ターン内で各認知モジュールが共有する typed snapshot である。

実際のフィールド（`WorkspaceFrame`）:

- `observation` — 元の Observation
- `interpreted_input` — `InterpretedInput` (text, language, intent_hint)
- `memory_summary` — `MemorySummary` (retrieved_memories)
- `affect` — `AffectSnapshot` (mood_label, arousal, valence, dominance, affect_summary)
- `relationship` — `RelationshipSnapshot` (actor_label, affinity, trust, familiarity, relationship_summary)
- `goals` — `tuple[GoalCandidate, ...]`
- `constraints` — `tuple[PolicyConstraint, ...]`
- `action_preferences` — `tuple[ActionPreference, ...]`
- `policy_summary` — `str | None`
- `candidate_action_plans` — `tuple[ActionPlan, ...]`

入れてはいけないもの。

- storeそのもの
- adapterそのもの
- manager参照
- 過去ログ全体
- 巨大な `dict[str, Any]`
- LLM prompt 文字列だけの巨大 context

`WorkspaceFrame` は「何でも入る箱」にしない。肥大化を防ぐため、機能間で共有必須な型だけを `contracts/` 側に切り出し、Feature 固有のデータは各 Feature 内に閉じて管理する。

### `presentation/`

`cognitive/` が決めた `ActionPlan`、または feature が生成した domain/action/reaction candidate を、実際にどのような形で見せるかに変換する。

MVPでは軽量。`SimplePresenter` が `ActionPlan` を `PresentedOutput` に変換する。
`EventReactionPresenter` は `ReactionCandidate` を `PresentedOutput` に変換するだけで、反応可否の判断、trust check、safety gate は行わない。

```text
ActionPlan
→ SimplePresenter
→ PresentedOutput
```

責務分離。

```text
cognitive/      = 何をしたいかを決める
presentation/   = どう見せるかを決める
adapters/       = どこへ送るかを担当する
```

### `features/`

新機能を縦切りで追加する場所。
各featureは Vertical Slice Architecture の考え方に基づいて整理する。feature固有の policy、planning、scoring、candidate generation、template、`FeatureDefinition` provider、および feature 固有の `ports`, `models`, `services` をこのフォルダ内に完結させる。ただし、`MemoryStore` などの安定したドメインPortは `contracts` 側に残し、feature-local な port はその feature 固有のものだけに限定する。

ただし、`features/` は好き勝手に内部実装を改造する場所ではない。
`CognitiveCycle` の拡張ポイントに参加する extension provider である。

各 feature は `features/<name>/` に縦切りで配置し、`FeatureDefinition` を返す `define_feature()` 関数を公開する。

```python
@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    pipeline_steps: Sequence[PipelineStep[PipelineStepResult]] = ()
    observation_sources: Sequence[ObservationSource] = ()
    learning_hooks: Sequence[LearningHook] = ()
    background_jobs: Sequence[BackgroundJob] = ()
```

現在実装済みの feature: `proactive_talk/`（salience scoring, goal proposal, proactive policy, expression抑制）と `event_reaction/`（activity event reaction policy、planning、template）。

`FeatureDefinition` は現在のところ内部拡張の型契約であり、自動検出（auto-discovery）や汎用レジストリによる動的ロードは実装されていない。
各 feature の有効化は `runtime/wiring/features.py` などの配線層で、明示的な関数呼び出しとパイプラインステップへのマニュアル追加によって行われる。

feature は `runtime/`、`adapters/`、`presentation/`、`safety/` に依存しない。runtime が feature を明示的に配線・実行する。

`event_reaction` は名前が同じでも層ごとに責務を分ける。

```text
features/event_reaction/
  反応可否、policy、planning、template、ReactionCandidate生成を担当する。

presentation/event_reaction.py
  ReactionCandidate を PresentedOutput に変換する。

runtime/ingress/activity_event_reaction.py
  trust check、reaction pipeline呼び出し、OutputSafetyGate適用を担当する。
```

### `adapters/`

外部技術との接続を担当する。
provider、transport、storage、SDK、backend implementation はここに置く。runtime state port は利用側の `runtime/state/` に置く。SQLite による永続化実装 (activity journal, memory, relationship など) は `adapters/persistence/sqlite/stores` に集約する。
`runtime/wiring/state.py` は設定に基づき SQLite store を選択し、port として注入してよい。

原則として `adapters/` は `runtime/` を import しない。
例外として backend adapter が runtime-owned port を実装できる条件:

- port が consuming runtime module の近くに意図的に置かれている。
- adapter が import する runtime module はその narrow port module だけ。
- adapter は `runtime/wiring`、`runtime/service`、`runtime/app`、`runtime/ingress`、`runtime/scheduler`、`runtime/delivery`、`runtime/lifecycle`、`runtime/observability` を import しない。
- 例外は architecture test に file/import pair と理由つきで登録する。

`adapters/app_gateway/` の責務は、外部アプリとの `Observation / AppAction / ActionResult` protocol boundary である。

`adapters/llm/` は LLM 技術境界である。
責務は、typed `LLMRequest` を受け取り typed `LLMResponse` を返すことに限定する。
実プロバイダ呼び出し、モデル選択、認証、ネットワーク I/O は adapter 境界の外へ漏らさない。
テストと local MVP は deterministic な `FakeLLMClient` を使う。
OpenAI provider は `adapters/llm/openai.py` に置き、Responses API との変換を adapter 内に閉じ込める。
real provider configuration は typed config で明示注入し、global discovery や service locator は使わない。
provider tests は `FakeLLMClient` または mocked provider client を使い、実ネットワークへ接続しない。
`cognitive/` は `adapters/llm/` を import せず、runtime wiring が constructor injection で接続する。

`adapters/memory/`（元 `adapters/stores/`）は memory store 技術境界である。
責務は、typed `MemoryQuery` を受け取り typed `MemorySearchResult` を返すことに限定する。
テストと local MVP は deterministic な `FakeMemoryStore` を使う。
LangChain / LangMem / vector store は `MemoryStore` 背後の optional adapter としてだけ扱う。
`cognitive/` は `MemoryQuery` と `MemorySearchResult` だけに依存し、LangChain、LangMem、vector DB SDK、adapter 型を import しない。
`runtime/wiring/` は constructor injection で adapter を明示的に組み立てる。
LangChain adapter は LangChain document / vectorstore 型を Iris contracts に漏らさない薄い変換層である。
In-memory vector adapter は外部サービスなしの deterministic adapter に限定する。
LangMem promotion / consolidation、実 embeddings provider、vector DB persistence は後続 phase まで入れない。
`cognitive/memory/` は store 実装を import せず、runtime wiring が constructor injection で接続する。

#### MemoryStore ポート階層

メモリストア境界は 2 層の protocol で表現する。

- `MemoryStore`: `search` / `put` のみの最小契約。LangChain/vector など書き込み API を持たない外部バックエンドの互換性のために維持する。
- `MutableMemoryStore(MemoryStore)`: `get` / `update` / `archive` / `filter` を追加した完全な CRUD 契約。`FakeMemoryStore` / `InMemoryMemoryStore` / `SQLiteMemoryStore` が実装する永続化/編集可能なバックエンドの正本。

`MemoryRecord` は `kind` (MemoryKind EPISODE/PREFERENCE/FACT/RELATIONSHIP_EVENT/TASK/NOTE)、`confidence`、`source_observation_id`、`created_at`、`updated_at`、`archived`、`metadata` を持つ。
`RELATIONSHIP_EVENT` は関係状態値 (affinity/trust/familiarity) ではなく、関係に関わる出来事・記憶のサマリを表す。`RelationshipSnapshot` の永続化は `IrisApp` 側で別のストレージを使う想定。
`MemoryQuery` は `kind` と `include_archived` を追加で受ける。
SQLite 永続ストアは `state.sqlite_path` をアカウントストアと共有し、`wire_runtime_state` が backend が `sqlite` なら `SQLiteMemoryStore`、`memory` なら `InMemoryMemoryStore` を選択する。
SQLite 永続ストアは `put` / `update` / `archive` 時に timezone-aware UTC のタイムスタンプで `created_at` / `updated_at` を正規化し、`actor_id` / `space_id` / `kind` / `archived` の各フィルタ用インデックスを作成する。
`build_app_from_config` は `memory_store` を必須引数として受け付け、`FakeMemoryStore` への暗黙フォールバックは持たない。`FakeMemoryStore` はテスト専用の決定論的バックエンドであり、ランタイム配線 (`serve` -> `build_runtime_components`) は `wire_runtime_state` の `stores.memory_store` を `build_app_from_config` に明示注入する。

AppGateway の責務。

- 外部アプリから Observation を受け取る
- 外部アプリへ AppAction を返す
- ActionResult を受け取る
- correlation_id / turn_id / session_id を管理する
- external ref と Iris internal ref を対応づける

注意点として、複数層で共有される外部プロバイダ参照 (`ExternalAccountRef`, `ExternalSpaceRef`) は `contracts/` に置くが、AppGateway 固有の入力コマンド DTO (`ActorMessageIngress` 等) は `adapters/app_gateway/` に留める。

AppGateway がやってはいけないこと。

- cognitive 判断
- 記憶更新
- Proactive 判断
- presentation 判断
- Discord / Voice 固有ロジックの深い実装

Discord の具体 API 操作は `iris-discord-bot` 側。
Voice / TTS / STT の具体処理は `iris-voice-runtime` 側。

### `safety/`

システムとして危険な出力や外部操作を止める。

v0.1 では safety を2段階に分ける。

```text
ActionSafetyGate:
- 外部送信してよいか
- tool を使ってよいか
- proactive 発話してよいか
- 権限が必要な操作ではないか

OutputSafetyGate:
- 実際の文面が危険ではないか
- プラットフォームに出してよい表現か
- 個人情報や過激表現が含まれていないか
```

構成。

```text
safety/
├── action_gate.py
├── output_filter.py
└── policy_engine.py
```

`cognitive/policy/inhibition` との違い。

```text
cognitive inhibition:
- 今は話さない
- しつこくしない
- 会話のテンポを守る
- キャラとして抑制する

safety:
- 危険な出力を止める
- 権限のない操作を止める
- 外部送信前に検査する
- 監査ログを残す
```

---

## 主要な型の責務

### `Observation`

外部世界または内部スケジューラから Iris に入る入力。

例。

- `ActorMessageObservation`
- `IdleTickObservation`
- `ActivityEventObservation`
- `PresenceSignalObservation`

Discord / Voice / Twitch などの具体イベントは、外部アプリまたは AppGateway で Observation に変換する。

型付き ingress の意味:

- `ActorMessageObservation`: actorから届いたテキストmessage。
- `IdleTickObservation`: runtime内部のidle tick。
- `ActivityEventObservation`: typing、app open/close、voice join/leaveなどの非message外部activity。
- `PresenceSignalObservation`: online、away、idleなどprovider/clientが観測したactor presence signal。voice channel在室状態は表さない。

`ActorMessageObservation` はactor text messageの唯一のtyped ingress。`ActivityEventObservation` はtext messageを表さない。typing開始/終了、voice join/leaveなどactor-scoped activityは解決済みのactorまたはaccount subjectを必須とする。`SYSTEM_INTERACTION` などsystem-level activityはsubjectなしを許可する。

`PresenceSignalObservation` はactor/account-scoped claimであり、解決済みのactorまたはaccount subjectを必須とする。

Observation固有の `metadata` はprovider固有の補助情報だけに使う。`activity_kind`、`presence_status`、`provider_event_id`、`provider_sequence`、`expires_at` などの中核意味はtyped fieldまたはenumで表し、metadataから推論しない。

`ActivityEventObservation` と `PresenceSignalObservation` は外部adapter/clientからの報告・claimであり、Iris内部stateを更新するcommandではない。runtime boundaryが `ObservationEnvelope.ingress` に `ObservationIngressContext` を付与し、`ObservationTrustPolicy` は認証済みingress capabilityだけを検査する。`ObservationContext.source` や user-controlled metadata をtrust判定に使ってはならない。

runtime state integrationの責務:

```text
ObservationTrustPolicy:
  authenticated ingress capabilityを検査する

ActivityIntegrator:
  trusted ActivityEventObservationをActivityEventRecordへ変換する
  accepted eventだけをActivityJournalへappendし、latest projectionを更新する

PresenceIntegrator:
  trusted PresenceSignalObservationをPresenceSnapshotへ変換する

SpaceOccupancyIntegrator:
  trusted VOICE_JOINED / VOICE_LEFTをlive-space occupancyへ反映する

EventReactionRunner:
  trusted ActivityEventObservationに対し、availabilityとactivity kindに基づく決定論的なreactionを生成する
  反応可能な場合のみ `PresentedOutput` を返し、text response pipelineには流さない
```

runtime stateのsource-of-truth:

- `ActivityJournal`: bounded runtime activity event journal。永続conversation historyではない。
- `ActivityProjectionStore`: actor/spaceごとのlatest activity projection。
- `PresenceStore`: actorごとの最新受理済みpresence snapshot。
- `SpaceOccupancyStore`: live spaceの現在occupants。
- `InteractionSpace`: 安定したlocation identity/contextのみ。occupantsを保持しない。

`ActivityEventRecord` は受理済みruntime eventであり、長期記憶ではない。`state.backend = "memory"` の `InMemoryActivityJournal` は bounded で、provider-event dedupe も同じ window 内の保証に限る。`state.backend = "sqlite"` では `SQLiteActivityJournal` が append-only audit log を永続化する。memory extraction は raw `ActivityEventRecord` ではなく、明示的な `MemoryCandidate` event から行う。

現在の runtime state は、current-state projection と durable state を分ける。`state.backend = "sqlite"` では account、memory、relationship、affect、activity journal、delivery outbox、scheduler target store、safety audit journal、runtime learning background jobs、memory candidate review store を SQLite backend に永続化する。Transcript は `conversation.transcript.enabled = true` の場合だけ SQLite backend に永続化する。activity projection、presence、space occupancy、ephemeral space binding、learning dispatch、short-term conversation history は process-local のまま。`AvailabilityResolver` と `WorkspaceContextAssembler` は `SituationContextSnapshot` を組み立て、`EventReactionPolicy` / `EventReactionPlanner` / `EventReactionRunner` は trusted `ActivityEventObservation` に対して決定論的な event reaction を返す。

基底 `Observation` は以下を運ぶ。

```text
- observation_id
- session_id
- context: ObservationContext
- occurred_at
- kind: ObservationKind
```

`Observation` は `actor` / `space_id` を直接持たない。
Actor / Account / Device / Space 情報は必ず `ObservationContext` に集約する。

```text
Observation
  observation_id: ObservationId
  session_id: SessionId
  context: ObservationContext
  occurred_at: datetime
  kind: ObservationKind

ObservationContext
  actor: Identity | None
  account_id: AccountId | None
  device_id: DeviceId | None
  space_id: SpaceId | None
  source: str | None
```

`actor`、`account_id`、`device_id`、`space_id` は optional。
ソースが人、account、device、space を特定できない場合は `ObservationContext` 内で `None` を使う。
旧形の `Observation.actor` / `Observation.space_id` は存在しない。
`actor.user_id` のようなユーザー中心のフィールドは存在せず、すべて `Identity.actor_id` を介してアクセスする。

### `Identity` と `InteractionSpace`

`Identity` はアクター中心の不変データ型で、認証・権限は含まない。

```text
actor_id: ActorId
actor_kind: ActorKind        # human / device / service / system / iris
display_name: str
provider: str
provider_subject: ExternalRef
account_id: AccountId | None
device_id: DeviceId | None
metadata: Mapping[str, str]
```

`InteractionSpace` は観測が起きた安定したロケーション識別情報とコンテキストで、`space_id` / `space_kind` (`direct_message` / `text_channel` / `thread` / `voice_channel` / `room` / `broadcast`) / `display_name` / `metadata` を持つ。

`InteractionSpace` は現在の在室者を保持せず、可変なルーム状態の正本にはならない。現在の在室者は `SpaceOccupancyStore` が単独で管理する。`WorkspaceFrame` が将来1ターン用の参加者snapshotを持つ場合も、`InteractionSpace` 自体をoccupancyの正本にはしない。

`SpaceOccupant` は actor-level の現在在室メンバーシップのみを表す。account_id / device_id は `IdentityResolver` / `AccountStore` / `Identity` 層が所有する。`ActivityEventRecord` や `PresenceSnapshot` は provenance として account_id / device_id を保持してよいが、`SpaceOccupant` では identity-link を重複して持たない。

`AccountProfile` は外部account identityを表す契約。
`account_id`、`provider`、`provider_subject`、`display_name`、任意の `linked_actor_id` を持つ。
AccountId はActorIdへリンクするcontext identifierであり、関係性やmemoryのownerではない。

`DeviceProfile` は観測元deviceを表す契約。
`device_id`、`device_kind`、`display_name`、任意の `owner_actor_id`、`DeviceCapability` を持つ。
DeviceId もcontext identifierであり、関係性やmemoryのownerではない。

PR 2以降のfuture work:
IdentityResolver / SpaceResolver、永続identity registry、account merging、memory/relationship scoping、DB永続化、認証/認可。
PR 1 foundationではresolver、store、adapter、managerをcontractsやWorkspaceFrameへ入れない。

### `WorkspaceFrame`

1ターン中の typed snapshot。
PipelineStep の結果を `FrameBuilder` が統合して作る。

Context snapshot:

```text
ActorContextSnapshot
  actor: Identity | None
  account_id: AccountId | None
  device_id: DeviceId | None

SpaceContextSnapshot
  space_id: SpaceId | None
  space: InteractionSpace | None
  participant_actor_ids: tuple[ActorId, ...]

SituationContextSnapshot
  latest_activity: ActivityEventRecord | None
  presence: PresenceSnapshot | None
  space_occupancy: SpaceOccupancySnapshot | None
  availability: AvailabilitySnapshot | None
```

`FrameBuilder.build_initial()` は `Observation.context` から `actor_context` と `space_context` を作り、オプションで `SituationContextSnapshot` を受け取る。
`WorkspaceFrame.situation_context` は `iris.runtime.state.context_assembler.WorkspaceContextAssembler` が `ActivityProjectionStore` / `PresenceStore` / `SpaceOccupancyStore` から組み立てて `IrisRuntimeService` 経由で渡される。
`AvailabilitySnapshot` は `AvailabilityResolver` が `PresenceSnapshot` と `ActivityEventRecord` から決定論的に導出する。
`WorkspaceFrame` は frozen typed snapshot のまま。resolver、store、adapter、manager、mutable context bag は入れない。

### Identity / Space resolution

`IdentityResolver` と `SpaceResolver` は `adapters/app_gateway/ports.py` に置く。
外部provider ref (`ExternalRef`) を `Identity` / `InteractionSpace` に変換するAppGateway境界portであり、`contracts/` と `cognitive/` はresolver protocolを知らない。

fake resolverはテストとローカルMVP配線向けに決定論的 `ActorId` / `SpaceId` を返す。
DB永続化、認証、認可、global registry、外部provider API callはしない。

### Relationship / memory scope

関係性は `ActorId` scope。
`RelationshipStep` は `frame.actor_context.actor.actor_id` をkeyとして使う。
`AccountId` と `DeviceId` はlink/context identifierであり、relationship owner keyではない。

Memory retrievalは `ActorId | None` と `SpaceId | None` scopeを受け取る。
`MemoryQuery.actor_id` は「誰に関するmemoryか」、`MemoryQuery.space_id` は「どのinteraction spaceで起きたmemoryか」を表す。
`AccountId` と `DeviceId` はmemory owner keyではない。

永続identity registry、account merging、DB永続化、認証/認可、長期memory consolidation jobはfuture work。

### `ActionPlan`

Iris が「何をしたいか」を表す。
まだ外部アプリ固有ではない。

LLM-backed response generation は `cognitive/action/response.py` の PipelineStep として扱う。
この step は `WorkspaceFrame` から typed response prompt を作り、注入された response generator から得た text を `ActionPlan.candidate_text` に入れる。
`WorkspaceFrame` は直接変更せず、`ActionSelectionResult` を返して `FrameBuilder` に統合させる。
LLM provider 形状への変換は `runtime/wiring/llm.py` が担当する。

例。

```text
ユーザーに返答したい
会話を続けたい
今は発話しない
tool を使いたい
```

#### no-action セマンティクス

no-action の正規の表現は以下に固定する。

```python
ActionPlan(turn_intent="no_action", candidate_text=None, should_respond=False)
```

`ActionPlan.is_no_action` プロパティがこの条件を判定する（`turn_intent == "no_action" and not should_respond`）。

no-action のルール。

- no-action は LLM を呼び出してはならない。
- no-action はユーザーに見えるテキスト出力を生成してはならない。
- no-action は外部送信を行ってはならない。
- no-action は proactive 発話として振る舞ってはならない。
- no-action は provider-neutral であり、Discord/TTS/STT 固有フィールドを含まない。
- runtime (`IrisApp.process_observation()`) は no-action 計画を検出し、action safety gate、presenter、output safety gate をスキップし、即座に `PresentedOutput(text=None)`（`is_sendable=False`）を返す。
- 実用的なスケジューリング、バックグラウンド自律ループ、Discord 送信は後続 phase に委譲し、no-action 本体には含めない。

### `PresentedOutput`

ActionPlan を「どう見せるか」に変換したもの。

例。

```text
text
style
emotion_hint
expression_hint
timing
priority
interruptible
```

### `AppAction`

外部アプリが実行できる具体命令。

例。

```text
SendMessageAction
SpeakAction
StopSpeechAction
SetAvatarExpressionAction
ToolCallAction
```

### `ActionResult`

外部アプリが実際に Action を実行した結果。

最低限必要な情報。

```text
- action_id
- correlation_id
- status: succeeded / failed / cancelled / blocked
- delivered_at
- error_reason
- external_message_id
```

Learning は ActionResult を受けてから行う。

---

## 依存方向

基本依存方向。

```text
contracts → core

cognitive → contracts, core

presentation → contracts, core

features → contracts, cognitive extension protocols, core

adapters → contracts, core

safety → contracts, core

runtime → cognitive, features, adapters, presentation, safety, contracts, core
```

禁止。

```text
cognitive → adapters
cognitive → runtime
cognitive → features
contracts → cognitive
contracts → adapters
features → adapters 原則禁止
adapters → cognitive 原則禁止
```

`runtime` だけが全体を知ってよい。
それ以外の層は依存方向を守る。

---

## Runtime Flow

```text
CLI / main.py / iris.runtime.server
→ Observation
→ CognitiveCycle (cognitive/cycle/)
   → SimplePerceptionStep (cognitive/perception/)
   → [MemoryRetrievalStep (cognitive/memory/)]   (optional)
   → [AppraisalStep (cognitive/affect/)]          (optional)
   → [RelationshipStep (cognitive/affect/)]        (optional)
   → [PolicyInhibitionStep (cognitive/policy/)]    (optional)
   → ResponseGenerationStep (cognitive/action/)
→ ActionPlan (contracts/)
→ ActionSafetyGate (safety/)
→ Presenter (presentation/)
→ PresentedOutput (contracts/)
→ OutputSafetyGate (safety/)
→ PresentedOutput
```

`IrisApp` (`iris/runtime/app.py`) が `process_observation()` で上記フローを実行します。

4種類の配線関数が `runtime/wiring/cognitive.py` に用意されています:

1. `wire_text_response_cognitive_cycle` — Perception + ResponseGeneration
2. `wire_memory_aware_text_response_cognitive_cycle` — Perception + MemoryRetrieval + ResponseGeneration
3. `wire_affect_memory_aware_text_response_cognitive_cycle` — Perception + (memory) + Appraisal + Relationship + ResponseGeneration
4. `wire_policy_affect_memory_aware_text_response_cognitive_cycle` — Perception + (memory) + Appraisal + Relationship + PolicyInhibition + ResponseGeneration

---

## 現状のスコープ

- text-only 1 ターン会話
- FakeLLM デフォルト (OpenAI / Ollama 切替可)
- 認識・メモリ検索・感情評価・関係性・ポリシー抑制 PipelineStep 実装済み (配線選択可能)
- proactive_talk feature 実装済み (salience scoring, goal proposal, policy)
- authenticated ingress capability による typed activity/presence claim の runtime integration 実装済み
- trusted voice join/leave からの in-memory space occupancy integration 実装済み
- `AvailabilityResolver` / `WorkspaceContextAssembler` による `SituationContextSnapshot` の組み立て実装済み
- 永続ストレージ: SQLite backend は account、memory、relationship、affect、activity journal、delivery outbox、scheduler target store、safety audit journal、background jobs、memory candidate reviews を永続化する。activity projection、presence、space occupancy、対話スペース解決、learning dispatch、short-term conversation history はエフェメラル。
- Transcript persistence は `conversation.transcript.enabled` で明示的に有効化し、`state.backend = "sqlite"` を使う場合だけ SQLite に保存する。short-term conversation history と long-term memory とは分離する。
- Scheduler lifecycle は config で有効化できる。`SchedulerRunner` は `IdleTickObservation` を発行し、`DeliverySafetyGate` と `DeliveryOutbox` を通した pull-based delivery だけを使う。
- Delivery は SQLite backend で durable outbox にできる。`DeliveryEnvelope`、lease、idempotent `ReportActionResult`、`DeliveryStatus` state machine は durable backend で永続化できる契約として実装済み。
- Runtime observability は `RuntimeTraceContext`、safe lifecycle logs、LLM request observer、startup diagnostics、read-only runtime doctor を実装済み。
- `MotivationResult` 型と `FrameBuilder` 対応は既存、step 実装は未着手
- LearningHook / RuntimeLearningHook / BackgroundJobQueue は実装済み。implicit candidate は review store に入り、approved candidate だけが MemoryStore へ promotion される。promotion 済み metadata と canonical MemoryStore の不整合は `promoted_memory_missing` として通常の冪等 hit と区別する。SQLite learning-state persistence、opt-in transcript persistence、deterministic long-conversation summary は実装済み
- 外部アプリ連携 (Discord, Voice, Twitch) は未実装
- AppGateway は Protocol とサーバーサイドの Identity Resolver / Space Resolver を定義済み (外部アプリのidentity永続化用)

---

## 関連ドキュメント

- cognitive.md: 認知サイクル、workspace、learning、proactive の詳細設計
- rules.md: AI コーディングルール、Do/Don't Examples
- legacy.md: 削除済みアーキテクチャ情報
- tests.md: アーキテクチャテスト受入基準

## Proactive Scheduler / Delivery Foundation

Proactive scheduler は default disabled である。Scheduler は `IdleTickObservation` などの typed internal `Observation` だけを発行し、LLM client、presenter、Discord/CLI/voice 送信 client を直接呼ばない。

配送 path は次に固定する。

```text
RuntimeScheduler
→ typed internal Observation
→ IrisRuntimeService
→ normal CognitiveCycle
→ ActionSafetyGate
→ Presenter
→ OutputSafetyGate
→ DeliverySafetyGate
→ DeliveryOutbox
→ external client polling
→ ActionResult
→ learning/audit hooks
```

`DeliveryOutbox` は sender ではない。外部 client が `PollAppActions` で lease し、platform send 後に `ReportActionResult` を返す。`PollAppActions` は `LEASED` 状態の item のみ返す。`ReportActionResult` は `SUCCEEDED` / `CANCELLED` / `BLOCKED` を terminal completion、`FAILED` のみ retry として扱う。同一報告の再送は全 status で idempotent とし、`delivery_id`、`lease_id`、`action_id`、`correlation_id`、`status`、`external_message_id`、`error_reason` の同一性で判定する。競合報告は `DeliveryOutboxError` を送出する。`state.backend = "memory"` では process-local outbox、`state.backend = "sqlite"` では `SQLiteDeliveryOutbox` が `DeliveryEnvelope`、lease、idempotency key、`DeliveryStatus` state machine を永続化する。

`SchedulerRunner` は `DeliveryAvailabilityProvider` protocol を通じて `AvailabilitySnapshot` を取得し、`DeliverySafetyGate` へ渡す。BUSY / UNAVAILABLE は delivery enqueue を block する。`DeliverySafetyGate` は送信rate limitそのものは持たない。プロアクティブ送信頻度は `IdleTickSource` が `min_interval_per_target_seconds` で制御し、strict policy の同一target直近block判定は `SafetyAuditJournal.recent_block_count()` を使う。`state.backend = "sqlite"` では safety audit と scheduler targets も restart 越しに保持される。

`NoAction`、sendable ではない `PresentedOutput`、`DeliverySafetyGate` が block した output は delivery outbox に入れない。
- external.md: 外部アプリとの責務分離
## Identity and Space Scoping

Use `actor_id` as the primary owner for memory and relationship semantics.
Use `space_id` as contextual scope, not as the primary owner of user memory.
Do not use `display_name` as a stable identifier.
Do not store conversation history directly on `SpaceBinding`.
## Space Context Rule

Memory、relationship、persona semantics の主スコープは `actor_id`。`space_id` は外部interaction contextとしてのみ使う。

Default runtime は `SpaceBinding` を永続化しない。Space に conversation history や persona state を紐づけない。

Retry 可能な `FAILED` は `PENDING` へ戻して `not_before` に retry 時刻、`last_error_reason` に失敗理由を保持する。最大試行後のみ `FAILED_PERMANENT` へ遷移する。
## Durable Memory / Relationship / Affect Scope

Memory は検索可能な長期 content を扱う。対象は facts、preferences、notes、tasks、relationship events である。`MemoryKind.RELATIONSHIP_EVENT` は relationship に関する出来事の summary であり、現在の relationship state ではない。

Relationship は `ActorId` を主キーにした current per-actor state として `RelationshipSnapshotRecord` に保存する。Affect は Iris の baseline/current affect state として `AffectBaselineRecord` に保存する。Global affect baseline は `scope="global"` と `actor_id=None` を使う。

SQLite backend は memory、relationship、affect、account、activity journal を durable にする。Activity projection、presence、space occupancy は ephemeral のままにする。`space_id` は durable relationship / affect の owner ではなく、memory でも補助的な interaction context として扱う。

- `contracts/appraisal.py` — Appraisal semantics split の typed signal contract。詳細は ADR 0018。
