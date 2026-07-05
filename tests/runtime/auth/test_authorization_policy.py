"""Runtime authorization policy tests."""

from __future__ import annotations

import pytest

from iris.runtime.auth.errors import RuntimePermissionDeniedError
from iris.runtime.auth.policy import ObservationRequestClaims, RuntimeAuthorizationPolicy
from iris.runtime.auth.principals import ClientKind, ClientPrincipal
from iris.runtime.auth.scopes import AuthScope
from iris.runtime.ingress.observation_ingress import ObservationCapability


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


@pytest.mark.parametrize(
    "claims",
    [
        ObservationRequestClaims(account_ref_provider="cli", has_actor=True),
        ObservationRequestClaims(account_ref_provider="cli", has_account_id=True),
        ObservationRequestClaims(space_ref_provider="cli", has_space_id=True),
    ],
)
def test_trusted_adapter_submit_denies_internal_identity_claims(
    claims: ObservationRequestClaims,
) -> None:
    """trusted_adapter も internal actor/account/space id を直接 claim できない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.TRUSTED_ADAPTER,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(principal, claims)


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


def test_account_and_space_provider_mismatch_denied() -> None:
    """account_ref.provider と space_ref.provider の不一致は principal 権限前に拒否される。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.TRUSTED_ADAPTER,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(
                account_ref_provider="cli",
                space_ref_provider="discord",
            ),
        )


def test_poll_and_report_require_provider_scope() -> None:
    """Delivery poll/report は scope と provider 所有権を要求する。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.TRUSTED_ADAPTER,
        scopes=frozenset({AuthScope.DELIVERY_POLL, AuthScope.DELIVERY_REPORT}),
    )

    policy.require_poll_app_actions(principal, "cli")
    policy.require_report_action_result(principal, "cli")
    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_poll_app_actions(principal, "discord")
    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_report_action_result(principal, "discord")


def test_trusted_adapter_submit_requires_external_provider_claim() -> None:
    """trusted_adapter SubmitObservation は provider refs なしで provider policy を迂回できない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.TRUSTED_ADAPTER,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(principal, ObservationRequestClaims())


def test_trusted_adapter_requires_trusted_submit_scope() -> None:
    """trusted_adapter は observation.submit.trusted がないと trusted ingress 不可。"""
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


def test_external_client_cannot_use_trusted_submit_scope() -> None:
    """external_client は trusted-only scope だけでは SubmitObservation できない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.EXTERNAL_CLIENT,
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(account_ref_provider="cli"),
        )


def test_trusted_adapter_admin_scope_does_not_escalate() -> None:
    """trusted_adapter に admin.runtime が混入しても admin 扱いしない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.TRUSTED_ADAPTER,
        scopes=frozenset({AuthScope.ADMIN_RUNTIME}),
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_poll_app_actions(principal, "cli")


def test_trusted_adapter_wildcard_provider_does_not_bypass_provider_policy() -> None:
    """trusted_adapter は wildcard provider で provider restriction を迂回できない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.TRUSTED_ADAPTER,
        provider="cli",
        allowed_providers=frozenset({"*"}),
        scopes=frozenset({AuthScope.DELIVERY_POLL}),
        observation_capabilities=frozenset(),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_poll_app_actions(principal, "discord")


def test_trusted_adapter_provider_profile_mismatch_denied_without_request_provider() -> None:
    """trusted_adapter は provider/allowed_providers 不整合でも SubmitObservation できない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.TRUSTED_ADAPTER,
        provider="discord",
        allowed_providers=frozenset({"slack"}),
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
        observation_capabilities=frozenset(),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(principal, ObservationRequestClaims())


def test_external_client_wildcard_provider_denied_without_request_provider() -> None:
    """external_client は provider claim がなくても wildcard allowed_providers を使えない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.EXTERNAL_CLIENT,
        provider="cli",
        allowed_providers=frozenset({"*"}),
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT}),
        observation_capabilities=frozenset(),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(principal, ObservationRequestClaims())


def test_trusted_adapter_provider_profile_mismatch_denies_poll_and_report() -> None:
    """trusted_adapter の provider/allowed_providers 不整合は delivery RPC でも拒否する。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.TRUSTED_ADAPTER,
        provider="discord",
        allowed_providers=frozenset({"slack"}),
        scopes=frozenset({AuthScope.DELIVERY_POLL, AuthScope.DELIVERY_REPORT}),
        observation_capabilities=frozenset(),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_poll_app_actions(principal, "slack")
    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_report_action_result(principal, "slack")


def test_trusted_adapter_internal_capability_denies_poll_and_report() -> None:
    """internal-only capability 混入は delivery RPC でも拒否する。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.TRUSTED_ADAPTER,
        provider="cli",
        allowed_providers=frozenset({"cli"}),
        scopes=frozenset({AuthScope.DELIVERY_POLL, AuthScope.DELIVERY_REPORT}),
        observation_capabilities=frozenset({ObservationCapability.INTERNAL_EVENT}),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_poll_app_actions(principal, "cli")
    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_report_action_result(principal, "cli")


def test_trusted_adapter_internal_event_capability_denied() -> None:
    """trusted_adapter は internal-only observation capability を持てない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.TRUSTED_ADAPTER,
        provider="cli",
        allowed_providers=frozenset({"cli"}),
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT_TRUSTED}),
        observation_capabilities=frozenset({ObservationCapability.INTERNAL_EVENT}),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(account_ref_provider="cli"),
        )


def test_external_client_capability_denied_by_policy() -> None:
    """external_client は programmatic principal 経路でも capabilities を持てない。"""
    policy = RuntimeAuthorizationPolicy()
    principal = ClientPrincipal(
        client_id="client-1",
        client_kind=ClientKind.EXTERNAL_CLIENT,
        provider="cli",
        allowed_providers=frozenset({"cli"}),
        scopes=frozenset({AuthScope.OBSERVATION_SUBMIT}),
        observation_capabilities=frozenset({ObservationCapability.INTEGRATE_ACTIVITY}),
        authenticated=True,
    )

    with pytest.raises(RuntimePermissionDeniedError):
        policy.require_submit_observation(
            principal,
            ObservationRequestClaims(account_ref_provider="cli"),
        )


def test_admin_runtime_scope_is_admin_only() -> None:
    """Admin principal のみ admin.runtime で各 RPC scope を満たせる。"""
    policy = RuntimeAuthorizationPolicy()
    principal = _principal(
        kind=ClientKind.ADMIN,
        scopes=frozenset({AuthScope.ADMIN_RUNTIME}),
    )

    policy.require_submit_observation(
        principal,
        ObservationRequestClaims(account_ref_provider="cli"),
    )
    policy.require_poll_app_actions(principal, "cli")
    policy.require_report_action_result(principal, "cli")


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
