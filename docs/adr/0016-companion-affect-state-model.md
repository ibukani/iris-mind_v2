# ADR 0016: Companion Affect State Model

## Status

Accepted

## Context

Iris の companion UX では、Iris 自身の mood、特定 actor との relationship、actor から観測された短期 affect、group-space の雰囲気、直近 interaction の tone を同じ state として扱うと、別ユーザー・別 space・別 interaction へ不自然に漏れる。

また、Space の生ログや一時的な場の雰囲気を user memory の primary owner にしない方針と整合させる必要がある。durable にすべき current state、ephemeral に留める短期 state、activity journal や current context から再構築できる derived state を分ける。

## Decision

Companion affect state は以下の vocabulary に分離する。

| State | Owner | Persistence | Prompt summary | Durable mutation |
|---|---|---|---|---|
| `IrisGlobalMood` | Iris | durable | #91 の budget 管理下で許可 | #72 worker / policy candidate 経由 |
| `ActorRelationshipState` | Actor | durable | #91 の budget 管理下で許可 | #102 policy が bounded candidate として更新 |
| `ActorAffectTrace` | Actor | derived | 圧縮 summary のみ許可 | direct durable mutation 不可 |
| `SpaceAtmosphereState` | Space | derived | current space のみに許可 | durable relationship / memory へ直書き不可 |
| `RecentInteractionTone` | Interaction | ephemeral | current turn/window のみに許可 | durable memory / relationship へ直書き不可 |

`IrisGlobalMood` は Iris 全体の baseline/current mood であり、actor、account、space の owner を持たない。既存の `AffectBaselineRecord(scope="global", actor_id=None)` と対応する。

`ActorRelationshipState` は actor ごとの durable relationship state であり、既存の `RelationshipSnapshotRecord(actor_id=...)` と対応する。Account は actor identity linking の補助 scope として `account_id` で参照できるが、現時点の durable relationship owner は `ActorId` とする。`AccountRelationshipState` を将来追加する場合も、既存 actor-owned durable state と競合しない derived view または明示 migration として扱う。

`ActorAffectTrace` は actor から観測された最近の emotion / VAD trace であり、relationship そのものではない。「今日は悲しい」は actor affect trace であり、Iris への trust / affinity 低下ではない。

`SpaceAtmosphereState` は group-space や channel の一時的な雰囲気である。Space は context scope であり、user memory、relationship、affect durable state の primary owner ではない。Space を user memory の primary owner にしない方針を維持する。

`RecentInteractionTone` は 1 ターンまたは短期 window に閉じた interaction tone である。これは durable memory として保存しない。

Direct-message と group-space は次の境界を持つ。

- DM は current actor の relationship state を参照できるが、group-space atmosphere を import しない。
- Group-space は current space の atmosphere を local tone として参照できるが、space atmosphere から actor relationship / global mood を直接更新しない。
- Group-space の一時的な荒れや盛り上がりは、direct-message relationship に漏らさない。
- Recent interaction tone は DM / group-space のどちらでも durable update source にしない。

#100 Appraisal semantics split は、この ADR の state vocabulary を参照して signal の意味を分離する。ただし appraisal signal は durable state を直接 mutate しない。

#102 Relationship update policy v2 は、この ADR の `ActorRelationshipState` を primary update target とする。raw score から直接 durable state を変更せず、typed reason / confidence / source event IDs を持つ bounded candidate を計算する。

#72 Companion state update worker は、この ADR の durable update target に対して candidate update を生成する。worker は durable store へ直接書き込まず、review-required または明示的に bounded な promotion path を通る。

Production-like な multi-client / multi-space durable update を有効化する前に、#74 multi-client ordering / conflict resolution の境界が必要になる。

## Non-decisions

- #100 の appraisal signal contract の詳細は決めない。
- #102 の update magnitude / cap / decay / review threshold は決めない。
- #72 の worker 実装、queue、retry、promotion path は決めない。
- User-facing prompt への実投入は決めない。Prompt context に入れる場合は #91 の prompt budget / trust boundary に従う。
- `SpaceAtmosphereState` や `RecentInteractionTone` 用の durable store は追加しない。
- SQLite schema migration は追加しない。

## Consequences

Companion affect state の混入を contract と tests で防ぐ。

- Global mood と actor/account-scoped relationship は別 state として扱う。
- Actor affect trace と actor relationship は別 state として扱う。
- Space atmosphere は current space に閉じ、user memory の primary owner にならない。
- Recent interaction tone は ephemeral であり、durable memory として扱わない。
- Durable update target は candidate update gate を通る。
- Prompt summary は raw stored state から分離し、#91 の budget に渡せる単位にする。

## Implementation anchors

- `iris/contracts/companion_affect.py`
- `iris/contracts/affect.py`
- `iris/contracts/relationship.py`
- `tests/contracts/test_companion_affect_state_model.py`
- `docs/adr/0002-runtime-state-persistence-policy.md`
- `docs/adr/0004-relationship-and-affect-state.md`
