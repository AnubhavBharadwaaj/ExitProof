"""Run the exit workflow on the synthetic dataset and print the dashboard numbers.

    python -m exitproof.demo
"""
from __future__ import annotations

import json

from .engine import Run, design_automation, load_workflow
from .mocks import MockAPIs
from .rules import ROOT, RulePacks
from .router import estimate_from_workflow

HR_HEAD = {"id": "hr.head@tbo.example", "type": "human", "role": "hr_head"}
FINANCE_HEAD = {"id": "finance.head@tbo.example", "type": "human", "role": "finance_head"}
HUMANS = {
    "accept_resignation": (HR_HEAD, True),
    "agree_release_date": (HR_HEAD, True),
    "settlement_signoff": (FINANCE_HEAD, True),
}


def run_one(employee: dict, workflow_id: str = "exit") -> Run:
    wf = load_workflow(workflow_id)
    run = Run(workflow=wf, employee=employee, case_id=f"EXIT-{employee['id']}", humans=HUMANS, apis=MockAPIs())
    return run.run()


def main():
    data = json.loads((ROOT / "data" / "synthetic_exits.json").read_text())
    packs = RulePacks()
    failures = packs.run_pack_tests()
    print("Rule pack self tests:", "pass" if not failures else failures)
    wf = load_workflow("exit")
    auto, total = design_automation(wf)
    print(f"Designed automation: {auto} of {total} steps ({auto / total:.1%}) with no human touch")
    print(f"Estimated model cost per exit: Rs {estimate_from_workflow(wf['steps']):.2f}")
    for emp, wf_id in ((data["employees"][0], "exit"), (data["employees"][1], "exit_fixed_term")):
        run = run_one(emp, wf_id)
        s = run.state["settlement"]
        print(f"\n== {run.case_id} ({wf_id}, {emp['state']})")
        print(f"  Clock A wages + leave encashment: Rs {s.clock_a_total:,.2f} due {s.wages_due}")
        print(f"  Clock B gratuity: Rs {s.gratuity:,.2f} (eligible={s.gratuity_eligible}) due {s.gratuity_due}")
        print(f"  Automation rate (this run): {run.automation_rate():.1%}")
        print(f"  Model cost (metered): Rs {run.router.total_inr:.3f}; tokens in/out {run.router.tokens}")
        print(f"  SIEM events: {[e['event.action'] for e in run.apis.siem]}")
        print(f"  Human queue: {[(q.step, q.reason) for q in run.human_queue]}")
        print(f"  Payments made: {len(run.apis.payments)}; audit chain valid: {run.audit.verify()}")


if __name__ == "__main__":
    main()
