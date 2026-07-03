# Learning Candidate Review Boundary

この文書は、学習候補を runtime 内部 store に直接触れずに確認・承認・却下・破棄するための service boundary を定義する。

## 目的

Iris の implicit memory extraction、reflection、consolidation、将来の persona / relationship / internal-state worker は、すぐ canonical state へ書いてよいとは限らない候補を生成する。Review boundary は、これらの候補を同じ lifecycle で扱うための共通境界である。

```text
candidate generated
→ pending_review
→ approved
→ promoted by a separate promotion service

candidate generated
→ pending_review
→ rejected

candidate generated
→ pending_review
→ discarded
```

## Service boundary

公開 service は `MemoryCandidateReviewService` である。現実装は memory candidate を対象にするが、返却 contract は `iris/contracts/review_candidates.py` の DTO を使い、runtime 内部の `MemoryCandidateReviewRecord` を呼び出し元へ公開しない。

主な API は次の通り。

```text
list_candidates(ReviewCandidateFilter | None) -> tuple[ReviewCandidateSummary, ...]
read(MemoryCandidateReviewId) -> ReviewCandidateDetail
approve(MemoryCandidateReviewId, ReviewDecisionRequest | None) -> ReviewDecisionResult
reject(MemoryCandidateReviewId, ReviewDecisionRequest | None) -> ReviewDecisionResult
discard(MemoryCandidateReviewId, ReviewDecisionRequest | None) -> ReviewDecisionResult
```

`approve`、`reject`、`discard` は同じ target state への再実行を `changed=False` として扱う。同一 terminal state への再実行は冪等だが、別 terminal state への遷移は許可しない。

## Filtering boundary

`ReviewCandidateFilter` は次の境界で候補を絞り込む。

- `status`: `pending_review` / `approved` / `rejected` / `discarded`。`None` の場合は lifecycle 横断で取得する。
- `candidate_type`: `memory` / `shared_episodic_memory` / `persona_patch` / `relationship` / `internal_state` / `consolidation`。
- `actor_id`: actor boundary。
- `account_id`: account boundary。
- `space_id`: space boundary。
- `limit`: 正の整数。

この filter は admin endpoint や Control Plane が将来利用する読み取り境界であり、本格 access control ではない。権限判定を追加する場合も、この filter と store record を直接外部へ渡さず、service boundary の手前で認可する。

## Candidate type contract

現時点で promotion 実装があるのは `memory` candidate だけである。将来の `shared_episodic_memory`、`persona_patch`、`relationship`、`internal_state`、`consolidation` は `ReviewCandidateType` と DTO で表現できるようにする。

Memory candidate の detail payload は `ReviewMemoryCandidatePayload` に閉じ込める。将来の candidate type では、同じ `ReviewCandidateDetail` に型付き payload を追加し、既存の `candidate_type` / `status` / `scope` / `metadata` を壊さない。

## Local AI / classifier metadata

小型 classifier や local model cascade が候補を生成した場合、候補 metadata を落としてはならない。少なくとも次の情報を文字列 metadata として保持できるようにする。

- `model_name`
- `model_version`
- `classifier_name`
- `classifier_version`
- `confidence`
- `reason`
- `source_event_id`
- `source_observation_id`
- `scope`

Rejected candidate の metadata と `review_reason` は、将来の suppression signal として使える。現時点では suppression policy 自体は実装しない。

## Promotion boundary

Review lifecycle と promotion workflow は分離する。

- `approve()` は review state を `approved` にするだけで、`MemoryStore` へ書き込まない。
- `ApprovedMemoryCandidatePromoter` が approved candidate を読み、promotion policy を通したうえで canonical `MemoryStore` へ書き込む。
- promotion 後は review record に `promoted_memory_id` を保存する。
- `promoted_memory_id` があるが canonical memory が見つからない場合は、通常の冪等 hit ではなく `promoted_memory_missing` として診断する。

この分離により、UI / admin endpoint / worker は「承認」と「永続 memory への昇格」を別の操作として扱える。

## Store boundary

`MemoryCandidateReviewService` は `MemoryCandidateReviewStore` protocol にだけ依存する。SQLite 実装は `iris/adapters/persistence/sqlite/stores/memory_candidate_reviews.py` に閉じ込める。

SQLite store は `memory_candidate_reviews.candidate_type` を保存する。既存 DB は v4 migration `review_candidate_type` で `candidate_type TEXT NOT NULL DEFAULT 'memory'` を追加する。

## スコープ外

- Review UI。
- LLM-based extraction worker。
- Persona / relationship / internal-state worker。
- 本格 access control。
- Bulk approval policy。
- Rejected candidate suppression policy の実行部分。
