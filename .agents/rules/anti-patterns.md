# Anti-Patterns

Reject these patterns unless a task explicitly asks for a temporary migration path and includes removal criteria plus tests.

## Service locator

Forbidden examples:

```python
container.resolve(...)
get_service(...)
locate(...)
resolve_optional(...)
```

Use constructor injection in runtime wiring.

## Global mutable registry

Forbidden:

```python
GLOBAL_FEATURES.append(feature)
registry.register(step)
```

Use explicit `FeatureDefinition` collection and runtime composition.

## Compatibility shim creep

Forbidden unless the task explicitly requests a migration path with removal criteria and tests:

- `legacy_*.py`
- wrapper APIs around removed structures
- translation layers that preserve old internal APIs
- TODO-based temporary bridges

Prefer target-native implementation.

## Cognitive God Service

Forbidden:

- LLM prompt building inside `CognitiveCycle.run()`
- memory updates inside `CognitiveCycle.run()`
- relationship updates inside `CognitiveCycle.run()`
- adapter execution inside `CognitiveCycle.run()`
- safety checks inside `CognitiveCycle.run()`

## Untyped internal state

Forbidden:

```python
frame.state["memory"] = ...
context["relationship"] = ...
result: dict[str, Any]
```

Create typed result and frame fields instead.

## Feature backdoor

Forbidden:

- feature imports runtime and registers itself globally
- feature imports adapter directly
- feature mutates cognitive internals
- feature bypasses `FeatureDefinition`

## Safety/presentation bypass

Forbidden:

```text
ActionSelectionStep → external send
ResponseGenerationStep → PresentedOutput
Adapter → safety decision
```

Keep the normal runtime flow.

## Test weakening

Forbidden:

- deleting architecture assertions to pass a task
- adding broad allowlists without expiration/removal conditions
- replacing meaningful tests with snapshot-only checks
- asserting implementation details that make refactoring impossible
