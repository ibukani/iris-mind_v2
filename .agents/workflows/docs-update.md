# Workflow: Documentation Update


Language policy: think/work in English when available; write the final user-facing report in Japanese; keep it compact.
Use this workflow when changing README, docs, agent rules, prompts, or checklists.

## Documentation rules

- Keep `AGENTS.md` and `CLAUDE.md` concise.
- Put detailed instructions under `.agents/`.
- Apply `.agents/rules/documentation-language.md` when choosing Japanese or English.
- Write human-facing documentation in Japanese by default.
- Agent-facing prompts, harness rules, and machine-oriented contracts may stay English when useful.
- Do not duplicate long rule text across many files.
- Update docs with code behavior when architecture changes.
- Prefer command examples that are valid for this repository.

## Required consistency checks

When editing docs, compare against:

- `README.md`
- `pyproject.toml`
- `docs/architecture.md`
- `docs/rules.md`
- `docs/tests.md`
- `.agents/rules/documentation-language.md`
- `tests/architecture/`

## Do not invent commands

Only document commands that work with this project unless explicitly marked as proposed.

Known commands:

```bash
make check
```

For documentation-only edits, run the smallest relevant check and state why full verification was not required. If command documentation changed, run `make check` when possible.

## Verification

For docs-only changes, at minimum inspect rendered Markdown mentally for broken links and stale paths. If commands or architecture claims changed, run the relevant tests or report why they were not run.
