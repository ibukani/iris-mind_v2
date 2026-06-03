# Prompt: OpenCode Implementation

```text
Work in this repository using `AGENTS.md` as the main instruction file.

Task:
<task>

Token policy:
- Use Primitive Prompt Mode when context gets long.
- Think/work in English.
- Final report must be Japanese and compact.


Follow:
- `.agents/workflows/implement.md`
- `.agents/rules/architecture.md`
- `.agents/rules/boundaries.md`
- `.agents/rules/anti-patterns.md`
- `.agents/rules/typing.md`
- `.agents/checklists/done.md`

Do not broaden the task. Keep the patch small and target-native.

Required guardrails:
- No forbidden imports.
- No service locator/global registry.
- No `dict[str, Any]` at internal boundaries.
- No compatibility shim unless this is an explicit migration task with removal criteria and tests.
- No safety/presentation bypass.

Run targeted tests first. Before final response, run or report inability to run:

```bash
make check
```
```
