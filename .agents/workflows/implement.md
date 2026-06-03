# Workflow: Implement Feature or Behavior

Use this workflow when adding a new behavior, contract, feature slice, pipeline step, adapter behavior, or runtime path.

## 1. Understand the target behavior

Identify:

- user-visible behavior
- affected layer
- existing contract types
- existing tests that describe nearby behavior
- whether architecture docs already cover the change

Do not start by creating a new abstraction.

## 2. Locate the correct layer

| Need | Likely location |
|---|---|
| New shared domain type | `iris/contracts/` |
| Cognitive processing | `iris/cognitive/` |
| Feature extension | `iris/features/<name>/` |
| Provider or storage backend | `iris/adapters/` |
| Presentation | `iris/presentation/` |
| Safety | `iris/safety/` |
| Wiring/startup | `iris/runtime/` |

## 3. Write or update tests first when practical

Prefer the closest test level:

- contract tests for types
- cognitive tests for steps
- feature tests for feature definition behavior
- runtime tests for end-to-end turn flow
- architecture tests for boundaries

## 4. Implement narrowly

- Keep changes local.
- Reuse existing contracts.
- Use constructor injection.
- Add typed result classes instead of dictionaries.
- Do not add compatibility shims.

## 5. Update docs only if behavior or architecture changed

Relevant docs:

- `README.md`
- `docs/architecture.md`
- `docs/rules.md`
- `docs/tests.md`
- `.agents/rules/*.md`

## 6. Verify

Run targeted tests first, then at least:

```bash
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/architecture -q
```

Run broader tests when the change is not isolated:

```bash
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
uv run pytest tests/ -q
```

## 7. Final report

Report:

- changed files
- behavior added
- tests/checks run
- risks and follow-up work
