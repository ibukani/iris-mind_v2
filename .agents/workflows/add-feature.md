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
