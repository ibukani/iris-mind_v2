# Legacy (削除済みアーキテクチャ)

このドキュメントは削除済みの旧アーキテクチャ情報を記録する。
現在のコードベースには適用されない。

---

## 削除済みパッケージ

| パッケージ | 説明 |
|---------|-------------|
| `iris/event` | EventBus、イベント型、イベントルーティング |
| `iris/kernel` | KernelProcess、PluginManager、supervisor |
| `iris/io` | I/O 抽象化レイヤ |
| `iris/account` | Account / Session 管理 |
| `iris/room` | Room / Channel 管理 |
| `iris/agency` | Agency / Orchestrator システム |
| `iris/memory` | memory パイプライン全体 (sensory, short-term, episodic, semantic)、LangMem |
| `iris/limbic` | Limbic システム (appraisal, classification, mood, relationship) |
| `iris/llm` | LLM プロバイダ、bridge、prompt システム |
| `iris/tools` | ツール登録と実行 |
| `iris/heartbeat` | Heartbeat / scheduler |
| `iris/admin` | Admin / 管理インタフェース |

### 削除した依存関係

grpcio, protobuf, googleapis-common-protos, langgraph, transformers, torch, chromadb, ollama, pydantic-compat.
langchain-core は core 依存としては削除されたが、`iris/adapters/memory/langchain.py` で optional adapter として利用可能。

### 削除したインフラ

- `proto/` — Protocol Buffers and gRPC service definitions
- `debug_tools/` — gRPC-based debug CLI
- Legacy skill files for Plugin/EventBus workflows

---

## 廃止した設計パターン

- PluginManager 中心の設計
- PluginProtocol / MANIFEST / plugin export 前提
- EventBus による主制御
- `iris/event/event_types.py` の互換 shim
- `iris/io/events.py` を共有イベント置き場にする構造
- `builder.py` に横断組み立てが集まる構造
- dispatcher の `action: str` 分岐
- memory / limbic / agency が暗黙に EventBus で連携する構造
- `contracts/events.py` による EventBus 的逃げ道
- 隠れた manager 連携

---

## 移行対応表 (旧→新)

| 旧構成 | 移行先 |
|---|---|
| `kernel/` | `runtime/` |
| `event/` | 廃止 |
| `io/` | `adapters/app_gateway/` |
| `account/` | `contracts/identity.py` |
| `room/` | `contracts/conversation.py` |
| `memory/` | `cognitive/memory/` + `features/memory_consolidation/` + `adapters/stores/` |
| `limbic/` | `cognitive/affect/` |
| `agency/` | `cognitive/policy/` + `cognitive/action/` |
| `llm/` | `adapters/llm/` + `cognitive/action/response.py` |
| `tools/` | `adapters/tools/` + `cognitive/action/tool_use.py` |
| `heartbeat/` | `runtime/scheduler.py` |
| `admin/` | `admin/` |

---

## 実装状態 (Phase 0-9 対応)

Phase 0: v0.1 設計固定 — 完了
Phase 1: architecture test 先行 — 完了 (18+ tests)
Phase 2: v2 scaffold — 完了
Phase 3: 最小会話ループ — 完了
Phase 4: LLM 移植 (FakeLLM / OpenAI / Ollama adapter) — 完了
Phase 5: memory 移植 (retrieval step + Fake/Vector/LangChain stores) — 完了
Phase 6: affect / relationship 移植 (appraisal, mood, relationship step) — 完了
Phase 7: policy / inhibition 移植 — 完了
Phase 8: proactive 実装 (features/proactive_talk/) — 完了
Phase 9: 旧構造削除 — 完了

未実装の拡張:
- MotivationStep (型/FrameBuilder は対応済み)
- LearningHook / BackgroundJob
- runtime scheduler, lifecycle, telemetry
- features/chat/, memory_consolidation/, relationship_update/, persona_patch/, command_control/
- adapters/tools/, embeddings/, external_clients/
- safety/policy_engine

---

## 旧テストファイル名 (アーカイブ)

以下のテストファイル名は現在のコードベースには存在しない。
現在の architecture test は `tests/architecture/` の4ファイルに統合されている。

```
tests/architecture/test_dependency_direction.py
tests/architecture/test_no_adapter_import_from_cognitive.py
tests/architecture/test_no_runtime_import_from_cognitive.py
tests/architecture/test_no_feature_import_from_cognitive.py
tests/architecture/test_no_service_locator.py
tests/architecture/test_no_eventbus_main_flow.py
tests/architecture/test_feature_extension_boundaries.py
tests/architecture/test_no_any_context.py
tests/architecture/test_workspace_frame_is_frozen.py
tests/architecture/test_pipeline_steps_return_typed_results.py
tests/architecture/test_frame_builder_owns_frame_updates.py
tests/architecture/test_cognitive_cycle_is_coordinator_only.py
```
