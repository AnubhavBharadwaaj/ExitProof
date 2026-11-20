"""F1 Two Clock Settlement.

Clock A (wages, including leave encashment): last working day + 2 working days, state holiday calendar.
Clock B (gratuity): last working day + 30 days.
Amounts come from the state rule pack; deadlines come from the central Labour Code pack.
Rule based on purpose: date maths and money maths never go to a model.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, asdict

from .rules import RulePacks, to_date


@dataclass
class Settlement:
    employee_id: str
    state: str
    last_working_day: str
    wages_due: str
    gratuity_due: str
    salary_for_days_worked: float
    leave_encashment: float
    leave_days_encashed: int
    gratuity: float
    gratuity_eligible: bool
    rule_versions: dict

    @property
    def clock_a_total(self) -> float:
        return round(self.salary_for_days_worked + self.leave_encashment, 2)

    def as_dict(self) -> dict:
        data = asdict(self)
        data["clock_a_total"] = self.clock_a_total
        return data


def service_years(join_date, last_working_day) -> int:
    """Completed years, with more than six months counted as a full year."""
    start, end = to_date(join_date), to_date(last_working_day)
    months = (end.year - start.year) * 12 + (end.month - start.month) - (1 if end.day < start.day else 0)
    years, rem = divmod(months, 12)
    return years + (1 if rem > 6 else 0)


def gratuity_eligible(packs: RulePacks, employment_type: str, years: int) -> bool:
    rule = packs.central["gratuity_eligibility"]
    minimum = rule["fixed_term_min_years"] if employment_type == "fixed_term" else rule["permanent_min_years"]
    return years >= minimum


def compute(packs: RulePacks, employee: dict, last_working_day, employment_type: str | None = None) -> Settlement:
    state = employee["state"]
    pack = packs.state(state)
    lwd = to_date(last_working_day)
    due = packs.clock_due_dates(lwd, state)
    basic = float(employee["monthly_basic_plus_da"])
    divisor = pack.leave_encashment["divisor"]
    per_day = basic / divisor

    days_encashed = min(int(employee["earned_leave_balance"]), int(pack.leave_encashment["max_encashable_days"]))
    leave_amount = round(per_day * days_encashed, 2)
    salary = round(per_day * int(employee["days_worked_in_last_month"]), 2)

    etype = employment_type or employee.get("employment_type", "permanent")
    years = service_years(employee["join_date"], lwd)
    eligible = gratuity_eligible(packs, etype, years)
    g = packs.central["gratuity_eligibility"]
    gratuity = round(basic * g["days_per_year"] / g["divisor"] * years, 2) if eligible else 0.0

    return Settlement(
        employee_id=employee["id"],
        state=state,
        last_working_day=lwd.isoformat(),
        wages_due=due["wages"].isoformat(),
        gratuity_due=due["gratuity"].isoformat(),
        salary_for_days_worked=salary,
        leave_encashment=leave_amount,
        leave_days_encashed=days_encashed,
        gratuity=gratuity,
        gratuity_eligible=eligible,
        rule_versions=packs.versions_used(state),
    )


def clock_status(settlement: Settlement, paid_on: dict[str, dt.date | None], today: dt.date) -> dict[str, str]:
    """on_time, late, open or breached for each clock, so the dashboard can show risk early."""
    out = {}
    for clock, due in (("wages", settlement.wages_due), ("gratuity", settlement.gratuity_due)):
        due_d = to_date(due)
        paid = paid_on.get(clock)
        if paid:
            out[clock] = "on_time" if paid <= due_d else "late"
        else:
            out[clock] = "breached" if today > due_d else "open"
    return out
