# Workflow: Bug Fix

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

## 4. Add regression coverage

If the bug was not already covered, add a focused test.

## 5. Verify

Run the reproducing test, then relevant broader checks.

```bash
uv run pytest tests/architecture -q
uv run ruff check .
uv run ruff format --check .
```

## 6. Report

Include:

- root cause
- fix summary
- regression test added or updated
- commands run
