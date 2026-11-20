"""F6 SOC Bridge and F7 Notice Window Policy.

Evidence:
  L1  a resignation does not reach the security team as an event; the DLP look back window differs by company.
  L3  security tickets are generated automatically from SIEM alerts, with every detail inside the ticket.
So ExitProof speaks the SOC's language: a watch event when notice starts, and one alert per exception with
full context, so the analyst's ticket opens itself. No new process for the SOC.
"""
from __future__ import annotations

import datetime as dt
import json

from .rules import ROOT, load_yaml, to_date

LOOKBACK_DAYS = {"last_week": 7, "last_month": 30}


def notice_window(resignation_date, last_working_day, config: dict | None = None) -> dict:
    """F7: the DLP review window HR chose, with its legal basis recorded on every run."""
    cfg = config or load_yaml(ROOT / "config" / "notice_window.yaml")
    start, end = to_date(resignation_date), to_date(last_working_day)
    choice = cfg["lookback"]
    if choice == "whole_notice":
        window_start = start
    else:
        window_start = max(start, end - dt.timedelta(days=LOOKBACK_DAYS[choice]))
    return {
        "lookback": choice,
        "from": window_start.isoformat(),
        "to": end.isoformat(),
        "systems_in_scope": cfg["systems_in_scope"],
        "excluded": cfg["excluded"],
        "legal_basis": cfg["legal_basis"],
        "log_retention_days": cfg["log_retention_days"],
    }


def watch_event(case_id: str, employee_id: str, window: dict) -> dict:
    return {
        "event.kind": "event",
        "event.category": ["iam"],
        "event.action": "employee_notice_started",
        "event.dataset": "exitproof.leaver",
        "labels": {"case_id": case_id},
        "user.id": employee_id,
        "exitproof.notice_window": window,
    }


def exception_alert(case_id: str, employee_id: str, exc: dict, audit_seq: int) -> dict:
    """One alert per exception, carrying everything the analyst needs (who, what, when, owner, evidence)."""
    return {
        "event.kind": "alert",
        "event.category": ["iam"],
        "event.action": f"leaver_access_{exc['reason']}",
        "event.severity": 73 if exc["reason"] == "used_after_disable" else 47,
        "event.dataset": "exitproof.leaver",
        "labels": {"case_id": case_id, "owner_team": exc["owner"], "audit_seq": str(audit_seq)},
        "user.id": employee_id,
        "service.name": exc["system"],
        "exitproof.evidence": exc,
        "message": f"Leaver {employee_id}: {exc['system']} {exc['reason'].replace('_', ' ')}",
    }


def to_cef(alert: dict) -> str:
    """Same alert as a CEF line for SIEMs that ingest syslog."""
    ext = f"suser={alert['user.id']} cs1Label=case cs1={alert['labels']['case_id']} msg={alert['message']}"
    sev = round(alert["event.severity"] / 10)
    return f"CEF:0|ExitProof|ExitProof|1.0|{alert['event.action']}|{alert['message']}|{sev}|{ext}"


def to_json(alert: dict) -> str:
    return json.dumps(alert, sort_keys=True)
