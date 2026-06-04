# Review Checklist

Use this when reviewing a patch or agent output.

## Blocking issues

- [ ] Incorrect behavior
- [ ] Architecture boundary violation
- [ ] Type boundary weakened
- [ ] Safety/presentation bypass
- [ ] no-action semantics broken
- [ ] Tests removed or weakened without justification
- [ ] Runtime wiring gained business logic
- [ ] Feature bypasses `FeatureDefinition`

## Non-blocking issues

- [ ] Naming could be clearer
- [ ] Tests could be more focused
- [ ] Documentation could be updated
- [ ] Duplicate helper could be consolidated
- [ ] Error message could be clearer

## Suggested verification

- [ ] Narrow behavior test
- [ ] Architecture tests
- [ ] Ruff
- [ ] Format check
- [ ] Mypy
- [ ] Full tests if behavior is broad
