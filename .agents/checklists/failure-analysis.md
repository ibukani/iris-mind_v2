# Checklist: Failure Analysis

Use when a strict gate fails.

- [ ] Exact command captured.
- [ ] First failing file/test captured.
- [ ] Failure class identified: lint, format, mypy, pyright, test, architecture, coverage, environment.
- [ ] No config relaxation used as a fix.
- [ ] Focused command selected for the next loop.
- [ ] Related tests inspected before behavior changes.
- [ ] Final report states what still fails, if anything.
