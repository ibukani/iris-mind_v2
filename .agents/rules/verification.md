# Verification Rules

Use deterministic commands as the source of truth for agent work.

## Command hierarchy

- `make ai-test-target TARGET=tests/path_or_file.py`: focused loop for the code being changed.
- `make ai-test-target TARGET='tests/path.py::test_name'`: focused loop for one test case.
- `make ai-arch`: architecture boundary and anti-pattern guard loop.
- `make ai-quick`: fast strict loop; runs lint, format, mypy, pyright, and architecture checks.
- `make ai-check`: full strict loop; runs every configured gate and keeps going after failures.
- `make check`: final full gate; stops on first failure and mirrors CI validation.
- `make coverage`: coverage-only full test loop.

## Expected use

During implementation:

1. Run the smallest focused test that covers the edit.
2. Run `make ai-quick` after local failures are fixed.
3. Run `make ai-check` before handoff or final report.

Use `make check` when a stop-on-first-failure command is preferable, such as CI-like validation.

## Autofix commands

- `make format-write` applies Ruff formatting.
- `make lint-fix` applies Ruff fixes.

Use these only after inspecting the target files and understanding the expected diff. Do not run broad autofix to hide unrelated failures or rewrite unrelated code.

## Failure reporting

For every failed command, report:

- exact command
- exit status if known
- first failing file or test
- whether the failure existed before the current edit if known
- next recommended fix

## Prohibited verification claims

Do not write `all checks passed` unless the full command actually passed in the current environment.

Do not replace a failed strict gate with a weaker command and call it equivalent.
