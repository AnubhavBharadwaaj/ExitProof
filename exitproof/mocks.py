"""Mock IT, Admin, Finance, email, ITSM and SIEM APIs.

Round 2 swaps these for TBO's provided mock interfaces; the skills call the same method names.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field


@dataclass
class MockAPIs:
    pay_date_offset_working_days: int = 0
    emails: list = field(default_factory=list)
    tickets: list = field(default_factory=list)
    siem: list = field(default_factory=list)
    payments: list = field(default_factory=list)
    revokes: list = field(default_factory=list)
    complaints: list = field(default_factory=list)

    def send_email(self, team: str, body: str):
        self.emails.append({"to": team, "body": body})

    def mirror_ticket(self, case_id: str, team: str, status: str):
        self.tickets.append({"case": case_id, "team": team, "status": status})

    def siem_send(self, event: dict):
        self.siem.append(event)

    def finance_pay(self, employee_id: str, amount: float, clock: str, due: dt.date) -> dict:
        self.payments.append({"employee": employee_id, "amount": amount, "clock": clock})
        return {"paid": amount, "clock": clock, "paid_on": due.isoformat(), "payment_no": len(self.payments)}

    def revoke(self, item_id: str, actions: list[str]) -> dict:
        self.revokes.append({"item": item_id, "actions": list(actions)})
        return {"item": item_id, "status": "revoked"}

    def route_complaint(self, to: str, case_id: str):
        self.complaints.append({"to": to, "case": case_id})
