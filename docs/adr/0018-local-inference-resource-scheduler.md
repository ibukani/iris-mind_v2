# 0018 ローカル推論資源 scheduler boundary

Status: Accepted

## Context

ローカル推論環境では、user-facing response generation、proactive generation、implicit memory extraction、reflection、relationship update、small-model classification が同じ CPU / GPU / VRAM 容量を共有する。BackgroundJobQueue は backlog、timeout、kind 別 concurrency を制御できるが、現在どの job が local inference resource を消費しているか、また background LLM job が large model slot を占有しているとき user-facing request をどう扱うかまでは表現しない。

Issue #88 は model-call budget と cascade policy を定義する。Issue #92 は queue metrics、backpressure、per-kind concurrency を定義する。Issue #93 はそれらを置き換えず、その上に runtime resource-lease boundary を追加する。

## Decision

provider 非依存の `iris.runtime.inference` boundary を追加する。

- resource state は `idle`、`busy`、`warming`、`unavailable` とする。
- lease acquisition は blocking wait せず、`acquired`、`defer`、`cancel`、`no_send`、`denied` の deterministic decision を返す。
- large LLM と background LLM は共有 large slot を使い、concurrency limit は 1 に固定する。
- small classifier、embedding、reranker は large LLM とは別 slot として扱う。
- user-facing response と safety-critical work は highest priority とする。
- background / proactive work は low priority とし、busy / warming / unavailable 時に defer / cancel / no-send できる。
- active な低優先度 large LLM provider call を安全に停止できない間は、その lease を scheduler 上だけで無効化しない。user-facing 側は large slot が空くまで provider call を開始せず、deterministic fallback / defer を返す。
- observability は prompt / payload を含めず、state、decision、reason、active slots、busy duration だけを記録する。

scheduler は config-gated とし、typed effective runtime config からのみ配線する。user-facing LLM wrapper は provider call 前に large LLM lease を取得し、lease できない場合は provider を呼ばず deterministic cascade fallback を返す。BackgroundJobRunner は resource profile または kind policy が LLM 使用を宣言する job にだけ background LLM lease を要求し、拒否された job は queue boundary 経由で defer または cancel する。

## Non-goals

この boundary は OS-level scheduling、GPU process management、distributed worker、provider-specific cancellation を実装しない。実行中 provider call を安全に停止できない段階では、scheduler は active low-priority lease を削除して high-priority lease を即時発行しない。これにより実プロセス上の large LLM 並走を避ける。将来 cooperative cancellation token を background worker / provider call 境界へ渡せるようになった場合だけ、低優先度 job の停止後に user-facing lease を発行する余地を残す。

## Consequences

user-facing response generation は background work を待たずに deterministic resource decision を得られる。active background LLM call が large slot を占有している場合、user-facing 側は provider を並走させず fallback / defer へ進む。proactive / background LLM job は hot path を block せず defer / cancel / no-send できる。scheduler policy による cancel / no-send は queue 上では失敗ではなく `cancelled` terminal status として記録する。queue metrics と per-kind concurrency は #92 が所有し、local resource state と model-slot lease decision は inference scheduler が所有する。
