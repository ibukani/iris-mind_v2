# Done Checklist

A task is not complete until the implementation, tests, and report are aligned.

## Required final state

- [ ] Code implements only the requested behavior.
- [ ] Architecture boundaries are preserved.
- [ ] Tests cover the new or fixed behavior.
- [ ] Existing tests were not weakened to pass the task.
- [ ] Documentation is updated if behavior, commands, or architecture changed.
- [ ] There are no new TODOs that hide required work.

## Required checks

Run the relevant subset. For broad code changes, run all.

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
uv run pytest tests/architecture -q
uv run pytest tests/ -q
```

## Final report template

```text
Changed files
- ...

Summary
- ...

Verification
- command: result
- command: result

Risks / follow-up
- ...
```

## Honesty rule

If a check was not run, say so. Include the reason.
