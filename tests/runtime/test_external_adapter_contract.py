"""Runtime-level external adapter contract tests."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, override

import pytest

from iris.adapters.app_gateway.fake_resolvers import FakeIdentityResolver, FakeSpaceResolver
from iris.adapters.app_gateway.stable_ids import stable_account_id, stable_space_id
from iris.adapters.grpc.mappers import GrpcRuntimeMapper
from iris.contracts.actions import ActionResult, ActionStatus, PresentedOutput
from iris.contracts.delivery import DeliveryReport, DeliveryStatus
from iris.contracts.observations import (
    ActivityEventObservation,
    Observation,
    PresenceSignalObservation,
)
from iris.core.ids import ExternalRef
from iris.generated.iris.api.v1 import observations_pb2
from iris.runtime.app import IrisApp
from iris.runtime.delivery.broker import RuntimeAppActionBroker
from iris.runtime.delivery.in_memory import InMemoryDeliveryOutbox
from iris.runtime.service import IrisRuntimeService
from tests.helpers.external_adapter_contract import (
    CONTRACT_OCCURRED_AT,
    ExternalAdapterContractFixture,
    build_activity_event_request,
    build_actor_message_request,
    build_presence_signal_request,
    build_send_message_delivery,
    discord_voice_adapter_fixture,
    external_adapter_contract_fixtures,
    generic_text_adapter_fixture,
)

if TYPE_CHECKING:
    from iris.contracts.workspace_context import SituationContextSnapshot
    from iris.runtime.service import ObservationEnvelope

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize(
    "fixture", external_adapter_contract_fixtures(), ids=lambda item: item.name
)
async def test_external_refs_resolve_to_runtime_identity_and_space(
    fixture: ExternalAdapterContractFixture,
) -> None:
    """ExternalAccountRef and ExternalSpaceRef resolve before runtime processing."""
    envelope = await _map_actor_message(fixture)

    actor = envelope.observation.context.actor
    assert actor is not None
    assert actor.provider == fixture.provider
    assert actor.provider_subject == fixture.provider_subject
    assert actor.display_name == fixture.account_display_name
    assert actor.account_id == stable_account_id(fixture.provider, fixture.provider_subject)
    assert envelope.observation.context.account_id == actor.account_id
    assert envelope.observation.context.space_id == stable_space_id(
        fixture.provider,
        fixture.provider_space_ref,
    )


async def test_external_refs_are_stable_when_display_names_change() -> None:
    """Display names are mutable labels and do not affect account/space identity keys."""
    fixture = generic_text_adapter_fixture()
    renamed_fixture = replace(
        fixture,
        account_display_name="Renamed Generic User",
        space_display_name="Renamed Generic Room",
    )

    first = await _map_actor_message(fixture)
    second = await _map_actor_message(renamed_fixture)

    assert first.observation.context.account_id == second.observation.context.account_id
    assert first.observation.context.space_id == second.observation.context.space_id


async def test_provider_isolation_separates_same_external_ids() -> None:
    """Same provider-local ids under different providers resolve to isolated ids."""
    base = generic_text_adapter_fixture()
    first_fixture = replace(
        base,
        provider="adapter-a",
        source="adapter-a",
        provider_subject="same-user",
        provider_space_ref="same-space",
    )
    second_fixture = replace(
        base,
        provider="adapter-b",
        source="adapter-b",
        provider_subject="same-user",
        provider_space_ref="same-space",
    )

    first = await _map_actor_message(first_fixture)
    second = await _map_actor_message(second_fixture)

    assert first.observation.context.account_id != second.observation.context.account_id
    assert first.observation.context.space_id != second.observation.context.space_id


async def test_account_isolation_separates_same_provider_different_subjects() -> None:
    """Different provider subjects under one provider resolve to isolated account ids."""
    base = generic_text_adapter_fixture()
    first_fixture = replace(base, provider_subject="same-provider-user-a")
    second_fixture = replace(base, provider_subject="same-provider-user-b")

    first = await _map_actor_message(first_fixture)
    second = await _map_actor_message(second_fixture)

    assert first.observation.context.account_id != second.observation.context.account_id
    assert first.observation.context.space_id == second.observation.context.space_id


async def test_space_isolation_separates_same_provider_different_spaces() -> None:
    """Different provider spaces under one provider resolve to isolated runtime space ids."""
    base = generic_text_adapter_fixture()
    first_fixture = replace(base, provider_space_ref="same-provider-space-a")
    second_fixture = replace(base, provider_space_ref="same-provider-space-b")

    first = await _map_actor_message(first_fixture)
    second = await _map_actor_message(second_fixture)

    assert first.observation.context.account_id == second.observation.context.account_id
    assert first.observation.context.space_id != second.observation.context.space_id


@pytest.mark.parametrize(
    "fixture", external_adapter_contract_fixtures(), ids=lambda item: item.name
)
async def test_actor_message_observation_returns_presented_output(
    fixture: ExternalAdapterContractFixture,
) -> None:
    """Actor message observations route through IrisApp and return PresentedOutput."""
    app = _RecordingApp(text="contract reply")
    service = IrisRuntimeService(app)
    envelope = await _map_actor_message(fixture)

    response = await service.handle_observation(envelope)

    assert response.correlation_id == envelope.correlation_id
    assert response.output.text == "contract reply"
    assert app.observations == [envelope.observation]


@pytest.mark.parametrize(
    "fixture", external_adapter_contract_fixtures(), ids=lambda item: item.name
)
async def test_activity_event_observation_is_accepted_without_llm_or_app_call(
    fixture: ExternalAdapterContractFixture,
) -> None:
    """Activity event observations are accepted and default to no-send without app calls."""
    app = _RecordingApp(text="should not be used")
    service = IrisRuntimeService(app)
    envelope = await _mapper().observation_envelope_from_proto(
        build_activity_event_request(fixture)
    )

    response = await service.handle_observation(envelope)

    assert isinstance(envelope.observation, ActivityEventObservation)
    assert response.correlation_id == envelope.correlation_id
    assert not response.output.is_sendable
    assert response.output.text is None
    assert app.observations == []


@pytest.mark.parametrize(
    ("activity_kind", "reason"),
    [
        (observations_pb2.ACTIVITY_KIND_ACTOR_INPUT_STARTED, "recording"),
        (observations_pb2.ACTIVITY_KIND_ACTOR_INPUT_STARTED, "speaking"),
        (observations_pb2.ACTIVITY_KIND_APP_OUTPUT_STARTED, "tts_playback"),
    ],
)
async def test_discord_voice_activity_uses_generic_interaction_contract(
    activity_kind: observations_pb2.ActivityKind.ValueType,
    reason: str,
) -> None:
    """Discord recording/speaking/playbackをprovider-neutral activityで表す。"""
    fixture = discord_voice_adapter_fixture()
    envelope = await _mapper().observation_envelope_from_proto(
        build_activity_event_request(
            fixture,
            activity_kind=activity_kind,
            metadata={
                "modality": "voice",
                "reason": reason,
                "expires_at": "2026-07-04T12:01:00Z",
            },
        )
    )

    assert isinstance(envelope.observation, ActivityEventObservation)
    assert envelope.observation.context.actor_id is not None
    assert envelope.observation.context.space_id is not None
    assert envelope.observation.metadata["modality"] == "voice"
    assert envelope.observation.metadata["reason"] == reason


@pytest.mark.parametrize(
    "fixture", external_adapter_contract_fixtures(), ids=lambda item: item.name
)
async def test_presence_signal_observation_is_accepted_without_llm_or_app_call(
    fixture: ExternalAdapterContractFixture,
) -> None:
    """Presence signal observations are accepted and default to no-send without app calls."""
    app = _RecordingApp(text="should not be used")
    service = IrisRuntimeService(app)
    envelope = await _mapper().observation_envelope_from_proto(
        build_presence_signal_request(fixture)
    )

    response = await service.handle_observation(envelope)

    assert isinstance(envelope.observation, PresenceSignalObservation)
    assert response.correlation_id == envelope.correlation_id
    assert not response.output.is_sendable
    assert response.output.text is None
    assert app.observations == []


async def test_poll_app_actions_and_report_action_result_complete_due_action() -> None:
    """PollAppActions and ReportActionResult contract works through the runtime broker."""
    fixture = generic_text_adapter_fixture()
    outbox = InMemoryDeliveryOutbox()
    broker = RuntimeAppActionBroker(outbox=outbox)
    await outbox.enqueue(build_send_message_delivery(fixture))
    await outbox.enqueue(
        build_send_message_delivery(
            discord_voice_adapter_fixture(),
            delivery_id="discord-delivery-1",
            action_id="discord-action-1",
            correlation_id="discord-corr-1",
        )
    )

    leased = await broker.poll_actions(
        provider=fixture.provider,
        now=CONTRACT_OCCURRED_AT,
        max_items=10,
    )
    assert len(leased) == 1
    assert leased[0].target.provider == fixture.provider
    assert leased[0].target.provider_space_ref == fixture.provider_space_ref

    completed = await broker.report_action_result(
        DeliveryReport(
            delivery_id=leased[0].delivery_id,
            lease_id=leased[0].lease_id,
            result=ActionResult(
                action_id=leased[0].action.action_id,
                correlation_id=leased[0].action.correlation_id,
                status=ActionStatus.SUCCEEDED,
                delivered_at=CONTRACT_OCCURRED_AT,
                external_message_id=ExternalRef("external-msg-1"),
                error_reason=None,
            ),
            reported_at=CONTRACT_OCCURRED_AT,
        )
    )

    assert completed.status is DeliveryStatus.SUCCEEDED
    assert (
        await broker.poll_actions(
            provider=fixture.provider,
            now=CONTRACT_OCCURRED_AT,
            max_items=10,
        )
        == ()
    )


def test_discord_voice_fixture_is_only_one_generic_fixture_case() -> None:
    """Discord voice remains a representative fixture, not the whole contract."""
    fixtures = external_adapter_contract_fixtures()

    assert {fixture.name for fixture in fixtures} == {"generic_text", "discord_voice"}
    assert {fixture.provider for fixture in fixtures} == {"generic-chat", "discord"}


async def _map_actor_message(
    fixture: ExternalAdapterContractFixture,
) -> ObservationEnvelope:
    return await _mapper().observation_envelope_from_proto(build_actor_message_request(fixture))


def _mapper() -> GrpcRuntimeMapper:
    return GrpcRuntimeMapper(
        identity_resolver=FakeIdentityResolver(),
        space_resolver=FakeSpaceResolver(),
    )


class _RecordingApp(IrisApp):
    """IrisApp fake that records cognitive-route observations."""

    def __init__(self, *, text: str) -> None:
        self._text = text
        self.observations: list[Observation] = []

    @override
    async def process_observation(
        self,
        observation: Observation,
        *,
        situation_context: SituationContextSnapshot | None = None,
    ) -> PresentedOutput:
        """Record observation and return deterministic output.

        Returns:
            Fixed PresentedOutput.
        """
        _ = situation_context
        self.observations.append(observation)
        return PresentedOutput(text=self._text)
