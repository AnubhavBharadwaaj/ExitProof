# Competitor scan: public PS 5b repositories (read 20 Nov 2026)

We searched GitHub for repositories created after 20 Oct 2026 that mention TBO, VoyageHack, DarwinBox, reserved decisions, final settlement or HR services, then cloned and read every PS 5b entry we found in full. Public repositories are a skewed sample, since many teams stay private until Round 2.

| Repository | What is there | Exit coverage | What it does well |
| --- | --- | --- | --- |
| [abhi-0605/Karya](https://github.com/abhi-0605/Karya) (KaryaOS) | 143 files, 20 commits, Python and FastAPI, 44 tests, measured benchmark on 200 synthetic onboarding runs | One `exit.yaml` with 6 steps. It reuses onboarding skills: `calculate_notice` calls `manager.assign_buddy`, `initiate_asset_return` calls `assets.allocate_laptop`, `compute_final_settlement` calls `payroll.setup_employee`, `deactivate_directory` calls `directory.create_account`. `final_settlement.yaml` has only the 30 day gratuity timeline, no 2 working day wages clock, no state rules, and lists eligible tenures explicitly (5 to 10, 15, 20), so 11 to 14 years match no rule. | Strong generic platform: hash chained audit, idempotent gateway with circuit breaker, kill switch, PII masker, model router, YAML workflows, ₹2.53 per onboarding and 86.8% automation reported for onboarding |
| [devesh1905/hireloop](https://github.com/devesh1905/hireloop) (HireLoop) | One README, design only | None; onboarding | Clear cost ladder: rules, a small decision model, a person, then a writer model |
| [Sudeep-A-Kulkarni/TBO-Helm](https://github.com/Sudeep-A-Kulkarni/TBO-Helm) (TBO Helm) | Research and design documents, a 10 slide deck, no code | Exits listed as the alternative; builds onboarding plus OpsDesk. Names the two working day F&F rule as a statutory clock to test. | Deep research ledger and an evaluation plan with duplicate effect metrics |
| [Arkz-Deepak/TBO.com-Hackathon](https://github.com/Arkz-Deepak/TBO.com-Hackathon) (TBO OneDesk) | A 10 slide deck and role documents, no code | None; onboarding for 5b, plus OpsDesk for 5a | One engine for both service lines |

## What none of them do (and ExitProof does)

| Gap found in every public entry | Evidence that it matters | ExitProof feature |
| --- | --- | --- |
| One settlement date | Wages incl. leave encashment in 2 working days; gratuity in 30 days | F1 Two Clock Settlement |
| One national rulebook | Leave is defined by each state's Shops and Establishments Act; state offices inspect | F1 state rule packs |
| Exit = onboarding steps in reverse | Four teams each remove one slice; team owned, shared, third party and AI access is owned by nobody | F2 Leaver Access Graph |
| Password reset treated as removal | An authenticator keeps producing codes until the MFA seed is enrolled again | F3 Shared Secret Rotation |
| Closed ticket treated as proof | Exit tickets are kept for audit; confirmations live in email; a key can still work after "done" | F4 Proof of Revocation, F5 Inbox Closer |
| No link to the security team | SOC tickets are generated from SIEM alerts with full context | F6 SOC Bridge |
| No position on watching the notice period | DLP look back windows differ by company; DPDP s.7(i) allows employment processing but not blanket surveillance | F7 Notice Window Policy |

We reuse the good generic ideas (hash chained audit, idempotency, kill switch, PII masking, YAML workflows) because the brief requires them, and spend our depth on the exit itself.
