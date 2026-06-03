# AGENTS.md

This repository is **Iris**, an AI companion cognitive runtime MVP. Treat this file as the entry point for Codex, OpenCode, and other coding agents.

## Must-follow token and language policy

These rules are embedded here, not delegated to another file, because they must be loaded at the start of every agent session.

### Primitive Prompt Mode

When writing or compressing task prompts for coding agents, use **Primitive Prompt Mode**: short English fragments, strong nouns/verbs, no filler.

Preferred task shape:

```text
Goal: add X.
Read: AGENTS.md, .agents/rules/architecture.md, .agents/rules/boundaries.md.
Scope: file A, file B if needed.
Do not: service locator, global registry, dict boundary, compatibility shim, safety/presenter bypass.
Keep: typed contracts, FeatureDefinition extension, no-action semantics.
Test: targeted pytest; pytest tests/architecture -q; ruff check; format check.
Report: Japanese, compact.
```

Avoid:

- long background paragraphs
- repeated architecture explanations
- politeness filler
- motivational wording
- speculative alternatives not needed for the task
- copying whole files into the prompt when paths are enough

### Language split

- Internal task analysis, scratch planning, and hidden reasoning when available: **English**.
- User-facing final responses and completion reports: **Japanese**.
- Code, identifiers, docstrings, and comments: follow the existing repository style.
- Commit messages: follow project convention if one exists; otherwise concise English is acceptable.

Do not reveal hidden reasoning. In Japanese final reports, summarize only decisions, changed files, verification, and risks.

### Token-saving hierarchy

When context is limited, prefer this order:

1. Task goal and acceptance criteria.
2. Relevant file paths.
3. Architecture rules that can fail the task.
4. Verification commands.
5. Extra background only if it changes the implementation.

### Compact Japanese report format

Use this shape unless the user asks otherwise:

```text
変更ファイル
- ...

概要
- ...

検証
- ...

残リスク
- ...
```

If nothing remains, write `なし` under `残リスク`.

## Required context

Before changing code, read the relevant files in this order:

1. `AGENTS.md` fully, including the token and language policy above
2. `.agents/README.md`
3. `.agents/rules/architecture.md`
4. `.agents/rules/boundaries.md`
5. `.agents/rules/cognitive-cycle.md`
6. `.agents/rules/testing.md`
7. The workflow under `.agents/workflows/` that matches the task

If a task touches existing behavior, also inspect the matching tests under `tests/` before editing.

## Project purpose

Iris is not a generic chatbot wrapper. It is a cognitive runtime for an AI companion with typed observation input, cognitive processing, safety/presentation boundaries, and app-agnostic action plans.

The target flow is:

```text
Observation
→ CognitiveCycle
→ WorkspaceFrame
→ ActionPlan
→ ActionSafetyGate
→ Presenter
→ PresentedOutput
→ OutputSafetyGate
→ AppAction / external app boundary
```

## Non-negotiable rules

- Preserve layer boundaries between `contracts`, `core`, `cognitive`, `features`, `adapters`, `presentation`, `safety`, and `runtime`.
- `cognitive/` must not import from `adapters/`, `runtime/`, or `features/`.
- `contracts/` must not import from `cognitive/`, `adapters/`, or `runtime/`.
- `features/` must extend through `FeatureDefinition`; do not patch cognitive internals directly.
- `CognitiveCycle` is a pipeline coordinator, not a God Service.
- `PipelineStep` implementations return typed results and do not mutate `WorkspaceFrame` directly.
- Do not introduce service locators, global mutable registries, compatibility shims, or temporary wrappers.
- Do not use `dict[str, Any]` or `dict[str, object]` at internal boundaries.
- Do not add new `action: str` dispatcher branches.
- Preserve canonical no-action semantics: no LLM call, no generated text, no external send.

## Workflows

Use these task contracts:

- Feature work: `.agents/workflows/implement.md`
- Bug fixes: `.agents/workflows/bugfix.md`
- Refactoring: `.agents/workflows/refactor.md`
- Reviews: `.agents/workflows/review.md`
- Documentation updates: `.agents/workflows/docs-update.md`

## Verification

At minimum, run the smallest relevant verification first, then the broader checks before finishing.

Common commands:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
uv run pytest tests/architecture -q
uv run pytest tests/ -q
```

If the environment cannot run a command, report the command, the failure reason, and what you verified instead.

## Completion report

When done, report in Japanese:

1. Files changed
2. Behavioral or architectural impact
3. Tests/checks run
4. Any commands that could not be run
5. Remaining risks or follow-up work
