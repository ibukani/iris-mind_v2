# CLAUDE.md

Use this file as the Claude Code entry point for the Iris repository. Shared agent instructions live in `AGENTS.md` and under `.agents/`. Read `AGENTS.md` first because it contains mandatory Primitive Prompt Mode and token/language policy.

## Read first

Before editing code, read:

1. `AGENTS.md`
2. `.agents/README.md`
3. `.agents/rules/architecture.md`
4. `.agents/rules/boundaries.md`
5. `.agents/rules/cognitive-cycle.md`
6. `.agents/rules/testing.md`
7. The matching workflow in `.agents/workflows/`

For broad changes, also read:

- `docs/architecture.md`
- `docs/rules.md`
- `docs/tests.md`
- `README.md`

## Claude Code operating rules

- Prefer small, reviewable changes.
- Inspect existing patterns before introducing a new abstraction.
- Update tests with behavior changes.
- Do not silently relax architecture tests or type checks.
- Do not create compatibility layers unless the task explicitly asks for migration support.
- When requirements are ambiguous, make the smallest change consistent with the architecture and document the assumption in the final report.

## Iris-specific hard constraints

- `CognitiveCycle` only coordinates pipeline steps.
- `WorkspaceFrame` stays typed, frozen, and free of service/store references.
- `ActionPlan` is app-agnostic.
- Presentation and safety happen outside cognitive processing.
- External apps are represented through `Observation`, `AppAction`, and `ActionResult` boundaries.
- Proactive behavior starts from internal observations such as `IdleTickObservation`; it must not bypass the cognitive cycle.

## Verification expectation

Use `.agents/checklists/done.md` before finishing. If possible, run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
uv run pytest tests/architecture -q
uv run pytest tests/ -q
```

Report failures exactly; do not claim a check passed unless it actually ran and passed.
