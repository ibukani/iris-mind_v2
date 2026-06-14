# Workflow: Add a Feature Slice

Language policy: think/work in English when available; write the final user-facing report in Japanese; keep it compact.
Use this when adding a new vertical feature under `iris/features/<name>/`.

## Required structure

```text
iris/features/<name>/
├── __init__.py
├── feature.py
└── ... feature-local modules ...
```

`feature.py` must expose a target-native provider such as:

```python
def define_feature() -> FeatureDefinition:
    return FeatureDefinition(...)
```

## Feature rules

A feature may:

- provide pipeline steps
- provide observation sources
- provide learning hooks
- provide background jobs
- define feature-local helpers and contracts when they do not cross global boundaries

A feature must not:

- import adapters directly
- import runtime directly
- mutate cognitive internals
- register itself globally
- call external apps directly
- bypass safety or presentation
- add `# noqa`, `# type: ignore`, `# pyright: ignore`, `typing.cast`, or `object.__setattr__`
- edit `.agents/approved-suppression-debt.toml` or its `.snap` companion. The merge-base guard `scripts/check_suppression_debt_changes.py` (wired into `make static-arch`, `make quick`, `make check`, and the `make ai-*` family) blocks silent registry changes unless the human-only `IRIS_APPROVE_SUPPRESSION_DEBT_UPDATE=1` signal is set. Coding agents must not export that variable.
- weaken `pyproject.toml`, architecture guards, Ruff, mypy, pyright, or pytest settings

## Wiring

Runtime wiring collects `FeatureDefinition` instances explicitly. Do not create a global plugin registry.

## Tests

Add or update:

- `tests/features/test_<name>_*.py`
- `tests/runtime/test_<name>_wiring.py` if runtime composition changes
- `tests/architecture/` if a new boundary rule is needed

## Verification

Use targeted feature/runtime tests while iterating. Before handoff or final report, run:

```bash
make ai-check
```

Use `make check` when CI-like stop-on-first-failure validation is preferred.
