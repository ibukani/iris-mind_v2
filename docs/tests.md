# テストとコード品質

---

## テスト実行方法

```bash
# All tests
uv run pytest tests/

# Quick run (short traceback)
uv run pytest tests/ -q

# Architecture guards only
uv run pytest tests/architecture -q

# Specific test file
uv run pytest tests/runtime/test_cli.py -q
```

---

## コード品質

```bash
# Lint check
uv run ruff check .

# Lint auto-fix
uv run ruff check --fix .

# Format check
uv run ruff format --check .

# Format
uv run ruff format .

# Type check
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
```

---

## Target-only test suite

All tests verify the current target architecture only.

### Architecture guards (`tests/architecture/`)

| File | Purpose |
|------|---------|
| `test_target_architecture_guards.py` | Forbidden symbols, layer dependency direction, runtime entrypoint rules, `__init__.py` rules, no service locator |
| `test_cognitive_runtime_boundaries.py` | Layer boundary rules |
| `test_cognitive_runtime_anti_patterns.py` | Anti-pattern scans (global mutable registries, untyped contracts, etc.) |
| `test_cognitive_runtime_contracts.py` | Design contract tests (frozen dataclasses, FrameBuilder, PipelineStep) |

These tests enforce that package boundaries remain clean.

---

## Architecture Test 受入基準

architecture test は「実装が動くか」ではなく、「設計境界が壊れていないか」を検査する。

---

## 合格条件

以下をすべて満たすこと。

1. `iris/cognitive/**` から `iris/adapters/**` を import していない。
2. `iris/cognitive/**` から `iris/runtime/**` を import していない。
3. `iris/cognitive/**` から `iris/features/**` を import していない。
4. `iris/contracts/**` から `iris/cognitive/**`、`iris/adapters/**`、`iris/runtime/**` を import していない。
5. `WorkspaceFrame` が frozen dataclass である。
6. `WorkspaceFrame` に `dict[str, Any]`、`dict[str, object]`、`MutableMapping` がない。
7. `PipelineStep.run()` が `PipelineStepResult` 派生型を返す。
8. `PipelineStep.run()` が `WorkspaceFrame` を mutate していない。
9. `FrameBuilder` が `replace(frame, ...)` で新しい frame を返す。
10. `CognitiveCycle.run()` に provider API、store save、relationship update、adapter execute がない。
11. `FeatureDefinition` 経由ではない feature 登録がない。
12. `runtime/wiring/**` 以外に service locator / global registry / resolve_optional がない。
13. `action: str` による dispatcher 分岐が増えていない。

---

## 例外を許す場合

例外は原則作らない。
どうしても必要な場合は、以下を同じ PR / commit に含める。

```text
- 例外の理由
- 期間
- 削除条件
- architecture test 側の明示的 allowlist
```

allowlist は永続化しない。
後続実装で放置される例外は設計負債として扱う。

---

## 関連ドキュメント

- architecture.md: 依存方向の定義
- rules.md: 禁止パターン一覧
