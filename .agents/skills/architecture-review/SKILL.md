---
name: architecture-review
description: Review implementation changes for Iris architecture drift, layer violations, and boundary regressions.
---

# Architecture Review Skill

Use this skill when reviewing changes that touch imports, contracts, cognitive pipeline code, runtime wiring, features, adapters, or safety/presentation boundaries.

## Goal

Find architecture drift before it becomes implementation debt.

## Procedure

1. Inspect changed files.
2. Classify each file by layer.
3. Check imports against `.agents/rules/architecture.md`.
4. Check cognitive-cycle rules against `.agents/rules/cognitive-cycle.md`.
5. Check boundary bypasses against `.agents/rules/boundaries.md`.
6. Recommend architecture tests when a rule should be enforced mechanically.

## Must flag

- `cognitive/` importing adapters/runtime/features
- `contracts/` importing implementation layers
- features importing adapters/runtime/presentation/safety
- service locator or global registry introduction
- `WorkspaceFrame` mutation
- untyped dictionaries at internal boundaries
- no-action semantic regression
- direct external send from cognitive code

## Output

```text
Architecture summary
Blocking violations
Non-blocking concerns
Suggested architecture tests
Verdict
```
