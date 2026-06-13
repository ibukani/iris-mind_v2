# Workflow: Review


Language policy: think/work in English when available; write the final user-facing report in Japanese; keep it compact.
Use this workflow for code review, architecture review, or agent-output review.

## Review priorities

1. Correctness
2. Architecture boundaries
3. Type safety
4. Test coverage
5. Simplicity
6. Documentation sync

## Check architecture first

Look for:

- forbidden imports
- service locator patterns
- global mutable registries
- `dict[str, Any]` at boundaries
- `CognitiveCycle` becoming a God Service
- feature code bypassing `FeatureDefinition`
- no-action semantics regression

## Check behavior

For each behavior change:

- identify expected input
- identify expected output
- confirm tests cover success and important edge cases
- confirm safety/presentation boundaries are preserved

## Check tests

Reject changes that:

- weaken architecture tests without a documented architecture change
- only test implementation details
- remove regression coverage
- assert exact LLM prose for non-deterministic providers

## Review output format

Use this Japanese structure:

```text
概要
ブロッキング事項
非ブロッキング事項
推奨テスト
アーキテクチャリスク
判定
```

For architecture-sensitive changes, read and apply:

- `.agents/rules/architecture.md`
- `.agents/rules/boundaries.md`
- `.agents/rules/cognitive-cycle.md`
- `.agents/rules/runtime-boundary.md`
- `.agents/checklists/architecture-review.md`

Add this block to the final review:

```text
Architecture verdict:
- Pass / Needs changes

Main risks:
- ...

Checklist failures:
- ...

Required fixes:
- ...

Optional improvements:
- ...
```
