# Workflow: Strict Gate / Test Fix

Use this workflow when the task is to fix Ruff, mypy, pyright, pytest, coverage, or architecture failures.

## Read first

- `AGENTS.md`
- `.agents/rules/ai-harness.md`
- `.agents/rules/verification.md`
- `.agents/rules/typing.md`
- `.agents/rules/testing.md`
- `.agents/rules/architecture.md` when an import or boundary failure appears

## Process

1. Capture the exact failing command and the first failure.
2. Classify the failure: lint, format, type, pyright, unit test, architecture, coverage.
3. Fix the root cause, not the checker.
4. Add or update tests when behavior changes.
5. Re-run the narrow command.
6. Run `make ai-quick`.
7. Run `make ai-check` when the error class is resolved.

## Forbidden fixes

- Adding `type: ignore` without a specific error code and comment.
- Replacing typed boundaries with `Any`, `object`, raw `dict`, or untyped callbacks.
- Marking tests xfail/skip to pass the gate.
- Lowering coverage.
- Removing architecture tests.
- Relaxing Ruff/mypy/pyright configuration.

## Report

Use the compact Japanese report from `AGENTS.md`. Include remaining failing commands if any.
