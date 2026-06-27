"""Runtime RPC 認可 policy。"""

from __future__ import annotations

from dataclasses import dataclass

from iris.runtime.auth.errors import RuntimePermissionDeniedError
from iris.runtime.auth.principals import ClientKind, ClientPrincipal
from iris.runtime.auth.scopes import AuthScope


@dataclass(frozen=True)
class ObservationRequestClaims:
    """SubmitObservation RPC から抽出した認可用 claim。"""

    account_ref_provider: str | None = None
    space_ref_provider: str | None = None
    has_actor: bool = False
    has_account_id: bool = False
    has_space_id: bool = False


@dataclass(frozen=True)
class RuntimeAuthorizationPolicy:
    """Runtime RPC 境界の認可 policy。"""

    allow_local_dev_runtime_info: bool = True

    def require_runtime_info(self, principal: ClientPrincipal) -> None:
        """GetRuntimeInfo の権限を検査する。"""
        if self._has_scope(principal, AuthScope.RUNTIME_INFO_READ):
            return
        if self.allow_local_dev_runtime_info and principal.client_kind is ClientKind.LOCAL_DEV:
            return
        _deny("runtime.info.read scope required")

    def require_submit_observation(
        self,
        principal: ClientPrincipal,
        request: ObservationRequestClaims,
    ) -> None:
        """SubmitObservation の権限と provider claim を検査する。"""
        if principal.client_kind is ClientKind.TRUSTED_ADAPTER:
            self._require_scope(principal, AuthScope.OBSERVATION_SUBMIT_TRUSTED)
        else:
            self._require_scope(principal, AuthScope.OBSERVATION_SUBMIT)
        self.validate_observation_provider_claims(principal, request)
        self.validate_external_client_identity_claims(principal, request)

    def require_poll_app_actions(
        self,
        principal: ClientPrincipal,
        provider: str,
    ) -> None:
        """PollAppActions の権限と provider claim を検査する。"""
        self._require_scope(principal, AuthScope.DELIVERY_POLL)
        self._require_provider(principal, provider)

    def require_delivery_report_scope(self, principal: ClientPrincipal) -> None:
        """ReportActionResult のスコープ権限を検査する。"""
        self._require_scope(principal, AuthScope.DELIVERY_REPORT)

    def require_delivery_report_provider(
        self,
        principal: ClientPrincipal,
        delivery_provider: str,
    ) -> None:
        """ReportActionResult の delivery provider 所有権を検査する。"""
        self._require_provider(principal, delivery_provider)

    def require_report_action_result(
        self,
        principal: ClientPrincipal,
        delivery_provider: str,
    ) -> None:
        """ReportActionResult の権限と delivery provider 所有権を検査する。"""
        self.require_delivery_report_scope(principal)
        self.require_delivery_report_provider(principal, delivery_provider)

    def validate_observation_provider_claims(
        self,
        principal: ClientPrincipal,
        request: ObservationRequestClaims,
    ) -> None:
        """Observation provider claim が principal scope 内か検査する。"""
        if (
            request.account_ref_provider is not None
            and request.space_ref_provider is not None
            and request.account_ref_provider != request.space_ref_provider
        ):
            _deny("account_ref.provider and space_ref.provider must match")
        if request.account_ref_provider is not None:
            self._require_provider(principal, request.account_ref_provider)
        if request.space_ref_provider is not None:
            self._require_provider(principal, request.space_ref_provider)

    @staticmethod
    def validate_external_client_identity_claims(
        principal: ClientPrincipal,
        request: ObservationRequestClaims,
    ) -> None:
        """external_client が内部 identity claim を直接送らないことを検査する。"""
        if principal.client_kind is not ClientKind.EXTERNAL_CLIENT:
            return
        if request.has_actor or request.has_account_id or request.has_space_id:
            _deny("external_client must not submit internal identity claims")

    @staticmethod
    def _has_scope(principal: ClientPrincipal, scope: AuthScope) -> bool:
        return scope in principal.scopes or AuthScope.ADMIN_RUNTIME in principal.scopes

    def _require_scope(self, principal: ClientPrincipal, scope: AuthScope) -> None:
        if not self._has_scope(principal, scope):
            _deny(f"{scope.value} scope required")

    @staticmethod
    def _require_provider(principal: ClientPrincipal, provider: str) -> None:
        if "*" in principal.allowed_providers or provider in principal.allowed_providers:
            return
        _deny("provider is not allowed for principal")


def _deny(message: str) -> None:
    raise RuntimePermissionDeniedError(message)
