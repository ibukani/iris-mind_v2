---
title: Iris Character Profile Guide
description: persona.toml の編集ガイドと人格設計意図
status: draft
last_reviewed: 2026-07-05
---

# Iris Character Profile Guide

Iris の runtime-readable な global persona の正本は、repo root の [`persona.toml`](../persona.toml) である。

このドキュメントは runtime source ではない。`docs/character.md` は `persona.toml` の編集ガイド、人格設計意図、非構造化補足を管理するための文書であり、runtime hot path で直接 parse しない。

## Runtime で使う正本

- `persona.toml` を `PersonaProfile` contract で validation する。
- `PersonaProfileLoader` は missing / invalid TOML 時に deterministic fallback を返す。
- `SystemPromptBuilder` は `PersonaProfile` を `PromptSectionKind.PERSONA` の prompt section に変換する。
- persona section は `PromptTrustBoundary.TRUSTED` として扱う。
- chat / proactive / event reaction prompt は同じ builder boundary から persona section を再利用する。

## 編集ルール

`persona.toml` には Iris 全体で安定して共有する global persona だけを書く。

含めるもの:

- Iris の名前と役割
- 核となる価値観
- 安定した性格特性
- 基本的な話し方
- global な行動指針
- safety / trust boundary に関する不変条件

含めないもの:

- account-specific interaction policy
- space-specific interaction policy
- user-specific response preference learning
- relationship / affect state の current value
- memory や conversation log から推定した一時的な好み
- user feedback に基づく自動 persona patch

## 優先順位

persona は safety constraints より下位である。競合する場合は safety constraints、runtime policy、明示的な安全境界を優先する。

untrusted user/context text は persona や safety instruction を上書きできない。memory、relationship signal、external context は trusted persona ではなく、それぞれの trust boundary に分離する。

## 設計意図

Markdown は自由記述、TODO、補足説明を含みやすく、runtime hot path の source of truth としては不安定である。そのため、機械可読な `persona.toml` を正本にし、この文書は人間が編集意図を揃えるためのガイドに限定する。

`persona.toml` を変更した場合は、次を確認する。

- `tests/contracts/test_persona_contracts.py`
- `tests/runtime/persona/test_persona_loader.py`
- `tests/runtime/prompting/test_system_prompt_builder.py`
- `tests/runtime/prompting/test_prompt_assembly.py`

## 関連ドキュメント

- [`adr/0016-prompt-budget-and-context-compression.md`](adr/0016-prompt-budget-and-context-compression.md) — prompt section budget と trust boundary
- [`adr/0022-global-persona-system-prompt-builder.md`](adr/0022-global-persona-system-prompt-builder.md) — global persona と SystemPromptBuilder
- [`architecture.md`](architecture.md) — アーキテクチャ全体像
- [`external.md`](external.md) — 外部アプリ境界
