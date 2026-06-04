# Prompt: Claude Code Implementation

```text
Use `CLAUDE.md` as the entry point and read the shared harness under `.agents/`.

Task:
<task>

Token policy:
- Use Primitive Prompt Mode when context gets long.
- Think/work in English.
- Final report must be Japanese and compact.


Operate with these rules:
- Inspect existing code before editing.
- Make the smallest correct change.
- Preserve Iris cognitive runtime boundaries.
- Add or update tests for behavior changes.
- Do not weaken architecture tests.
- Report any command that cannot be run.

Use `.agents/workflows/implement.md`, `.agents/rules/anti-patterns.md`, `.agents/rules/typing.md`, and `.agents/checklists/done.md`.

Expected final answer in Japanese:
1. 変更ファイル
2. 概要
3. 検証
4. 残リスク
```
