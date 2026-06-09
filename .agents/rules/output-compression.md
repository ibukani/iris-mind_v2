# Output Compression Rules

Agent-visible replies should keep facts dense and remove filler. These rules do not change Iris runtime personality, product prompts, safety gates, or user-facing companion dialogue.

## English

Use Caveman Mode:

```text
Respond terse. Keep technical substance. Remove fluff.
```

Prefer:

```text
Bug: auth middleware token expiry check uses `<`; need `<=`.
Fix: update config. Verify: run full suite.
```

Avoid:

```text
Sure, I would be happy to help. The issue is likely caused by...
In order to fix this issue, you should...
```

## Japanese

Use Genshijin Mode:

```text
賢い原始人のように短く返す。技術情報は残す。無駄だけ消す。
```

Prefer:

```text
修正可能。
原因: 認証middleware token期限check。
```

Avoid:

```text
修正することができます。
認証ミドルウェアにおけるトークンの有効期限チェックの部分に原因がある可能性があります。
```

## Safety Valve

Use precise normal language for destructive operations, data loss risk, security/privacy issues, irreversible commands, migrations, compliance warnings, reviews, verification failures, and residual risks.
