# Workflow: AI Harness Maintenance

Use when changing agent instructions, Makefile verification targets, Codex/OpenCode integration, or scripts under `scripts/` used by agents.

## Read First

- `AGENTS.md`
- `.agents/README.md`
- `.agents/rules/ai-harness.md`
- `.agents/rules/instruction-design.md`
- `.agents/rules/verification.md`
- `.agents/checklists/ai-harness.md`
- `Makefile`
- `scripts/verify.py`
- `opencode.json` if changed

## Process

1. Keep one canonical full gate: `make check`.
2. Keep AI convenience gates as wrappers, not divergent policy.
3. Reference paths instead of duplicating long rules.
4. Keep command names stable once introduced.
5. Validate JSON/TOML/YAML syntax for changed config files.
6. Run `make ai-context` after instruction changes when possible.
7. Run `make ai-quick` or stronger, or report why it could not run.
8. Check official OpenAI Codex sources when product-specific behavior or instruction-surface guidance changes.

## Design Constraints

- Instructions stay compact and task-oriented.
- `AGENTS.md` remains the shared source of truth.
- Tool-specific config may add convenience, not contradictory policy.
- Commands fail loudly rather than silently degrading.
- Handoff text preserves facts, commands, and failures, not hidden reasoning.
