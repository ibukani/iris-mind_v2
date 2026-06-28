# Testing and Verification Rules

Tests are part of the agent harness. Do not treat them as optional cleanup.

## Standard command

Before reporting completion, run:

```bash
make check
```

`make verify` is an alias for `make check`. Both call `scripts/verify.py`.

The full check runs, in order:

1. `ruff check .`
2. `ruff format --check .`
3. `mypy iris tests scripts main.py`
4. `pyright .`
5. `scripts/check_suppression_debt_changes.py` (debt-registry)
6. `make static-arch` (architecture tests via imports, semgrep, debt-registry, arch)
7. `pytest` default targets with coverage (non-E2E tests)
8. `pytest tests/e2e -m "e2e and not llm_live"` (process-level E2E, separately from coverage targets)

Default test targets exclude `tests/e2e` — normal coverage runs non-E2E tests only.
E2E tests run separately as part of the full `make check` gate.
Live LLM tests (`llm_live` marker) are excluded from the default gate entirely.

Use this while iterating:

```bash
make quick
```

`make quick` skips the full test suite, coverage gate, and E2E tests, but still runs lint, format check, mypy, pyright, debt-registry, and architecture tests.

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

## Suppression-free test patterns

Tests must not use suppressions as a shortcut. Do not use `# type: ignore`,
`# noqa`, `# pyright: ignore`, `typing.cast`, or `object.__setattr__` in tests
unless already human-approved in `.agents/approved-suppression-debt.toml`.

If tests need private access, frozen mutation checks, provider fakes, or type
assertions, create typed helpers under `tests/helpers/`.

For frozen dataclass immutability checks, use:

```python
from tests.helpers.immutability import assert_frozen_field

assert_frozen_field(instance, "field_name", replacement_value)
```

Do not use these patterns for frozen dataclass tests:

```python
instance.field = replacement_value  # type: ignore[misc]
setattr(instance, "field", replacement_value)  # noqa: B010
object.__setattr__(instance, "field", replacement_value)  # noqa: PLC2801
```

Do not weaken architecture tests to make implementation tasks pass.

## Weak-agent escape hatches

Do not use these shortcuts to make gates pass:

- Do not skip or xfail tests instead of fixing tests or implementation.
- Do not swallow broad exceptions with default returns.
- Do not branch on pytest or test environment markers in production code.
- Do not create fire-and-forget async tasks.
- Do not expand architecture scanner exclusions.
- Do not add fake, dummy, mock, stub, or placeholder production shortcuts.

### Registry changes are a human task

Tests may not edit `.agents/approved-suppression-debt.toml` or its snapshot.
`scripts/check_suppression_debt_changes.py` blocks those changes in the
normal verification path. The guard only accepts them when
`IRIS_APPROVE_SUPPRESSION_DEBT_UPDATE=1` is set, which is a human-only
action. See `.agents/rules/typing.md` and
`.agents/suppression-debt-remediation.md` for the full policy and cleanup
plan.

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
