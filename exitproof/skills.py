"""Exit skills. Each one is small, named, and registered; the workflow YAML decides the order."""
from __future__ import annotations

import datetime as dt

from . import access as acc
from . import inbox, settlement, soc
from .engine import HumanQueueItem, skill
from .governance import ReservedDecisionError, mask
from .rules import to_date

POSH_WORDS = ("harass", "appearance", "uncomfortable", "inappropriate", "touched", "sexual")


# ---------------------------------------------------------------- intake and decisions
@skill("inbox.parse_resignation")
def parse_resignation(run, step):
    masked = mask(run.employee["resignation_email"], [run.employee["name"]])
    parsed = inbox.parse_resignation(masked, run.router)
    run.state["last_working_day"] = parsed["last_working_day"]
    run.state["resignation_date"] = run.state.get("resignation_date", dt.date(2026, 11, 30))
    if parsed["needs_human"]:
        run.human_queue.append(HumanQueueItem(step["id"], "unclear_last_day", {"email": masked}))
        return {"halt": True, "reason": "last working day unclear"}
    return {"last_working_day": parsed["last_working_day"].isoformat(), "model_saw": masked}


@skill("case.open")
def open_case(run, step):
    return {"case_id": run.case_id}


@skill("approval.request")
def approval(run, step):
    action = step["reserved"]
    run.human_queue.append(HumanQueueItem(step["id"], "reserved_decision", {"action": action}))
    actor, approve = run.humans.get(step["id"], ({"id": "agent", "type": "agent"}, True))
    try:
        decision = run.reserved.decide(action, actor, approve)
    except ReservedDecisionError as exc:
        return {"halt": True, "blocked": str(exc)}
    if not decision["approved"]:
        return {"halt": True, **decision}
    return decision


# ---------------------------------------------------------------- F1 two clock settlement
@skill("rules.compute_exit_dates")
def compute_dates(run, step):
    due = run.packs.clock_due_dates(run.state["last_working_day"], run.employee["state"])
    run.state["due"] = due
    return {k: v.isoformat() for k, v in due.items()}


@skill("rules.compute_wages_clock")
def compute_wages(run, step):
    s = settlement.compute(run.packs, run.employee, run.state["last_working_day"],
                           run.workflow["params"].get("employment_type"))
    run.state["settlement"] = s
    return {"clock_a_total": s.clock_a_total, "due": s.wages_due, "leave_days": s.leave_days_encashed}


@skill("rules.compute_gratuity_clock")
def compute_gratuity(run, step):
    s = run.state["settlement"]
    return {"gratuity": s.gratuity, "eligible": s.gratuity_eligible, "due": s.gratuity_due}


@skill("payroll.pay")
def pay(run, step):
    s = run.state["settlement"]
    clock = step["clock"]
    amount = s.clock_a_total if clock == "wages" else s.gratuity
    if amount == 0:
        return {"clock": clock, "amount": 0, "skipped": "not eligible"}
    key = f"{run.case_id}:{clock}:pay"
    due = to_date(s.wages_due if clock == "wages" else s.gratuity_due)
    result = run.idem.run(key, run.apis.finance_pay, run.employee["id"], amount, clock, due)
    run.state.setdefault("paid_on", {})[clock] = to_date(result["paid_on"])
    return result


# ---------------------------------------------------------------- F2 F3 access graph and rotation
@skill("access.build_graph")
def build_graph(run, step):
    items = acc.build_graph(run.employee)
    run.state["access"] = items
    orphans = acc.orphan_items(items)
    return {"items": len(items), "outside_central_teams": [i.id for i in orphans]}


@skill("access.team_attestation")
def team_attestation(run, step):
    needs = [i for i in run.state["access"] if i.needs_attestation]
    if not needs:
        return {"attest_requested_from": [], "no_human_needed": True}
    run.human_queue.append(HumanQueueItem(step["id"], "attestation", {"items": [i.id for i in needs]}))
    return {"attest_requested_from": sorted({i.owner_team for i in needs})}


def _disable(run, item, actions):
    lwd = to_date(run.state["last_working_day"])
    key = f"{run.case_id}:{item.id}:revoke"
    run.idem.run(key, run.apis.revoke, item.id, actions)
    item.disabled_at = dt.datetime.combine(lwd, dt.time(18, 0))
    run.state.setdefault("done_actions", {})[item.id] = set(actions)


@skill("secrets.rotate_shared")
def rotate_shared(run, step):
    out = []
    for item in run.state["access"]:
        if item.kind == "shared_login":
            _disable(run, item, item.revoke_actions)
            out.append({"item": item.id, "actions": item.revoke_actions,
                        "complete": acc.rotation_complete(item, run.state["done_actions"][item.id])})
    return {"rotated": out}


@skill("access.cancel_third_party")
def cancel_third_party(run, step):
    done = []
    for item in run.state["access"]:
        if item.kind == "third_party":
            _disable(run, item, item.revoke_actions)
            done.append(item.id)
    return {"cancelled": done}


@skill("access.revoke_tokens")
def revoke_tokens(run, step):
    done = []
    for item in run.state["access"]:
        if item.kind in ("ai_or_token", "team_owned"):
            _disable(run, item, item.revoke_actions)
            done.append(item.id)
    return {"revoked": done}


# ---------------------------------------------------------------- F5 inbox closer
@skill("inbox.send_work_order")
def send_work_order(run, step):
    team = step["team"]
    items = [i.id for i in run.state["access"] if i.owner_team == team]
    run.apis.send_email(team, f"Exit {run.case_id}: please remove {items} by {run.state['last_working_day']}")
    run.apis.mirror_ticket(run.case_id, team, "work order sent")
    return {"team": team, "items": items}


@skill("inbox.read_replies")
def read_replies(run, step):
    verdicts = inbox.read_replies(run.employee["team_replies"], run.router)
    for v in verdicts:
        run.apis.mirror_ticket(run.case_id, v.team, v.status)
        if v.status == "closed":
            for item in run.state["access"]:
                if item.owner_team == v.team and item.disabled_at is None:
                    _disable(run, item, item.revoke_actions)
        else:
            run.human_queue.append(HumanQueueItem(step["id"], "team_not_done", {"team": v.team, "reply": v.text}))
    return {v.team: v.status for v in verdicts}


# ---------------------------------------------------------------- F4 proof, F6 SOC bridge, F7 window
@skill("proof.check_revocation")
def proof(run, step):
    lwd = to_date(run.state["last_working_day"])
    check_time = dt.datetime.combine(lwd + dt.timedelta(days=step["offset_days"]), dt.time(18, 0))
    exceptions = acc.proof_of_revocation(run.state["access"], run.employee.get("usage_log", []), check_time)
    alerts = []
    for exc in exceptions:
        if exc["item"] in run.state.setdefault("alerted", set()):
            continue
        run.state["alerted"].add(exc["item"])
        alert = soc.exception_alert(run.case_id, run.employee["id"], exc, len(run.audit.entries) + 1)
        run.apis.siem_send(alert)
        alerts.append(alert["event.action"] + ":" + exc["item"])
    return {"day": step["offset_days"], "exceptions": alerts}


@skill("soc.send_watch_event")
def watch(run, step):
    window = soc.notice_window(run.state["resignation_date"], run.state["last_working_day"])
    run.state["notice_window"] = window
    run.apis.siem_send(soc.watch_event(run.case_id, run.employee["id"], window))
    return {"sent": "employee_notice_started"}


@skill("policy.notice_window")
def notice_window(run, step):
    w = run.state["notice_window"]
    return {"lookback": w["lookback"], "from": w["from"], "to": w["to"], "basis": w["legal_basis"]}


# ---------------------------------------------------------------- conversation and retention
@skill("chat.exit_conversation")
def exit_conversation(run, step):
    text = mask(run.employee.get("exit_conversation", ""), [run.employee["name"]])
    run.router.meter("exit_conversation", tokens_in=6500, tokens_out=1400, confidence=0.9)
    if any(w in text.lower() for w in POSH_WORDS):
        # Route only, never decide (brief guardrail). The agent cannot open, judge or close it.
        run.apis.route_complaint("internal_committee", run.case_id)
        run.human_queue.append(HumanQueueItem(step["id"], "posh_routed", {"to": "internal_committee"}))
        return {"posh": "routed_to_internal_committee"}
    return {"posh": "none"}


@skill("dpdp.start_retention")
def start_retention(run, step):
    lwd = to_date(run.state["last_working_day"])
    return {"logs_kept_until": (lwd + dt.timedelta(days=365)).isoformat(), "rule": "DPDP Rules 2025, Rule 6"}
