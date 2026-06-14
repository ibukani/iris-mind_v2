# Suppression Debt Remediation Plan

This document is the human-reviewed roadmap for retiring every entry currently
present in `.agents/approved-suppression-debt.toml`.

All current entries expire on `2026-06-30`. They are debt, not permission. Each
group below names an owner and the test that must pass after removal so the
guard `test_suppression_debt_registry.py` will accept the deletion.

## Status legend

- `status: open` — no work merged yet.
- `status: in-progress` — branch exists or work is queued.
- `status: removed` — entry deleted, registry snap refreshed, guard passes.

## Group 1 — `iris/adapters/grpc/server.py` `BLE001`

- File: `iris/adapters/llm/openai.py:103` (BLE001)
- Status: open
- Owner: runtime/grpc maintainer
- What needs to be fixed: gRPC service entry catch-all is a global fallback
  for `SubmitObservation` and friends. Replace with typed error channels
  (`grpc.aio.ServicerContext.abort` with a precise `StatusCode`) once the
  generated stub exposes typed fault enums per call.
- Test that must pass after removal: `uv run pytest tests/runtime/test_grpc_runtime_ingress.py -q`
  plus the existing `tests/architecture/test_suppression_debt_registry.py`
  which will fail until the entry is removed.
- Type: adapter boundary.

## Group 2 — `scripts/_subprocess_runner.py` `S404`

- File: `scripts/_subprocess_runner.py:9` (S404)
- Status: open
- Owner: harness scripts maintainer
- What needs to be fixed: introduce a typed `AuditedProcessRunner` port
  under `scripts/` that wraps `subprocess.run` with an explicit allow-list
  of binary names. Re-route the three scripts
  (`scripts/verify.py`, `scripts/generate_protos.py`, `scripts/ai_report.py`)
  through the port and remove the bare `import subprocess` in
  `_subprocess_runner.py`.
- Test that must pass after removal: `uv run pytest tests/scripts -q`
  and `uv run python scripts/verify.py --quick` (smoke).
- Type: scripts/harness.

## Group 3 — `tests/e2e/helpers.py` `S404` and `S603`

- File: `tests/e2e/helpers.py:11` (S404), `:90` (S603)
- Status: open
- Owner: e2e harness maintainer
- What needs to be fixed: move subprocess invocation into a dedicated
  `tests/e2e/runtime_process.py` port that exposes `start()` and
  `stop()` methods. The e2e helpers should depend on the port, not on
  `subprocess` directly. With the port in place, both the S404 import
  noqa and the S603 call-site noqa disappear.
- Test that must pass after removal: `uv run pytest tests/e2e -m "e2e and not llm_live"`
  and the architecture guard.
- Type: e2e subprocess.

## Group 4 — `tests/e2e/test_runtime_process_config.py` `S404`

- File: `tests/e2e/test_runtime_process_config.py:5` (S404)
- Status: open
- Owner: e2e harness maintainer
- What needs to be fixed: re-export the same `AuditedProcessRunner` port
  (or the `tests/e2e/runtime_process.py` helper from Group 3) from the
  test module. Remove the bare `import subprocess` after the import
  becomes unneeded.
- Test that must pass after removal: same as Group 3.
- Type: e2e subprocess.

## Sequencing

Groups 3 and 4 share the same fix; they should be removed together in a
single PR to keep the registry clean. Groups 1 and 2 are independent and
can be tackled in parallel.

After each removal:

1. Re-run `uv run python scripts/check_suppression_debt_changes.py`
   without the approval env var to confirm the guard still passes.
2. Run `uv run pytest tests/architecture -q` to confirm the registry
   parser still validates the reduced registry.
3. Refresh `.agents/approved-suppression-debt.toml.snap` with the
   updated sha256 — only the human reviewer can do this under the
   approval flow described in `AGENTS.md` and
   `.agents/rules/typing.md`.

## Renewal policy

If an entry cannot be removed by the expiry date, the human reviewer
must either:

- extend the entry's `expires` value with a written justification
  recorded in this document, or
- close the entry by removing the underlying suppression.

Automated renewal is not permitted. Coding agents must never edit
`expires`.
