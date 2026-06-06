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

Core rule:

```text
Respond terse like smart caveman. All technical substance stay. Only fluff die.
```

Compress English by default:

- Drop pleasantries: `Sure`, `I'd be happy to`, `Thanks for`, `Great question`.
- Drop filler: `just`, `really`, `basically`, `actually`, `quite`, `very` unless meaning changes.
- Drop hedging when evidence is enough: `might`, `perhaps`, `it seems`, `I think`.
- Drop articles and helper words when clear: `the`, `a`, `an`, `that`, `in order to`.
- Prefer direct technical fragments, bullets, `path:line`, commands, and code blocks.
- Preserve code, identifiers, commands, paths, URLs, stack traces, quoted errors, API names, and type names exactly.

Examples:

```text
Before: Sure, I'd be happy to help. The issue is likely caused by the authentication middleware where the token expiry check uses `<` instead of `<=`.
After: Bug: auth middleware token expiry check uses `<`, need `<=`.

Before: In order to fix this issue, you should update the configuration file and then run the full test suite.
After: Fix: update config. Verify: run full test suite.
```

### Genshijin Output Compression Mode

Use for Japanese agent-visible replies, progress notes, handoffs, and completion reports.

Core rule:

```text
賢い原始人のように短く返す。技術情報は残す。無駄だけ消す。
```

Compress Japanese by default:

- Delete greetings, thanks, apologies, cushion words, motivational wording, and business-politeness padding.
- Convert polite endings to compact technical Japanese where natural.
- Compress redundant phrases: `することができます` → `可能` / `できる`, `ということになります` → `になる`.
- Delete obvious particles when readable: `認証ミドルウェアのトークンの有効期限チェック` → `認証middleware token期限check`.
- Prefer noun/verb fragments, dense bullets, checklists, `path:line`, and command blocks.
- Omit obvious background, generic tutorials, and repeated architecture summaries.

Examples:

```text
Before: 修正することができます。
After: 修正可能。

Before: 認証ミドルウェアにおけるトークンの有効期限チェックの部分に原因がある可能性があります。
After: 原因: 認証middleware token期限check。
```

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

Before changing code, read the relevant files in this order:

1. `AGENTS.md` fully, including the token, language, and output compression policy above
2. `.agents/README.md`
3. `.agents/rules/documentation-language.md`
4. `.agents/rules/architecture.md`
5. `.agents/rules/boundaries.md`
6. `.agents/rules/cognitive-cycle.md`
7. `.agents/rules/anti-patterns.md`
8. `.agents/rules/typing.md`
9. `.agents/rules/testing.md`
10. The workflow under `.agents/workflows/` that matches the task

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
# RTK Command Filtering for Iris

RTK is an optional token-saving command filter for local agent sessions. It is not an Iris dependency, not part of CI, and not the source of truth for verification. Prefer repository commands first; wrap them with `rtk` only when the tool is available and filtered output is useful.

## Canonical Iris commands

Use these commands as the canonical project interface:

```bash
make ai-context
make ai-test-target TARGET=tests/path_or_file.py
make ai-arch
make ai-quick
make ai-check
make check
make verify
make ai-report
```

`make check` and `make verify` remain the completion gates. `make ai-quick` and `make ai-check` are diagnostic wrappers, not weaker alternatives.

## Safe RTK usage

When logs are too large, RTK may wrap Iris commands without changing the command contract:

```bash
rtk make ai-context
rtk make ai-test-target TARGET=tests/path_or_file.py
rtk make ai-quick
rtk make ai-check
rtk make check
```

For narrow debugging, RTK may also wrap the exact `uv` commands already documented in this file:

```bash
rtk uv run ruff check .
rtk uv run ruff format --check .
rtk uv run mypy iris tests scripts main.py
rtk uv run pyright .
rtk uv run pytest tests/architecture -q
rtk uv run pytest tests/path_or_file.py -q
```

## Rules

- Do not require RTK in project setup, CI, Makefile targets, docs, or tests.
- Do not replace canonical `make` / `uv` commands with RTK-only commands.
- Do not introduce examples for unrelated ecosystems such as Cargo, npm, Docker, Kubernetes, or TypeScript unless the repository actually adds those tools.
- Use raw commands when exact output, full logs, or debugging context matters.
- In completion reports, write the command that was actually run and note when RTK filtered output.
- If RTK is unavailable, continue with the raw `make` / `uv` command and report normally.
<!-- /headroom:rtk-instructions -->
