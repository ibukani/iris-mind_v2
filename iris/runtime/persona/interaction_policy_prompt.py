"""Approved interaction policy の prompt section adapter."""

from __future__ import annotations

from typing import TYPE_CHECKING

from iris.contracts.prompting import PromptSectionInput, PromptSectionKind, PromptTrustBoundary

if TYPE_CHECKING:
    from iris.contracts.interaction_policy import ApprovedInteractionPolicy
    from iris.core.ids import AccountId, SpaceId


def build_interaction_policy_section(
    policies: tuple[ApprovedInteractionPolicy, ...],
    *,
    account_id: AccountId,
    space_id: SpaceId | None,
) -> PromptSectionInput | None:
    """Scope に一致する approved policy を #91 section として表現する。

    Section budget の適用は caller の共通 ``RuntimePromptAssembler`` に委ねる。
    この adapter は global persona section を変更せず、policy section だけを返す。

    Returns:
        Scope に一致する interaction policy section。候補がない場合は ``None``。
    """
    selected = _select_policies(policies, account_id=account_id, space_id=space_id)
    if not selected:
        return None
    return PromptSectionInput(
        kind=PromptSectionKind.INTERACTION_POLICY,
        title="Approved interaction policy",
        trust_boundary=PromptTrustBoundary.INTERNAL_DERIVED,
        items=tuple(f"{policy.policy_kind.value}: {policy.value}" for policy in selected),
    )


def interaction_policy_constraints(
    policies: tuple[ApprovedInteractionPolicy, ...],
    *,
    account_id: AccountId,
    space_id: SpaceId | None,
) -> tuple[str, ...]:
    """ResponsePrompt.constraints へ渡す scoped policy instructions を返す。

    Returns:
        Scope に一致する policy instruction 列。
    """
    section = build_interaction_policy_section(
        policies,
        account_id=account_id,
        space_id=space_id,
    )
    return () if section is None else section.items


def _select_policies(
    policies: tuple[ApprovedInteractionPolicy, ...],
    *,
    account_id: AccountId,
    space_id: SpaceId | None,
) -> tuple[ApprovedInteractionPolicy, ...]:
    selected: dict[str, ApprovedInteractionPolicy] = {}
    for policy in policies:
        if policy.account_id != account_id:
            continue
        if policy.space_id is not None and policy.space_id != space_id:
            continue
        # space-specific policy deterministically overrides account-wide policy.
        key = policy.policy_kind.value
        previous = selected.get(key)
        if previous is None or (previous.space_id is None and policy.space_id is not None):
            selected[key] = policy
    return tuple(selected[key] for key in sorted(selected))
