# Iris Runtime API

このドキュメントは `iris-mind_v2` の外部 gRPC 契約を記述する。`iris-cli_v2` のようなクライアントは、この API を通じて Cognitive Runtime とやり取りする。

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
- **`actor_kind`**: `ACTOR_KIND_HUMAN` とする。

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
## Identity and Space Resolution Semantics

External clients should send stable external references. They should not send
Iris-internal `account_id` values.

- `provider` is a stable provider identifier such as `cli`, `discord`, or `web`.
- `provider_subject` is stable within the provider and identifies the external account.
- `display_name` is display-only and must not be used as an identity key.
- `provider_space_ref` is stable within the provider and identifies the external interaction context.
- `space_kind` should be specified by clients.

Examples:

- CLI one-shot: `provider=cli`, stable local `provider_subject`, and an optional one-shot `space_ref`.
- CLI REPL: same account ref across turns and a session-stable `provider_space_ref`.
- Discord DM: Discord user ID as `provider_subject`; stable DM conversation ID as `provider_space_ref` when available.
- Discord channel: Discord user ID as `provider_subject`; channel ID as `provider_space_ref`.
- Discord thread: Discord user ID as `provider_subject`; thread ID as `provider_space_ref`.
- Future proactive/system observation: use a system or Iris actor kind and a stable system/provider space ref when there is an interaction context.

Actor identity is the primary owner for memory and relationship semantics.
`space_id` is contextual scope, not the primary owner of user memory.
## ExternalSpaceRef space semantics

`ExternalSpaceRef` は default server でエフェメラルかつ決定論的に解決される。default runtime は `SpaceBinding` を永続化しない。

安定した `space_id` が必要な client は、provider内で安定した `provider_space_ref` を送ること。

例:

- CLI one-shot: `provider = "cli"`、`provider_space_ref = "oneshot:<request-id>"`。one-shot context が不要なら省略可能なruntime経路では送らない。
- CLI REPL: `provider = "cli"`、`provider_space_ref = "session:<stable-repl-session-id>"`
- Discord DM: `provider = "discord"`、`provider_space_ref = "dm:<stable-dm-id>"`
- Discord channel: `provider = "discord"`、`provider_space_ref = "channel:<channel-id>"`
- Discord thread: `provider = "discord"`、`provider_space_ref = "thread:<thread-id>"`

`display_name`、metadata、`space_kind` は `space_id` のidentity keyではない。
