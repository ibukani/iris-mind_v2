"""Shared safety helpers for long-term memory candidates."""

from __future__ import annotations

import re

_MAX_PREFERRED_NAME_LENGTH = 40

CREDENTIAL_LIKE_PATTERNS = (
    r"api\s*" + "key",
    "api" + "key",
    "sec" + "ret",
    "tok" + "en",
    "pass" + "word",
    "pass" + "wd",
    "bear" + "er",
    "OPENAI" + "_API_KEY",
    r"sk-",
    "github" + "_pat_",
    "パス" + "ワード",
    "トー" + "クン",
    "秘密" + "鍵",
    "認証" + "情報",
    "API" + r"\s*" + "キー",
    "api" + r"\s*" + "キー",
)

SENSITIVE_PROFILE_PATTERNS = (
    r"うつ病",
    r"鬱病",
    r"統合失調症",
    r"双極性障害",
    r"発達障害",
    r"ADHD",
    r"自閉",
    r"癌",
    r"がん患者",
    r"キリスト教徒",
    r"イスラム教徒",
    r"ユダヤ教徒",
    r"仏教徒",
    r"右翼",
    r"左翼",
    r"保守派",
    r"リベラル",
    r"自民党支持",
    r"共産党支持",
    r"ゲイ",
    r"レズビアン",
    r"バイセクシュアル",
    r"トランスジェンダー",
    r"LGBT",
    r"depression",
    r"depressed",
    r"schizophrenia",
    r"bipolar",
    r"autistic",
    r"cancer",
    r"Christian",
    r"Muslim",
    r"Jewish",
    r"Buddhist",
    r"conservative",
    r"liberal",
    r"Democrat",
    r"Republican",
    r"gay",
    r"lesbian",
    r"bisexual",
    r"transgender",
)

_UNSAFE_PREFERRED_NAME_VALUE_PATTERNS = (
    r"^(?:この|その|あの)(?:変数|プロジェクト|関数|クラス|名前|値|対象|項目)を.+",
    r"^(?:これ|それ|あれ|彼|彼女)を.+",
    r"\b(?:this|that|him|her|them|variable|project|function|class)\b",
)

_UNSAFE_PREFERRED_NAME_MEMORY_PATTERNS = (
    r"^ユーザーの希望呼称は「(?:この|その|あの)(?:変数|プロジェクト|関数|クラス|名前|値|対象|項目)を.+」。$",
    r"^ユーザーの希望呼称は「(?:これ|それ|あれ|彼|彼女)を.+」。$",
    r"^User's preferred name is (?:this|that|him|her|them|variable|project|function|class)\b",
)


def contains_credential_like_content(value: str) -> bool:
    """Return whether text appears to contain credential-like material."""
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in CREDENTIAL_LIKE_PATTERNS)


def contains_sensitive_profile_content(value: str) -> bool:
    """Return whether profile-like text contains sensitive attributes."""
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in SENSITIVE_PROFILE_PATTERNS)


def is_safe_preferred_name(value: str) -> bool:
    """Return whether a captured preferred-name value is safe to store."""
    stripped = value.strip()
    if not stripped or len(stripped) > _MAX_PREFERRED_NAME_LENGTH:
        return False
    return not any(
        re.search(pattern, stripped, re.IGNORECASE)
        for pattern in _UNSAFE_PREFERRED_NAME_VALUE_PATTERNS
    )


def is_unsafe_preferred_name_memory_text(text: str) -> bool:
    """Return whether normalized preferred-name memory text is object labeling."""
    return any(
        re.search(pattern, text, re.IGNORECASE)
        for pattern in _UNSAFE_PREFERRED_NAME_MEMORY_PATTERNS
    )
