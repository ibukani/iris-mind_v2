# Identity and Space Semantics

Iris-Mind runtime における Account、Actor、Identity、Space の意味を定義する。

## Account

Account は外部provider上のアカウント binding を表す。人物そのものではない。

- identity key: `provider + provider_subject`
- `display_name`: 可変の表示用データ。identity key に使わない。
- `actor_kind`: client が既知なら指定する。`ExternalAccountRef` の
  `ACTOR_KIND_UNSPECIFIED` は HUMAN として解決される。
- `account_id`: Iris 内部ID。
- 複数 Account は同じ Actor に link できる。

## Actor

Actor は Iris 内部の主体。長期記憶、関係性、将来のpersona状態の主スコープ。

Actor は human、device、service、system、Iris 自身を表せる。1人のhumanが複数provider accountを持つ場合、Account link で同じ Actor に束ねる。Account unlink は既定で記憶を削除しない。

## Identity

Identity は1 observation内で解決済みの snapshot。永続aggregateではない。

Identity は `actor_id`, `actor_kind`, `display_name`, optional provider info, optional `account_id`, optional `device_id`, metadata を含む。
直接指定する `Identity.actor_kind` の `ACTOR_KIND_UNSPECIFIED` は拒否される。

## Space Persistence Policy

Default Iris-Mind runtime は `SpaceBinding` を永続化しない。

Space は `ExternalSpaceRef` から導出されるエフェメラルで決定論的なcontext。Space の安定identityは `provider + provider_space_ref` から計算される。このため、永続binding tableなしで安定した `space_id` を得られる。

Space は将来の conversation log や memory record にcontextとして記録してよい。ただし Space 自体は durable aggregate root ではない。

| Concept | Persisted? | Primary purpose |
|---|---:|---|
| AccountProfile | Yes | External account binding |
| Account → Actor link | Yes | Cross-account identity continuity |
| Actor | Yes / logically durable | Main subject for memory and relationship |
| Identity | No | Per-observation resolved snapshot |
| Space | No | External interaction context |
| SpaceBinding | No in default runtime | Reserved extension only |
| MemoryRecord | Yes | Long-term memory |
| ConversationLog | Future yes | Raw event/log history |

## SpaceBinding

`SpaceBinding` と `SpaceBindingStore` は予約済みextension contract。default runtime では永続化せず、配線しない。

明示的な外部integrationが将来必要になった場合のみ使う。その場合も conversation history、long-term personality state、user memory body、relationship state を SpaceBinding に置いてはならない。

## Scope Rule

Memory、relationship、persona semantics の主スコープは `actor_id`。`space_id` は外部interactionのcontext scopeとしてのみ扱う。
