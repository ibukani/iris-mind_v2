---
name: prompt-compression
description: Compress long agent prompts into Primitive Prompt Mode while preserving constraints, tests, and acceptance criteria.
---

# Skill: Prompt Compression

Use this skill when an agent prompt, issue handoff, or implementation instruction is too long.

## Goal

Compress the task into the Primitive Prompt Mode defined in `AGENTS.md` without losing acceptance criteria or architecture constraints.

## Steps

1. Extract the exact goal.
2. Keep only relevant file paths, tests, and rules.
3. Convert prose into compact English fragments.
4. Preserve hard constraints verbatim when possible.
5. Require Japanese final report.
6. Remove examples unless they are acceptance criteria.

## Output shape

```text
Goal: ...
Read: ...
Scope: ...
Do not: ...
Keep: ...
Test: ...
Report: Japanese, compact.
```

## Do not remove

- architecture boundary constraints
- no-action semantics
- test commands
- explicit acceptance criteria
- safety/presentation separation
