# Pre-Change Checklist

Before editing code, answer these questions.

## Scope

- [ ] What exact behavior or structure should change?
- [ ] Which layer owns the change?
- [ ] Which files already implement nearby behavior?
- [ ] Which tests already cover nearby behavior?

## Boundary check

- [ ] Does the change preserve `cognitive/` independence from `adapters/`, `runtime/`, and `features/`?
- [ ] Does the change preserve typed contracts?
- [ ] Does the change avoid service locators and global registries?
- [ ] Does the change keep presentation/safety outside cognitive logic?

## Test plan

- [ ] What is the narrowest test to run first?
- [ ] Should an architecture test be added or updated?
- [ ] Should a contract test be added or updated?
- [ ] Should a runtime flow test be added or updated?
