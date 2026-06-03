# Workflow: Documentation Update

Use this workflow when changing README, docs, agent rules, prompts, or checklists.

## Documentation rules

- Keep `AGENTS.md` and `CLAUDE.md` concise.
- Put detailed instructions under `.agents/`.
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
- `tests/architecture/`

## Do not invent commands

Only document commands that work with this project unless explicitly marked as proposed.

Known commands:

```bash
uv run python main.py --text "hello"
uv run python -m iris.runtime.cli --text "hello"
uv run ruff check .
uv run ruff format --check .
uv run mypy iris/core iris/contracts iris/cognitive iris/presentation iris/safety iris/features iris/adapters iris/runtime
uv run pytest tests/ -q
uv run pytest tests/architecture -q
```

## Verification

For docs-only changes, at minimum inspect rendered Markdown mentally for broken links and stale paths. If commands or architecture claims changed, run the relevant tests or report why they were not run.
