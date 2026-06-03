# Workflow: Add a Feature Slice

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

```bash
uv run pytest tests/features -q
uv run pytest tests/runtime -q
uv run pytest tests/architecture -q
uv run ruff check .
uv run ruff format --check .
```
