# Workflow: Implement Feature or Behavior

Language policy: think/work in English when available; write the final user-facing report in Japanese; keep it compact.
Use this workflow when adding a new behavior, contract, feature slice, pipeline step, adapter behavior, or runtime path.

## 1. Understand the target behavior

Identify:

- user-visible behavior
- affected layer
- existing contract types
- existing tests that describe nearby behavior
- whether architecture docs already cover the change

Do not start by creating a new abstraction.

## 2. Locate the correct layer

| Need | Likely location |
|---|---|
| New shared domain type | `iris/contracts/` |
| Cognitive processing | `iris/cognitive/` |
| Feature extension | `iris/features/<name>/` |
| Provider or storage backend | `iris/adapters/` |
| Presentation | `iris/presentation/` |
| Safety | `iris/safety/` |
| Wiring/startup | `iris/runtime/` |

## 3. Write or update tests first when practical

Prefer the closest test level:

- contract tests for types
- cognitive tests for steps
- feature tests for feature definition behavior
- runtime tests for end-to-end turn flow
- architecture tests for boundaries

## 4. Implement narrowly

- Keep changes local.
- Reuse existing contracts.
- Use constructor injection.
- Add typed result classes instead of dictionaries.
- Do not add compatibility shims unless the task explicitly requests a migration path with removal criteria and tests.

### Suppression escape hatches

- Do not add `# noqa`, `# type: ignore`, `# pyright: ignore`, `typing.cast`, or `object.__setattr__`.
- Do not edit `.agents/approved-suppression-debt.toml` during normal implementation tasks.
- Do not weaken `pyproject.toml`, architecture guards, Ruff, mypy, pyright, or pytest settings.
- If suppression seems necessary, stop and report the diagnostic and proposed debt entry. Do not apply it.

## 4.1. Reject local patches that preserve bad structure

If the narrow implementation would require duplicated logic, special-case branching, or preserving a bad boundary, perform a minimal enabling refactor first.

Allowed:

- extract a shared typed helper
- move logic to the owning layer
- add a small contract type
- remove obsolete duplication

Forbidden:

- one-off `if` / `else` patches around a bad boundary
- compatibility wrappers around bad APIs
- copying logic into another layer
- bypassing tests because the change is small

## 5. Update docs only if behavior or architecture changed

Relevant docs:

- `README.md`
- `docs/architecture.md`
- `docs/rules.md`
- `docs/tests.md`
- `.agents/rules/*.md`

## 5.1. Runtime-sensitive task rule

If the task touches runtime service, observation integration, event reaction, observation routing, ingress trust, proactive behavior, or external side effects:

1. Read `.agents/rules/runtime-boundary.md`.
2. Identify the extension path before editing:
   - integration pipeline
   - situation context provider
   - observation router + runtime handler
   - cognitive app/cycle
   - adapter boundary
3. Do not add direct observation-type branches to `IrisRuntimeService`.
4. Add or update architecture tests when introducing a new boundary rule.
5. Add or update behavior tests when changing trust, capability, no-send, safety, or external action semantics.

## 6. Verify

Run targeted tests first while working. Before handoff or final report, run:

```bash
make ai-check
```

Use `make ai-check` to collect the full failure list for agent handoff. Use `make check` when CI-like stop-on-first-failure validation is preferred. Use `make quick` or `make ai-quick` only for iteration.

If full verification cannot run, report the exact failure reason and the narrower commands that did run.

## 7. Final report

Report in Japanese:

- 変更ファイル
- 概要
- 検証
- 残リスク

For architecture-sensitive changes, include the impact fields from `.agents/checklists/completion-report.md`.
