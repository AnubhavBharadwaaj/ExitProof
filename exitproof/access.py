"""F2 Leaver Access Graph, F3 Shared Secret Rotation, F4 Proof of Revocation.

Evidence behind these features (docs/EVIDENCE.md):
  L2  four teams each remove only their own slice on the last day; nobody holds the full list.
  L4  access a team set up for itself is left to that team; a central disable does not touch it.
  L5  an authenticator keeps producing valid codes for a shared login until the MFA seed is enrolled again.
  L8  third party benefit cards stay live after exit.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

CENTRAL_TEAMS = {"identity_pam", "email", "it_desktop", "physical_security"}

# Revoke order: things that act on their own first, the account that would let someone notice last.
REVOKE_ORDER = ["ai_or_token", "shared_login", "team_owned", "third_party", "central"]


@dataclass
class AccessItem:
    id: str
    kind: str
    system: str
    owner_team: str
    mfa: str | None = None
    needs_attestation: bool = False
    revoke_actions: list[str] = field(default_factory=list)
    disabled_at: dt.datetime | None = None


def build_graph(employee: dict) -> list[AccessItem]:
    """Every item the leaver can reach, with an owner and the actions that really remove it."""
    items = []
    for raw in employee["access"]:
        item = AccessItem(
            id=raw["id"], kind=raw["kind"], system=raw["system"], owner_team=raw["owner_team"], mfa=raw.get("mfa")
        )
        item.needs_attestation = item.owner_team not in CENTRAL_TEAMS
        item.revoke_actions = revoke_actions_for(item)
        items.append(item)
    items.sort(key=lambda i: REVOKE_ORDER.index(i.kind))
    return items


def revoke_actions_for(item: AccessItem) -> list[str]:
    if item.kind == "shared_login":
        actions = ["rotate_password"]
        if item.mfa:
            actions.append("enrol_new_mfa_seed")  # F3: a new password alone does not evict the leaver
        actions.append("record_new_seed_holder")
        return actions
    if item.kind == "ai_or_token":
        return ["revoke_token", "disable_agent_runs"]
    if item.kind == "third_party":
        return ["cancel_with_provider"]
    if item.kind == "team_owned":
        return ["rotate_or_delete_key", "team_lead_attests"]
    return ["disable_account"]


def orphan_items(items: list[AccessItem]) -> list[AccessItem]:
    """Items no central exit team would touch: the leaks of L2 and L4."""
    return [i for i in items if i.owner_team not in CENTRAL_TEAMS]


def rotation_complete(item: AccessItem, done_actions: set[str]) -> bool:
    """F3: a shared login with MFA is only closed when the seed was enrolled again."""
    return set(item.revoke_actions) <= done_actions


def proof_of_revocation(items: list[AccessItem], usage_log: list[dict], check_time: dt.datetime) -> list[dict]:
    """F4: compare disabled_at with last_used. Any use after disable is an exception for the SOC."""
    last_used = {u["item"]: dt.datetime.fromisoformat(u["last_used"]) for u in usage_log}
    exceptions = []
    for item in items:
        used = last_used.get(item.id)
        if item.disabled_at is None:
            exceptions.append({"item": item.id, "system": item.system, "reason": "not_disabled", "owner": item.owner_team})
        elif used and used > item.disabled_at and used <= check_time:
            exceptions.append(
                {
                    "item": item.id,
                    "system": item.system,
                    "reason": "used_after_disable",
                    "disabled_at": item.disabled_at.isoformat(),
                    "last_used": used.isoformat(),
                    "owner": item.owner_team,
                }
            )
    return exceptions
