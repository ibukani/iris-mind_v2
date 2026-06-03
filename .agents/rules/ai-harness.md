# AI Harness Rules

These rules define how Codex, OpenCode, Claude Code, and other coding agents should operate in this repository. They complement the strict lint/type/test gate; they do not replace it.

## Primary goal

Optimize for repeatable, inspectable agent work. Every agent session should leave behind code that can be checked by deterministic commands, not by trust in the model.

## Required operating loop

1. Restate the task as a compact implementation contract.
2. Identify the matching workflow in `.agents/workflows/`.
3. Read only the rules needed for that workflow after the mandatory files in `AGENTS.md`.
4. Inspect existing tests before changing behavior.
5. Make the smallest architecture-preserving change that satisfies the task.
6. Run focused tests while iterating.
7. Run `make ai-check` or explain exactly why it could not run.
8. Report changed files, checks, failures, and residual risk in Japanese.

## Do not hide uncertainty

If a check fails, keep the failure visible. Do not claim the task is complete unless the failure is unrelated and explicitly documented.

## No quality-gate escape hatches

Do not weaken these to make a task pass:

- Ruff rule selection or ignores
- mypy strictness
- pyright strictness
- pytest warning behavior
- coverage threshold
- architecture guard tests
- no-action contract tests

Fix the code, tests, or task scope instead.

## Context budget rule

For long sessions, prefer file paths, exact commands, and failing diagnostics over broad prose. Do not paste entire files into prompts when a path and symbol name are sufficient.

## Multi-agent handoff rule

When handing work from one agent to another, include only:

- goal
- changed files
- relevant rules/workflow paths
- commands already run
- current failing diagnostics
- next smallest action

Do not include speculation or historical discussion unless it changes the next action.
