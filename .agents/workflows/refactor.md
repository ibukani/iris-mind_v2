# Workflow: Refactor

Use this workflow when improving structure without intentionally changing behavior.

## Refactor scope

Allowed refactors:

- reduce duplication
- improve type boundaries
- split a God object
- move code to the correct layer
- clarify naming
- remove obsolete compatibility code
- simplify tests without weakening coverage

Forbidden refactors:

- behavior changes hidden in cleanup
- broad rewrites without tests
- new abstraction layers without repeated use
- compatibility shims that preserve bad APIs

## Before editing

1. Identify the behavior that must remain unchanged.
2. Find tests that cover it.
3. Run a narrow baseline test if possible.
4. Note architecture tests that protect the boundary being changed.

## During refactor

- Preserve public contracts unless intentionally changing them.
- Move code by responsibility, not by convenience.
- Keep commits/patches small.
- Do not alter user-facing behavior unless the task explicitly requests it.

## After editing

Run at least:

```bash
uv run pytest tests/architecture -q
uv run ruff check .
uv run ruff format --check .
```

Also run the targeted tests for touched behavior.

## Report

State clearly:

- what structure changed
- what behavior should be unchanged
- what tests confirm equivalence
- any remaining design debt
