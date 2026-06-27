"""Runtime authorization policy tests."""

from __future__ import annotations

import pytest

from iris.runtime.auth.errors import RuntimePermissionDeniedError
from iris.runtime.auth.policy import ObservationRequestClaims, RuntimeAuthorizationPolicy
from iris.runtime.auth.principals import ClientKind, ClientPrincipal
from iris.runtime.auth.scopes import AuthScope


def test_external_submit_denies_internal_identity_claims() -> None:
    """external_client は actor/account_id/space_id を直接 claim できない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.EXTERNAL_CLIENT,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(
                account_ref_provider="cli",
                has_account_id=True,
            ),
        )


def test_provider_mismatch_denied() -> None:
    """allowed_providers 外の provider claim は拒否される。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.EXTERNAL_CLIENT,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(account_ref_provider="discord"),
        )


def test_poll_and_report_require_provider_scope() -> None:
    """Delivery poll/report は scope と provider 所有権を要求する。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.EXTERNAL_CLIENT,
        scopes=frozenset({AuthScope.DELIVERY_POLL, AuthScope.DELIVERY_REPORT}),
    )

    policy.require_poll_app_actions(principal, "cli")
    policy.require_report_action_result(principal, "cli")
    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_poll_app_actions(principal, "discord")
    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_report_action_result(principal, "discord")


def test_trusted_adapter_requires_trusted_submit_scope() -> None:
    """trusted_adapter は observation.submit_trusted がないと trusted ingress 不可。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.TRUSTED_ADAPTER,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(account_ref_provider="cli"),
        )


def _principal(
    *,
    kind: ClientKind,
    scopes: frozenset[AuthScope],
) -> ClientPrincipal:
    return ClientPrincipal(
        client_id="client-1",
        client_kind=kind,
        provider="cli",
        allowed_providers=frozenset({"cli"}),
        scopes=scopes,
        observation_capabilities=frozenset(),
        authenticated=True,
    )
