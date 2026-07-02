"""Iris契約全体で使用するNewType ID定義。"""

from __future__ import annotations

from typing import NewType

ObservationId = NewType("ObservationId", str)
ActivityId = NewType("ActivityId", str)
ActionId = NewType("ActionId", str)
DeliveryId = NewType("DeliveryId", str)
LeaseId = NewType("LeaseId", str)
TurnId = NewType("TurnId", str)
SessionId = NewType("SessionId", str)
ConversationId = NewType("ConversationId", str)
TranscriptId = NewType("TranscriptId", str)
CorrelationId = NewType("CorrelationId", str)
ExternalRef = NewType("ExternalRef", str)
AccountId = NewType("AccountId", str)
ActorId = NewType("ActorId", str)
DeviceId = NewType("DeviceId", str)
SpaceId = NewType("SpaceId", str)
