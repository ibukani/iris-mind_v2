# Done Checklist

A task is not complete until the implementation, tests, and report are aligned.

## Required final state

- [ ] Code implements only the requested behavior.
- [ ] Architecture boundaries are preserved.
- [ ] Tests cover the new or fixed behavior.
- [ ] Existing tests were not weakened to pass the task.
- [ ] Documentation is updated if behavior, commands, or architecture changed.
- [ ] There are no new TODOs that hide required work.

## Required checks

Run targeted checks while working. Before final completion, run:

```bash
make check
```

`make verify` is equivalent. If only documentation changed, run the smallest relevant command and explain why full verification was not needed.

Use `make quick` only for iteration; do not present it as full completion verification for behavior or architecture changes.

## Final report language

Write the final report in Japanese. Keep it compact. Internal work may be English, but do not expose hidden reasoning.

## Final report template

```text
変更ファイル
- ...

概要
- ...

検証
- command: result
- command: result

残リスク
- ...
```

## Honesty rule

If a check was not run, say so. Include the reason.
