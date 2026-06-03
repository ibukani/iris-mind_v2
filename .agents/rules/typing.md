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
