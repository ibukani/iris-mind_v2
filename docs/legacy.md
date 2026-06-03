# Legacy (削除済みアーキテクチャ)

このドキュメントは削除済みの旧アーキテクチャ情報を記録する。
現在のコードベースには適用されない。

---

## 削除済みパッケージ

| Package | Description |
|---------|-------------|
| `iris/event` | EventBus, event types, event routing |
| `iris/kernel` | KernelProcess, PluginManager, supervisor |
| `iris/io` | I/O abstraction layer |
| `iris/account` | Account/Session management |
| `iris/room` | Room/Channel management |
| `iris/agency` | Agency/Orchestrator system |
| `iris/memory` | Full memory pipeline (sensory, short-term, episodic, semantic), LangMem |
| `iris/limbic` | Limbic system (appraisal, classification, mood, relationship) |
| `iris/llm` | LLM providers, bridge, prompt system |
| `iris/tools` | Tool registration and execution |
| `iris/heartbeat` | Heartbeat/scheduler |
| `iris/admin` | Admin/management interfaces |

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

| 既存 | 移行先 |
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

## MVP実装履歴 (完了済みフェーズ)

Phase 0: v0.1 設計固定
Phase 1: architecture test 先行
Phase 2: v2 scaffold
Phase 3: 最小会話ループ
Phase 4: LLM 移植
Phase 5: memory 移植
Phase 6: affect / relationship 移植
Phase 7: policy / inhibition 移植
Phase 8: proactive 実装
Phase 9: 旧構造削除

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
