# Workflow: AI Harness Maintenance

Use this workflow when changing agent instructions, Makefile verification targets, OpenCode/Codex integration, or scripts under `scripts/` used by agents.

## Read first

- `AGENTS.md`
- `.agents/rules/ai-harness.md`
- `.agents/rules/verification.md`
- `.agents/checklists/ai-harness.md`
- `Makefile`
- `scripts/verify.py`
- `opencode.json` if present

## Process

1. Keep one canonical full gate: `make check`.
2. Keep AI convenience gates as wrappers, not divergent policy.
3. Do not duplicate long rules across many files. Reference paths instead.
4. Keep command names stable once introduced.
5. Validate JSON/TOML/YAML syntax for changed configuration files.
6. Run `make ai-context` after instruction changes when possible.
7. Run `make ai-quick` or report why it could not run.

## Design constraints

- Instructions should be compact and task-oriented.
- Tool-specific config may exist, but repository-level `AGENTS.md` remains the shared source of truth.
- Commands should fail loudly rather than silently degrading.
- Handoff text should preserve facts, commands, and failures, not hidden reasoning.
