# ADR 0011: Memory vector index backend

## 状態

採用

## 決定

`MemoryStore` を唯一の正本とする。vector database は `memory_id`、埋め込み、
source digest、embedding provider/model/dimension、検索用 metadata だけを保持する
再生成可能な派生 index とする。

開発・テストでは `InMemoryVectorMemoryIndex`、永続構成では
`QdrantVectorMemoryIndex` を選択できる。認知層は `EmbeddingClient` と
`VectorMemoryIndex` の provider-neutral contract のみ参照する。

`MemoryVectorIndexRebuilder` は正本を走査し、missing、stale、embedding 非互換 entry を
upsert する。任意で orphan を削除する。同一状態での再実行は変更を生まない。
現在の起動時制御は `memory.vector.rebuild_on_startup` の boolean のみである。有効時は
正本全体を検査し、missing/stale/incompatible entry を同期するMVP動作とする。

Qdrant既存collectionがvector sizeを公開する場合、設定済みembedding dimensionとの
不一致をindex incompatibilityとして起動時に拒否する。距離設定が公開され、Cosine以外の
場合も拒否する。

memory write は正本保存を先に完了する。vector upsert 障害は設定により fail-open とし、
raw memory text を記録せず診断情報だけをログへ残す。retrieval pipeline は
`VectorMemoryIndex.entry()` から既存 embedding vector を再利用し、overlap detection のために
同じ memory record を毎回再 embedding しない。

## 理由

検索 index の障害や再作成が canonical memory の耐久性を損なわない構造にするため。
source digest と embedding identity により、再起動後も stale/非互換 entry を検出できる。

## 制約

- 通常 CI は外部 Qdrant を要求しない。
- 現在の embedding provider は決定論的 fake のみ。
- Qdrant transport は REST のみ。`prefer_grpc` は予約設定。
- `off | missing_only | stale_only | full` の詳細mode、manual rebuild API、background rebuild
  schedulingは対象外。
- migration framework、backup/export policy、sqlite-vec、Chroma、pgvectorは対象外。
