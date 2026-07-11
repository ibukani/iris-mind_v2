# CLAUDE.md

Claude Code entry point for Iris.

Read `AGENTS.md` fully, then follow its task routing into `.agents/`. `AGENTS.md` is the shared source of truth; this file adds no separate architecture or verification policy.

Before editing:

1. Read `.agents/README.md`.
2. Read the matching `.agents/workflows/` file.
3. Read only the task-relevant rules, checklist, and skill routed by `AGENTS.md`.
4. Inspect existing code and tests.

Use `.agents/checklists/done.md` before handoff. Run `make check` when possible; report exact failures and unrun commands.
