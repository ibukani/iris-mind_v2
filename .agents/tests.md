# Test & Quality Rules for AI Coding Agents

## Test Execution Commands

```bash
# All tests
uv run pytest tests/

# Quick run
uv run pytest tests/ -q

# Architecture guards only (MUST PASS before commit)
uv run pytest tests/architecture -q

# Specific test file
uv run pytest tests/runtime/test_cli.py -q
```

## Code Quality Commands

Run ALL of these before considering work complete:

```bash
# Lint check
uv run ruff check .

# Lint auto-fix
uv run ruff check --fix .

# Format check
uv run ruff format --check .

# Format
uv run ruff format .

# Type check
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
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

## Architecture Test Files

| File | Purpose |
|------|---------|
| `tests/architecture/test_target_architecture_guards.py` | Forbidden symbols, layer dependency direction, runtime entrypoint rules, `__init__.py` rules, no service locator |
| `tests/architecture/test_cognitive_runtime_boundaries.py` | Layer boundary rules |
| `tests/architecture/test_cognitive_runtime_anti_patterns.py` | Anti-pattern scans (global mutable registries, untyped contracts, etc.) |
| `tests/architecture/test_cognitive_runtime_contracts.py` | Design contract tests (frozen dataclasses, FrameBuilder, PipelineStep) |

## Exception Policy

Exceptions are NOT permitted by default. If an exception is unavoidable, the SAME PR/commit MUST include:

- Reason for the exception
- Time-limited duration
- Removal conditions
- Explicit allowlist entry in architecture tests

Allowlists are NEVER permanent. Failures left in place by subsequent implementation are considered design debt.

## Pre-Commit Checklist

Before committing, run and verify:

```bash
uv run ruff check .          # Must pass
uv run ruff format --check .  # Must pass
uv run mypy iris/...          # Must pass
uv run pytest tests/ -q       # Must pass
uv run pytest tests/architecture -q  # Must pass
```
