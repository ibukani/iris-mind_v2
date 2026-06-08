# Checklist: Failure Analysis

Use when a strict gate fails.

## Automated by scripts/verify.py

Run `make ai-check` or `make check`. The script automatically prints:

- exact command (`==> {name}: ...`)
- first failing file or test (`first failure:`)
- failure class (`class:`)
- recommended focused next command (`next:`)
- anti-config-relaxation reminder (`note:`)
- final summary (`Failure-analysis summary:`)

## Human checklist

Only this item still requires human judgment:

- [ ] Related tests inspected before behavior changes.

## Fallback (when verify.py cannot run)

If the script is unavailable, perform these steps manually:

- Capture the exact command that failed.
- Identify the first failing file or test from tool output.
- Classify the failure: lint, format, type, pyright, architecture,
  tests+coverage, environment.
- Do not relax config to pass; fix code or tests instead.
- Select the focused next command from the Makefile or run the tool directly.
- In the final report, state what still fails.
