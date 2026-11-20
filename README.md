# ExitProof

**An agent first exits platform that pays on both legal clocks and proves every access is dead.**

TBO VoyageHack 4.0 · Problem Statement 5b, AI Native HR Services Platform (DarwinBox) · Service line: **Exits**, from resignation to full and final settlement.

> An exit is not finished when HR closes the ticket. It is finished when the money is paid on time and every key is proven dead.

Status: Round 1 working prototype. 28 tests passing. Runs on Python 3.10+ with one dependency (PyYAML).

---

## ★ What only ExitProof does

Every feature below exists because a finding from our primary research broke an assumption a normal HR workflow makes. See [docs/EVIDENCE.md](docs/EVIDENCE.md) for the eight findings (L1 to L8) and their sources.

| | Feature | The leak it closes | How it works | Code |
| --- | --- | --- | --- | --- |
| ★ F1 | **Two Clock Settlement** | L6, L7: wages incl. leave encashment are due in 2 working days, gratuity in 30 days; the amount follows the state act, the deadline follows the Labour Code | Clock A and Clock B computed from a central pack plus one rule pack per state, with state holidays, effective dates and a named legal owner. Each pack carries its own tests. | [`settlement.py`](exitproof/settlement.py), [`rulepacks/`](rulepacks) |
| ★ F2 | **Leaver Access Graph** | L2, L4, L8: four teams each remove one slice; team owned, shared, third party and AI access belongs to nobody | Builds the full list at acceptance in four classes, assigns an owner and revoke actions, revokes self acting items (tokens, agents) first, and asks team leads to attest what central teams cannot see | [`access.py`](exitproof/access.py) |
| ★ F3 | **Shared Secret Rotation** | L5: an authenticator keeps producing valid codes until the MFA seed is enrolled again | A shared login is closed only when the password is rotated **and** a new MFA seed is enrolled and its holder recorded | [`access.py`](exitproof/access.py) |
| ★ F4 | **Proof of Revocation** | L4: "done" on a ticket does not mean the access is dead | Compares disabled at with last used for every item on day +1 and day +7; any use after disable becomes an exception | [`access.py`](exitproof/access.py) |
| ★ F5 | **Inbox Closer** | L3: the exit ticket is kept for audit; real confirmations happen by email | Sends each team its work order by email, reads replies with rules first and a small model second, closes or reopens the order, and mirrors status to the ITSM ticket | [`inbox.py`](exitproof/inbox.py) |
| ★ F6 | **SOC Bridge** | L1, L3: resignations never reach the SOC; SOC tickets are generated from SIEM alerts | Sends a watch event when notice starts and one alert per exception with full context (JSON or CEF), so the SOC ticket opens itself | [`soc.py`](exitproof/soc.py) |
| ★ F7 | **Notice Window Policy** | L1: the DLP look back window differs by company | HR chooses whole notice, last month or last week in config; the DPDP s.7(i) basis, systems in scope and one year log retention are recorded on every run | [`config/notice_window.yaml`](config/notice_window.yaml) |

### What the public competitors do not cover

We cloned and read every public PS 5b repository we could find on 20 Nov 2026 ([docs/COMPETITOR_SCAN.md](docs/COMPETITOR_SCAN.md)). All four centre on onboarding. The only exit flow among them reuses onboarding skills and encodes only the 30 day gratuity clock. None handles state rules, the 2 working day wages clock, team owned or shared access, MFA seeds, proof after revocation, or the SOC.

---

## Demo

```bash
pip install pyyaml pytest
python -m exitproof.demo      # runs two synthetic exits end to end
python -m pytest -q           # 28 tests
```

What the demo shows for Rahul (Maharashtra, permanent, last day Mon 28 Dec 2026):

- Clock A: ₹1,95,000 (20 days' salary + 45 days' leave, capped by the state pack from a balance of 52) due **Wed 30 Dec 2026**.
- Clock B: ₹3,15,000 gratuity (7 years) due **27 Jan 2027**.
- SIEM gets a watch event at notice, an alert because the access card was never returned (the team's reply said "not returned yet"), and on **day 7** an alert because the team AWS key was used after it was "disabled". Day 1 alone would have missed it.
- His exit conversation mentions comments about appearance, so it is **routed** to the internal committee. The agent cannot decide it.
- PAN and bank numbers never reach a model.

And for Ananya (Karnataka, fixed term, last day Thu 24 Dec 2026): wages due **Tue 29 Dec** because 25 Dec is a holiday and the weekend is off; gratuity ₹30,000 because fixed term staff qualify after one year, added as the one file workflow `exit_fixed_term.yaml`.

## Numbers

| Metric | Value | How |
| --- | --- | --- |
| Steps with no human touch | 22 of 26 (84.6%) by design; 23 of 26 when no team owned access exists | `design_automation()` over `workflows/exit.yaml` and measured per run |
| Model cost per exit | ₹0.21 | 14,400 input and 2,000 output tokens on Gemini 2.5 Flash-Lite at $0.10 and $0.40 per 1M tokens ([Google](https://developers.googleblog.com/gemini-25-flash-lite-is-now-stable-and-generally-available/)), ₹93.44 per $ ([PTI, 18 Nov 2026](https://telanganatoday.com/rupee-closes-higher-at-93-44-despite-strong-dollar-and-market-weakness)); dates and money are rules at ₹0. Hosting is measured in Round 2. |
| Duplicate payments or revokes on retry | 0 | Idempotency key per payment and per revoke |
| Agent completed reserved decisions | 0 | Enforced and tested |

## How it meets the brief

| Brief objective | ExitProof |
| --- | --- |
| 1. Automate end to end | Inbox Closer + mock IT, Admin, Finance, ITSM and SIEM APIs ([`mocks.py`](exitproof/mocks.py)) |
| 2. Build a platform, not a point solution | YAML workflows with `extends`, a skill registry, rule packs; see [docs/EXTENDING.md](docs/EXTENDING.md) |
| 3. Keep humans on the decisions that matter | [`config/reserved_decisions.yaml`](config/reserved_decisions.yaml): accepting a resignation, release date or notice buyout, payroll sign off; POSH, grievance and whistleblower are route only. The brief's minimum set is locked. |
| 4. Comply by design | Versioned, effective dated rule packs with their own tests and a named legal owner |
| 5. Keep a clean system of record | Hash chained audit log recording actor, rule versions, model and outcome |
| 6. Fail safely | Idempotency keys; unclear or unfinished work goes to a human queue with context |
| 7. Serve people where they work | Email first; Slack or Teams chat in Round 2 |
| 8. Prove cost and impact with numbers | Cost per exit, automation rate, escalation rate per run |
| Kill switch | [`config/killswitch.yaml`](config/killswitch.yaml) or `KillSwitch.pause_skill()`, no code change |
| PII handling | Names, PAN and bank numbers masked before any model call |
| Labour law as rules | Notice, final settlement timelines, gratuity and leave rules are code and YAML, never prompts |

## Project layout

```
exitproof/      engine, skills, rules, settlement, access, inbox, soc, router, governance, mocks, demo
rulepacks/      central Labour Code clocks + one pack per state
workflows/      exit.yaml (26 steps) and exit_fixed_term.yaml (one file extension)
config/         reserved decisions, models, notice window, kill switch, company calendar
data/           synthetic exits (fictional people only)
docs/           EVIDENCE.md, COMPETITOR_SCAN.md, EXTENDING.md
tests/          28 tests
```

## Assumptions and limits

- State leave values in `rulepacks/states/` are illustrative for the demo; the named legal owner must verify them before use.
- APIs are mocks until TBO shares its starter kit; Round 2 swaps them for TBO's interfaces with the same method names.
- Model calls are metered with budgeted token counts; Round 2 replaces them with live calls on TBO's synthetic dataset.

## Licences and tools

- PyYAML (MIT), pytest (MIT). ExitProof itself is MIT licensed.
- AI coding assistant used: Claude (Anthropic), for research support, code drafting and documentation. The team reviewed and owns every line.
