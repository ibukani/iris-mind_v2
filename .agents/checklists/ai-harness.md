# Checklist: AI Harness Change

Use before reporting changes to agent instructions or verification commands.

- [ ] `AGENTS.md` still names the canonical full gate.
- [ ] New instructions do not contradict existing architecture rules.
- [ ] No quality gate was weakened.
- [ ] OpenCode config uses valid JSON if `opencode.json` changed.
- [ ] Make targets are listed in `make help`.
- [ ] New scripts avoid hidden network access and background work.
- [ ] Failure handling is explicit.
- [ ] `make ai-context` works, or the failure is reported.
- [ ] `make ai-quick` or stronger was run, or the failure is reported.
