# Done Checklist

A task is not complete until the implementation, tests, and report are aligned.

## Automated by scripts/verify.py

Run the full gate before reporting completion:

```bash
make check
```

`verify.py` automatically runs lint, format, type, pyright, architecture tests, and coverage. If any check fails, it prints the failure class, first failing location, and recommended next command.

Use `make quick` only for iteration. Do not present it as full completion verification.

If only documentation changed, run the smallest relevant command and explain why full verification was not needed.

## Human checklist

These items still require human judgment:

- [ ] Code implements only the requested behavior.
- [ ] Architecture boundaries are preserved (architecture tests run automatically by `make check`).
- [ ] Tests cover the new or fixed behavior; existing tests were not weakened.
- [ ] Documentation is updated if behavior, commands, or architecture changed.
- [ ] No new TODOs hide required work.
- [ ] Final report is in Japanese, compact, and follows the template below.
- [ ] If a check was not run, say so and include the reason.

## Final report template

```text
変更ファイル
- ...

概要
- ...

検証
- command: result
- command: result

残リスク
- ...
```

## Fallback (when verify.py cannot run)

Run each step manually:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run mypy iris tests scripts main.py`
4. `uv run pyright .`
5. `uv run pytest tests/architecture -q`
6. `uv run pytest tests/ --cov=iris --cov-branch --cov-fail-under=90`
