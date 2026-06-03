# Testing and Verification Rules

Tests are part of the agent harness. Do not treat them as optional cleanup.

## Standard command

Before reporting completion, run:

```bash
make check
```

`make verify` is an alias for `make check`. Both call `scripts/verify.py`.

The full check runs, in order:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime iris/errors.py
uv run pyright .
uv run pytest tests/architecture -q
uv run pytest tests/ -q
```

Use this while iterating:

```bash
make quick
```

`make quick` skips the full test suite, but still runs lint, format check, type check, and architecture tests.

## Targeted test selection

Use the closest test first while working:

| Change area | First tests to run |
|---|---|
| contracts | `uv run pytest tests/contracts -q` |
| cognitive steps | `uv run pytest tests/cognitive -q` |
| runtime flow | `uv run pytest tests/runtime -q` |
| features | `uv run pytest tests/features -q` |
| adapters | `uv run pytest tests/adapters -q` |
| dependency boundaries | `make arch` |

## Architecture tests are mandatory

Architecture tests verify design boundaries. They are not cosmetic.

Do not skip them after changes that touch imports, contracts, pipeline steps, runtime wiring, feature registration, or adapters.

## When tests fail

1. Read the failing assertion.
2. Identify whether the failure is behavioral, architectural, typing-related, or test-staleness.
3. Fix the implementation if the test captures an intended rule.
4. Update tests only when the intended behavior or architecture changed.
5. Never weaken architecture tests to make an unrelated task pass.

## No unverified completion claims

Do not write “all tests pass” unless the full command actually ran and passed.

If a command cannot run, report:

- command attempted
- exact failure reason
- what narrower verification was possible
- residual risk
