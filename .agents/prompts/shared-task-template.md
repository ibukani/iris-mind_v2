# Shared Agent Task Template

Use this template when asking any coding agent to work on Iris.

```text
Task:
<one clear task>

Context:
- This is the Iris cognitive runtime repository.
- Read AGENTS.md first.
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
- `uv run pytest tests/architecture -q` passes.

Report:
- Changed files
- Summary
- Verification commands and results
- Risks/follow-up
```
