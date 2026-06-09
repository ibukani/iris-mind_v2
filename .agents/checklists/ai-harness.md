# AI Harness Checklist

Use before reporting changes to agent instructions, harness rules, Makefile targets, or verification scripts.

- `AGENTS.md` still names `make check` as the canonical full gate.
- New instructions do not contradict architecture or boundary rules.
- No lint, type, pyright, pytest, or coverage gate was weakened.
- Command names match `make help`.
- JSON/TOML/YAML syntax is valid for changed config files.
- New scripts avoid hidden network access and background work.
- Failure handling is explicit.
- `make ai-context` works, or the failure is reported.
- `make ai-quick` or stronger was run, or the failure is reported.
- Post-task retrospective includes reusable lessons and AGENTS.md update candidates when useful.
