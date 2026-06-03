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
- types.md: AppGateway、AppAction、ActionResult の型定義
- legacy.md: 削除済みアーキテクチャ情報
