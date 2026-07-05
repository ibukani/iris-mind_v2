# ADR 0014: Public Remote Auth Boundary

## Status

Accepted.

## Context

Iris runtime は local development を簡単に保つ必要がある。一方で、gRPC runtime を
loopback 以外へ bind すると、`SubmitObservation` と pull-based delivery API が外部
から到達可能になる。remote/public usage は明示的な認証・認可境界なしで許可しない。

既存の `ObservationCapability` は runtime state/effect capability であり、RPC への
アクセス認可ではない。既存の unauthenticated external ingress と trusted adapter
ingress の分離は維持する。

## Decision

- `server.local_only=true` を既定値のままにする。loopback local development は簡単で安全に保つ。
- `server.local_only=false` は `auth.mode=required` を必須にする。
- remote bind は TLS を必須にする。ただし開発用途だけ `auth.allow_insecure_remote=true`
  で明示的に unsafe override できる。
- 最初の実装は static bearer token verifier とする。
- raw bearer token は config、example、log、error に保存・表示しない。
- server は token hash だけを env から読み込む。TOML には token secret を置かない。
- bearer token は typed `ClientPrincipal` に対応する。
- `trusted_adapter` は external adapter 専用 profile とする。admin ではなく、`allowed_providers` と最小 scope で制限する。
- `trusted_adapter` は wildcard provider、`admin.runtime`、通常 client 用 `observation.submit` を持てない。
- `external_client` は `observation.submit.trusted`、`delivery.poll`、`delivery.report`、`admin.runtime`、`ObservationCapability` を持てない。
- `AuthScope` が RPC access を認可する。
- `ObservationCapability` は runtime observation effects を認可する。
- provider scope は provider impersonation を防ぐ。`request.provider`、
  `account_ref.provider`、`space_ref.provider` は `ClientPrincipal.allowed_providers`
  の範囲内でなければならない。`trusted_adapter` の `SubmitObservation` は
  `account_ref.provider` または `space_ref.provider` を持つ外部参照を要求する。
- external ingress は Iris 内部の `ActorId` / `AccountId` / `SpaceId` を直接 claim できない。
- `ObservationContext.source` と user-controlled metadata は auth/trust 判定に使わない。
- delivery polling/reporting API は remote/public mode で unauthenticated にしない。
- trusted adapter ingress capability は token 由来の `ClientPrincipal` から渡す。標準 profile は `integrate_activity` / `integrate_presence` / `update_space_occupancy` までに限定し、`react_to_activity` は後続Issueで明示追加する。
- 旧 `access_token` / `role` / `permissions` metadata 互換は追加しない。

## Out Of Scope

- OAuth/OIDC
- user login
- DB-backed token admin
- Control Plane auth UI / admin workflow
- mTLS 必須化

## Implementation anchors

- `iris/runtime/auth/context.py`
- `iris/runtime/auth/policy.py`
- `iris/runtime/auth/principals.py`
- `iris/runtime/auth/scopes.py`
- `iris/runtime/auth/static_tokens.py`
- `iris/runtime/config/auth.py`
- `iris/adapters/grpc/auth_interceptor.py`
- `iris/runtime/wiring/grpc.py`
- `tests/runtime/auth/test_authorization_policy.py`
- `tests/runtime/auth/test_static_token_verifier.py`
- `tests/runtime/auth/test_token_generation.py`
- `tests/runtime/config/test_auth_config.py`
- `tests/adapters/grpc/test_grpc_auth_interceptor.py`
- `tests/architecture/test_auth_boundary_guards.py`

## Consequences

Local default は従来どおり fake/local development に向く。remote/public deployment は
`auth.mode=required` と TLS、または明示 unsafe override がない限り起動前 config
validation で失敗する。delivery API は local/internal trust 前提から、RPC scope と
provider ownership check を持つ境界へ変わる。
