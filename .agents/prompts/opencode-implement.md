# Prompt: OpenCode Implementation

```text
Work in this repository using `AGENTS.md` as the main instruction file.

Task:
<task>

Follow:
- `.agents/workflows/implement.md`
- `.agents/rules/architecture.md`
- `.agents/rules/boundaries.md`
- `.agents/checklists/done.md`

Do not broaden the task. Keep the patch small and target-native.

Required guardrails:
- No forbidden imports.
- No service locator/global registry.
- No `dict[str, Any]` at internal boundaries.
- No compatibility shim unless explicitly requested.
- No safety/presentation bypass.

Run targeted tests first. Before final response, run or report inability to run:

```bash
uv run pytest tests/architecture -q
uv run ruff check .
uv run ruff format --check .
```
```
