# Cognitive Cycle と拡張設計

## 認知サイクル

Iris の中核は `cognitive/` にあり、認知サイクル、記憶、感情、動機、行動選択、学習を担当する。

中心は `CognitiveCycle`。

```python
class CognitiveCycle:
    async def run(self, observation: Observation) -> CycleResult:
        ...
```

ただし、`CognitiveCycle` は God Service にしない。
処理本体ではなく pipeline coordinator として実装する。

基本フロー。

```text
Observation
→ PerceptionStep
→ MemoryRetrievalStep
→ AppraisalStep
→ MotivationStep
→ PlanningStep
→ ActionSelectionStep
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

`WorkspaceFrame` は、会話ターン内で各認知モジュールが共有する typed snapshot である。

入れてよいもの。

- observation
- interpreted input
- identity context
- conversation context
- retrieved memory summary
- affect state
- relationship snapshot
- motivation state
- goals
- constraints
- candidate actions

入れてはいけないもの。

- storeそのもの
- adapterそのもの
- manager参照
- 過去ログ全体
- 巨大な `dict[str, Any]`
- LLM prompt 文字列だけの巨大 context

`WorkspaceFrame` は「何でも入る箱」にしない。

---

## Learning と BackgroundJob

Learning は ActionResult 後に行う。

```text
ActionPlan
→ Presentation
→ SafetyGate
→ Adapter
→ ActionResult
→ LearningHook
```

理由。

- 送信成功したか
- 失敗したか
- safety で blocked されたか
- user interrupt により cancelled されたか

を見てから記憶や関係性を更新する必要がある。

### LearningHook

hot path で実行する軽量処理。

- 会話ログの追加
- working memory 更新
- relationship の軽い更新
- background job の enqueue

### BackgroundJob

hot path から外す重い処理。

- 長期記憶抽出
- LangMem extraction
- persona patch proposal
- episodic → semantic promotion
- 重い reflection

---

## Proactive の設計

Proactive は特殊な別システムではなく、内部 Observation から始まる CognitiveCycle として扱う。

```text
Scheduler
→ IdleTickObservation
→ CognitiveCycle
→ WorkspaceFrame
→ SalienceScorer
→ GoalProposer
→ PolicyConstraint
→ ActionProvider
→ SpeakAction or NoAction
```

`features/proactive_talk/` が直接 memory や policy の内部実装を改造してはいけない。

---


## 関連ドキュメント

- architecture.md: 全体構造、各層の責務、依存方向
- rules.md: 認知サイクルに関する Do/Don't
