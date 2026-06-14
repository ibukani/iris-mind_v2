# Workflow: Bug Fix


Language policy: think/work in English when available; write the final user-facing report in Japanese; keep it compact.
Use this workflow for incorrect behavior, failing tests, regressions, or runtime errors.

## 1. Reproduce

Run the narrowest command that reproduces the issue.

Examples:

```bash
uv run pytest tests/runtime/test_no_action_flow.py -q
uv run pytest tests/cognitive/test_response_generation.py -q
```

## 2. Classify the failure

Choose one:

- behavior bug
- architecture boundary violation
- typing bug
- test expectation drift
- dependency/configuration issue

## 3. Fix root cause

Do not paper over symptoms by:

- weakening tests
- adding broad try/except blocks
- introducing compatibility wrappers
- bypassing architecture rules
- adding `# noqa`, `# type: ignore`, `# pyright: ignore`, `typing.cast`, or `object.__setattr__`
- editing `.agents/approved-suppression-debt.toml` or its `.snap` companion. The merge-base guard `scripts/check_suppression_debt_changes.py` (wired into `make static-arch`, `make quick`, `make check`, and the `make ai-*` family) blocks silent registry changes unless the human-only `IRIS_APPROVE_SUPPRESSION_DEBT_UPDATE=1` signal is set. Coding agents must not export that variable.
- weakening `pyproject.toml`, Ruff, mypy, pyright, or pytest settings

## 4. Add regression coverage

If the bug was not already covered, add a focused test.

## 5. Verify

Run the reproducing test, then relevant broader checks.

```bash
make check
```

Use the targeted regression test first, then `make check` before final report.

## 6. Report

Include:

- root cause
- fix summary
- regression test added or updated
- commands run
