# ADR 0003: Identity-Owned Memory

## 状態

採択

## 背景

Iris の memory は、会話履歴そのものではなく、検索可能な長期情報を保持する。
対象は facts、preferences、notes、tasks、relationship events である。

`space_id` は interaction context として有用だが、actor の記憶や関係性の主 owner ではない。
同じ actor は複数の space に現れるため、space を durable owner にすると記憶が分断される。

## 決定

- `MemoryRecord` は検索可能な長期 content を表す。
- `MemoryRecord.actor_id` は「誰に関する memory か」を表す主 scope とする。
- `MemoryRecord.space_id` は発生場所や検索補助の context scope として扱う。
- `MemoryKind.RELATIONSHIP_EVENT` は relationship に関する出来事の memory であり、現在の relationship state ではない。
- `RelationshipSnapshot` / `AffectSnapshot` は `MemoryRecord` として保存しない。
- SQLite backend は memory store を durable にする。

## 影響

Memory extraction は、検索したい facts/preferences/notes/tasks/event summary だけを memory として保存する。
current relationship state と Iris の affect baseline は、それぞれ専用 store が所有する。

Presence、space occupancy、activity projection は durable memory ではない。
これらは runtime の ephemeral projection として扱う。
