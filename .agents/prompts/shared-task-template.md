# Shared Agent Task Template

Use this template when asking any coding agent to work on Iris. Compress further with Primitive Prompt Mode when context is tight.

```text
Goal: <one clear task>.
Read: AGENTS.md, .agents/README.md, .agents/workflows/<workflow>.md.
Also read task-relevant rules from AGENTS.md Required context routing.
Scope: <files/directories>.
Do not: broaden scope, break layer boundaries, add service locator/global registry, use dict boundary, bypass safety/presentation.
Acceptance: <observable result>; <tests added/updated>; make check passes or failure is reported exactly.
Report: Japanese. 変更ファイル, 概要, 検証, 残リスク.
```
