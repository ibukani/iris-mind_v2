# 共有エピソード記憶候補の型付き契約

## 目的

この文書は、AIコンパニオンとしての Iris が「一緒に過ごしてきた」「内輪ネタがある」「以前の出来事を覚えている」と感じられる体験を作るための共有エピソード記憶候補の型付き契約を定義する。

この契約は profile / preference memory とは別物である。`MemoryCandidate` は名前、好み、応答スタイル、言語設定などの durable user profile / preference を扱う。Shared episodic memory candidate は、Iris とユーザーが共有した出来事、関係性に影響した体験、繰り返し参照される内輪ネタなどを review-required な候補として表現する。

## 実装上の参照先

- `iris/contracts/shared_episodic_memory.py`
- `iris/contracts/review_candidates.py`
- `tests/contracts/test_shared_episodic_memory_candidates.py`
- `tests/contracts/test_review_candidates.py`

## 候補種別

`SharedEpisodicMemoryKind` は次の companion-specific 種別を持つ。

| 種別 | 用途 |
|---|---|
| `shared_event` | Iris とユーザーが共有した具体的な出来事。 |
| `running_joke` | 後続会話で再利用される内輪ネタ。 |
| `companion_milestone` | 初回成功、初回接続、関係性上の節目。 |
| `user_helped_iris_or_iris_helped_user` | ユーザーが Iris を助けた、または Iris がユーザーを助けた体験。 |
| `conflict_and_repair` | 誤解、衝突、不快感と、その後の修復。 |
| `memorable_failure_or_teasing` | 失敗談や軽いからかい。ただし羞恥・攻撃性の policy を必ず通す。 |
| `recurring_topic_with_emotion` | 感情を伴って何度も出る話題。 |

## 必須 provenance

`SharedEpisodicMemoryCandidate` は次の境界情報を必須にする。

- `actor_id`: 共有体験の相手 actor。
- `account_id`: durable user boundary。Space 単独を所有者にしない。
- `space_id`: 体験が発生した会話空間。
- `source_events`: 1件以上の `SharedEpisodicSourceEventRef`。
- `source_events[].source_event_id`: runtime / worker が追跡する source event ID。
- `source_events[].observation_id`: 根拠 observation。
- `source_events[].occurred_at`: 根拠 event の発生時刻。
- `occurred_at`: shared episode として扱う代表時刻。
- `confidence`: 0.0 以上 1.0 以下の信頼度。
- `reason`: review で読める根拠説明。

これにより #69 の implicit extraction worker、#70 の reflection / consolidation worker、#75 の review service、#94 の retrieval / reranking が同じ境界情報を参照できる。

## レビュー優先ポリシー

Shared episodic memory candidate は canonical memory へ自動保存しない。既定値は次の通り。

```text
review_required = true
admission_policy = review_required
admission_risk = normal
```

`ReviewCandidateType.SHARED_EPISODIC_MEMORY` の detail payload は `ReviewSharedEpisodicMemoryCandidatePayload` で表現する。`ReviewMemoryCandidatePayload` とは別の field に置き、profile / preference memory と shared episodic memory を混ぜない。

`approve()` は review lifecycle を進めるだけで、canonical memory への promotion ではない。実際の promotion policy、canonical store、retrieval index への反映は後続 Issue の worker / promoter 側で扱う。

## 機微・私的・羞恥内容の受け入れポリシー

共有エピソードは親密さを作れる一方で、羞恥・攻撃・秘密の固定化につながりやすい。そのため admission risk を必ず持つ。

| Risk | 初期方針 |
|---|---|
| `normal` | `review_required`。 |
| `private` | `review_required`。本人に関わる私的文脈として扱う。 |
| `sensitive` | `review_required`。高信頼度でも自動保存しない。 |
| `embarrassing` | `review_required`。からかい、失敗談、恥ずかしい出来事を無条件に保存しない。 |
| `secret_like` | `reject`。credential、secret、認証情報、秘密相当の内容は shared memory にしない。 |

`secret_like` に `review_required` を指定すると contract validation で拒否する。`review_required` policy で `review_required=false` にすることも拒否する。

## 検索用メタデータ

`SharedEpisodicRetrievalMetadata` は #94 の retrieval / reranking が参照する軽量 metadata である。

- `topics`: 検索 topic。空白だけの値は禁止。
- `emotional_context`: その体験に紐づく感情文脈。
- `relationship_signal`: familiarity / trust / repair などの関係性 signal。
- `salience`: 0.0 以上 1.0 以下の候補重要度。

これは retrieval 用の signal であり、関係性 snapshot や affect state の canonical store ではない。


## 後続ワーカー・昇格処理の制約

#69 の extractor、#70 の reflection / consolidation worker、将来の promoter は、この contract validation を迂回してはならない。ワーカーが shared episodic candidate を生成する場合も、まず `SharedEpisodicMemoryCandidate` または `ReviewSharedEpisodicMemoryCandidatePayload` を構築し、`review_required`、`admission_policy`、`admission_risk` の検証を通す。

特に `secret_like` を `pending_review` として保存したり、`private` / `sensitive` / `embarrassing` を review なしに canonical memory へ昇格したりしてはならない。後続実装で store / service / worker fixture を追加する場合は、この文書の policy を regression test として固定する。

## スコープ外

- LLM-based extraction worker の実装。これは #69。
- consolidation / reflection worker の実装。これは #70。
- review UI。
- canonical memory への promotion。
- retrieval pipeline / embedding / reranking の実装。これは #94。
- synchronous hot path での extraction。
