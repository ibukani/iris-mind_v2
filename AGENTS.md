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
Do not: service locator, global registry, dict boundary, compatibility shim unless explicit migration task, safety/presenter bypass.
Keep: typed contracts, FeatureDefinition extension, no-action semantics.
Test: targeted pytest while working; make check before final report.
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
6. `.agents/rules/anti-patterns.md`
7. `.agents/rules/typing.md`
8. `.agents/rules/testing.md`
9. The workflow under `.agents/workflows/` that matches the task

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
- `contracts/` must not import from `cognitive/`, `adapters/`, or `runtime`.
- `features/` must extend through `FeatureDefinition`; do not patch cognitive internals directly.
- `CognitiveCycle` is a pipeline coordinator, not a God Service.
- `PipelineStep` implementations return typed results and do not mutate `WorkspaceFrame` directly.
- Do not introduce service locators, global mutable registries, temporary wrappers, or compatibility shims unless the task explicitly requests a migration path with removal criteria and tests.
- Do not use `dict[str, Any]` or `dict[str, object]` at internal boundaries.
- Do not add new `action: str` dispatcher branches.
- Preserve canonical no-action semantics: no LLM call, no generated text, no external send.

## Workflows

Use these task contracts:

- New feature slices under `iris/features/<name>/`: `.agents/workflows/add-feature.md`
- General behavior implementation: `.agents/workflows/implement.md`
- Bug fixes: `.agents/workflows/bugfix.md`
- Refactoring: `.agents/workflows/refactor.md`
- Reviews: `.agents/workflows/review.md`
- Documentation updates: `.agents/workflows/docs-update.md`
- Strict gate repairs: `.agents/workflows/test-fix.md`
- Architecture boundary changes: `.agents/workflows/architecture.md`
- AI harness maintenance: `.agents/workflows/ai-harness.md`

## AI Harness Operation

Use repository commands instead of ad-hoc tool behavior. `AGENTS.md` remains the shared source of truth for Codex, OpenCode, Claude Code, and other agents. Tool-specific config may add convenience commands, but must not contradict these rules.

Additional mandatory rules for harness work:

- `.agents/rules/ai-harness.md`
- `.agents/rules/verification.md`

AI-oriented command aliases:

```bash
make ai-context
make ai-test-target TARGET=tests/path_or_file.py
make ai-arch
make ai-quick
make ai-check
make ai-report
```

Use `make ai-context` to show the active harness paths. Use `make ai-report` to generate the Japanese completion report skeleton.

## Strict AI Coding Quality Gate

Do not weaken lint, type, pyright, pytest, or coverage settings to make work pass. This repository prioritizes strict AI-coding feedback over short-term convenience. Fix code and tests instead of relaxing configuration.

The strictness policy is scoped, not uniform:

- Ruff uses `select = ["ALL"]`; only formatter conflicts and explicitly documented context exceptions are ignored.
- mypy runs strict checks across `iris`, `tests`, `scripts`, and `main.py`.
- mypy maximum `Any` restrictions apply to core architecture code: `contracts`, `core`, `cognitive`, `features`, `presentation`, `safety`, and `runtime`.
- `adapters` may tolerate incomplete external-library typing at the boundary, but must not leak untyped values into internal contracts.
- `tests` and `scripts` stay typed, but are not held to the same decorator/third-party-helper strictness as production architecture code.
- pyright runs in strict mode across production code and in standard mode across tests/scripts.
- pytest treats config, markers, xfail, and warnings strictly.
- Coverage is part of the full gate and fails below 90%.

## Suppression Policy

Do not silence quality gates just to make checks pass.

Suppressions are allowed only when they are local, rule-specific, and documented with a reason. Prefer fixing the design, adding a typed boundary, or improving tests before adding a suppression.

Allowed examples:

```python
import subprocess  # noqa: S404 -- subprocess is isolated in the audited process runner boundary
value = external_api.value  # type: ignore[attr-defined] -- third-party package lacks complete stubs
result = client.call()  # pyright: ignore[reportUnknownMemberType] -- external API returns dynamically typed object
```

## Verification

Use the repository verification entry point before reporting completion.

```bash
make check
```

`make verify` is an alias for `make check`. Both run `scripts/verify.py`, which executes:

1. `uv run ruff check .`
2. `uv run ruff format --check .`
3. `uv run mypy iris tests scripts main.py`
4. `uv run pyright .`
5. `uv run pytest tests/architecture -q`
6. `uv run pytest tests/ --cov=iris --cov-branch --cov-report=term-missing:skip-covered --cov-report=html --cov-fail-under=90`

Use `make quick` while iterating when the full suite is too broad for the current edit. It still runs lint, format, mypy, pyright, and architecture checks.

Use `make ai-quick` and `make ai-check` for agent sessions that should keep running after the first failure and produce a fuller failure list. These are diagnostics wrappers around the same strict checks, not weaker gates.

If the environment cannot run a command, report the command, the failure reason, and what you verified instead.

## Completion report

When done, report in Japanese:

1. Files changed
2. Behavioral or architectural impact
3. Tests/checks run
4. Any commands that could not be run
5. Remaining risks or follow-up work


<!-- headroom:rtk-instructions -->
# RTK (Rust Token Killer) - Token-Optimized Commands

When running shell commands, **always prefix with `rtk`**. This reduces context
usage by 60-90% with zero behavior change. If rtk has no filter for a command,
it passes through unchanged — so it is always safe to use.

## Key Commands
```bash
# Git (59-80% savings)
rtk git status          rtk git diff            rtk git log

# Files & Search (60-75% savings)
rtk ls <path>           rtk read <file>         rtk grep <pattern>
rtk find <pattern>      rtk diff <file>

# Test (90-99% savings) — shows failures only
rtk pytest tests/       rtk cargo test          rtk test <cmd>

# Build & Lint (80-90% savings) — shows errors only
rtk tsc                 rtk lint                rtk cargo build
rtk prettier --check    rtk mypy                rtk ruff check

# Analysis (70-90% savings)
rtk err <cmd>           rtk log <file>          rtk json <file>
rtk summary <cmd>       rtk deps                rtk env

# GitHub (26-87% savings)
rtk gh pr view <n>      rtk gh run list         rtk gh issue list

# Infrastructure (85% savings)
rtk docker ps           rtk kubectl get         rtk docker logs <c>

# Package managers (70-90% savings)
rtk pip list            rtk pnpm install        rtk npm run <script>
```

## Rules
- In command chains, prefix each segment: `rtk git add . && rtk git commit -m "msg"`
- For debugging, use raw command without rtk prefix
- `rtk proxy <cmd>` runs command without filtering but tracks usage
<!-- /headroom:rtk-instructions -->
