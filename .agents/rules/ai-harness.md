# AI Harness Rules

These rules define repeatable, inspectable agent work. They complement strict lint/type/test gates; they do not replace them.

## Operating Loop

1. Restate the task as a compact implementation contract.
2. Identify the matching workflow in `.agents/workflows/`.
3. Read only task-relevant rules after the mandatory context in `AGENTS.md`.
4. Inspect existing tests before changing behavior.
5. Make the smallest architecture-preserving change that satisfies the task.
6. Run focused tests while iterating.
7. Run `make ai-quick`, `make ai-check`, or stronger before handoff; report if impossible.
8. Report changed files, checks, failures, residual risk, and reusable lessons in Japanese.

## Quality Gate Invariants

- Do not weaken Ruff, mypy, pyright, pytest, or coverage policy.
- Ruff keeps `select = ["ALL"]` unless a documented project-wide policy change is requested.
- Core architecture code keeps maximum mypy `Any` restrictions.
- Adapters may handle incomplete external typing only at provider boundaries.
- Tests and scripts stay typed.
- Coverage threshold stays 90% for the full gate.

## Autofix

Use `make format-write` or `make lint-fix` only after inspecting the expected target diff.

Do not use broad autofix to hide unrelated failures or rewrite unrelated code.

## Context Budget

Prefer file paths, symbols, exact commands, and failing diagnostics over broad prose. Do not paste entire files into prompts when a path and symbol name are enough.

## Handoff

Include only:

- goal
- changed files
- relevant rules/workflow paths
- commands already run
- current failing diagnostics
- next smallest action

Do not include speculation or historical discussion unless it changes the next action.
