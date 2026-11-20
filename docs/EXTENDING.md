# Developer guide: extending ExitProof without touching the core

The engine (`exitproof/engine.py`) knows nothing about exits. Everything specific lives in files.

## Add a state

1. Copy `rulepacks/states/maharashtra.yaml` to `rulepacks/states/<state>.yaml`.
2. Fill `act`, `leave_encashment` and `holidays`, set `version`, `effective_from` and the `legal_owner`.
3. Run `python -m pytest`. Employees with `"state": "<state>"` now settle on that state's leave rules and holiday calendar. If a pack is missing, the engine raises a clear error naming the file to add.

## Change a law or a deadline

Edit `rulepacks/central/labour_codes.yaml`, bump `version` and `effective_from`, and add a case under `tests:`. `RulePacks.run_pack_tests()` refuses a pack whose own tests fail. Every audit entry records the pack versions it used.

## Add an exit variant (the live extension test)

Create one file in `workflows/`, for example `exit_fixed_term.yaml`:

```yaml
id: exit_fixed_term
version: 1
extends: exit
params:
  employment_type: fixed_term
```

It inherits all 26 steps and changes only the parameter. `test_extension_variant_is_one_file_and_core_unchanged` proves it.

## Add a step or a skill

1. Write a function in `exitproof/skills.py` (or a new module) and register it with `@skill("team.action")`.
2. Add a step to the workflow YAML with `skill`, `mode` (`auto` or `human`) and, for decisions, `reserved: <action>`.
3. If it is a decision, add it to `config/reserved_decisions.yaml`. Agents can never complete it.

## Change the model or provider

Edit `config/models.yaml`. The router meters every call in INR and escalates to the larger model only below `escalate_below_confidence`.

## Pause anything

Add a workflow id or skill name to `config/killswitch.yaml` (or call `KillSwitch.pause_skill`). The run parks in the human queue with its state attached.
