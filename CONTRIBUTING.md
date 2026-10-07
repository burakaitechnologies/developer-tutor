# Contributing

Thank you for helping. Read this page before you change a file. The kit teaches beginners, and most rules here protect them. To add a card, a milestone, a skill, a tripwire, a guard rule or a hook, read [.claude/docs/extending.md](.claude/docs/extending.md) as well.

## Principles

- **Teaching first.** A change must help a beginner learn, or must keep them safe while they work.
- **One home for each fact.** A fact lives in one file. Other files link to it. `validate.py` checks the links.
- **Plain words.** Use short sentences. Explain each term the first time it appears.
- **An observed failure first.** A new feature needs a failure that you saw in a real session or a test. Write the failure in the change note.
- **No network.** Shipped code makes no network call. See [SECURITY.md](SECURITY.md).
- **Python 3.9 and the standard library only.** Do not add a third-party package.
- **No personal data.** Use neutral examples. Never add names, e-mail addresses, handles or absolute machine paths.

## Run the checks

Run the commands from the repository root. Use one Python order on every page, the same as the README. On Windows, type `py -3`. If that does not work, type `python`. On macOS and Linux, type `python3`. If that does not work, type `python`. In the commands below, `<python>` stands for the one that works.

1. Check the kit files. This takes a few seconds:

   ```
   <python> -I -B -X utf8 .claude/tools/validate.py
   ```

2. Run the quick self-tests:

   ```
   <python> -I -B -X utf8 .claude/tools/selftest.py --quick
   ```

3. Run the full self-tests. This takes about one minute:

   ```
   <python> -I -B -X utf8 .claude/tools/selftest.py
   ```

4. Run the Python 3.9 check on the test code:

   ```
   <python> tests/lint_py39.py
   ```

5. Run the mock-CLI scenarios. They start the real `claude` program with a fake model. You do not need to log in. If `claude` is not on the PATH, the scenarios print SKIP and exit with 0.

   ```
   <python> tests/test_mock_cli.py
   ```

6. Run the simulated session tool. With no arguments it prints its command list:

   ```
   <python> tests/sim_session.py
   ```

Run the self-tests on Python 3.9 as well as on a newer Python. CI runs both on Ubuntu, Windows and macOS. See the note in `.github/workflows/selftest.yml` about the macOS Python 3.9 job, which is not verified yet.

## Developer mode

While you edit a hook, turn the hooks off for this project. Create `.claude/settings.local.json` with this content:

```json
{"disableAllHooks": true}
```

The file is ignored by Git. Delete it when you finish. Never commit it.

## Rules for tests

- Build every secret-shaped test string from fragments at run time. A key-shaped literal must not appear in any shipped file.
- Generate fixtures at run time, or write them with the editor. Do not commit a fixture that looks dangerous, such as a delete command.
- Use no personal data in fixtures. The personal-data scan checks the shipped files.
- Test on folder names with a space and a Turkish letter. Windows users have these.
- Write only to a scratch folder under the system temporary folder. Remove it at the end.
- Test the failure path too. A check that cannot fail is not a check.

## File and byte rules

- Line endings are LF.
- Files are UTF-8 without a byte-order mark.
- No trailing spaces. No tabs.
- Hook output is plain ASCII where possible. Hooks write bytes to the console, so the output never crashes on a Windows code page.
- Python files start with `from __future__ import annotations`. They set `sys.dont_write_bytecode = True`.
- HTML comments are allowed only in `CLAUDE.md`, the README files, the docs and the templates. Never put one in a skill, an agent, a rule or the output style.
- Headings use sentence case.

## Skill and agent front matter

- Write the `description` of a skill as a folded block: `description: >-`, with the text on the following lines.
- Keep `description` plus `when_to_use` to 210 characters or fewer for each skill. Keep the total for all eleven skills to 2,300 characters or fewer. `validate.py` checks both.
- Put the trigger phrases first. Claude Code cuts the listing after 1,536 characters, checked 2026-10-07.
- Never write a double-quoted `description` that contains an inner quote. Claude Code drops the whole skill without a message.
- Agent `description` values are 250 characters or fewer. Give each agent a short read-only tool list.
- No agent may have both a read tool and a web tool.
- Use `${CLAUDE_SKILL_DIR}` or `${CLAUDE_PROJECT_DIR}` only in a `SKILL.md` body. Elsewhere, write a path from the project root.

## Facts that change between Claude Code versions

The kit relies on the facts below. Check each one again when Claude Code changes. Update the file named in the right column when a fact changes.

| Fact the kit relies on | Where it is written down | Last checked |
|---|---|---|
| The skill listing budget is 1% of the context window. Each description and when_to_use text is cut at 1,536 characters. | Claude Code skills docs. The limit is `SKILL_DESC_MAX` in `validate.py`. | 2026-10-07 |
| Skill allow rules use the form `Skill(name)`. | Claude Code skills docs and the settings in `settings.json`. | 2026-10-07 |
| A PreToolUse hook that prints `permissionDecision: "allow"` skips the permission prompt. The kit never prints it, and a test fails if it does. | Claude Code hooks docs. The test is in `selftest_guard.py`. | 2026-10-07 |
| Plain stdout becomes context only for some events. The docs list SessionStart, UserPromptSubmit, UserPromptExpansion and PostModelSwitch. The kit uses the first two only. | Claude Code hooks docs. | 2026-10-07 |
| PostToolUse and SubagentStart need one JSON object. Other stdout is a hook error. | Claude Code hooks docs. | 2026-10-07 |
| Stop with `additionalContext` makes Claude take another turn. The kit prints nothing on Stop. | Claude Code hooks docs. | 2026-10-07 |
| A hook output field is capped at 10,000 characters. The kit caps its output at 9,000. | Claude Code hooks docs. | 2026-10-07 |
| Exit code 2 blocks a PreToolUse call, even when the JSON says allow. | Claude Code hooks docs. | 2026-10-07 |
| Interactive sessions hold back hooks until you accept the trust dialog. `claude -p` never shows the dialog. | Claude Code hooks docs and SECURITY.md. | 2026-10-07 |
| A session started in a subfolder does not run hooks. CLAUDE.md files in subfolders load on demand. | Claude Code memory docs. The mock-CLI scenario M-21 checks it. | 2026-10-07 |
| Desktop permission modes are Manual, Accept edits, Plan and Auto. The mode selector sits next to the send button. Shift+Tab cycles the modes in the terminal. | Claude Code Desktop docs and interactive mode docs. | 2026-10-07 |
| The Desktop mode you pick overrides `defaultMode` for that folder. | Claude Code Desktop docs. | 2026-10-07 |
| The tested Claude Code version is 2.1.288. The changelog dates it 2 October 2026. The helper scripts need 2.1.139 or newer, a figure from the kit's design. | Claude Code changelog. | 2026-10-07 |
| A Claude Code account is Pro, Max, Team, Enterprise or Console. The free plan has no Claude Code. | Claude Code setup docs. | 2026-10-07 |
| On native Windows, Claude Code runs commands without a sandbox. | Claude Code sandboxing docs. | 2026-10-07 |
| Terminal transcripts are kept for 30 days by default (`cleanupPeriodDays`). Desktop transcripts are kept at any age unless `desktopSessionCleanupPeriodDays` is set. | Claude Code settings reference. | 2026-10-07 |
| Hook launcher text in `tools/hooks.json`. On Windows, `python3` can be the Microsoft Store stub. The kit detects the stub. | `tools/hooks.json`, `doctor.py`, mock-CLI scenario M-10. | 2026-10-07 |
| The grep tool hides lines longer than about 500 characters. | Named in the kit's design notes. Not found in the Claude Code docs. | Not verified |
| "TrustFall", a May 2026 report about trust dialogs. | Secondary news summaries only. Not verified. | Not verified |
| CI actions: `actions/checkout` and `actions/setup-python` are both at major version 7. | Each action's README on GitHub. | 2026-10-07 |
| Anthropic's terms require users of Claude Code to be adults. The README states this. No exact clause was checked. | Anthropic's consumer terms. | Not verified |

## Licence

There is no licence file yet. The owner chooses a licence before or after publishing. Until then the default copyright rules apply. Do not add a licence file, and do not pick a licence in a change. Ask the owner.

## Regenerate the generated files

Some files are generated. Never edit them by hand. Run these commands in this order, from the repository root:

```
<python> -I -B -X utf8 .claude/tools/validate.py --write-commands
```

```
<python> -I -B -X utf8 .claude/tools/validate.py --write-index
```

```
<python> -I -B -X utf8 .claude/tools/validate.py --write-manifest
```

Run `--write-manifest` last. It records the SHA-256 value of every shipped file. Any later change makes the manifest stale.

## Release checklist

1. Choose the version. Update `.claude/VERSION` and `.claude/CHANGELOG.md`.
2. Run the checks in the section above. All must pass.
3. Run the full self-tests on Windows, macOS and Linux, and on Python 3.9 and a newer Python.
4. Run `tests/test_mock_cli.py` on a machine with Claude Code. Copy the results into `docs/test-report.md`.
5. Regenerate the generated files in the order above. Write the manifest last.
6. Check that the project has no `settings.local.json`, no `agent-memory/` folder and no `__pycache__/` folder.
7. Check that `.claude/settings.json` has no `hooks` key. The hooks must stay off in the shipped kit.
8. Run the personal-data scan. It is part of `validate.py --release`.
9. Make sure no TO FILL AT RELEASE text is left in the README files or the changelog, and update the result column of `docs/test-report.md`. Then create the release tag. Then download the tag as a ZIP, copy the kit into an empty folder and run `doctor.py verify`.
10. Ask the owner to run the live check in `docs/test-report.md`. Record the result there.

## Dropped guard rows

No guard row was dropped in version 1.0.0. If you drop a row from the guard catalogue, add a row here. Give the rule name, the reason and the date.
