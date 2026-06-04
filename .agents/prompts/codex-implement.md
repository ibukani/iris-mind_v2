# Prompt: Codex Implementation

```text
You are working in the Iris repository.

Read `AGENTS.md`, then follow `.agents/workflows/implement.md`, `.agents/rules/anti-patterns.md`, and `.agents/rules/typing.md`.

Implement this task:
<task>

Hard constraints:
- Preserve layer boundaries.
- `cognitive/` must not import from `adapters/`, `runtime/`, or `features/`.
- Use typed contracts, not `dict[str, Any]` boundary objects.
- Do not add service locators or global registries.
- Do not add compatibility shims unless this is an explicit migration task with removal criteria and tests.
- Preserve no-action semantics.

Before finishing, run the narrowest relevant tests, then:

```bash
make check
```

If you cannot run a command, report why.

Final report format in Japanese:
- 変更ファイル
- 概要
- 検証
- 残リスク
```
