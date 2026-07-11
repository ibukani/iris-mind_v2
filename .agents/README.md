# Iris Agent Harness

Repository-level harness for Codex, OpenCode, Claude Code, and other coding agents.

Purpose:

- keep durable project rules
- route tasks to the right workflow
- keep verification commands stable
- keep token/language policy discoverable
- provide skills and checklists for repeated review/repair work

Root entry files:

- `AGENTS.md`: shared entry point for agents that read AGENTS files.
- `CLAUDE.md`: thin Claude Code entry point; delegates all common rules to `AGENTS.md`.

## Directory Map

```text
.agents/
├── rules/       stable architecture, language, verification, output rules
├── workflows/   task contracts for implementation, docs, review, repair
├── checklists/  pre-change, done, harness, failure-analysis checks
├── prompts/     copyable agent prompts
└── skills/      on-demand deep review and repair skills
```

## Task Routing

Start with `AGENTS.md`, then read only task-relevant harness files.

- Any task: matching `.agents/workflows/*.md`.
- Documentation, comments, docstrings, prompts, or reports: `.agents/rules/documentation-language.md`.
- Behavior, runtime wiring, architecture, or tests: architecture, boundaries, cognitive-cycle, anti-patterns, typing, and testing rules.
- AI harness, Makefile, agent rules, prompts, or verification scripts: `.agents/rules/ai-harness.md` and `.agents/rules/verification.md`.
- Instruction structure, ownership, or prompt design: `.agents/rules/instruction-design.md`.
- Output compression examples: `.agents/rules/output-compression.md`.
- Deep review/repair: matching `.agents/skills/*/SKILL.md`.

## Verification

Canonical full gate:

```bash
make check
```

Use `make quick` or `make ai-quick` while iterating. Use `make ai-check` before handoff when a keep-going failure list is useful. Do not weaken strict gates.

## Source Of Truth

Architecture is enforced by `tests/architecture/`. When docs and tests disagree, inspect implementation and architecture tests before changing either.

Detailed command policy lives in `.agents/rules/verification.md`. Quality strictness lives in `pyproject.toml` plus `.agents/rules/testing.md`.

## Language

Human-facing documentation, docstrings, explanatory comments, reports, and PR text are Japanese by default.

Agent-facing prompts, harness rules, and machine-oriented contracts may use English when it improves precision.

## Maintenance

Keep one owner for each rule. `AGENTS.md` routes and states invariants; detailed policy belongs in `.agents/rules/`; task sequences belong in workflows; repeatable specialist procedures belong in skills. Validate inventory with `make ai-context`.
