"""Versioned rule packs and the working day calendar.

Central pack (Labour Codes) decides WHEN money is paid. State packs decide HOW MUCH leave is owed.
Rules live in YAML with effective dates and a named legal owner, never in prompts.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def load_yaml(path: Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def to_date(value) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    return dt.date.fromisoformat(str(value))


@dataclass
class StatePack:
    state: str
    version: str
    effective_from: dt.date
    legal_owner: str
    act: str
    leave_encashment: dict
    holidays: set[dt.date] = field(default_factory=set)


class RulePacks:
    """Loads the central pack, every state pack and company settings from disk."""

    def __init__(self, root: Path = ROOT):
        self.root = root
        self.central = load_yaml(root / "rulepacks" / "central" / "labour_codes.yaml")
        self.company = load_yaml(root / "config" / "company.yaml")
        self.states: dict[str, StatePack] = {}
        for path in sorted((root / "rulepacks" / "states").glob("*.yaml")):
            raw = load_yaml(path)
            self.states[raw["state"]] = StatePack(
                state=raw["state"],
                version=str(raw["version"]),
                effective_from=to_date(raw["effective_from"]),
                legal_owner=raw["legal_owner"],
                act=raw["act"],
                leave_encashment=raw["leave_encashment"],
                holidays={to_date(h) for h in raw.get("holidays", [])},
            )

    # ------------------------------------------------------------------ calendar
    def state(self, name: str) -> StatePack:
        if name not in self.states:
            raise KeyError(
                f"No rule pack for state '{name}'. Add rulepacks/states/{name}.yaml; the engine needs no change."
            )
        return self.states[name]

    def is_working_day(self, day: dt.date, state: str) -> bool:
        off = {WEEKDAYS.index(d) for d in self.company["weekly_off"]}
        return day.weekday() not in off and day not in self.state(state).holidays

    def add_working_days(self, start: dt.date, n: int, state: str) -> dt.date:
        day = start
        added = 0
        while added < n:
            day += dt.timedelta(days=1)
            if self.is_working_day(day, state):
                added += 1
        return day

    # ------------------------------------------------------------------ clocks
    def clock_due_dates(self, last_working_day, state: str) -> dict[str, dt.date]:
        lwd = to_date(last_working_day)
        clocks = self.central["clocks"]
        return {
            "wages": self.add_working_days(lwd, clocks["wages"]["working_days"], state),
            "gratuity": lwd + dt.timedelta(days=clocks["gratuity"]["calendar_days"]),
        }

    def versions_used(self, state: str) -> dict[str, str]:
        return {"central": str(self.central["version"]), f"state.{state}": self.state(state).version}

    # ------------------------------------------------------------------ self tests
    def run_pack_tests(self) -> list[str]:
        """Every rule pack ships its own tests; a pack whose tests fail cannot be used."""
        failures = []
        for case in self.central.get("tests", []):
            got = self.clock_due_dates(case["given"]["last_working_day"], case["given"]["state"])
            for key, want in case["expect"].items():
                clock = key.replace("_due", "")
                if got[clock] != to_date(want):
                    failures.append(f"{case['name']}: {key} expected {want}, got {got[clock]}")
        return failures
