"""Static bearer token verifier tests."""

from __future__ import annotations

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


def test_static_token_verifier_returns_principal() -> None:
    """Valid bearer token maps to typed ClientPrincipal."""
    bearer = "sample-token"
    payload = json.dumps(
        [
            {
                "client_id": "cli-1",
                "token_sha256": hash_token(bearer),
                "client_kind": "external_client",
                "provider": "cli",
                "allowed_providers": ["cli"],
                "scopes": ["observation.submit"],
                "observation_capabilities": [],
            }
        ]
    )
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
        {
            "TOKENS": json.dumps(
                [
                    {
                        "client_id": "cli-1",
                        "token_sha256": hash_token("sample-token"),
                        "client_kind": "external_client",
                        "provider": "cli",
                        "allowed_providers": ["cli"],
                        "scopes": ["observation.submit"],
                        "observation_capabilities": [],
                    }
                ]
            )
        },
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
