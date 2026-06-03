# Pre-Commit Checklist

Before committing code changes, run the canonical verification command unless the change is documentation-only and the exception is explicitly reported.

## Standard path

- [ ] `make check`

`make verify` is an equivalent alias.

## Iteration helpers

Use these while working, not as a replacement for final verification.

- [ ] `make quick`
- [ ] `make lint`
- [ ] `make format`
- [ ] `make type`
- [ ] `make arch`
- [ ] `make test`

## Manual review

- [ ] No architecture tests were weakened.
- [ ] No new service locator, global registry, compatibility shim, or temporary wrapper was added.
- [ ] No new `dict[str, Any]` or `dict[str, object]` was added at internal boundaries.
- [ ] Behavior changes have tests.
- [ ] Documentation changed when commands, behavior, or architecture changed.
