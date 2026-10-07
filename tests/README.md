# Tests that need Claude Code

The product folder `.claude/` has its own offline checks: `tools/validate.py` and `tools/selftest.py`. They run without Claude Code. This folder adds the checks that need the real program. They answer a different question: does Claude Code actually load, send, run and block what the product says it does?

**Layer 3, the real CLI with a fake model (`test_mock_cli.py`).** Each scenario starts the real `claude` command in a scratch copy of the product. The folder name has a space and a Turkish letter, and the root holds decoy `random.py` and `json.py` files. The model is a small fake server (`harness/mock_api.py`) on 127.0.0.1. It only echoes text or makes the tool calls the scenario asks for. It logs every request, and a request is exactly what a real model would have received. So the scenarios prove what Claude Code loaded (CLAUDE.md, rules, output style, skills, agents), which hooks ran and with which exit code, and which tool calls were denied, asked or allowed. They do not prove how a real model behaves. Nothing needs a login: the child process gets a throw-away key made up at run time, no account variables, and its own config folder. If `claude` is not on the PATH, every scenario prints SKIP and the exit code is 0.

**Layer 4, simulated sessions (`sim_session.py`).** This wraps the real hook scripts. Each command plays one step: a session start, a learner message, a tutor answer, a file write, a shell command. It prints what the model would see. State between commands (session id, prompt counter, fake clock, surface) is kept in a folder next to the project (`DIR.sim`), so the tutor agent never sees it in the project tree and separate calls behave like one session. A tutor agent and a novice agent can talk to each other through it, and a rubric judges the result. `scenario_core_12turn.py` is the scripted version of such a session. These runs prove the loop around the model, not the model.

**Layers 5 to 8 are not here.** The adversarial review, the README walk-through by a zero-context agent, the completeness review and the owner's live check with a real login are done by people and real models. Their results go into `docs/test-report.md`. Use `harness/RESULTS-TEMPLATE.md` to record which scenario ran, when, and with which Claude Code version.

## Commands

Run them from the repository root. They need Python 3.9 or newer and nothing else.

```
python tests/test_mock_cli.py --list                 list the scenarios M-1 .. M-29
python tests/test_mock_cli.py                        run all (about 2 minutes); exit code 1 if any FAIL
python tests/test_mock_cli.py --only M-7,M-12 -v     run some, and print the evidence lines
python tests/test_mock_cli.py --json results.json    also save the results for harness/results_table.py
python tests/test_mock_cli.py --product PATH         test another .claude folder (the default is the one next to tests/)
python tests/sim_session.py init                     make a scratch project and print its path
python tests/sim_session.py --project DIR start      then: turn-start, turn-end, post-write, pre-bash, inbox-write, state, ...
python tests/sim_session.py                          print the full command list
python tests/harness/scenario.py --hooks --prompt "hello" --prompt "RUN: echo hi"   try a conversation by hand
python tests/harness/multi_turn.py --hooks           one process: hello, /compact, one more message
python tests/harness/results_table.py results.json   fill the release table
python tests/lint_py39.py                            find Python 3.10+ syntax in this folder (or any PATH)
```

## What is in the harness

| File | What it does |
|---|---|
| `harness/mock_api.py` | the fake model API. Directives in a prompt: `RUN:` `PS:` `READ:` `WRITE:` `TOOL:` `TOOLS:` `SKILL:` `AGENT:` |
| `harness/mockcli.py` | `start_mock`, `make_project`, `run_claude`, `run_claude_stream`, the `Run` object |
| `harness/scenario.py`, `multi_turn.py` | small command line front ends |
| `harness/stream_summary.py`, `requests_view.py` | read a stream-json capture or a mock request log |
| `harness/tools/run_case.py` and friends | the older one-case command line (`show.py`, `pairs.py`, `lastuser.py`, `subs.py`); output goes to `harness/runs/` (git-ignored) |
| `guard_mcli.py` | the guard checks of the guard package; they use `harness/tools/run_case.py` |

Facts that surprised us while building this, and that the scenarios now check:

- The skill list is cut by size. With a 200K-token model, Claude Code listed 4 of the 11 skills by name only. See M-4.
- Which text Claude Code sends differs by model family. Older models get the output style, agents and skill list as system-reminder blocks in the first user message. Newer ones get a system-role message. The helpers in `Run` read both.
- `Skill(name)` allow rules only apply in a folder the user has trusted. `-p` never asks, so a scenario must record the trust answer first (`run_claude(..., trusted=True)`).
- The PowerShell tool is offered in `-p` only with `CLAUDE_CODE_USE_POWERSHELL_TOOL=1`.
