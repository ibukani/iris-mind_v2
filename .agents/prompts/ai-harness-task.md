# AI Harness Task Prompt

Use this prompt shape for Codex/OpenCode when changing agent instructions, harness scripts, or verification commands.

```text
Goal: <one concrete harness change>.
Read: AGENTS.md, .agents/README.md, .agents/workflows/ai-harness.md.
Also read: .agents/rules/ai-harness.md, .agents/rules/verification.md, .agents/checklists/ai-harness.md.
Scope: <files/directories>.
Do not: weaken ruff/mypy/pyright/pytest/coverage, rename stable make targets, duplicate long rules.
Keep: make check canonical, AI commands wrappers only, compact durable guidance.
Test: make ai-context; make ai-quick or stronger.
Report: Japanese. Files, summary, checks, risks, reusable lessons.
```
