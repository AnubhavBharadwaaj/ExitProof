import datetime as dt
import json

import pytest

from exitproof import access as acc
from exitproof import settlement, soc
from exitproof.demo import HUMANS, run_one
from exitproof.engine import Run, design_automation, load_workflow
from exitproof.governance import (AuditLog, IdempotencyStore, KillSwitch, ReservedDecisionError,
                                  ReservedDecisions, mask)
from exitproof.inbox import classify_reply
from exitproof.mocks import MockAPIs
from exitproof.router import estimate_from_workflow
from exitproof.rules import ROOT, RulePacks

DATA = json.loads((ROOT / "data" / "synthetic_exits.json").read_text())
RAHUL, ANANYA = DATA["employees"]


@pytest.fixture(scope="module")
def packs():
    return RulePacks()


# ------------------------------------------------------------ F1 two clock settlement
def test_rule_pack_self_tests_pass(packs):
    assert packs.run_pack_tests() == []


def test_two_clocks_monday_exit(packs):
    due = packs.clock_due_dates("2026-12-28", "maharashtra")
    assert due["wages"] == dt.date(2026, 12, 30)      # 2 working days
    assert due["gratuity"] == dt.date(2027, 1, 27)    # 30 calendar days


def test_wages_clock_skips_state_holiday_and_weekend(packs):
    # Thu 24 Dec 2026 exit in Karnataka: Fri 25 is a holiday, Sat and Sun are off
    assert packs.clock_due_dates("2026-12-24", "karnataka")["wages"] == dt.date(2026, 12, 29)


def test_leave_encashment_is_capped_by_state_pack_and_paid_on_clock_a(packs):
    s = settlement.compute(packs, RAHUL, "2026-12-28")
    assert s.leave_days_encashed == 45                # Maharashtra pack cap, balance was 52
    assert s.clock_a_total == 195000.0
    assert s.wages_due == "2026-12-30"


def test_same_balance_other_state_gives_other_amount(packs):
    karnataka_rahul = {**RAHUL, "state": "karnataka"}
    assert settlement.compute(packs, karnataka_rahul, "2026-12-28").leave_days_encashed == 30


def test_gratuity_permanent_needs_five_years_fixed_term_one(packs):
    assert settlement.compute(packs, RAHUL, "2026-12-28").gratuity == 315000.0
    assert settlement.compute(packs, ANANYA, "2026-12-24", "permanent").gratuity == 0.0
    assert settlement.compute(packs, ANANYA, "2026-12-24", "fixed_term").gratuity == 30000.0


def test_missing_state_pack_is_a_clear_error(packs):
    with pytest.raises(KeyError, match="Add rulepacks/states/goa.yaml"):
        packs.state("goa")


def test_clock_status_flags_breach(packs):
    s = settlement.compute(packs, RAHUL, "2026-12-28")
    status = settlement.clock_status(s, {"wages": None}, today=dt.date(2026, 12, 31))
    assert status["wages"] == "breached" and status["gratuity"] == "open"


# ------------------------------------------------------------ F2 F3 F4 access
def test_access_graph_finds_items_no_central_team_owns():
    items = acc.build_graph(RAHUL)
    orphans = {i.id for i in acc.orphan_items(items)}
    assert orphans == {"aws_key", "ti_shared", "meal_card", "gh_pat", "agent_bot"}
    assert items[0].kind == "ai_or_token"           # things that act on their own are revoked first


def test_shared_login_needs_new_mfa_seed_not_just_password():
    item = next(i for i in acc.build_graph(RAHUL) if i.id == "ti_shared")
    assert "enrol_new_mfa_seed" in item.revoke_actions
    assert not acc.rotation_complete(item, {"rotate_password", "record_new_seed_holder"})
    assert acc.rotation_complete(item, set(item.revoke_actions))


def test_proof_of_revocation_catches_use_after_disable_on_day_7_not_day_1():
    items = acc.build_graph(RAHUL)
    for i in items:
        i.disabled_at = dt.datetime(2026, 12, 28, 18, 0)
    day1 = acc.proof_of_revocation(items, RAHUL["usage_log"], dt.datetime(2026, 12, 29, 18, 0))
    day7 = acc.proof_of_revocation(items, RAHUL["usage_log"], dt.datetime(2027, 1, 4, 18, 0))
    assert day1 == []
    assert [e["item"] for e in day7] == ["aws_key"]


# ------------------------------------------------------------ F5 inbox closer
@pytest.mark.parametrize("text,status", [
    ("Laptop LT-2231 received at the desk, wiped. Done.", "closed"),
    ("Card not returned yet, will block it today", "open"),
    ("ok will check", "unclear"),
])
def test_reply_classifier(text, status):
    assert classify_reply("team", text).status == status


# ------------------------------------------------------------ F6 F7 soc bridge and notice window
def test_notice_window_options():
    for choice, start in (("whole_notice", "2026-11-30"), ("last_month", "2026-11-30"), ("last_week", "2026-12-21")):
        cfg = {"lookback": choice, "systems_in_scope": [], "excluded": [], "legal_basis": "s.7(i)",
               "log_retention_days": 365}
        assert soc.notice_window("2026-11-30", "2026-12-28", cfg)["from"] == start


def test_alert_carries_full_context_for_auto_ticket():
    exc = {"item": "aws_key", "system": "Team AWS access key", "reason": "used_after_disable",
           "disabled_at": "x", "last_used": "y", "owner": "platform_team"}
    alert = soc.exception_alert("EXIT-1", "E1", exc, 9)
    assert alert["exitproof.evidence"] == exc and alert["labels"]["owner_team"] == "platform_team"
    assert soc.to_cef(alert).startswith("CEF:0|ExitProof|")


# ------------------------------------------------------------ governance
def test_agent_cannot_complete_reserved_decision():
    with pytest.raises(ReservedDecisionError):
        ReservedDecisions().decide("resignation.accept", {"id": "bot", "type": "agent"}, True)


def test_wrong_human_role_cannot_sign_off_payroll():
    with pytest.raises(ReservedDecisionError):
        ReservedDecisions().decide("payroll.settlement_signoff", {"id": "x", "type": "human", "role": "hr_head"}, True)


def test_posh_is_route_only_even_for_humans():
    with pytest.raises(ReservedDecisionError, match="route only"):
        ReservedDecisions().decide("complaint.posh", {"id": "x", "type": "human", "role": "hr_head"}, True)


def test_minimum_reserved_set_cannot_be_removed():
    cfg = {"minimum_set_locked": True, "reserved": [{"action": "resignation.accept", "approver_role": "hr_head"}]}
    with pytest.raises(ValueError):
        ReservedDecisions(cfg)


def test_audit_chain_detects_tampering():
    log = AuditLog()
    log.append("agent", "a")
    log.append("human", "b")
    assert log.verify()
    log.entries[0]["action"] = "edited"
    assert not log.verify()


def test_retry_never_pays_twice():
    store, calls = IdempotencyStore(), []
    pay = lambda: calls.append(1) or {"paid": 1}
    store.run("EXIT-1:wages:pay", pay)
    assert store.run("EXIT-1:wages:pay", pay)["replayed"] is True
    assert len(calls) == 1


def test_pii_masked_before_model():
    out = mask("Rahul Demo PAN ABCDE1234F account 001122334455", ["Rahul Demo"])
    assert "ABCDE1234F" not in out and "001122334455" not in out and "Rahul" not in out


# ------------------------------------------------------------ end to end
def test_full_exit_run_end_to_end():
    run = run_one(RAHUL)
    assert run.automation_rate() == pytest.approx(22 / 26)
    assert len(run.apis.payments) == 2
    actions = [e["event.action"] for e in run.apis.siem]
    assert actions[0] == "employee_notice_started"
    assert "leaver_access_used_after_disable" in actions       # team key still used after disable
    assert "leaver_access_not_disabled" in actions              # access card not returned
    assert run.apis.complaints == [{"to": "internal_committee", "case": "EXIT-E10442"}]
    assert run.audit.verify()
    assert all("ABCDE1234F" not in str(c) for c in run.step_log)


def test_agent_alone_stops_at_first_reserved_decision():
    wf = load_workflow("exit")
    run = Run(workflow=wf, employee=RAHUL, case_id="EXIT-X", humans={}, apis=MockAPIs()).run()
    assert run.step_log[-1]["step"] == "accept_resignation"
    assert run.apis.payments == []


def test_kill_switch_pauses_without_code_change():
    wf = load_workflow("exit")
    ks = KillSwitch({"paused_skills": ["payroll.pay"]})
    run = Run(workflow=wf, employee=RAHUL, case_id="EXIT-K", humans=HUMANS, apis=MockAPIs(), killswitch=ks).run()
    assert run.apis.payments == [] and run.human_queue[-1].reason.startswith("skill 'payroll.pay' paused")


def test_extension_variant_is_one_file_and_core_unchanged():
    wf = load_workflow("exit_fixed_term")
    assert wf["params"]["employment_type"] == "fixed_term" and len(wf["steps"]) == 26
    run = run_one(ANANYA, "exit_fixed_term")
    assert run.state["settlement"].gratuity == 30000.0


def test_design_numbers_used_in_the_deck():
    wf = load_workflow("exit")
    assert design_automation(wf) == (22, 26)
    assert round(estimate_from_workflow(wf["steps"]), 2) == 0.21
