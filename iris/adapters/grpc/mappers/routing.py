"""Observation contextからdelivery routing情報への変換。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.adapters.grpc.mappers.common import raise_mapping_error
from iris.contracts.delivery import DeliveryRouteHint, DeliverySurface
from iris.core.ids import ExternalRef
from iris.generated.iris.api.v1 import spaces_pb2

if TYPE_CHECKING:
    from iris.generated.iris.api.v1 import observations_pb2


def delivery_route_hint_from_context(
    context: observations_pb2.ObservationContext,
) -> DeliveryRouteHint | None:
    """Provider routing fieldsをObservationContext外へ保持する。

    Returns:
        refsがある場合はdelivery route hint、ない場合はNone。
    """
    provider = _route_provider_from_context(context)
    if provider is None:
        return None
    provider_subject = (
        ExternalRef(context.account_ref.provider_subject)
        if context.HasField("account_ref") and context.account_ref.provider_subject
        else None
    )
    provider_space_ref = (
        ExternalRef(context.space_ref.provider_space_ref)
        if context.HasField("space_ref") and context.space_ref.provider_space_ref
        else None
    )
    display_name = None
    if context.HasField("account_ref") and context.account_ref.display_name:
        display_name = context.account_ref.display_name
    elif context.HasField("space_ref") and context.space_ref.display_name:
        display_name = context.space_ref.display_name
    return DeliveryRouteHint(
        provider=provider,
        provider_subject=provider_subject,
        provider_space_ref=provider_space_ref,
        display_name=display_name,
        surface=_surface_from_context(context),
    )


def _route_provider_from_context(
    context: observations_pb2.ObservationContext,
) -> str | None:
    """参照が持つdelivery providerを返す。

    Returns:
        account/space参照が持つprovider。参照がない場合はNone。
    """
    account_provider = context.account_ref.provider if context.HasField("account_ref") else ""
    space_provider = context.space_ref.provider if context.HasField("space_ref") else ""
    if account_provider and space_provider and account_provider != space_provider:
        raise_mapping_error("account_ref.provider space_ref.provider mismatch")
    return account_provider or space_provider or None


def _surface_from_context(context: observations_pb2.ObservationContext) -> DeliverySurface:
    """External space kind を provider-neutral delivery surface へ写像する。

    Returns:
        DeliverySurface: provider-neutral な delivery surface。
    """
    if not context.HasField("space_ref"):
        return DeliverySurface.UNKNOWN
    return {
        spaces_pb2.SPACE_KIND_DIRECT_MESSAGE: DeliverySurface.PRIVATE_DIRECT_MESSAGE,
        spaces_pb2.SPACE_KIND_TEXT_CHANNEL: DeliverySurface.PUBLIC_CHANNEL,
        spaces_pb2.SPACE_KIND_THREAD: DeliverySurface.PUBLIC_CHANNEL,
        spaces_pb2.SPACE_KIND_ROOM: DeliverySurface.PUBLIC_CHANNEL,
        spaces_pb2.SPACE_KIND_BROADCAST: DeliverySurface.PUBLIC_CHANNEL,
        spaces_pb2.SPACE_KIND_VOICE_CHANNEL: DeliverySurface.VOICE,
    }.get(context.space_ref.space_kind, DeliverySurface.UNKNOWN)
