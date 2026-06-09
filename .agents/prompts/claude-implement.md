# Prompt: Claude Code Implementation

```text
Goal: <task>.
Entry: CLAUDE.md, then shared harness under AGENTS.md and .agents/README.md.
Workflow: .agents/workflows/implement.md.
Also read task-relevant rules from AGENTS.md Required context routing.
Do not: service locator, global registry, dict boundary, compatibility shim unless explicit migration, safety/presenter bypass.
Keep: Iris layer boundaries, typed contracts, no-action semantics, small reviewable patch.
Test: targeted tests first; make check before final when possible.
Report: Japanese. 変更ファイル, 概要, 検証, 残リスク.
```
