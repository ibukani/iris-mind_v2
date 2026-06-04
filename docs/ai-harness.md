# AI Harness Guide

This repository uses strict quality gates plus repository-level agent instructions to make Codex, OpenCode, and other coding agents easier to steer and audit.

## Shared source of truth

- `AGENTS.md` is the root instruction file.
- `.agents/rules/` contains reusable rules.
- `.agents/workflows/` contains task-specific operating procedures.
- `Makefile` and `scripts/verify.py` are the deterministic verification entry points.
- `opencode.json` maps OpenCode slash commands to this repository's harness commands.

## Command hierarchy

```bash
make ai-test-target TARGET=tests/path_or_file.py
make ai-arch
make ai-quick
make ai-check
make check
```

Use `make ai-test-target` while iterating on a small change. Use `make ai-quick` before broader edits are reported. Use `make ai-check` before handoff when possible. Use `make check` as the canonical full gate.

## Codex usage

Start Codex from the repository root so it loads `AGENTS.md`. For specialized tasks, include the workflow path in the prompt, for example:

```text
Goal: fix pyright failures in runtime wiring.
Read: AGENTS.md, .agents/workflows/test-fix.md, .agents/rules/typing.md.
Test: make ai-quick, then make ai-check if feasible.
Report: Japanese.
```

## OpenCode usage

OpenCode reads project instructions from `AGENTS.md`. The checked-in `opencode.json` also references the AI harness rules and provides commands such as `/ai-quick`, `/ai-check`, `/ai-arch`, `/ai-report`, and `/ai-review`.

## Failure policy

A failed gate is useful signal. Do not hide it by weakening configuration, skipping tests, adding broad ignores, or replacing typed boundaries with `Any`.

When a command fails, report the exact command, the first failing file or test, and the next smallest fix.
