"""gRPC mapper packageの公開API。"""

from __future__ import annotations

from iris.adapters.grpc.mappers.common import GrpcMappingError, timestamp_from_datetime
from iris.adapters.grpc.mappers.delivery import (
    delivery_envelope_to_proto,
    delivery_envelopes_to_poll_response,
    delivery_id_from_report_proto,
    delivery_report_from_proto,
)
from iris.adapters.grpc.mappers.errors import map_exception_to_grpc, map_provider_error_to_status
from iris.adapters.grpc.mappers.observations import (
    GrpcRuntimeMapper,
    RuntimeIngressProfile,
    delivery_route_hint_from_context,
    external_account_ref_from_proto,
    external_space_ref_from_proto,
    identity_from_proto,
)
from iris.adapters.grpc.mappers.outputs import presented_output_to_proto

__all__ = (
    "GrpcMappingError",
    "GrpcRuntimeMapper",
    "RuntimeIngressProfile",
    "delivery_envelope_to_proto",
    "delivery_envelopes_to_poll_response",
    "delivery_id_from_report_proto",
    "delivery_report_from_proto",
    "delivery_route_hint_from_context",
    "external_account_ref_from_proto",
    "external_space_ref_from_proto",
    "identity_from_proto",
    "map_exception_to_grpc",
    "map_provider_error_to_status",
    "presented_output_to_proto",
    "timestamp_from_datetime",
)
