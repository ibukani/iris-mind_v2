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
│   └── policy.py
│
├── runtime/
│   ├── app.py
│   ├── config.py
│   ├── server.py
│   └── wiring/
│       ├── app.py
│       ├── cognitive.py
│       ├── features.py
│       ├── llm.py
│       ├── memory.py
│       └── presentation.py
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
│   └── presenter.py
│
├── features/
│   └── proactive_talk/
│       ├── definition.py
│       ├── goals.py
│       ├── models.py
│       ├── policy.py
│       └── scoring.py
│
├── adapters/
│   ├── app_gateway/
│   │   └── ports.py
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

将来の拡張予定（未実装）:
- `cognitive/motivation/` — MotivationStep の実装（`MotivationResult` 型と `FrameBuilder` 対応は既存）
- `cognitive/learning/` — LearningHook / BackgroundJob
- `runtime/scheduler.py`, `background_jobs.py`, `lifecycle.py`, `telemetry.py`
- `features/chat/`, `features/memory_consolidation/`, `features/relationship_update/`, `features/persona_patch/`, `features/command_control/`
- `adapters/tools/`, `adapters/embeddings/`, `adapters/external_clients/`
- `safety/policy_engine.py`

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

層間で共享する型を置く。

主な責務。

- `Observation`
- `Action` / `ActionPlan`
- `Identity` (actor-centered)
- `InteractionSpace` / `SpaceParticipant`
- `Memory` / `MemorySearchResult`
- `Policy` / `ActionPreference` / `PolicyConstraint`

`Identity` は人間・デバイス・サービス・システム・Iris 自身を区別する `ActorKind` を持つ。
`AccountId` / `DeviceId` は任意の関連リンクで、認証・権限はここで扱わない。

注意点。

- `contracts/ports.py` は原則作らない。
- Port は利用側モジュールの近くに置く。
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

アプリケーション起動、構成、スケジューリング、バックグラウンドジョブを担当する。

主な責務。

- アプリ起動
- 設定読み込み
- dependency wiring
- scheduler
- background job
- lifecycle
- telemetry

注意点。

- `runtime/composition.py` 1ファイルにすべて詰め込まない。
- `runtime/wiring/` に分割する。
- `runtime/wiring/` は constructor injection に限定する。
- `runtime/wiring/` に業務ロジックや認知ロジックを書かない。

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

`WorkspaceFrame` は「何でも入る箱」にしない。

### `presentation/`

`cognitive/` が決めた `ActionPlan` を、実際にどのような形で見せるかに変換する。

MVPでは軽量。`SimplePresenter` が `ActionPlan` を `PresentedOutput` に変換する。

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

現在実装済みの feature: `proactive_talk/`（salience scoring, goal proposal, proactive policy, expression抑制）。

`runtime/wiring/features.py` は `FeatureDefinition` を集めて登録するだけにする。

### `adapters/`

外部技術との接続を担当する。

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

AppGateway の責務。

- 外部アプリから Observation を受け取る
- 外部アプリへ AppAction を返す
- ActionResult を受け取る
- correlation_id / turn_id / session_id を管理する
- external ref と Iris internal ref を対応づける

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
- `TranscriptObservation`
- `IdleTickObservation`
- `AudienceMessageObservation`
- `GameEventObservation`

Discord / Voice / Twitch などの具体イベントは、外部アプリまたは AppGateway で Observation に変換する。

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

`InteractionSpace` は観測が起きた相互作用のコンテキストで、`space_id` / `space_kind` (direct_message / channel / thread / room / broadcast) / `display_name` / `participants` を持つ。`SpaceParticipant` は `actor_id` と `participant_kind` を運ぶ。

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
```

`FrameBuilder.build_initial()` は `Observation.context` から `actor_context` と `space_context` を作る。
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
- 永続ストレージは未実装 (InMemoryStore / FakeMemoryStore のみ)
- `MotivationResult` 型と `FrameBuilder` 対応は既存、step 実装は未着手
- LearningHook / BackgroundJob は未実装
- 外部アプリ連携 (Discord, Voice, Twitch) は未実装
- AppGateway は Protocol と決定論的fake resolverのみ定義 (将来の外部アプリ用)

---

## 関連ドキュメント

- cognitive.md: 認知サイクル、workspace、learning、proactive の詳細設計
- rules.md: AI コーディングルール、Do/Don't Examples
- legacy.md: 削除済みアーキテクチャ情報
- tests.md: アーキテクチャテスト受入基準
- external.md: 外部アプリとの責務分離
