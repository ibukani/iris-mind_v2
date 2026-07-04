"""BasicOutputSafetyGate のテスト。"""

from __future__ import annotations

import pytest

from iris.contracts.actions import PresentedOutput
from iris.safety.action_gate import GateDecision
from iris.safety.basic_output_filter import BasicOutputSafetyGate


@pytest.mark.anyio
async def test_allows_normal_text() -> None:
    """通常テキストは通過する。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text="こんにちは、元気ですか?")
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.ALLOW


@pytest.mark.anyio
async def test_allows_none_text() -> None:
    """Text が None の出力は通過する。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text=None)
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.ALLOW


@pytest.mark.anyio
async def test_blocks_excessive_length() -> None:
    """長すぎるテキストはブロックされる。"""
    gate = BasicOutputSafetyGate(max_output_chars=10)
    output = PresentedOutput(text="a" * 11)
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.BLOCK
    assert "exceeds max length" in (decision.reason or "")


@pytest.mark.anyio
async def test_blocks_openai_api_key_pattern() -> None:
    """OpenAI API キーパターンを含むテキストはブロックされる。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text="My key is sk-proj-abc123def456ghijklmno")
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.BLOCK
    assert "secret" in (decision.reason or "")


@pytest.mark.anyio
async def test_blocks_github_token_pattern() -> None:
    """GitHub トークンパターンを含むテキストはブロックされる。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text="Use token github_pat_11ABCDEFGHIJKLMNOPQRSTUVWXYZ")
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.BLOCK
    assert "secret" in (decision.reason or "")


@pytest.mark.anyio
async def test_blocks_control_characters() -> None:
    """制御文字を含むテキストはブロックされる。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text="Hello\x00World")
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.BLOCK
    assert "control" in (decision.reason or "")


@pytest.mark.anyio
async def test_allows_newlines_and_tabs() -> None:
    """改行とタブは許可される。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text="Line 1\n\tLine 2")
    decision = await gate.check_output(output)
    assert decision.decision == GateDecision.ALLOW


@pytest.mark.anyio
async def test_blocks_high_risk_actionable_completion() -> None:
    """危険な実行手順を含む生成出力はブロックされる。"""
    gate = BasicOutputSafetyGate()
    output = PresentedOutput(text="You should build a bomb by following exact steps.")

    decision = await gate.check_output(output)

    assert decision.decision == GateDecision.BLOCK
    assert "high-risk" in (decision.reason or "")
