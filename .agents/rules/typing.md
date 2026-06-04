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

## Suppression policy

Suppressions are escape hatches, not normal fixes.

Do not use these in protected architecture layers:

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

Allowed exception zones:

- `iris/adapters/` may use local suppressions only at external SDK or provider boundaries.
- `tests/` should use helpers or fixtures instead of suppressions; frozen dataclass immutability tests must use `tests.helpers.immutability.assert_frozen_field`.
- local `scripts/` may use local suppressions for harness operations when the reason is documented.

Allowed suppression shape outside protected layers:

```python
import subprocess  # noqa: S404 -- local harness runs fixed command tuples only
value = client.value  # type: ignore[attr-defined] -- third-party package lacks complete stubs
```

Forbidden suppression shapes:

```python
x = value  # noqa
x = value  # noqa: RULE
x = value  # type: ignore
object.__setattr__(instance, "field", value)
```

When a suppression seems necessary, prefer precise signatures, a typed contract, `Protocol`, `TypeGuard`, helper extraction, or adapter-side normalization first.

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
