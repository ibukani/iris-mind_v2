# AI Harness Task Prompt

Use this prompt shape for Codex/OpenCode when changing this repository. Keep it compact.

```text
Goal: <one concrete change>.
Read: AGENTS.md, .agents/rules/ai-harness.md, .agents/rules/verification.md, <task workflow>.
Scope: <files/directories>.
Do not: weaken ruff/mypy/pyright/pytest/coverage, add Any boundary, skip tests, add compatibility shim.
Test: focused pytest; make ai-quick; make ai-check before final if feasible.
Report: Japanese. Files, summary, checks, risks.
```
