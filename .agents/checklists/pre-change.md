# Pre-Change Checklist

Before editing code, confirm scope, boundaries, and the first test.

## Scope

- [ ] What exact behavior or structure should change?
- [ ] Which layer owns the change?
- [ ] Which files and tests already cover nearby behavior?

## Boundary check

- [ ] Does the change preserve `cognitive/` independence from `adapters/`, `runtime/`, and `features/`?
- [ ] Does the change preserve typed contracts and avoid service locators / global registries?
- [ ] Does the change keep presentation/safety outside cognitive logic?

## First test

- [ ] Narrowest test identified and run.
- [ ] Test type identified: unit / contract / architecture / flow.
- [ ] `make quick` passes before broadening scope.
