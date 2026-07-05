"""Static bearer token verifier tests."""

from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from iris.runtime.auth.errors import RuntimeUnauthenticatedError
from iris.runtime.auth.principals import ClientKind
from iris.runtime.auth.scopes import AuthScope
from iris.runtime.auth.static_tokens import (
    StaticBearerTokenVerifier,
    create_static_token,
    hash_token,
)
from iris.runtime.ingress.observation_ingress import ObservationCapability

type TokenEntryPayload = dict[str, str | list[str] | None]


@dataclass(frozen=True, kw_only=True)
class TokenEntryOverrides:
    """Static token entry test data overrides."""

    client_id: str = "cli-1"
    raw_bearer: str = "sample-credential"
    client_kind: str = "external_client"
    provider: str | None = "cli"
    allowed_providers: tuple[str, ...] = ("cli",)
    scopes: tuple[str, ...] = ("observation.submit",)
    observation_capabilities: tuple[str, ...] = ()


def _token_entry(overrides: TokenEntryOverrides | None = None) -> TokenEntryPayload:
    values = overrides or TokenEntryOverrides()
    return {
        "client_id": values.client_id,
        "token_sha256": hash_token(values.raw_bearer),
        "client_kind": values.client_kind,
        "provider": values.provider,
        "allowed_providers": list(values.allowed_providers),
        "scopes": list(values.scopes),
        "observation_capabilities": list(values.observation_capabilities),
    }


def test_static_token_verifier_returns_principal() -> None:
    """Valid bearer token maps to typed ClientPrincipal."""
    bearer = "sample-credential"
    payload = json.dumps([_token_entry(TokenEntryOverrides(raw_bearer=bearer))])
    verifier = StaticBearerTokenVerifier.from_env({"TOKENS": payload}, "TOKENS")

    principal = verifier.verify_authorization(f"Bearer {bearer}")

    assert principal.client_id == "cli-1"
    assert principal.client_kind is ClientKind.EXTERNAL_CLIENT
    assert principal.allowed_providers == frozenset({"cli"})
    assert principal.scopes == frozenset({AuthScope.OBSERVATION_SUBMIT})
    assert principal.authenticated


@pytest.mark.parametrize("authorization", [None, "", "Basic secret", "Bearer wrong"])
def test_static_token_verifier_rejects_missing_or_invalid_token(
    authorization: str | None,
) -> None:
    """Missing, malformed, and invalid bearer tokens fail closed."""
    verifier = StaticBearerTokenVerifier.from_env(
        {"TOKENS": json.dumps([_token_entry()])},
        "TOKENS",
    )

    with pytest.raises(RuntimeUnauthenticatedError) as exc_info:
        verifier.verify_authorization(authorization)

    assert "wrong" not in str(exc_info.value)


def test_generated_token_json_contains_hash_only() -> None:
    """Generated env JSON contains token hash but never raw bearer token."""
    generated = create_static_token(
        client_id="adapter-1",
        client_kind=ClientKind.TRUSTED_ADAPTER,
        provider="discord",
        allowed_providers=frozenset({"discord"}),
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
        observation_capabilities=frozenset({ObservationCapability.INTEGRATE_ACTIVITY}),
    )

    assert generated.raw_token.startswith("iris_rt_")
    assert len(generated.raw_token) >= 40
    assert generated.token_sha256 == hash_token(generated.raw_token)
    assert generated.raw_token not in generated.entry_json
    assert generated.token_sha256 in generated.entry_json
    assert "observation.submit.trusted" in generated.entry_json


def test_static_token_verifier_accepts_trusted_adapter_profile() -> None:
    """trusted_adapter profile は provider / scope / capabilities を principal に復元する。"""
    bearer = "trusted-credential"
    payload = json.dumps(
        [
            _token_entry(
                TokenEntryOverrides(
                    client_id="discord-adapter",
                    raw_bearer=bearer,
                    client_kind="trusted_adapter",
                    provider="discord",
                    allowed_providers=("discord",),
                    scopes=(
                        "runtime.info.read",
                        "observation.submit.trusted",
                        "delivery.poll",
                        "delivery.report",
                    ),
                    observation_capabilities=("integrate_activity",),
                )
            )
        ]
    )
    verifier = StaticBearerTokenVerifier.from_env({"TOKENS": payload}, "TOKENS")

    principal = verifier.verify_authorization(f"Bearer {bearer}")

    assert principal.client_kind is ClientKind.TRUSTED_ADAPTER
    assert principal.client_id == "discord-adapter"
    assert principal.provider == "discord"
    assert principal.allowed_providers == frozenset({"discord"})
    assert principal.scopes == frozenset(
        {
            AuthScope.RUNTIME_INFO_READ,
            AuthScope.OBSERVATION_SUBMIT_TRUSTED,
            AuthScope.DELIVERY_POLL,
            AuthScope.DELIVERY_REPORT,
        }
    )
    assert principal.observation_capabilities == frozenset(
        {ObservationCapability.INTEGRATE_ACTIVITY}
    )


@pytest.mark.parametrize(
    "entry",
    [
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider=None,
                allowed_providers=("discord",),
                scopes=("observation.submit.trusted",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=(),
                scopes=("observation.submit.trusted",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=("*",),
                scopes=("observation.submit.trusted",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=("slack",),
                scopes=("observation.submit.trusted",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=("discord",),
                scopes=("admin.runtime",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=("discord",),
                scopes=("observation.submit",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=("discord",),
                scopes=("observation.submit.trusted",),
                observation_capabilities=("internal_event",),
            )
        ),
        _token_entry(
            TokenEntryOverrides(
                client_kind="trusted_adapter",
                provider="discord",
                allowed_providers=("discord",),
                scopes=("observation.submit.trusted",),
                observation_capabilities=("register_delivery_target",),
            )
        ),
    ],
)
def test_trusted_adapter_token_profile_validation_rejects_overbroad_or_invalid_entries(
    entry: TokenEntryPayload,
) -> None:
    """trusted_adapter token は provider / scope / allowed_providers 境界を fail closed する。"""
    with pytest.raises(RuntimeUnauthenticatedError):
        StaticBearerTokenVerifier.from_env({"TOKENS": json.dumps([entry])}, "TOKENS")


@pytest.mark.parametrize(
    "entry",
    [
        _token_entry(TokenEntryOverrides(scopes=("observation.submit.trusted",))),
        _token_entry(TokenEntryOverrides(scopes=("delivery.poll",))),
        _token_entry(TokenEntryOverrides(scopes=("delivery.report",))),
        _token_entry(TokenEntryOverrides(scopes=("admin.runtime",))),
        _token_entry(TokenEntryOverrides(allowed_providers=("*",))),
        _token_entry(TokenEntryOverrides(observation_capabilities=("integrate_activity",))),
    ],
)
def test_external_client_token_profile_validation_rejects_trusted_or_admin_capability(
    entry: TokenEntryPayload,
) -> None:
    """external_client token は trusted/admin/delivery 権限や wildcard provider を持てない。"""
    with pytest.raises(RuntimeUnauthenticatedError):
        StaticBearerTokenVerifier.from_env({"TOKENS": json.dumps([entry])}, "TOKENS")


def test_create_static_token_uses_same_profile_validation() -> None:
    """create-token path でも static env entry と同じ profile validation を使う。"""
    with pytest.raises(RuntimeUnauthenticatedError):
        create_static_token(
            client_id="adapter-1",
            client_kind=ClientKind.TRUSTED_ADAPTER,
            provider="discord",
            allowed_providers=frozenset({"*"}),
            scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
            observation_capabilities=frozenset(),
        )
