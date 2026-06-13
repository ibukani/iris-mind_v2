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
4. Prefer precise signatures, typed contracts, `Protocol`, `TypeGuard`, helpers, or adapter normalization over suppression comments.
5. For frozen dataclass immutability tests, use `tests.helpers.immutability.assert_frozen_field`.
6. Add or update tests when behavior changes.
7. Re-run the narrow command.
8. Run `make ai-quick`.
9. Run `make ai-check` when the error class is resolved.

## Forbidden fixes

Suppression escape hatches:
- Do not add `# noqa`, `# type: ignore`, `# pyright: ignore`, `typing.cast`, or `object.__setattr__`.
- Do not edit `.agents/approved-suppression-debt.toml` during normal implementation tasks.
- Do not weaken `pyproject.toml`, architecture guards, Ruff, mypy, pyright, or pytest settings.
- If suppression seems necessary, stop and report the diagnostic and proposed debt entry. Do not apply it.

Additionally:
- Adding `# noqa` in protected architecture layers.
- Adding `type: ignore` or `pyright: ignore` in protected architecture layers.
- Adding `type: ignore` without a specific error code and reason outside protected layers.
- Adding `typing.cast` in protected architecture layers to silence type errors.
- Replacing typed boundaries with `Any`, `object`, raw `dict`, or untyped callbacks.
- Adding generic object/dict accessor helpers such as `_get_value(item: object, name: str)` in protected layers.
- Using `object.__setattr__` or `# noqa: B010` for frozen dataclass tests.
- Marking tests xfail/skip to pass the gate.
- Lowering coverage.
- Removing architecture tests.
- Relaxing Ruff/mypy/pyright configuration.

## Report

Use the compact Japanese report from `AGENTS.md`. Include remaining failing commands if any.
