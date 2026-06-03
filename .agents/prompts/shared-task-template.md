# Shared Agent Task Template

Use this template when asking any coding agent to work on Iris. For shorter prompts, apply the Primitive Prompt Mode embedded in `AGENTS.md`.

```text
Task:
<one clear task>

Context:
- This is the Iris cognitive runtime repository.
- Read AGENTS.md first.
- Use the token/language policy embedded in `AGENTS.md`.
- Think/work in English; final report in Japanese.
- Follow `.agents/workflows/<workflow>.md`.
- Preserve architecture boundaries from `.agents/rules/architecture.md`.

Constraints:
- Do not introduce service locators or global mutable registries.
- Do not use `dict[str, Any]` at internal boundaries.
- Do not bypass ActionPlan → Safety → Presenter → OutputSafety flow.
- Do not change behavior outside the task scope.

Acceptance criteria:
- <observable result>
- <tests added/updated>
- `make check` passes, or any inability to run it is reported exactly.

Report in Japanese:
- 変更ファイル
- 概要
- 検証
- 残リスク
```
