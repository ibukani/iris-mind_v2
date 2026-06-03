# Test & Quality Rules for AI Coding Agents

This compatibility file points to the structured harness rules under `.agents/rules/testing.md`.

## Canonical verification

Before reporting completion, run:

```bash
make check
```

`make verify` is an alias for `make check`.

Both commands call `scripts/verify.py` and run:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime iris/errors.py
uv run pyright .
uv run pytest tests/architecture -q
uv run pytest tests/ -q
```

Use `make quick` only while iterating. It runs lint, format, mypy, pyright, and architecture tests, but skips the full test suite.

## Targeted checks

```bash
make lint
make format
make type
make arch
make test
```

## Architecture Test Pass Criteria (ALL 13 MUST PASS)

Architecture tests verify that design boundaries are intact. These are NOT optional.

1. `iris/cognitive/**` does NOT import from `iris/adapters/**`
2. `iris/cognitive/**` does NOT import from `iris/runtime/**`
3. `iris/cognitive/**` does NOT import from `iris/features/**`
4. `iris/contracts/**` does NOT import from `iris/cognitive/**`, `iris/adapters/**`, `iris/runtime/**`
5. `WorkspaceFrame` is a frozen dataclass
6. `WorkspaceFrame` contains NO `dict[str, Any]`, `dict[str, object]`, `MutableMapping`
7. `PipelineStep.run()` returns a `PipelineStepResult` subclass
8. `PipelineStep.run()` does NOT mutate `WorkspaceFrame`
9. `FrameBuilder` returns a NEW frame using `replace(frame, ...)`
10. `CognitiveCycle.run()` contains NO provider API calls, store saves, relationship updates, or adapter executions
11. All feature registrations use `FeatureDefinition`
12. No service locator / global registry / `resolve_optional` outside `runtime/wiring/**`
13. No new `action: str` dispatcher branches added

## Exception Policy

Exceptions are NOT permitted by default. If an exception is unavoidable, the SAME PR/commit MUST include:

- Reason for the exception
- Time-limited duration
- Removal conditions
- Explicit allowlist entry in architecture tests

Allowlists are NEVER permanent. Failures left in place by subsequent implementation are considered design debt.
