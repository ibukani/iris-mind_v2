# Iris Runtime API

このドキュメントは `iris-mind` の外部 gRPC 契約を記述する。`iris-cli` のようなクライアントは、この API を通じて Cognitive Runtime とやり取りする。

## Runtime Service エンドポイント

デフォルトの `IrisRuntimeService` は標準的な gRPC サーバである。ランタイムは単純なインタラクションのため unary RPC で動作し、特に `SubmitObservation` と `GetRuntimeInfo` を提供する。

## RPC メソッド

### `GetRuntimeInfo`

接続中の Mind インスタンスに関する安定したメタデータを返す。
クライアントは接続時にこれを用いて互換性を確認できる。

```protobuf
message GetRuntimeInfoResponse {
  string runtime_name = 1;         // e.g. "iris-mind"
  string runtime_version = 2;      // e.g. "0.1.0"
  string api_version = 3;          // e.g. "iris.runtime.v1"
  repeated string supported_features = 4; // e.g. "submit_observation", "persistent_account", "ephemeral_space"
}
```

### `SubmitObservation`

クライアント側から認知ランタイムへイベントを送信する。単純な CLI チャットでは、ユーザメッセージ送信に利用する。

```protobuf
message SubmitObservationRequest {
  string correlation_id = 1;
  iris.api.v1.Observation observation = 2;
}
```


## Runtime Auth / trusted external adapter profile

remote / public bind で Runtime API を使う場合、旧 Discord bot の `access_token` / `role` / `permissions` metadata 互換は使わない。gRPC metadata は standard `authorization: Bearer <token>` のみを認証入力にする。`ObservationContext.source`、`ObservationContext.metadata`、payload metadata は user-controlled field なので trust 判定に使わない。

外部アダプタは通常 client ではなく、ユーザー発話、presence / activity、pull-based delivery、`ActionResult` reporting を代行する `trusted_adapter` principal として発行する。`trusted_adapter` は admin ではない。provider と scope は token profile で最小化する。

### Discord trusted adapter token 例

```bash
python -m iris.runtime.server auth create-token \
  --client-id discord-adapter \
  --client-kind trusted_adapter \
  --provider discord \
  --allowed-provider discord \
  --scope runtime.info.read \
  --scope observation.submit.trusted \
  --scope delivery.poll \
  --scope delivery.report \
  --observation-capability integrate_activity
```

この command は raw token、SHA-256 hash、`IRIS_RUNTIME_TOKENS` に入れる hash-only JSON entry を表示する。raw token は一度だけ表示されるため、config file、docs、log へ保存しない。server 側は hash-only JSON entry だけを読む。

`IRIS_RUNTIME_TOKENS` entry の形。実値は上の command 出力を使う。

```json
[
  {
    "client_id": "discord-adapter",
    "client_kind": "trusted_adapter",
    "provider": "discord",
    "allowed_providers": ["discord"],
    "scopes": [
      "runtime.info.read",
      "observation.submit.trusted",
      "delivery.poll",
      "delivery.report"
    ],
    "observation_capabilities": ["integrate_activity"],
    "token_sha256": "<sha256-of-raw-token>"
  }
]
```

### local development 設定例

loopback の開発用途では既定の `local_dev` を使える。これは unauthenticated loopback を許すため、public bind には使わない。

```toml
[server]
host = "127.0.0.1"
local_only = true

[auth]
mode = "local_dev"
allow_unauthenticated_loopback = true
```

外部アダプタ移行テストを local で production-like に寄せる場合は、loopback でも `auth.mode = "required"` と static bearer token を使う。

### production-like 設定例

remote bind では `auth.mode = "required"` と TLS を有効にする。token secret は TOML に書かず、`IRIS_RUNTIME_TOKENS` 環境変数へ hash-only entry を入れる。

```toml
[server]
host = "0.0.0.0"
local_only = false

[server.tls]
enabled = true
cert_chain_path = "/etc/iris/runtime.crt"
private_key_path = "/etc/iris/runtime.key"

[auth]
mode = "required"
allow_unauthenticated_loopback = false
```

TLS を使わない remote bind は開発用途だけ `auth.allow_insecure_remote = true` で明示する。production-like 接続では使わない。

### scope / provider 境界

- `SubmitObservation`: `trusted_adapter` は `observation.submit.trusted` と `ExternalAccountRef` または `ExternalSpaceRef` の provider claim が必要。通常 `external_client` は `observation.submit` が必要。
- `PollAppActions`: `delivery.poll` と `PollAppActionsRequest.provider` が `allowed_providers` に含まれることが必要。
- `ReportActionResult`: `delivery.report` と delivery item の provider が `allowed_providers` に含まれることが必要。さらに delivery lease / action identity は delivery broker が検証する。
- `trusted_adapter` token は wildcard provider や `admin.runtime` を持てない。標準許可 capability は `integrate_activity`、`integrate_presence`、`update_space_occupancy` に限定し、reaction pipeline を有効化する `react_to_activity` は別Issueで明示追加する。
- `external_client` token は `observation.submit.trusted`、`delivery.poll`、`delivery.report`、`admin.runtime`、`ObservationCapability` を持てない。
- 外部 ingress は `actor_id` / `account_id` / `space_id` を直接主張せず、`ExternalAccountRef` / `ExternalSpaceRef` を使う。

## CLI クライアントが要求・推奨されるフィールド

### `SubmitObservationRequest`
- **`correlation_id`**: クライアントが生成するリクエスト追跡用のユニーク ID。レスポンスにそのままエコーされる。

### `Observation`
- **`observation_id`**: クライアントが生成する Observation 用のユニーク ID。
- **`session_id`**: クライアントが生成するセッション識別子。
  - **ワンショット CLI プロンプトの場合**: `session_id` はコマンドごとに一意に生成してよい。
  - **CLI REPL の場合**: `session_id` は REPL セッション中ずっと一定に保つ。
- **`kind`**: `OBSERVATION_KIND_ACTOR_MESSAGE` とする。
- **`occurred_at`**: 必須。イベント発生時の protobuf `Timestamp`。

### `ObservationContext`
- **`source`**: `"cli"` とする。
- **`account_ref`** *(推奨)*: 外部クライアントは `account_id` や `Identity` ではなく `account_ref` で自身を識別する。
- **`space_ref`** *(推奨)*: コンテキストとなる空間表現。エフェメラルに解決される。

### `ExternalAccountRef`
サーバ側 Identity Resolver が内部 Identity のルックアップまたは暗黙生成に利用する。
- **`provider`**: `"cli"` とする。
- **`provider_subject`**: クライアント側ローカルユーザの安定識別子 (例: ローカル OS ユーザ名や固定 CLI ID)。
- **`display_name`**: マッパーが要求する。ユーザの表示名。
- **`actor_kind`**: 既知なら明示する。`ExternalAccountRef` では
  `ACTOR_KIND_UNSPECIFIED` も受理され、`ACTOR_KIND_HUMAN` として解決される。
  この既定値は直接指定する `Identity` には適用されない。

### `ExternalSpaceRef`
外部インタラクションコンテキストを表す。サーバ側でエフェメラルに解決され、永続化されない。
- **ワンショット CLI プロンプトの場合**: `space_ref` は任意、またはコマンドごとに生成してよい。
- **CLI REPL の場合**: `space_ref` が推奨され、`provider_space_ref` はセッション中ずっと一定に保つ。

## CLI リクエスト例

```python
import time
from iris.generated.iris.runtime.v1 import runtime_pb2
from iris.generated.iris.api.v1 import observations_pb2, identity_pb2, spaces_pb2
from google.protobuf.timestamp_pb2 import Timestamp

ts = Timestamp()
ts.GetCurrentTime()

request = runtime_pb2.SubmitObservationRequest(
    correlation_id="cli-req-123",
    observation=observations_pb2.Observation(
        observation_id="obs-123",
        session_id="repl-456",
        kind=observations_pb2.OBSERVATION_KIND_ACTOR_MESSAGE,
        occurred_at=ts,
        context=observations_pb2.ObservationContext(
            source="cli",
            account_ref=identity_pb2.ExternalAccountRef(
                provider="cli",
                provider_subject="local-user-id",
                display_name="Local User",
                actor_kind=identity_pb2.ACTOR_KIND_HUMAN,
            ),
            space_ref=spaces_pb2.ExternalSpaceRef(
                provider="cli",
                provider_space_ref="session:repl-456",
                display_name="CLI REPL Session",
                space_kind=spaces_pb2.SPACE_KIND_DIRECT_MESSAGE,
            )
        ),
        actor_message=observations_pb2.ActorMessagePayload(
            text="Hello, Iris!",
            external_message_id="msg-123"
        )
    )
)
```

## `PresentedOutput`

`SubmitObservation` のレスポンスには `PresentedOutput` が含まれる。
- **`text`**: 認知ランタイムが生成した、ユーザに見える主要な返答。CLI クライアントが表示すべき内容。
- **`style_hint`, `emotion_hint`, `expression_hint`**: 任意の UI 提示ヒント。
- **`delay_ms`, `priority`, `interruptible`**: 提示タイミングと挙動のヒント。単純な CLI クライアントは最初は無視してよい。
- **空の出力**: `output.text` が空の場合、CLI はクラッシュを避け、フォールバック表示するか何も出力しないかしてよい。

## Identity / Space 解決セマンティクス

外部クライアントは安定した外部参照を送る。Iris 内部の `account_id` は送らない。

- `provider` は `cli`、`discord`、`web` などの安定した provider 識別子である。
- `provider_subject` は provider 内で安定し、外部アカウントを識別する。
- `display_name` は表示専用であり、identity key として使わない。
- `provider_space_ref` は provider 内で安定し、外部インタラクションコンテキストを識別する。
- `space_kind` はクライアントが指定することを推奨する。

例:

- CLI one-shot: `provider=cli`、安定したローカル `provider_subject`、必要なら one-shot 用 `space_ref` を送る。
- CLI REPL: turn 間で同じ `account_ref` を使い、REPL セッション中は安定した `provider_space_ref` を送る。
- Discord DM: Discord user ID を `provider_subject` にし、利用可能なら安定した DM conversation ID を `provider_space_ref` にする。
- Discord channel: Discord user ID を `provider_subject` にし、channel ID を `provider_space_ref` にする。
- Discord thread: Discord user ID を `provider_subject` にし、thread ID を `provider_space_ref` にする。
- 将来の proactive / system observation: interaction context がある場合は、system または Iris actor kind と安定した system/provider space ref を使う。

Memory と relationship の主要な所有者は actor identity である。
`space_id` は contextual scope であり、user memory の主要所有者ではない。

## `ExternalSpaceRef` の space セマンティクス

`ExternalSpaceRef` は default server でエフェメラルかつ決定論的に解決される。default runtime は `SpaceBinding` を永続化しない。

安定した `space_id` が必要な client は、provider内で安定した `provider_space_ref` を送ること。

例:

- CLI one-shot: `provider = "cli"`、`provider_space_ref = "oneshot:<request-id>"`。one-shot context が不要なら省略可能なruntime経路では送らない。
- CLI REPL: `provider = "cli"`、`provider_space_ref = "session:<stable-repl-session-id>"`
- Discord DM: `provider = "discord"`、`provider_space_ref = "dm:<stable-dm-id>"`
- Discord channel: `provider = "discord"`、`provider_space_ref = "channel:<channel-id>"`
- Discord thread: `provider = "discord"`、`provider_space_ref = "thread:<thread-id>"`

`display_name`、metadata、`space_kind` は `space_id` の identity key ではない。

## Pull-based Delivery API（pull型配送API）

Retry 可能な `FAILED` は `PENDING` へ戻して `not_before` に次回 retry 時刻、`last_error_reason` に失敗理由を保持する。最大試行後のみ `FAILED_PERMANENT` へ遷移する。

`PollAppActions` と `ReportActionResult` は proactive delivery outbox 用の pull 型 API である。local development では local dev principal を使えるが、public network に unauthenticated で公開してはならない。remote / public bind では runtime auth boundary が `DELIVERY_POLL` / `DELIVERY_REPORT` scope と provider ownership を検査する。

外部 client は `PollAppActions(provider, max_items)` で provider ごとの due action を lease する。`PollAppActions` は `LEASED` 状態の item のみ返す。terminal item（`SUCCEEDED` / `FAILED_PERMANENT` / `CANCELLED` / `BLOCKED`）は返さない。Mind runtime は Discord / CLI / voice などの platform send を直接実行しない。現 phase の delivery polling API は `SendMessageAction` のみを返し、`NoAction` は配送されない。

外部 client は platform send 後に `ReportActionResult` を呼ぶ。`SUCCEEDED` / `CANCELLED` / `BLOCKED` は terminal completion となり、それぞれ `DeliveryStatus.SUCCEEDED` / `CANCELLED` / `BLOCKED` に遷移する。`FAILED` のみ retry 可能で、retry 可能なら release し、最大試行後は permanent failure にする。同一 `ActionResult` の再報告は全 status で idempotent に扱う。同一性は `delivery_id`、`lease_id`、`action_id`、`correlation_id`、`status`、`external_message_id`、`error_reason` で判定する。同じ `delivery_id` / `lease_id` でこれらが異なる再報告は `DeliveryOutboxError` を送出する。

`SchedulerRunner` は `DeliveryAvailabilityProvider` protocol を通じて配信先の `AvailabilitySnapshot` を取得し、`DeliverySafetyGate` へ渡す。`availability=None` の場合は safety gate は availability check を skip する。BUSY / UNAVAILABLE は delivery enqueue を block する。
