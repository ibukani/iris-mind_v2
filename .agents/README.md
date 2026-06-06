# Iris Agent Harness

This directory is the repository-level harness for AI coding agents.

It exists to make agent work repeatable by supplying:

- stable project rules
- task-specific workflows
- completion checklists
- reusable prompts
- token-saving prompt policy embedded in `AGENTS.md`
- documentation language policy
- on-demand skills

Root entry files:

- `AGENTS.md` is the shared entry point for Codex, OpenCode, and other agents that read AGENTS files.
- `CLAUDE.md` is the Claude Code entry point.

## Directory map

```text
.agents/
├── rules/       # Stable architecture and implementation rules
├── workflows/   # Task contracts for implementation, refactor, bugfix, review, docs
├── checklists/  # Pre-change, pre-commit, done, and review checks
├── prompts/     # Copyable prompts for Codex, OpenCode, Claude Code
└── skills/      # On-demand reusable skills
```

## How to use this harness

1. Start from `AGENTS.md` or `CLAUDE.md`.
2. Read the relevant rule files.
3. Apply the Primitive Prompt Mode and token/language policy embedded in `AGENTS.md`.
4. Apply `.agents/rules/documentation-language.md` for documentation language choice.
5. Pick one workflow from `.agents/workflows/`.
6. Use `.agents/checklists/pre-change.md` before editing.
7. Use `.agents/checklists/done.md` before reporting completion.

## Standard verification

Use one canonical command before reporting completion:

```bash
make check
```

`make verify` is an alias. Both call `scripts/verify.py` and run strict Ruff, format check, mypy, pyright, architecture tests, and the full test suite with coverage gate. Use `make quick` for iteration only.

## Source of truth

The project architecture is enforced by tests under `tests/architecture/`.

When documentation and tests disagree, do not guess. Inspect implementation and architecture tests, then update documentation and tests together if the architecture intentionally changed.

## Existing flat files

Older flat files may exist directly under `.agents/`, such as `.agents/architecture.md`, `.agents/cognitive.md`, `.agents/rules.md`, and `.agents/tests.md`.

Prefer the structured files under this directory for new agent sessions. Keep the flat files only as compatibility references unless a separate migration task removes them.

## Token-saving mode

Primitive Prompt Mode and the token/language policy are embedded directly in `AGENTS.md` so every agent session loads them. Do not move those mandatory rules into optional prompt files.

## Documentation language

Use `.agents/rules/documentation-language.md` when changing README, docs, design notes, review summaries, implementation explanations, PR text, prompts, or harness rules.

Human-facing documentation is Japanese by default. Agent-facing prompts and machine-oriented rules may stay English when useful.

## AI harness additions

Use these files for Codex/OpenCode harness work:

- `.agents/rules/ai-harness.md` — agent operating loop and handoff rules.
- `.agents/rules/verification.md` — command hierarchy and failure reporting rules.
- `.agents/workflows/test-fix.md` — strict gate repair workflow.
- `.agents/workflows/architecture.md` — architecture change workflow.
- `.agents/workflows/ai-harness.md` — instruction and verification harness maintenance workflow.
- `.agents/checklists/ai-harness.md` — checklist for instruction/command changes.
- `.agents/checklists/failure-analysis.md` — checklist for strict gate failures.

Prefer `make ai-quick` during iteration and `make ai-check` before handoff.
