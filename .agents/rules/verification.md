# Verification Rules

Use deterministic commands as the source of truth for agent work.

## Command Hierarchy

- `make ai-test-target TARGET=tests/path_or_file.py`: focused test loop.
- `make ai-test-target TARGET='tests/path.py::test_name'`: focused one-test loop.
- `make ai-arch`: architecture and anti-pattern guard loop.
- `make ai-quick`: fast strict loop; lint, format, mypy, pyright, architecture tests.
- `make ai-check`: full strict loop; keeps going after failures.
- `make check`: final full gate; stop-on-first-failure CI-like validation.
- `make coverage`: coverage-only full test loop.

## Expected Use

1. Run the smallest relevant focused command while editing.
2. Run `make ai-quick` after local failures are fixed.
3. Run `make ai-check` before handoff when a full failure list is useful.
4. Run `make check` for final validation when possible.

`make verify` is an alias for `make check`.

## Autofix Commands

- `make format-write`: apply Ruff formatting.
- `make lint-fix`: apply Ruff fixes after inspecting the expected target diff.

Do not run broad autofix to hide unrelated failures or rewrite unrelated code.

## Failure Reporting

When a command fails, report:

- exact command
- exit status if known
- first failing file or test
- whether failure likely predates current edit, if known
- next recommended fix

## Prohibited Claims

- Do not write `all checks passed` unless the full command actually passed.
- Do not replace a failed strict gate with a weaker command and call it equivalent.
