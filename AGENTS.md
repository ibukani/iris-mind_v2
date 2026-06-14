# AGENTS.md

This repository is **Iris**, an AI companion cognitive runtime MVP. Treat this file as the entry point for Codex, OpenCode, and other coding agents.

## Must-follow token, language, and output compression policy

These rules are embedded here, not delegated to another file, because they must be loaded at the start of every agent session.

<!-- /headroom:rtk-instructions -->
### Headroom CCR / retrieval policy

When context is compressed, summarized, truncated, or marked as retrievable, do not guess missing details.

Use Headroom retrieval tool when exact original content affects correctness.

Prefer retrieval for:

- test failures
- stack traces
- command outputs
- diffs
- file contents
- search results
- long logs
- architecture rules
- API contracts
- verification output

Do not retrieve for obvious background, already-visible code, or low-risk summaries.

If retrieval tool is unavailable, say exact source was unavailable and proceed with visible context only.
<!-- /headroom:rtk-instructions -->

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

### Caveman Output Compression Mode

Use for English agent-visible replies, progress notes, handoffs, and completion reports.

Core rule: terse English, all technical substance, no fluff.

Drop pleasantries, filler, unsupported hedging, and generic background. Keep identifiers, commands, paths, URLs, errors, stack traces, and API names exact.

Examples and edge cases: `.agents/rules/output-compression.md`.

### Genshijin Output Compression Mode

Use for Japanese agent-visible replies, progress notes, handoffs, and completion reports.

Core rule: 賢い原始人のように短く返す。技術情報は残す。無駄だけ消す。

削る: 挨拶、謝意、クッション語、冗長な敬語、motivational wording、既知背景。残す: identifiers, commands, paths, URLs, errors, stack traces, API names。

Examples and edge cases: `.agents/rules/output-compression.md`.

### Mode selection and safety valve

- English natural language: use Caveman Mode.
- Japanese natural language: use Genshijin Mode.
- Mixed Japanese/English: compress each natural-language segment with the matching mode; keep code and identifiers exact.
- User asks `詳しく`, `FULL`, `網羅`, `比較`, or similar: expand enough for the request, still avoid filler.
- Destructive operations, data loss risk, security/privacy issues, irreversible commands, migrations, and compliance warnings: use normal precise language over maximum compression.
- Reviews, verification failures, and residual risks must keep evidence, severity, and reproduction steps. Do not over-compress findings.
- This policy controls coding-agent communication only. It must not change Iris runtime personality, user-facing companion dialogue, safety gates, prompts, or product behavior.

### Language split

- Internal task analysis, scratch planning, and hidden reasoning when available: **English**.
- User-facing final responses and completion reports: **Japanese**.
- Human-facing repository documentation is **Japanese by default**. This includes `README.md`, `docs/`, design notes, review summaries, implementation explanations, and PR text written for human readers.
- AI/coding-agent instructions, machine-oriented prompts, harness rules, and implementation contracts may be **English** when it improves precision or tool compatibility.
- Code identifiers, public API names, protocol fields, commands, and paths must keep their exact existing spelling.
- New or updated docstrings and explanatory comments are **Japanese by default** when they explain behavior, intent, rationale, architecture, or caveats for human readers.
- Short mechanical comments, generated code, external API/protocol wording, and agent-only implementation contracts may stay **English** when it improves precision or matches surrounding code.
- Commit messages: follow project convention if one exists; otherwise concise English is acceptable.

Do not reveal hidden reasoning. In Japanese final reports, summarize only decisions, changed files, verification, and risks.

See `.agents/rules/documentation-language.md` for detailed documentation language rules.

### Token-saving hierarchy

When context is limited, prefer this order:

1. Task goal and acceptance criteria.
2. Relevant file paths.
3. Architecture rules that can fail the task.
4. Verification commands.
5. Extra background only if it changes the implementation.

<!-- /headroom:rtk-instructions -->
### Prefix stability policy

Keep stable instructions before dynamic task context.

Stable prefix first:

1. Repository identity.
2. Architecture rules.
3. Safety rules.
4. Verification rules.
5. Output format.

Dynamic context later:

- current branch
- current task
- date/time
- recent failures
- latest diff
- temporary notes

Do not place timestamps, branch names, or session-specific notes near the top of this file.
<!-- /headroom:rtk-instructions -->

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

Always read:

1. `AGENTS.md` fully, including token, language, and output compression policy.
2. `.agents/README.md`.
3. The matching workflow under `.agents/workflows/`.
4. Any named or clearly matching skill under `.agents/skills/`.

Read extra rules by task:

- Documentation, comments, docstrings, prompts, or reports: `.agents/rules/documentation-language.md`.
- Behavior, runtime wiring, architecture, or tests: `.agents/rules/architecture.md`, `.agents/rules/boundaries.md`, `.agents/rules/cognitive-cycle.md`, `.agents/rules/anti-patterns.md`, `.agents/rules/typing.md`, `.agents/rules/testing.md`.
- Runtime service, observation integration, event reaction, observation routing, ingress trust, runtime side effects, or proactive runtime behavior: `.agents/rules/runtime-boundary.md`.
- AI harness, Makefile, agent rules, prompts, or verification scripts: `.agents/rules/ai-harness.md`, `.agents/rules/verification.md`.
- Architecture-sensitive implementation or review: `.agents/checklists/architecture-review.md`.

If a task touches existing behavior, inspect matching tests under `tests/` before editing.

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
- Keep runtime boundary behavior split by responsibility: integration, context assembly, routing, reaction planning, presentation, safety filtering, and cognitive processing must not collapse into one service.
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

Stable policy:

- Ruff stays `select = ["ALL"]` except documented project-wide ignores.
- mypy stays strict across `iris`, `tests`, `scripts`, and `main.py`.
- Core architecture code keeps maximum `Any` restrictions.
- Adapters may handle incomplete external-library typing only at provider boundaries.
- pyright, pytest strictness, and 90% coverage gate remain enabled.
- Source of truth: `pyproject.toml`, `.agents/rules/testing.md`, `.agents/rules/verification.md`.

## Suppression Policy

Do not silence quality gates just to make checks pass.

Suppression escape hatches (`# noqa`, `# type: ignore`, `# pyright: ignore`,
`typing.cast`, `object.__setattr__`) are forbidden by default.

Normal implementation tasks must not add suppressions. Coding agents must not edit
`.agents/approved-suppression-debt.toml` during normal tasks.

If a checker failure seems impossible to fix without suppression, stop and report
the diagnostic and proposed debt entry for human review. Do not apply the
suppression or registry entry.

Protected architecture layers (`iris/contracts/`, `iris/core/`, `iris/cognitive/`,
`iris/features/`, `iris/presentation/`, `iris/safety/`, `iris/runtime/`) must
never contain escape hatches.

Exception zones (`iris/adapters/`, `tests/`, `scripts/`) may only contain escape
hatches when registered in `.agents/approved-suppression-debt.toml`.

Bare `# noqa`, bare `# type: ignore`, and bare `# pyright: ignore` are always
forbidden.

### Registry update approval

The registry files (`.agents/approved-suppression-debt.toml` and its
`.agents/approved-suppression-debt.toml.snap`) are normally read-only for
coding agents. Adding or extending entries is a human-approved task.

The merge-base guard `scripts/check_suppression_debt_changes.py` blocks
silent registry changes. The guard is wired into `make static-arch`,
`make quick`, `make check`, and the `make ai-*` family. It computes the
diff against `origin/main` (or `main`) and fails if either registry file
appears in the change set without the approval signal.

The approval signal is a single environment variable:

```bash
export IRIS_APPROVE_SUPPRESSION_DEBT_UPDATE=1
make check
```

Only a human reviewer exports this variable. Coding agents must not set
it under any circumstance. The guard intentionally ignores commit
messages, branch names, and file-level markers to keep the signal
impossible to trigger by accident.

When the guard fails, revert accidental registry changes or escalate to
the human reviewer for approval. See
`.agents/suppression-debt-remediation.md` for the per-entry cleanup plan
and `.agents/rules/typing.md` for the suppression policy.

Architecture guards mechanically enforce this policy:
- `test_suppression_debt_registry.py` — validates entry shape, expiry, and
  exact line references inside the registry.
- `test_suppression_debt_registry_is_frozen.py` — guards the registry
  snapshot hash from silent regeneration.
- `test_no_unapproved_suppressions.py` — prevents escape hatches in
  exception zones that are not registered.
- `test_no_cast_in_protected_layers.py` — prevents `typing.cast` and
  `object.__setattr__` from leaking into protected layers.
- `scripts/check_suppression_debt_changes.py` — git merge-base guard
  that blocks silent registry growth.

## Verification

Use the repository verification entry point before reporting completion.

```bash
make check
```

`make verify` is an alias. Both run `scripts/verify.py`: Ruff check, Ruff format check, mypy, pyright, architecture tests, full pytest with branch coverage and 90% threshold.

Use `make quick` while iterating: lint, format, mypy, pyright, architecture tests.

Use `make ai-quick` and `make ai-check` when an agent needs keep-going diagnostics. They are wrappers, not weaker gates.

If the environment cannot run a command, report the command, the failure reason, and what you verified instead.

## Completion report

When done, report in Japanese:

1. Files changed
2. Behavioral or architectural impact
3. Tests/checks run and results
4. Commands that could not run
5. Remaining risks or follow-up work

## Post-task retrospective

After non-trivial tasks, include compact lessons in the final report or handoff:

- What changed.
- Problems encountered.
- Root causes.
- How issues were resolved.
- Validation commands and results.
- Reusable lessons for future agents.
- AGENTS.md update candidates, if any.

Update `AGENTS.md` only for durable guidance:

- recurring mistakes seen across tasks
- stable project-specific conventions
- repeated review feedback
- routing guidance that prevents unnecessary file reading
- validation commands that agents should run often

Do not add:

- one-off errors or temporary task notes
- long logs, stack traces, or troubleshooting transcripts
- stale implementation details likely to drift
- vague preferences without project-specific action
- content better suited for `docs/troubleshooting.md`, architecture docs, or `.agents/`

If `AGENTS.md` grows too large, move detailed guidance to `.agents/` or `docs/` and link the path here.


<!-- headroom:rtk-instructions -->
# RTK Command Filtering for Iris

RTK is optional local output filtering. It is not an Iris dependency, CI contract, or source of truth. Canonical commands remain the `make` / `uv` commands above.

Use RTK only as a wrapper when filtered output helps:

```bash
rtk make ai-context
rtk make ai-test-target TARGET=tests/path_or_file.py
rtk make ai-quick
rtk make ai-check
rtk make check
```

Rules:

- Do not require RTK in setup, CI, Makefiles, docs, or tests.
- Do not document RTK-only commands as canonical.
- Use raw commands when exact output or full logs matter.
- Report the command actually run and note when RTK filtered output.
- If RTK is unavailable, run the raw `make` / `uv` command.
<!-- /headroom:rtk-instructions -->
