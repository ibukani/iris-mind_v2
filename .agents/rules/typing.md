# Typing Rules

Iris relies on typed boundaries so coding agents cannot silently turn the runtime into a bag of dictionaries.

## Internal boundary rule

Do not use these types at module boundaries:

```python
dict[str, Any]
dict[str, object]
MutableMapping[str, Any]
Mapping[str, Any]
Any
```

Use typed dataclasses, enums, protocols, or explicit contract types instead.

## Checker-aware authoring rules

Write code so Ruff, mypy, and pyright pass by construction. Do not rely on a later cleanup pass.

### Public API docstrings

Ruff uses `select = ["ALL"]` with Google pydocstyle. Therefore every public module, class, function, and method introduced by a change must have a docstring.

A symbol is public when its name does not start with `_`.

Before adding a function, class, or module, decide whether it is truly public:

- If it is only used inside one module, make it private with a leading `_`.
- If it is part of a contract, port, feature definition, runtime entry point, or adapter boundary, keep it public and add a docstring immediately.
- Do not add public helpers without docstrings as temporary implementation details.

Preferred simple public function shape:

```python
def build_action_plan(selection: ActionSelection) -> ActionPlan:
    """Build an action plan from a typed action selection."""
```

For non-trivial public functions, use Google-style sections:

```python
def create_presented_output(plan: ActionPlan, text: str) -> PresentedOutput:
    """Create output for a sendable action plan.

    Args:
        plan: Typed action plan selected by the cognitive cycle.
        text: Text that has already passed response generation.

    Returns:
        Presented output ready for the output safety gate.
    """
```

Do not write vague docstrings:

```python
def build_action_plan(selection: ActionSelection) -> ActionPlan:
    """Build."""
```

### Type-checker-first implementation

All new functions must have explicit parameter and return types. Do not wait for mypy or pyright to request them.

Use these defaults:

- Return `None` explicitly for side-effect-only functions.
- Use `T | None` when `None` is a valid value.
- Avoid `object` unless runtime type narrowing follows immediately.
- Avoid `Any` in protected architecture layers.
- Convert external SDK payloads into Iris dataclasses at adapter boundaries.
- Use `Protocol` or a typed dataclass instead of `dict[str, Any]`.
- Use `@override` when overriding a base-class or protocol method implementation.

Preferred boundary shape:

```python
@dataclass(frozen=True)
class MemorySearchResult:
    """Typed memory search result returned by memory adapters."""

    text: str
    score: float
```

Avoid this shape:

```python
def search_memory(query: str) -> dict[str, Any]:
    ...
```

### Ruff-first implementation

Ruff is configured broadly. New code should avoid common violations before running the checker.

Use these defaults:

- Add `from __future__ import annotations` to new Python files.
- Keep public modules, classes, functions, and methods documented.
- Keep functions small enough to avoid complexity, branch, argument, local-variable, return-count, and statement-count violations.
- Do not add unused parameters.
- Do not add unused `self`; if an object has no state, prefer a function or `@staticmethod`.
- Do not use `print`; use a typed logger or return structured data.
- Do not use broad `except Exception` unless the boundary requires it and the reason is documented.
- Do not introduce subprocess calls outside scripts or audited adapter boundaries.
- Do not add inline `# noqa` for ordinary Ruff failures.

### Pyright-first implementation

Pyright treats unknown types as errors in production code. Avoid unknowns by design.

Use these defaults:

- Do not pass untyped third-party values into `contracts`, `core`, `cognitive`, `features`, `presentation`, `safety`, or `runtime`.
- Normalize provider responses inside `adapters`.
- Add explicit typed intermediate variables when inference would otherwise become unknown.
- Prefer small typed conversion functions over chained dynamic access.
- Do not use `getattr`, generic object accessors, or untyped dictionaries to hide unknown provider shapes.

Preferred adapter pattern:

```python
def _to_memory_result(payload: ProviderResult) -> MemorySearchResult:
    """Convert a provider result into an Iris memory result."""
    return MemorySearchResult(text=payload.text, score=payload.score)
```

### Prevention before remediation

Before creating or editing code, check this list:

1. Is this symbol public? If yes, add a docstring now. If no, make it private.
2. Are all parameters and returns typed?
3. Does the implementation avoid `Any`, `object`, and generic dictionaries at internal boundaries?
4. Are external-library values normalized inside `adapters`?
5. Is an override marked with `@override`?
6. Is the function small enough to avoid Ruff complexity and size rules?
7. Are there no unused arguments, unused `self`, unused imports, or temporary compatibility shims?
8. Are tests using helpers instead of `type: ignore`, `# noqa`, `pyright: ignore`, `typing.cast`, or `object.__setattr__`?

### Remediation order

If a checker fails, fix the design before adding suppressions.

Use this order:

1. Rename internal helpers to private names if they do not need to be public.
2. Add missing docstrings for public API.
3. Add precise parameter and return types.
4. Replace `dict[str, Any]` or `object` with dataclasses, enums, protocols, or typed contracts.
5. Move dynamic SDK handling into `adapters`.
6. Split large functions instead of suppressing complexity rules.
7. Remove unused arguments or change the design so the argument is needed.

Do not add suppressions merely because Ruff, mypy, or pyright reported an error.

Normal implementation tasks must not add suppressions. If a checker failure seems
impossible to fix without suppression, stop and report:

- exact diagnostic
- file and line
- attempted design fixes
- proposed typed alternative
- proposed suppression-debt entry for human review only

Do not apply the suppression. Do not apply the registry entry.

Preferred fixes before considering suppression:

- precise signatures
- dataclasses
- enums
- `Protocol`
- `TypeGuard`
- adapter-side normalization
- helper extraction
- smaller functions
- test helpers

## Suppression policy

Suppressions are escape hatches, not normal fixes. They are forbidden by default.

### Coding agent rule

Normal implementation tasks must not add suppressions. Coding agents must not edit
`.agents/approved-suppression-debt.toml`.

If a checker failure seems impossible to fix without suppression, stop and report:

- exact diagnostic
- file and line
- attempted design fixes
- proposed typed alternative
- proposed suppression-debt entry for human review only

Do not apply the suppression. Do not apply the registry entry.

### Escape hatch types

These are never allowed in protected architecture layers:

- `# noqa`
- `# type: ignore`
- `# pyright: ignore`
- `typing.cast(...)`
- `object.__setattr__(...)`

Protected layers are:

- `iris/contracts/`
- `iris/core/`
- `iris/cognitive/`
- `iris/features/`
- `iris/presentation/`
- `iris/safety/`
- `iris/runtime/`

Exception zones (`iris/adapters/`, `tests/`, `scripts/`) may only contain
suppression escape hatches when the exact occurrence is registered in
`.agents/approved-suppression-debt.toml`.

### Bare suppression rules

Bare suppressions are always forbidden:

```python
x = value  # noqa            # forbidden — no rule code
x = value  # type: ignore    # forbidden — no error code
x = value  # pyright: ignore # forbidden — no rule code
```

### Forbidden suppression shapes

These are always forbidden regardless of layer:

```python
x = value  # noqa             # bare
x = value  # type: ignore     # bare
object.__setattr__(instance, "field", value)  # except in __post_init__ for frozen dataclass metadata normalization
```

### Debt registry

`.agents/approved-suppression-debt.toml` is the human-approved debt registry.
Architecture test `test_suppression_debt_registry.py` mechanically enforces that
every exception-zone suppression has a matching entry.

Entries are temporary debt, not normal permission. New entries require explicit
human approval.

## Cast policy

Do not use `typing.cast` in protected architecture layers.

A cast is a type-checker assertion, not runtime validation. Do not use it to silence mypy or pyright in internal code.

Use one of these instead:

- precise function signatures
- `TypeGuard` with runtime checks
- `Protocol` for structural requirements
- frozen dataclass or explicit contract conversion
- adapter-side normalization from provider payloads into Iris contracts

`typing.cast` is allowed only in:

- `iris/adapters/` at external SDK or provider boundaries
- `tests/`
- local `scripts/`

Allowed casts must be local, rule-specific, documented with a reason, and must not leak untyped provider values into internal contracts.

## Generic accessor rule

Do not add generic object/dict accessor helpers in protected layers.

Forbidden examples:

```python
def _get_value(item: object, name: str) -> object: ...
def read_field(payload: object, key: str) -> object: ...
```

These helpers hide boundary problems. Normalize external values at adapter boundaries into typed contracts instead.

## Dataclass rules

Use frozen dataclasses for immutable turn snapshots and contract values where possible.

Required for `WorkspaceFrame`:

```python
@dataclass(frozen=True)
class WorkspaceFrame:
    ...
```

## Enum and Literal rules

Do not add open-ended string dispatch for behavior.

Forbidden:

```python
if action == "send":
    ...
elif action == "speak":
    ...
```

Prefer typed contracts, enums, and explicit classes.

## Ports and protocols

Ports belong near the consumer.

Good examples:

```text
cognitive/action/ports.py
cognitive/memory/ports.py
presentation/ports.py
safety/ports.py
adapters/app_gateway/ports.py
```

Avoid a central `contracts/ports.py` that accumulates unrelated abstractions.

## Adapter type leakage

Adapters translate provider-specific objects into Iris contracts.

Provider payloads must not leak into:

- `cognitive/`
- `contracts/`
- `presentation/`
- `features/`

## Tests for typing changes

When adding or changing contracts, add tests under the nearest relevant directory:

- `tests/contracts/`
- `tests/cognitive/`
- `tests/runtime/`
- `tests/architecture/`

Architecture tests should enforce repeated rules rather than relying on prose.
