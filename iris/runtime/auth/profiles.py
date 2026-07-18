"""Runtime auth profile capability definitions."""

from __future__ import annotations

from iris.runtime.auth.scopes import AuthScope
from iris.runtime.ingress.observation_ingress import ObservationCapability

TRUSTED_ADAPTER_SCOPES = frozenset(
    {
        AuthScope.RUNTIME_INFO_READ,
        AuthScope.OBSERVATION_SUBMIT_TRUSTED,
        AuthScope.DELIVERY_POLL,
        AuthScope.DELIVERY_REPORT,
    }
)

EXTERNAL_CLIENT_FORBIDDEN_SCOPES = frozenset(
    {
        AuthScope.OBSERVATION_SUBMIT_TRUSTED,
        AuthScope.DELIVERY_POLL,
        AuthScope.DELIVERY_REPORT,
        AuthScope.TRANSCRIPT_CLEANUP,
        AuthScope.ADMIN_RUNTIME,
    }
)

TRUSTED_ADAPTER_OBSERVATION_CAPABILITIES = frozenset(
    {
        ObservationCapability.INTEGRATE_ACTIVITY,
        ObservationCapability.INTEGRATE_PRESENCE,
        ObservationCapability.UPDATE_SPACE_OCCUPANCY,
    }
)
