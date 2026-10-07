# Security

This page lists everything the kit runs or changes. It also says how to check it yourself. Facts about Claude Code were checked in its documentation on 2026-10-07.

## Read this first

- The kit is text files until you turn on the helper scripts.
- The safety guard stops accidents and obvious mistakes. It does not stop a determined or tricked agent.
- Windows has no operating-system sandbox for Claude Code commands. The Claude Code sandboxing page says so, checked 2026-10-07.

## Everything that runs or changes behaviour

### The permission floor

| Part | What it does | When it applies |
|---|---|---|
| `.claude/settings.json`, `permissions` | Denies reads of secret files such as `.env`, key files and cloud credentials. Denies force pushes and destructive commands. Asks before other risky commands. Allows the eleven skills to start. | Every Claude Code session in the folder. It works without Python. |
| `.claude/.gitignore` | Ignores `agent-memory/tutor-data/`, `settings.local.json`, `*.tutor-backup` and Python caches. Nothing else. | When Git reads the folder. |

### Commands the skills may run without a question

A skill may run only the commands in its front matter (`allowed-tools`). Each command also has a PowerShell form. Any other command is not pre-approved by a skill.

| Skill | Commands it may run without a question | Network |
|---|---|---|
| tutor | `doctor.py check`; `python --version` (also `python3` and `py -3`); `printenv CLAUDE_CODE_ENTRYPOINT` | No |
| progress | `doctor.py progress` | No |
| tutor-setup | `python --version` (also `python3` and `py -3`); `printenv CLAUDE_CODE_ENTRYPOINT` | No |
| before-push | `git status`, `git log`, `git remote -v`, `git check-ignore`, `git ls-files`, `git grep`, `git shortlog`; `gh --version`; `gh repo view` | Yes: `gh repo view` asks GitHub through your own `gh` program |
| git-rescue | `git status`, `git log`, `git reflog -n`, `git stash list` | No |
| explain, fix-it, learn, new-project, save-point, think-first | None listed in the front matter | Not applicable |

The `doctor.py` pattern in the table covers the `python3`, `python` and `py -3` forms.

### The helper scripts (hooks)

The hooks are off in the shipped kit. You turn them on with `doctor.py enable-hooks` or with `install.py --enable-hooks`. They use the Python named in the launcher.

| Hook | Runs when | Reads | Writes | Can block a step? |
|---|---|---|---|---|
| SessionStart | A session starts, resumes, is cleared, is compacted or is forked | Your profile, the state file, `now.md`, the decision index, and read-only Git status | `state/state.json`. On a startup or a clear, removes chat copies older than 30 days. | No |
| UserPromptSubmit | Before each message you send | Your message, the profile, the state and ledger files, and your progress list | `state/recent-user.json` (the last five messages, redacted), `state/activity.jsonl`, `state/state.json`. Writes `chat/` only if chat copy is on. | No |
| PreToolUse | Before a shell command, Write, Edit or NotebookEdit call | The tool call, read-only Git state, and the scripts a command names | `state/state.json`, guard counters only. | Yes. It denies a dangerous call or asks you first. |
| PostToolUse | After a shell command, Write, Edit or NotebookEdit call | The tool result and the inbox folder | `state/activity.jsonl`, `state/state.json`, and `learner/progress.jsonl`. Deletes the inbox files it reads. | No |
| Stop | When Claude finishes an answer | The final answer text, your profile and the activity log | `state/ledger.jsonl`, `state/state.json`, and `learner/progress.jsonl`. Prints nothing. | No |
| SubagentStart | When a helper agent starts | The helper type name (`agent_type`) from its input | Nothing | No |

The hook log never stores your prompt or command text. It stores only the error type, the module and the line.

### The tools you run

| Tool | Who runs it, and when | What it changes | Network |
|---|---|---|---|
| `tools/doctor.py` | You, or a skill. The skill rules are in the table above. | `enable-hooks` and `disable-hooks` edit `settings.json` and keep a backup. `share-notes` edits `.claude/.gitignore` and the project root `.gitignore`. `wipe` deletes tutor data, and only with `--yes`. | No, except `share-notes on`. It asks GitHub through your own `gh` program. |
| `tools/install.py` | You, once for each project, and again for an update or an uninstall. | Copies kit files into your project. Merges `settings.json`. Writes lines to `.claude/.gitignore`. | No |
| `tools/validate.py` | Maintainers and CI | Nothing, unless you give a `--write-` option. Those options rewrite generated files in the kit. | No |
| `tools/selftest.py` | Maintainers, CI, and `install.py`, which runs a quick run in a temporary copy | Temporary folders only | No |

The self-test files in `.claude/tools/` are in the learner's copy. The scripts in the repository's `tests/` folder are not. They are for maintainers, and each one is listed below.

| Repository-only script | Who runs it | What it changes | Network |
|---|---|---|---|
| `tests/test_mock_cli.py` | Maintainers. It starts the real `claude` program against a fake model. | Temporary folders only | Local only: a fake model on 127.0.0.1 |
| `tests/guard_mcli.py` | Maintainers. Guard checks through the real `claude` program and the fake model. | Temporary folders only | Local only: 127.0.0.1 |
| `tests/harness/` | Maintainers. The test harness that the two files above use. | Temporary folders only | Local only: 127.0.0.1 |
| `tests/sim_session.py` | Maintainers | Temporary folders only | No |
| `tests/scenario_core_12turn.py` | Maintainers. A scripted 12-turn session against the real hooks. | Temporary folders only | No |
| `tests/lint_py39.py` | Maintainers and CI. It reads the test code only. | Nothing | No |

## No script of the kit makes a network call

No script of the kit makes a network call. The one exception is `doctor.py share-notes on`. That command asks GitHub through your own `gh` program, and only after you agree.

You can check this yourself.

1. Run the security scan. It looks for network modules, code-running calls and unsafe subprocess calls:

   ```
   python .claude/tools/selftest.py --security
   ```

2. Search the Python files for import lines. Your editor can search a folder. Look in `.claude/hooks/` and `.claude/tools/`. Search for lines that start with `import socket`, `import urllib`, `import http`, `import requests` or `import ftplib`, and for `from urllib` or `from http`. Text hits are normal. The same words appear in strings, regular expressions and test lists, and no shipped module imports them. The security scan in step 1 is the real check.

If the scan reports a problem, do not use that copy.

## Install only from a release tag, and compare the manifest

Download the ZIP of a release tag. Do not download the main branch of the repository. The release notes name the tag.

After you copy the kit into your project, run this command from the project folder:

```
python .claude/tools/doctor.py verify
```

The command compares each kit file with the SHA-256 value in `MANIFEST.txt`. It also runs the security scan. A changed file is reported. Do not use a copy that reports a changed file, unless you made the change yourself.

## Audit someone else's folder before you trust it

A project folder can hold hooks and settings that run when you open it. Claude Code asks you whether to trust the folder in interactive use. It does not ask in non-interactive mode (`claude -p`). Before you trust a folder that you did not write, list what it can run:

```
python .claude/tools/doctor.py audit path/to/other-project
```

The audit runs nothing and changes nothing. It lists hooks, status lines, key-helper commands, environment settings, allow rules, `.mcp.json`, scripts in `package.json`, and similar items. Ask Claude to explain each item before you trust the folder.

## Threat model and limits

The guard stops accidents and obvious mistakes. Examples:

- deleting the project folder, the home folder or a drive root
- a force push to any remote
- a secret file read by a shell program
- a key-shaped value written into a file or a command
- a change to the kit's own safety files

The guard does not stop:

- a model that reads text from a web page or a file and follows it (prompt injection)
- a determined agent
- scripts that the model did not write, and compiled programs
- MCP tools and web fetches
- commands that you type yourself in the terminal
- edits made outside Claude Code
- a hook that times out, or a broken `settings.json`

The full list of known gaps is in [How the kit works](.claude/docs/how-it-works.md#the-safety-guard-and-its-known-gaps). Maintainers also keep the list of command-guard gaps in the repository's `tests/guard-known-gaps.txt`. That file does not cover the commit and push scanner or the things the guard cannot see at all; those are in the page above.

## What is stored, and how to wipe it

The tutor stores its data in your project, in `.claude/agent-memory/tutor-data/`. It holds your profile, notes, progress list, journal, state and, if you turn it on, chat copies. Git ignores this folder.

Claude Code keeps its own transcript of each session on your computer. Terminal session transcripts are deleted after 30 days by default (`cleanupPeriodDays`). Desktop app transcripts are kept at any age unless you set `desktopSessionCleanupPeriodDays`. The settings reference, checked 2026-10-07, says so.

To delete the tutor's data, run one of these commands:

```
python .claude/tools/doctor.py wipe chat
```

```
python .claude/tools/doctor.py wipe state
```

```
python .claude/tools/doctor.py wipe all
```

Each command shows how many files it would delete. It deletes them only when you add `--yes`.

## Privacy

- Everything you type goes to Anthropic. That is the same as any Claude Code chat.
- Claude Code keeps the transcript on your computer. The tutor's own copies are redacted. The transcript is not.
- If you paste a key or a password into a chat, rotate it. Make a new key, then delete the old one at the provider that issued it.
- Chat copies are off by default.
- OneDrive, iCloud, Dropbox and Google Drive can upload your notes. Keep your project outside synced folders. A Git folder inside a synced folder can break.
- The tutor's scripts make no network calls, except as described above.

## How to report a vulnerability

Use this repository's **Security** tab. Choose **Report a vulnerability**. This is private reporting.

Do not open a public issue for a security problem. If the button is missing, the owner has not turned on private reporting yet. For a GitHub contact, use the repository page, or run `gh repo view` in your own terminal to see the repository's owner.

## Supported versions

Fixes go to the latest release only. Older tags do not get fixes. The current version is in `.claude/VERSION`.
