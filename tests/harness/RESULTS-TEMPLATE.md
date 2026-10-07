# Results of the tests that need Claude Code

The main agent fills this in at release and copies the table into `docs/test-report.md`.
Run `python tests/test_mock_cli.py --json results.json`, then `python tests/harness/results_table.py results.json` prints the rows with result, date and version already filled in.

| Field | Value |
|---|---|
| Product version (`.claude/VERSION`) | |
| Claude Code version (`claude --version`) | |
| Operating system | |
| Python version that ran the tests | |
| Date | |
| Run by | |
| Mock model or real model | mock model (a real model is not used by these tests) |

Result words: `OK` (all checks passed), `FAIL: <first problem>`, `SKIP: <reason>` (the scenario could not run honestly), `not run`.
A FAIL stays in the table. Do not edit a scenario to turn it green; fix the product or record why the scenario is wrong.

## Layer 3: the real CLI with the fake model (`tests/test_mock_cli.py`)

| Test id | What it proves | Result | Date | Claude Code version |
|---|---|---|---|---|
| M-1 | CLAUDE.md reaches the model whole, with its HTML comment stripped, on both prompt families | | | |
| M-2 | Output style 'tutor' is in the model's context; keep-coding-instructions keeps the coding section | | | |
| M-3 | All 6 rule files are loaded into the first user message (default model and 200K model) | | | |
| M-4 | All 11 skills are listed with their full descriptions under a 200K window (and the default model) | | | |
| M-5 | Both agents are listed to the model with description and read-only tools, and appear in the init event | | | |
| M-6 | The init event shows the wiring (style, skills, agents), the CLI version, and the placeholder key in use | | | |
| M-7 | Hooks ON: state capsule in the FIRST request, per-message line in the SECOND request of a resumed session | | | |
| M-8 | Hooks ON: all 6 hook modes fire through the real launcher with exit 0, empty stderr and valid output | | | |
| M-9 | A missing hook script, handler or library never blocks (exit 0, or exit 1 with one line; never 2) | | | |
| M-10 | Hooks ON but python3 not on PATH: records the exact hook error text; nothing blocks, session continues | | | |
| M-11 | Guard: force pushes are DENIED with the 'Stopped on purpose' text; a plain push ASKS; status passes | | | |
| M-12 | Floor: Read of .env (3 spellings) and .env.local is denied; Write of .env.example is allowed | | | |
| M-13 | Floor (hooks off): the inbox Write raises no prompt in default mode; a Write to state/x.json is blocked | | | |
| M-14 | Hooks ON: an inbox Write is answered 'Saved:' / 'Refused:' by PostToolUse; a state/ Write is denied | | | |
| M-15 | Floor: Skill(...) allow rules start all 11 skills with no prompt in default mode (needs a trusted folder) | | | |
| M-16 | Guard: rm -rf of a project subfolder (and other hard-to-undo commands) ASK and change nothing | | | |
| M-17 | Guard: rm -rf of regenerable folders (node_modules, dist, build, __pycache__) is NOT asked and runs | | | |
| M-18 | Guard: reading a secret file with a shell program is DENIED; mentioning the name or .env.example passes | | | |
| M-19 | Guard: writing a secret-shaped value (built at run time) into a file or a command is DENIED | | | |
| M-20 | Guard through the PowerShell tool: same decisions as Bash (needs CLAUDE_CODE_USE_POWERSHELL_TOOL=1) | | | |
| M-21 | Started in a sub-folder: CLAUDE.md, rules and skills load; no SessionStart hook runs; style stays default | | | |
| M-22 | /compact in one process: CLAUDE.md, rules and style stay, the skill list is gone, SessionStart(compact) re-injects | | | |
| M-23 | `claude doctor` finds no invalid settings in the product's settings.json, also after hooks are enabled | | | |
| M-24 | defaultMode acceptEdits from settings.json shows in the init event when no mode is passed | | | |
| M-25 | Hooks OFF (the shipped state) with PATH stripped of python/py: no hook error anywhere; text-only first hour | | | |
| M-26 | Harness: a planted token reaches the mock; the child has no real credential; tests/ holds no key or path | | | |
| M-27 | Hooks ON: a Turkish prompt (non-ASCII) reaches the hook through the launcher intact and is stored as typed | | | |
| M-28 | Hooks ON: a machine-made prompt (background helper finished) prints nothing and is not stored as learner words | | | |
| M-29 | tools/doctor.py enable-hooks writes a settings.json that Claude Code accepts; all 6 events fire; disable-hooks undoes it | | | |

## Other scripted layers

| Test id | What it proves | Result | Date | Claude Code version |
|---|---|---|---|---|
| guard_mcli.py | the guard text, the floor rules and the Read negations work through the real CLI (the guard package's own checks) | | | |
| scenario_core_12turn.py | a scripted 12-turn session: one ledger row per answer, verified progress rows, forged quote refused (gate G0 check 3, hook side) | | | |
| lint_py39.py | no Python 3.10+ syntax or library use in tests/ (and, when pointed at it, in the product) | | | |

## Not covered by these tests (records for `docs/test-report.md`, "Not verified with a real model")

- How a real model reacts: whether it follows the output style, relays a guard stop in plain words, grades a check, starts a skill from its description.
- The interactive screen: the trust dialog, the permission prompt text for a hook `ask`, how hook errors are drawn, Desktop behaviour.
- macOS and Linux (the scenarios run anywhere `claude` is on PATH, but were first run on Windows 11).
- A machine where Python is installed but `python3` is not on PATH, and Windows without Git Bash.
