"""Workflow engine and skill registry.

The engine knows nothing about exits. Workflows are YAML files; skills register themselves by name.
Adding a state, an exit variant or a new service line means adding files, not editing this module.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .governance import AuditLog, IdempotencyStore, KillSwitch, PausedError, ReservedDecisions
from .router import ModelRouter
from .rules import ROOT, RulePacks, load_yaml

SKILLS: dict[str, Callable] = {}


def skill(name: str):
    def register(fn):
        SKILLS[name] = fn
        return fn
    return register


def load_workflow(workflow_id: str, root: Path = ROOT) -> dict:
    wf = load_yaml(root / "workflows" / f"{workflow_id}.yaml")
    if "extends" in wf:
        base = load_workflow(wf["extends"], root)
        merged = {**base, **{k: v for k, v in wf.items() if k != "extends"}}
        merged["params"] = {**base.get("params", {}), **wf.get("params", {})}
        return merged
    wf.setdefault("params", {})
    return wf


@dataclass
class HumanQueueItem:
    step: str
    reason: str
    context: dict


@dataclass
class Run:
    workflow: dict
    employee: dict
    case_id: str
    packs: RulePacks = field(default_factory=RulePacks)
    router: ModelRouter = field(default_factory=ModelRouter)
    audit: AuditLog = field(default_factory=AuditLog)
    idem: IdempotencyStore = field(default_factory=IdempotencyStore)
    reserved: ReservedDecisions = field(default_factory=ReservedDecisions)
    killswitch: KillSwitch = field(default_factory=KillSwitch)
    humans: dict = field(default_factory=dict)          # step id -> (actor, approve) supplied by people
    apis: object = None
    state: dict = field(default_factory=dict)
    human_queue: list[HumanQueueItem] = field(default_factory=list)
    step_log: list[dict] = field(default_factory=list)

    def run(self) -> "Run":
        from . import skills  # noqa: F401  (registers the exit skills)
        for step in self.workflow["steps"]:
            try:
                self.killswitch.check(self.workflow["id"], step["skill"])
            except PausedError as exc:
                self.human_queue.append(HumanQueueItem(step["id"], str(exc), {"state": dict(self.state)}))
                self.audit.append("system", "paused", step=step["id"], reason=str(exc))
                break
            result = SKILLS[step["skill"]](self, step)
            touched_by_human = step["mode"] == "human" and not (
                isinstance(result, dict) and result.get("no_human_needed"))
            self.step_log.append({"step": step["id"], "mode": step["mode"], "human_touch": touched_by_human,
                                  "result": result})
            self.audit.append(
                "human" if touched_by_human else "agent",
                step["skill"],
                step=step["id"],
                rule_versions=self.packs.versions_used(self.employee["state"]),
                model=self.router.calls[-1].model if step.get("llm") and self.router.calls else None,
                outcome=_short(result),
            )
            if isinstance(result, dict) and result.get("halt"):
                break
        return self

    # --------------------------------------------------------------- metrics
    def automation_rate(self) -> float:
        done = [s for s in self.step_log]
        return sum(1 for s in done if not s["human_touch"]) / len(done)

    def escalation_rate(self) -> float:
        extra = [q for q in self.human_queue if q.reason != "reserved_decision"]
        return len(extra) / max(len(self.step_log), 1)


def _short(result) -> str:
    text = str(result)
    return text if len(text) < 160 else text[:157] + "..."


def design_automation(workflow: dict) -> tuple[int, int]:
    steps = workflow["steps"]
    return sum(1 for s in steps if s["mode"] == "auto"), len(steps)


def now() -> dt.datetime:
    return dt.datetime.now()
