# Feature Boundary Skill

Use this skill when adding or reviewing a feature under `iris/features/`.

## Goal

Ensure features remain vertical slices and do not become backdoors into runtime or cognitive internals.

## Required checks

- Feature exposes `FeatureDefinition`.
- Feature does not import `iris/adapters`.
- Feature does not import `iris/runtime`.
- Feature does not import `iris/presentation` or `iris/safety`.
- Feature does not mutate `WorkspaceFrame` directly.
- Runtime wiring explicitly collects feature definitions.
- Tests exist under `tests/features/` and, if needed, `tests/runtime/`.

## Output

```text
Feature boundary status
Violations
Required tests
Suggested patch direction
```
