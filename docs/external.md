# External Apps との関係

## 概要

Iris 本体は `Cognitive Runtime` として設計する。
Discord Bot、Voice Runtime、Twitch Client などは外部アプリとして分離する。

推奨構成。

```text
iris-core = Cognitive Runtime
iris-discord-bot = Discord App Runtime
iris-voice-runtime = Voice / Media Runtime
iris-twitch-client = Stream App Runtime
```

---

## Iris 本体の責務

- 入力を Observation として解釈する
- 会話状態を管理する
- 記憶を検索・更新する
- 関係性を評価する
- 返答方針を決める
- Proactive 発話を決める
- ActionPlan を作る
- 安全検査をする

---

## 外部アプリの責務

- Discord API / 音声 / Twitch / Avatar などに接続する
- 外部イベントを Observation に変換する
- Iris から返された AppAction を実行する
- ActionResult を返す
- rate limit / reconnect / platform 固有処理を扱う

外部アプリがやってはいけないこと。

- 返答内容を決める
- Proactive 発話するか決める
- 記憶を更新する
- 関係性を更新する
- キャラ性を決める
- 重要度判断を独自に行う

外部アプリは、外部世界と Iris の翻訳機である。

---

## AppGateway

`adapters/app_gateway/` の責務は、外部アプリとの `Observation / AppAction / ActionResult` protocol boundary である。

`IdentityResolver` と `SpaceResolver` は `adapters/app_gateway/ports.py` のport。
`provider` と `ExternalRef` を `Identity` / `InteractionSpace` へ変換する。
これは外部境界の責務であり、`contracts/` や `cognitive/` はresolver protocolを知らない。

fake resolverはテストとローカルMVP用。
決定論的 `ActorId` / `SpaceId` を返し、network call、database、global registry、auth、account mergingはしない。

## gRPC ingress

`adapters/grpc/` はtransport adapter。
proto DTOを `ObservationEnvelope` へ変換し、`IrisRuntimeService` へ委譲し、
`RuntimeResponse` をproto DTOへ戻す。
認知判断、memory更新、relationship更新、policy判断、LLM呼び出しは持たない。

Proto構成。

- `proto/iris/api/v1/` — 共有DTO（Identity, ExternalAccountRef, Observation, PresentedOutput）
- `proto/iris/runtime/v1/` — service定義とRPC request/response
- `make generate-protos` で `iris/generated/` 以下に再生成

### ExternalAccountRef

外部クライアントがIris内部の `AccountId` や `ActorId` を直接持たなくてよいよう、
`iris.api.v1.ExternalAccountRef` を `ObservationContext.account_ref` 経由で受け取れる。

```proto
message ExternalAccountRef {
  string provider = 1;
  string provider_subject = 2;
  string display_name = 3;
  ActorKind actor_kind = 4;
  map<string, string> metadata = 5;
}
```

境界の責務と Identity / Account 解決モデル:

- **Actor**: Iris内部の主体（Human, Device, Service, System, Iris）。
- **Account**: 外部providerのアカウントバインディング（AccountProfile）。
- **Identity**: 1回の観測に付随する、AccountProfileとリンク先Actorから構築されたスナップショット。
- **AccountStore**: 外部アカウントバインディングと任意で設定される `linked_actor_id` を保存する。
- **AccountService**: Runtime-level internal service for account lookup, link, and unlink operations. It wraps AccountStore and keeps higher-level account use cases away from storage adapters.
- **SQLiteAccountStore**: Local/Server runtime向けの永続化 AccountStore 実装。
- **IdentityResolver**: `ExternalAccountRef` を受け取り、`AccountStore` を通じて `Identity` へ解決する。

解決の流れの例:
```text
ExternalAccountRef(provider="discord", provider_subject="123")
→ AccountProfile(account_id="account-discord-...", linked_actor_id="actor-ibuki")
→ Identity(actor_id="actor-ibuki", account_id="account-discord-...")
```

**注意事項**:
- 複数のアカウントが同じ Actor に解決されるのは、明示的なリンクが設定されている場合のみである。
- 自動的なアカウントマージはサポートされない。
- アンリンク（unlink）は、今後のIdentity解決にのみ影響する。過去のメモリや関係性の履歴を遡って書き換えることはない。

外部クライアントはIris内部の `AccountId` や `ActorId` を知らない場合、`ExternalAccountRef` を送信する。
gRPC / AppGateway 境界が `IdentityResolver` で `ExternalAccountRef` を型付き `Identity` へ解決する。
解決済みの `Identity` は `ObservationContext.actor` に格納され、そこから `account_id` もセットされる。
cognitive 層は `IdentityResolver` も生成protoもimportせず、解決済みの `actor` と `account_id` だけを受け取る。

resolverが未注入のservicerに `account_ref` が来た場合は `INVALID_ARGUMENT` を返す。
`actor` と `account_ref` の両方が来た場合、および `account_ref` と `account_id` の両方が来た場合は `INVALID_ARGUMENT` を返す（曖昧状態）。

### ExternalSpaceRef

Space は主要な永続的会話履歴ではなく、Observation のためのランタイムコンテキストです。
外部クライアントが直接 Iris 内部の `SpaceId` を持たなくてよいよう、
`iris.api.v1.ExternalSpaceRef` を `ObservationContext.space_ref` 経由で受け取れます。

```proto
message ExternalSpaceRef {
  string provider = 1;
  string provider_space_ref = 2;
  string display_name = 3;
  SpaceKind space_kind = 4;
  map<string, string> metadata = 5;
}
```

境界の責務と Space 解決モデル:

- **InteractionSpace**: Iris 内部の安定したロケーション識別情報とコンテキスト。在室者は保持しない。
- **ExternalSpaceRef**: 外部プロバイダのロケーション情報（例: Discordのチャンネル、CLIルームなど）。
- **SpaceBinding**: 予約済みextension contract。default runtime では永続化も配線もしない。
- **SpaceBindingStore**: 予約済みextension contract。通常のspace解決には使わない。
- **RawInteractionLog**: （将来構想）バックアップや再処理のために生のObservationとResponseを保存する場所。

解決の流れの例:
```text
ExternalSpaceRef(provider="discord", provider_space_ref="123")
→ deterministic SpaceId(space-discord-<hash>)
```

**注意事項**:
- この機能は `InteractionSpace` 自体の永続化を導入しません。
- 現在の在室者は `InteractionSpace` の責務ではありません。後続PRで導入予定の `SpaceOccupancyStore` が正本を担います。
- ルームの会話履歴（room conversation history）の保存機能も導入しません。
- メモリと関係性（Relationship）の永続化は、引き続きアクター中心（Actor-centered）です。

AppGateway の責務。

- 外部アプリから Observation を受け取る
- 外部アプリへ AppAction を返す
- ActionResult を受け取る
- correlation_id / turn_id / session_id を管理する
- external ref と Iris internal ref を対応づける

AppGateway がやってはいけないこと。

- cognitive 判断
- 記憶更新
- Proactive 判断
- presentation 判断
- Discord / Voice 固有ロジックの深い実装

Discord の具体 API 操作は `iris-discord-bot` 側。
Voice / TTS / STT の具体処理は `iris-voice-runtime` 側。

---

## 関連ドキュメント

- architecture.md: adapters 層の責務、依存方向
- legacy.md: 削除済みアーキテクチャ情報
