# ADR 0001: Use Ephemeral Deterministic Space Resolution

## Status

Accepted

## Context

Iris-Mind は CLI session、Discord channel、Discord thread、将来の外部surfaceに対して安定したcontext IDを必要とする。

一方で Space は memory、relationship、persona、conversation history のdurable ownerではない。これらの主スコープは Actor。

## Decision

Default runtime は `provider + provider_space_ref` から Space をエフェメラルかつ決定論的に解決する。

Default runtime は `SpaceBinding` を永続化しない。

## Consequences

- 同じ外部space refは同じ `space_id` を生成する。
- `space_bindings` table は不要。
- Memory と relationship は Actor-centered のまま。
- 将来の `ConversationLog` は `space_id` をcontextとして記録してよい。
- `SpaceBindingStore` は明示的にdocumentされたfuture extensionとしてのみ残す。
