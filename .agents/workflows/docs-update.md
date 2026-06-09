# Workflow: Documentation Update

Use when changing README, docs, agent rules, prompts, checklists, comments, or docstrings.

Language policy: work in English when useful; user-facing final report in Japanese; keep it compact.

## Rules

- Keep `AGENTS.md` and `CLAUDE.md` concise.
- Put detailed durable guidance under `.agents/` or `docs/`.
- Apply `.agents/rules/documentation-language.md`.
- Human-facing docs, docstrings, and explanatory comments are Japanese by default.
- Agent-facing prompts, harness rules, and machine-oriented contracts may use English when useful.
- Do not duplicate long rules across many files.
- Document only commands that work in this repository unless explicitly marked proposed.

## Consistency Checks

Compare changed docs against relevant sources:

- `README.md`
- `pyproject.toml`
- `Makefile`
- `.agents/README.md`
- `.agents/rules/documentation-language.md`
- `.agents/rules/verification.md`
- `tests/architecture/`
- surrounding code style for comments/docstrings

Preserve identifiers, protocol names, commands, paths, and external API names exactly.

## Verification

For docs-only changes, at minimum inspect Markdown structure for broken links, stale paths, bad fences, and stale commands.

If command, architecture, or harness behavior claims changed, run the relevant make target or report why it could not run.
