# Entropy Audit Skill

Use this skill for cleanup reviews after multiple AI-agent changes.

## Goal

Find accumulated complexity, duplication, and architecture drift.

## Audit targets

- duplicate helpers
- unused compatibility wrappers
- stale TODOs
- over-broad abstractions
- untyped boundary dictionaries
- hidden global state
- docs/tests drift
- feature code leaking into runtime or cognitive internals
- runtime wiring gaining business logic

## Procedure

1. Inspect recent changes or the target directory.
2. Group findings by risk: correctness, architecture, maintainability, tests, docs.
3. Prefer small cleanup patches over broad rewrites.
4. Suggest architecture tests for recurring drift.

## Output

```text
High-risk entropy
Medium-risk entropy
Low-risk cleanup
Suggested tests/guards
Suggested cleanup order
```
