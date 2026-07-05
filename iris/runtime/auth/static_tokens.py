"""Static bearer token verifier for runtime gRPC auth."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import json
import secrets
from typing import TypeGuard

from iris.runtime.auth.errors import RuntimeUnauthenticatedError
from iris.runtime.auth.principals import ClientKind, ClientPrincipal
from iris.runtime.auth.profiles import (
    EXTERNAL_CLIENT_FORBIDDEN_SCOPES,
    TRUSTED_ADAPTER_OBSERVATION_CAPABILITIES,
    TRUSTED_ADAPTER_SCOPES,
)
from iris.runtime.auth.scopes import AuthScope
from iris.runtime.ingress.observation_ingress import ObservationCapability

_TOKEN_BYTES = 32
type _JsonPrimitive = str | int | float | bool | None
type _JsonValue = _JsonPrimitive | list[_JsonValue] | dict[str, _JsonValue]


@dataclass(frozen=True)
class StaticTokenEntry:
    """Env JSON から読み込んだ bearer token hash entry。"""

    client_id: str
    token_sha256: str
    client_kind: ClientKind
    provider: str | None
    allowed_providers: frozenset[str]
    scopes: frozenset[AuthScope]
    observation_capabilities: frozenset[ObservationCapability]


@dataclass(frozen=True)
class GeneratedToken:
    """create-token command が表示する token と hash entry。"""

    raw_token: str
    token_sha256: str
    entry_json: str


class StaticBearerTokenVerifier:
    """Static SHA-256 token hash based bearer verifier."""

    def __init__(self, entries: tuple[StaticTokenEntry, ...]) -> None:
        """Verifier を token entry 群で初期化する。"""
        self._entries = entries

    @property
    def entry_count(self) -> int:
        """登録済み token entry 数を返す。"""
        return len(self._entries)

    @classmethod
    def from_env(
        cls,
        env: dict[str, str],
        env_key: str,
    ) -> StaticBearerTokenVerifier:
        """環境変数 JSON から verifier を構築する。

        Returns:
            構築済み verifier。

        Raises:
            RuntimeUnauthenticatedError: token entry JSON が不正な場合。
        """
        raw = env.get(env_key)
        if raw is None or not raw.strip():
            return cls(())
        parsed: _JsonValue = json.loads(raw)
        if not _is_json_list(parsed):
            message = "static token config must be a JSON array"
            raise RuntimeUnauthenticatedError(message)
        entries = tuple(_entry_from_json(item) for item in parsed)
        return cls(entries)

    def verify_authorization(self, authorization: str | None) -> ClientPrincipal:
        """Authorization header を検証し ClientPrincipal を返す。

        Returns:
            認証済み client principal。

        Raises:
            RuntimeUnauthenticatedError: bearer token が無効な場合。
        """
        token = _bearer_token(authorization)
        token_hash = hash_token(token)
        for entry in self._entries:
            if hmac.compare_digest(token_hash, entry.token_sha256):
                return ClientPrincipal(
                    client_id=entry.client_id,
                    client_kind=entry.client_kind,
                    provider=entry.provider,
                    allowed_providers=entry.allowed_providers,
                    scopes=entry.scopes,
                    observation_capabilities=entry.observation_capabilities,
                    authenticated=True,
                )
        message = "invalid bearer token"
        raise RuntimeUnauthenticatedError(message)


def hash_token(token: str) -> str:
    """Bearer token の SHA-256 hex digest を返す。

    Returns:
        SHA-256 hex digest。
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_static_token(
    *,
    client_id: str,
    client_kind: ClientKind,
    provider: str | None,
    allowed_providers: frozenset[str],
    scopes: frozenset[AuthScope],
    observation_capabilities: frozenset[ObservationCapability],
) -> GeneratedToken:
    """新規 bearer token と env JSON entry を生成する。

    Returns:
        raw token と hash-only JSON entry。
    """
    _validate_static_token_profile(
        client_kind=client_kind,
        provider=provider,
        allowed_providers=allowed_providers,
        scopes=scopes,
        observation_capabilities=observation_capabilities,
    )
    token = "iris_rt_" + secrets.token_urlsafe(_TOKEN_BYTES)
    token_hash = hash_token(token)
    entry = {
        "client_id": client_id,
        "token_sha256": token_hash,
        "client_kind": client_kind.value,
        "provider": provider,
        "allowed_providers": sorted(allowed_providers),
        "scopes": sorted(scope.value for scope in scopes),
        "observation_capabilities": sorted(
            capability.value for capability in observation_capabilities
        ),
    }
    return GeneratedToken(
        raw_token=token,
        token_sha256=token_hash,
        entry_json=json.dumps(entry, sort_keys=True),
    )


def _bearer_token(authorization: str | None) -> str:
    if authorization is None:
        message = "missing bearer token"
        raise RuntimeUnauthenticatedError(message)
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        message = "malformed bearer token"
        raise RuntimeUnauthenticatedError(message)
    token = authorization[len(prefix) :].strip()
    if not token:
        message = "missing bearer token"
        raise RuntimeUnauthenticatedError(message)
    return token


def _entry_from_json(value: _JsonValue) -> StaticTokenEntry:
    if not _is_json_object(value):
        message = "static token entry must be an object"
        raise RuntimeUnauthenticatedError(message)
    client_id = _required_str(value, "client_id")
    token_sha256 = _required_str(value, "token_sha256")
    entry = StaticTokenEntry(
        client_id=client_id,
        token_sha256=token_sha256,
        client_kind=ClientKind(_required_str(value, "client_kind")),
        provider=_optional_provider(value, "provider"),
        allowed_providers=frozenset(_required_str_list(value, "allowed_providers")),
        scopes=frozenset(AuthScope(item) for item in _required_str_list(value, "scopes")),
        observation_capabilities=frozenset(
            ObservationCapability(item)
            for item in _required_str_list(value, "observation_capabilities")
        ),
    )
    _validate_static_token_profile(
        client_kind=entry.client_kind,
        provider=entry.provider,
        allowed_providers=entry.allowed_providers,
        scopes=entry.scopes,
        observation_capabilities=entry.observation_capabilities,
    )
    return entry


def _validate_static_token_profile(
    *,
    client_kind: ClientKind,
    provider: str | None,
    allowed_providers: frozenset[str],
    scopes: frozenset[AuthScope],
    observation_capabilities: frozenset[ObservationCapability],
) -> None:
    if client_kind is ClientKind.TRUSTED_ADAPTER:
        _validate_trusted_adapter_profile(
            provider=provider,
            allowed_providers=allowed_providers,
            scopes=scopes,
            observation_capabilities=observation_capabilities,
        )
        return
    if client_kind is ClientKind.EXTERNAL_CLIENT:
        _validate_external_client_profile(
            allowed_providers=allowed_providers,
            scopes=scopes,
            observation_capabilities=observation_capabilities,
        )
        return
    if client_kind is not ClientKind.ADMIN and AuthScope.ADMIN_RUNTIME in scopes:
        message = "admin.runtime scope is only valid for admin principals"
        raise RuntimeUnauthenticatedError(message)


def _validate_trusted_adapter_profile(
    *,
    provider: str | None,
    allowed_providers: frozenset[str],
    scopes: frozenset[AuthScope],
    observation_capabilities: frozenset[ObservationCapability],
) -> None:
    if provider is None:
        message = "trusted_adapter requires provider"
        raise RuntimeUnauthenticatedError(message)
    if not allowed_providers:
        message = "trusted_adapter requires allowed_providers"
        raise RuntimeUnauthenticatedError(message)
    if "*" in allowed_providers:
        message = "trusted_adapter must not use wildcard allowed_providers"
        raise RuntimeUnauthenticatedError(message)
    if provider not in allowed_providers:
        message = "trusted_adapter provider must be included in allowed_providers"
        raise RuntimeUnauthenticatedError(message)
    unknown_scopes = scopes - TRUSTED_ADAPTER_SCOPES
    if unknown_scopes:
        message = "trusted_adapter has scope outside trusted adapter profile"
        raise RuntimeUnauthenticatedError(message)
    unknown_capabilities = observation_capabilities - TRUSTED_ADAPTER_OBSERVATION_CAPABILITIES
    if unknown_capabilities:
        message = "trusted_adapter has capability outside trusted adapter profile"
        raise RuntimeUnauthenticatedError(message)


def _validate_external_client_profile(
    *,
    allowed_providers: frozenset[str],
    scopes: frozenset[AuthScope],
    observation_capabilities: frozenset[ObservationCapability],
) -> None:
    forbidden_scopes = scopes & EXTERNAL_CLIENT_FORBIDDEN_SCOPES
    if forbidden_scopes:
        message = "external_client has forbidden trusted/admin scope"
        raise RuntimeUnauthenticatedError(message)
    if observation_capabilities:
        message = "external_client must not have observation capabilities"
        raise RuntimeUnauthenticatedError(message)
    if "*" in allowed_providers:
        message = "external_client must not use wildcard allowed_providers"
        raise RuntimeUnauthenticatedError(message)


def _required_str(payload: dict[str, _JsonValue], key: str) -> str:
    value = payload.get(key)
    if isinstance(value, str) and value:
        return value
    message = f"static token entry missing {key}"
    raise RuntimeUnauthenticatedError(message)


def _optional_provider(payload: dict[str, _JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, str) and value:
        return value
    message = f"static token entry invalid {key}"
    raise RuntimeUnauthenticatedError(message)


def _required_str_list(payload: dict[str, _JsonValue], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        message = f"static token entry missing {key}"
        raise RuntimeUnauthenticatedError(message)
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item:
            message = f"static token entry invalid {key}"
            raise RuntimeUnauthenticatedError(message)
        result.append(item)
    return tuple(result)


def _is_json_list(value: object) -> TypeGuard[list[_JsonValue]]:
    return isinstance(value, list)


def _is_json_object(value: object) -> TypeGuard[dict[str, _JsonValue]]:
    return isinstance(value, dict)
