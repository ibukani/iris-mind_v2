---
name: test-repair
description: Repair failing tests or add regression coverage without weakening the architecture harness.
---

# Test Repair Skill

Use this skill when tests fail or when adding regression coverage.

## Goal

Repair behavior or tests without weakening the architecture harness.

## Procedure

1. Reproduce the narrowest failing test.
2. Read the failure message and relevant test file.
3. Classify the failure: behavior, architecture, typing, setup, or stale expectation.
4. Fix implementation first when the test encodes an intended rule.
5. Update tests only when intended behavior changed.
6. Run the narrow test again.
7. Run architecture tests when boundaries are touched.

## Forbidden

- deleting assertions to pass
- adding broad architecture allowlists
- replacing meaningful tests with shallow smoke tests
- hiding failures behind try/except
- claiming checks passed without running them

## Output

```text
Failure
Root cause
Fix
Regression coverage
Commands run
Remaining risk
```
