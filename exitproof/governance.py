"""Governance primitives the brief makes non negotiable.

  * Reserved decisions: an agent can never complete them; the list is config HR can extend.
  * Hash chained audit log: every action records inputs, rule or prompt version, model and outcome.
  * Idempotency: a retried payment or revoke returns the first result instead of acting twice.
  * Kill switch: HR pauses any workflow or skill with no code change.
  * PII masking: PAN, bank account and names are masked before any model call.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field

from .rules import ROOT, load_yaml

MINIMUM_RESERVED = {"resignation.accept", "exit.release_date_or_buyout", "payroll.settlement_signoff", "complaint.posh"}


class ReservedDecisionError(PermissionError):
    pass


class PausedError(RuntimeError):
    pass


# ---------------------------------------------------------------- reserved decisions
@dataclass
class ReservedDecisions:
    config: dict = field(default_factory=lambda: load_yaml(ROOT / "config" / "reserved_decisions.yaml"))

    def __post_init__(self):
        actions = {r["action"] for r in self.config["reserved"]}
        missing = MINIMUM_RESERVED - actions
        if self.config.get("minimum_set_locked") and missing:
            raise ValueError(f"Reserved decision list is missing the brief's minimum set: {sorted(missing)}")

    def rule(self, action: str) -> dict | None:
        return next((r for r in self.config["reserved"] if r["action"] == action), None)

    def decide(self, action: str, actor: dict, approve: bool) -> dict:
        rule = self.rule(action)
        if rule is None:
            return {"action": action, "decided_by": actor["id"], "approved": approve}
        if actor.get("type") == "agent":
            raise ReservedDecisionError(f"Agents cannot complete reserved decision '{action}'")
        if rule.get("mode") == "route_only":
            raise ReservedDecisionError(f"'{action}' is route only; it can be routed, never decided here")
        if actor.get("role") != rule["approver_role"]:
            raise ReservedDecisionError(f"'{action}' needs role {rule['approver_role']}, got {actor.get('role')}")
        return {"action": action, "decided_by": actor["id"], "approved": approve}


# ---------------------------------------------------------------- audit
GENESIS = "0" * 64


def _hash(entry: dict) -> str:
    return hashlib.sha256(json.dumps(entry, sort_keys=True, default=str).encode()).hexdigest()


@dataclass
class AuditLog:
    entries: list[dict] = field(default_factory=list)

    def append(self, actor: str, action: str, **details) -> dict:
        prev = self.entries[-1]["hash"] if self.entries else GENESIS
        body = {"seq": len(self.entries) + 1, "actor": actor, "action": action, "prev_hash": prev, **details}
        body["hash"] = _hash(body)
        self.entries.append(body)
        return body

    def verify(self) -> bool:
        prev = GENESIS
        for e in self.entries:
            body = {k: v for k, v in e.items() if k != "hash"}
            if e["prev_hash"] != prev or _hash(body) != e["hash"]:
                return False
            prev = e["hash"]
        return True


# ---------------------------------------------------------------- idempotency
@dataclass
class IdempotencyStore:
    done: dict[str, dict] = field(default_factory=dict)

    def run(self, key: str, fn, *args, **kwargs) -> dict:
        if key in self.done:
            return {**self.done[key], "replayed": True}
        result = fn(*args, **kwargs)
        self.done[key] = result
        return result


# ---------------------------------------------------------------- kill switch
@dataclass
class KillSwitch:
    config: dict = field(default_factory=lambda: load_yaml(ROOT / "config" / "killswitch.yaml"))

    def pause_workflow(self, workflow_id: str):
        self.config.setdefault("paused_workflows", []).append(workflow_id)

    def pause_skill(self, skill: str):
        self.config.setdefault("paused_skills", []).append(skill)

    def check(self, workflow_id: str, skill: str):
        if workflow_id in (self.config.get("paused_workflows") or []):
            raise PausedError(f"workflow '{workflow_id}' paused by HR")
        if skill in (self.config.get("paused_skills") or []):
            raise PausedError(f"skill '{skill}' paused by HR")


# ---------------------------------------------------------------- PII
PAN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
ACCOUNT = re.compile(r"\b\d{9,18}\b")


def mask(text: str, names: list[str] | None = None) -> str:
    text = PAN.sub("<PAN>", text)
    text = ACCOUNT.sub("<ACCOUNT>", text)
    for i, name in enumerate(names or [], start=1):
        for part in name.split():
            text = re.sub(rf"\b{re.escape(part)}\b", f"<PERSON_{i}>", text)
    return text
