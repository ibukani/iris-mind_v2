# MVP 実装計画

---

## Go / No-Go 条件

### Go 条件

以下を守るなら実装に入ってよい。

- v0.1 設計を固定する
- architecture test を先に置く
- 最初のMVPを text-only / FakeLLM までに絞る
- 旧構造を温存しようとしない
- 互換 shim を作らない
- 既存コードは部品として移植する

### No-Go 条件

以下の方針なら止める。

- 旧構造と v0.1 を長期共存させる
- 既存テストを全部通すために互換層を作る
- 最初から memory / affect / proactive まで全部入れる
- CognitiveCycle に全部の処理を書く
- features から cognitive 内部を直接改造する

---

## MVP Scope Lock

v0.1 の最初の実装では、完成版 Iris を作らない。
AIコーディングエージェントには、以下のスコープを固定して渡す。

### MVP で作るもの

```text
core/ids.py
contracts/identity.py
contracts/observations.py
contracts/actions.py
cognitive/workspace/frame.py
cognitive/cycle/models.py
cognitive/cycle/pipeline.py
cognitive/cycle/frame_builder.py
cognitive/cycle/service.py
presentation/presenter.py
safety/action_gate.py
safety/output_filter.py
adapters/app_gateway/ports.py
features/definition.py
runtime/wiring/cognitive.py
runtime/wiring/presentation.py
```

最初に通す流れ。

```text
UserMessageObservation
→ CognitiveCycle
→ PerceptionStep
→ ActionSelectionStep
→ ActionPlan
→ ActionSafetyGate
→ SimplePresenter
→ OutputSafetyGate
→ SendMessageAction
→ ActionResult
```

### MVP で作らないもの

```text
LangMem integration
long-term memory promotion
persona patch generation
relationship update details
mood simulation details
proactive talk details
Discord runtime
Voice runtime
TTS/STT integration
Twitch integration
Avatar control
PerformanceDirector
EventBus
PluginManager compatibility layer
API 互換 shim
```

MVP 時点でこれらが必要に見えても、空実装や wrapper を先に置かない。
必要になった phase で feature として追加する。

### MVP 完了条件

MVP は以下を満たしたら完了とする。

1. text-only の1ターン会話が通る。
2. `CognitiveCycle` が adapter、runtime、features を import していない。
3. `WorkspaceFrame` が frozen dataclass である。
4. `PipelineStep` が typed result を返す。
5. `FrameBuilder` だけが frame を更新する。
6. `ActionPlan → Safety → Presentation → Safety → AppAction` の順序が固定されている。
7. architecture test が通る。

---

## 関連ドキュメント

- architecture.md: 全体構造
- rules.md: 実装時の Do/Don't
- tests.md: architecture test の受入基準
