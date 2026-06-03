# Pre-Commit Checklist

Use this before committing or handing off a patch.

## Code quality

- [ ] `uv run ruff check .`
- [ ] `uv run ruff format --check .`
- [ ] `uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime`

## Tests

- [ ] Targeted tests for changed area
- [ ] `uv run pytest tests/architecture -q`
- [ ] `uv run pytest tests/ -q` when the change is broad or behavior-impacting

## Architecture

- [ ] No forbidden imports
- [ ] No service locator or global registry
- [ ] No new untyped boundary dictionaries
- [ ] No compatibility shims unless explicitly requested
- [ ] No hidden behavior changes in refactors
- [ ] no-action semantics preserved

## Docs

- [ ] README/docs updated if behavior changed
- [ ] `.agents/` rules updated if agent guidance changed
- [ ] Commands in docs are still valid
