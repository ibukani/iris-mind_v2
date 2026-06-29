"""v0.1向け最小限のワンターンコグニティブランタイムフローテスト。

以下のエンドツーエンドパスをテストする:
  ActorMessageObservation
  → CognitiveCycle (PerceptionStep → ActionSelectionStep)
  → ActionSafetyGate
  → SimplePresenter
  → OutputSafetyGate
  → PresentedOutput
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from iris.cognitive.perception.basic import SimplePerceptionStep
from iris.contracts.actions import ActionPlan, PresentedOutput
from iris.contracts.observations import ActorMessageObservation, ObservationContext, ObservationKind
from iris.core.ids import ObservationId, SessionId
from iris.features.basic_action.definition import SimpleActionSelectionStep
from iris.runtime.app import IrisApp
from iris.safety.action_gate import GateDecision, SafetyDecision
from tests.helpers.output_pipeline import make_output_pipeline


@pytest.fixture
def app() -> IrisApp:
    """デフォルトの知覚ステップとアクションステップを持つIrisAppを返す。

    Returns:
        IrisApp: 設定済みのIrisAppインスタンス。
    """
    return IrisApp(
        steps=[SimplePerceptionStep(), SimpleActionSelectionStep()],
        output_pipeline=make_output_pipeline(),
    )


@pytest.fixture
def actor_message() -> ActorMessageObservation:
    """サンプルのアクターメッセージ観測を返す。

    Returns:
        ActorMessageObservation: サンプルの観測インスタンス。
    """
    return ActorMessageObservation(
        observation_id=ObservationId("obs-1"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.ACTOR_MESSAGE,
        text="Hello, Iris!",
    )


@pytest.mark.anyio
async def test_one_turn_flow_returns_presented_output(
    app: IrisApp, actor_message: ActorMessageObservation
) -> None:
    """基本的なワンターンフローが入力テキストを含むPresentedOutputを返すことを確認する。"""
    result = await app.process_observation(actor_message)
    assert isinstance(result, PresentedOutput)
    assert result.text == "Hello, Iris!"


@pytest.mark.anyio
async def test_one_turn_flow_with_empty_text_returns_presented_output(app: IrisApp) -> None:
    """空テキストでもPresentedOutputが生成されることを確認する。"""
    idle = ActorMessageObservation(
        observation_id=ObservationId("obs-2"),
        session_id=SessionId("session-1"),
        context=ObservationContext(),
        occurred_at=datetime.now(UTC),
        kind=ObservationKind.IDLE_TICK,
        text="",
    )
    result = await app.process_observation(idle)
    assert isinstance(result, PresentedOutput)


@pytest.mark.anyio
async def test_action_safety_gate_blocks(actor_message: ActorMessageObservation) -> None:
    """ブロックするアクションセーフティゲートがNoneテキストのPresentedOutputを生成することを確認する。"""

    class BlockingGate:
        async def check_plan(self, plan: ActionPlan) -> SafetyDecision:
            _ = self, plan
            return SafetyDecision(decision=GateDecision.BLOCK, reason="test block")

    app = IrisApp(
        steps=[SimplePerceptionStep(), SimpleActionSelectionStep()],
        output_pipeline=make_output_pipeline(action_gate=BlockingGate()),
    )
    result = await app.process_observation(actor_message)
    assert isinstance(result, PresentedOutput)
    assert result.text is None


@pytest.mark.anyio
async def test_output_safety_gate_blocks(actor_message: ActorMessageObservation) -> None:
    """ブロックする出力セーフティゲートがNoneテキストのPresentedOutputを生成することを確認する。"""

    class BlockingGate:
        async def check_output(self, output: PresentedOutput) -> SafetyDecision:
            _ = self, output
            return SafetyDecision(decision=GateDecision.BLOCK, reason="test block")

    app = IrisApp(
        steps=[SimplePerceptionStep(), SimpleActionSelectionStep()],
        output_pipeline=make_output_pipeline(output_gate=BlockingGate()),
    )
    result = await app.process_observation(actor_message)
    assert isinstance(result, PresentedOutput)
    assert result.text is None
