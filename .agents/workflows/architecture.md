# Workflow: Architecture Change

Use this workflow when changing package boundaries, pipeline flow, contracts, runtime wiring, safety/presentation behavior, or feature extension points.

## Read first

- `AGENTS.md`
- `docs/architecture.md`
- `.agents/rules/architecture.md`
- `.agents/rules/boundaries.md`
- `.agents/rules/cognitive-cycle.md`
- `.agents/rules/anti-patterns.md`
- `.agents/rules/testing.md`

## Process

1. Identify the layer being changed.
2. Identify allowed inbound and outbound imports for that layer.
3. Inspect matching architecture tests under `tests/architecture/`.
4. Add or update architecture tests before broad refactors.
5. Keep contracts typed and explicit.
6. Keep `CognitiveCycle` as a coordinator, not a policy/service container.
7. Run `make ai-arch`.
8. Run `make ai-quick`.

## Boundary red flags

Stop and redesign if the change requires:

- `cognitive` importing `runtime`, `adapters`, or `features`
- `contracts` importing implementation packages
- new global registries
- string-dispatch action branches
- broad compatibility shims
- untyped boundary dictionaries

## Report

Include the architecture rule affected, the test that protects it, and any migration risk.
