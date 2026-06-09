# Done Checklist

A task is complete only when implementation, tests, and report align.

## Full Gate

Run before reporting completion:

```bash
make check
```

`scripts/verify.py` runs lint, format, mypy, pyright, architecture tests, and coverage.

Use `make quick` only for iteration. Do not present it as full completion verification.

For docs-only changes, run the smallest relevant command and explain why full verification was not needed.

## Human Checks

- Code changes implement only the requested behavior.
- Architecture boundaries still match `AGENTS.md` and `.agents/rules/architecture.md`.
- No unrelated rewrites, broad autofix churn, or hidden TODOs.
- New or changed behavior has focused tests when practical.
- Final report is Japanese, compact, and includes commands/results.
- If a check was not run, report the reason.

## Final Report Template

```text
変更ファイル
- ...

概要
- ...

検証
- command: result

残リスク
- ...
```

## Fallback

If `make check` cannot run, report the failure and run relevant manual steps when possible:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run mypy iris tests scripts main.py`
4. `uv run pyright .`
5. `uv run pytest tests/architecture -q`
6. `uv run pytest tests/ --cov=iris --cov-branch --cov-fail-under=90`
