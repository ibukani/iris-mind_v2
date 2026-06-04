"""Iris契約全体で使用するNewType ID定義。"""

from __future__ import annotations

from typing import NewType

ObservationId = NewType("ObservationId", str)
ActionId = NewType("ActionId", str)
TurnId = NewType("TurnId", str)
SessionId = NewType("SessionId", str)
ConversationId = NewType("ConversationId", str)
CorrelationId = NewType("CorrelationId", str)
ExternalRef = NewType("ExternalRef", str)
AccountId = NewType("AccountId", str)
ActorId = NewType("ActorId", str)
DeviceId = NewType("DeviceId", str)
SpaceId = NewType("SpaceId", str)
