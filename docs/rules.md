# 実装ルール

## AI コーディング向けルール

AIコーディングエージェントには、以下のルールを必ず守らせる。

1. 主処理は CognitiveCycle が明示的に制御する。
2. CognitiveCycle は God Service ではなく pipeline coordinator とする。
3. 各 PipelineStep は WorkspaceFrame を直接 mutate しない。
4. 各 PipelineStep は typed result を返す。
5. FrameBuilder が StepResult を WorkspaceFrame に統合する。
6. 外部入力はすべて Observation に変換する。
7. 外部出力は ActionPlan → ActionSafetyGate → Presentation → OutputSafetyGate → AppAction の順に通す。
8. Learning は ActionResult を受けてから行う。
9. cognitive/ は adapters/ と runtime/ を import しない。
10. cognitive/ は features/ を import しない。
11. features/ は FeatureDefinition による extension provider として登録する。
12. features/ は cognitive 内部を直接改造しない。
13. Service Locator / resolve_optional / グローバル registry 呼び出しを禁止する。
14. 新機能は features/<name>/ に縦切りで追加する。
15. 互換 shim・一時 wrapper・旧API維持は原則作らない。
16. dispatcher の action: str 分岐を増やさない。
17. dict[str, Any] や dict[str, object] を内部境界に使わない。
18. runtime/wiring は constructor injection のみにする。
19. 依存方向は architecture test で強制する。

---

## v0.1 で追加する実装固定ルール

v0.1 は、v1.2 の方針を変えるものではない。
目的は、AIコーディングエージェントが実装時に迷いやすい抽象部分を、最低限の型・境界・禁止例まで落とし込むことである。

v0.1 で追加する固定ルール。

1. `CognitiveCycle.run()` は pipeline coordinator に限定する。
2. `CognitiveCycle.run()` に LLM prompt 構築、記憶更新、関係性更新、adapter 呼び出し、safety 判定を書かない。
3. `PipelineStep` は `WorkspaceFrame` を受け取り、typed `PipelineStepResult` を返す。
4. `PipelineStep` は `WorkspaceFrame` を mutate しない。
5. `FrameBuilder` だけが step result を統合して次の `WorkspaceFrame` を作る。
6. MVP の `FeatureDefinition` は最小フィールドから開始し、未使用 extension point の空実装を量産しない。
7. `dict[str, Any]`、`dict[str, object]`、`action: str` dispatcher、service locator は内部境界では使わない。
8. 旧構造の互換 wrapper を作るより、既存コードを責務単位で移植する。

---

## Implementation Do / Don't Examples

### CognitiveCycle

良い例。

```python
for step in self._steps:
    result = await step.run(frame)
    frame = self._frame_builder.apply(frame, result)
```

悪い例。

```python
memory = await self.memory.search(actor_text)
mood = self.relationship.update(memory)
reply = await self.llm.chat(memory, mood, actor_text)
await self.discord.send(reply)
```

理由。
`CognitiveCycle` が複数責務を持ち、adapter と認知処理が混ざるため。

### WorkspaceFrame

良い例。

```python
return replace(frame, memory_summary=MemorySummary(retrieved_memories=memories))
```

悪い例。

```python
frame.state["facts"] = facts
frame.managers["memory"] = memory_manager
```

理由。
便利箱化し、依存方向とテスト容易性が壊れるため。

### Feature

良い例。

```python
def define_feature() -> FeatureDefinition:
    return FeatureDefinition(
        name="chat",
        pipeline_steps=(ChatActionSelectionStep(llm_port),),
        learning_hooks=(ConversationLogHook(store),),
    )
```

悪い例。

```python
from iris.cognitive.cycle.service import global_cycle

global_cycle.register_hook(...)
```

理由。
隠れた global registry になり、AI が後続実装でツギハギにしやすくなるため。

### Adapter

良い例。

```python
observation = ActorMessageObservation(
    observation_id=ObservationId("obs-1"),
    session_id=SessionId("session-1"),
    actor=Identity(
        actor_id=ActorId("actor-1"),
        actor_kind=ActorKind.HUMAN,
        display_name="Mina",
        provider="discord",
        provider_subject=ExternalRef("12345"),
    ),
    space_id=SpaceId("space-1"),
    occurred_at=datetime.now(UTC),
    kind=ObservationKind.ACTOR_MESSAGE,
    text=message.content,
)
return observation
```

悪い例。

```python
if message.content.startswith("!"):
    return await command_manager.execute(message)
```

理由。
外部アプリ側が cognitive 判断を持ち始めるため。

`actor` / `account_id` / `device_id` / `space_id` が決まらないケースは `ObservationContext` 内で `None` を渡す。
`Observation.actor` / `Observation.space_id` や `actor.user_id` のようなユーザー中心フィールドは存在しない。

---

## エージェントガイドライン

### Wiring rules

- Use explicit constructor injection in wiring files
- Wiring files must not call `resolve()`, `get_service()`, or `locate()`
- Wiring files must not define domain classes (CognitiveCycle, PipelineStep, etc.)

### Adding features

- Add features as target-native implementations in `iris/features/`
- Use `FeatureDefinition` protocol from `iris/features/definition.py`
- Features must not mutate `WorkspaceFrame` directly
- Features must not import from `iris/adapters`, `iris/runtime`, `iris/presentation`, `iris/safety`
- 実装例: `iris/features/proactive_talk/` (salience scoring, goal proposal, policy, definition)

### Testing rules

- Architecture guards in `tests/architecture/` must remain passing

---

## 関連ドキュメント

- architecture.md: 依存方向、禁止パターン
- legacy.md: 削除済みアーキテクチャ情報
