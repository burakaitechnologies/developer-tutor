# Extending the kit

This page is for people who change the kit itself: the concept cards, the milestones, the skills, the tripwires, the guard rules and the hooks. Learners do not need it. Read the repository's CONTRIBUTING file first. It has the rules for files, tests and releases.

The commands below run from the repository root. Use the Python order from the README: `py -3` on Windows, `python3` on macOS and Linux, and `python` if those fail. In the commands, `<python>` stands for that one.

## 1. Run the checks after each change

1. Check the kit files. This takes a few seconds:

   ```
   <python> -I -B -X utf8 .claude/tools/validate.py
   ```

2. Run the self-test module that matches your change, for example `files`, `guard`, `trip`, `hooks`, `prompts` or `perf`:

   ```
   <python> -I -B -X utf8 .claude/tools/selftest.py --only files
   ```

3. Before you finish, run every module:

   ```
   <python> -I -B -X utf8 .claude/tools/selftest.py
   ```

`validate.py` prints ERROR and WARN lines. It exits 1 on any ERROR. It checks the links between files, the word and token budgets of the files every session loads, the skill and agent front matter, the concept cards, the milestones, the glossary, the probes and the manifest. With `--release` it also runs the personal-data scan. A WARN line never fails the run.

When you change a generated input, regenerate in this order. Write the manifest last:

```
<python> -I -B -X utf8 .claude/tools/validate.py --write-commands
```

```
<python> -I -B -X utf8 .claude/tools/validate.py --write-index
```

```
<python> -I -B -X utf8 .claude/tools/validate.py --write-manifest
```

`--write-commands` rewrites the skill table in `docs/commands.md`. `--write-index` rewrites `knowledge/concepts-index.txt`. `--write-manifest` records the SHA-256 value of every shipped file, so any later change makes the manifest stale.

## 2. Concept cards

Each concept card is one JSON object on one line in `knowledge/concepts/<domain>.jsonl`. Write the file as UTF-8 with LF line endings. Every card has the same 16 keys, in this order:

| Key | Rule |
|---|---|
| `id` | Lower case words joined by hyphens. Starts with the domain and a hyphen, for example `git-repo`. Unique across all files. |
| `title` | A short name. Not empty. |
| `domain` | One of `term`, `files`, `git`, `gh`, `cc`, `prog`, `web`, `data`, `test`, `sec`, `arch`, `proj`, `ai`. Must match the file name. |
| `tier` | `1` or `2`. Version 1 has no tier 3. |
| `needs` | Up to 3 concept ids that must come first. No cycles. Chains of tier-1 cards are at most two steps deep. |
| `terms` | A list of words. The first is the main term. The rest are aliases. |
| `signals` | Lower case text of at least 4 characters. The tutor matches them against commands, file names and the learner's message. Do not use generic words alone. |
| `plain` | At most 35 words in plain language. It names the real term and uses no metaphor. |
| `check` | One question that ends with a question mark. It must not be a yes-or-no question. |
| `check_type` | `explain`, `predict`, `do`, `debug` or `review`. A domain with more than 35 percent `explain` gets a warning. |
| `rubric` | Two or three short bullets that describe what a good answer shows. |
| `try` | One safe, reversible step with the exact command and what the learner should see. |
| `pitfall` | The wrong belief, and the correct idea. |
| `volatile` | `true` or `false`. Use `true` for product behaviour that changes over time. |
| `src` | Required when `volatile` is `true`: a link that starts with `http` to the primary document. Empty otherwise. |
| `verified` | A real date as `YYYY-MM-DD`. Required when `volatile` is `true`: the day the facts were checked. Empty or a date otherwise. |

The glossary, `knowledge/glossary.jsonl`, holds jargon terms that have no card. Its keys are `term`, `aliases`, `plain` (1 to 25 words), `domain` and `jargon` (true). A term lives in a card or in the glossary, never in both.

To add a card, add its row, add its id to the `Concepts:` line of at least one milestone, then regenerate the index and run the checks in section 1.

## 3. Milestones

`knowledge/milestones.md` is a menu, not a syllabus. It has 12 headings, `## M1` to `## M12`, in order. Each milestone has these lines:

- a heading in the form `## M<number> <title>`
- `Project:`, one sentence about the real project the milestone builds
- `Concepts:`, a comma-separated list of card ids. Each id must exist as a card.
- `Alone when:`, the signals that show the learner can do it alone. Every milestone needs one.
- `Stumbling:`, the usual mistakes

The file has at most 120 lines. Keep the hard-gates section at the end. Each tier-1 card should appear in at least one milestone. If it does not, say why in the change note.

## 4. Skills

A skill is one folder, `skills/<name>/`, with a `SKILL.md` file. It may hold `references/*.md` files in the same folder, and nothing else.

- `name` is the folder name.
- `description` is a folded block, `description: >-`, with the trigger phrases first.
- `when_to_use` is optional.
- `allowed-tools` lists only the commands the skill needs. Keep them read-only where you can. `validate.py` warns about a git command that changes history.
- `description` and `when_to_use` together are at most 210 characters for each skill. The descriptions of all skills together are at most 2,300 characters. Claude Code cuts each listing at 1,536 characters.
- Never write a double-quoted `description` that contains an inner quote. Claude Code drops the skill without a message.
- The skill-directory variable of Claude Code works only in the body of `SKILL.md`. Elsewhere, write a path from the project root.

The kit has eleven skills. `validate.py` lists their names, and `settings.json` has one `Skill(name)` allow rule for each. A new skill changes the list, the allow rules, the self-test counts of eleven and the skill table. Discuss it with the owner first. After the change, run the checks in section 1, then `--write-commands`.

## 5. Tripwires

A tripwire looks at one file the agent just wrote, or at one shell command, and reports a pattern that a beginner project should not carry silently. Tripwires only nudge. They never block. The rules are in `hooks/lib/archrules.py`.

Each rule has:

- an id and a kind: `code`, `manifest`, `top-dir`, `big-file` or `workflow`
- a plain message in the `MESSAGES` table, with `short`, `why`, `safe` and `lesson`. The `lesson` value must be a concept id that exists.
- a place in `PRIORITY`, which sets the order in which rules are shown
- an entry in `MODEL_VISIBLE_RULES` if the model should see it. Other rules are only logged to `activity.jsonl`.

Patterns use bounded gaps only, never an unbounded `[^x]*`, so a hostile file cannot stall the hook. Files over 200 KB and lines over 2,000 characters are skipped or cut before any pattern runs.

To add a rule, add its positive and negative samples to `tools/selftest_data/trip_samples.json`, under `rules`, with the rule id. Then run `selftest.py --only trip`.

## 6. Guard rules

The guard decides with one of three tiers. `block` denies the call. `ask` lets the learner decide, with the reason shown. `warn` gives a one-line heads-up to the model. The rules are in `hooks/lib/guardrules.py`. Each rule has a plain message in `hooks/guard-messages.json`, with `short`, `why`, `safe` and `lesson`.

The corpora are tab-separated files in `tools/selftest_data/`. Each row has six columns: the tool (`Bash`, `PowerShell`, `Write`, `Edit` or `NotebookEdit`), the expected decision, the rule ids, the folder, the command or path, and a note.

- `guard_evasion.tsv`: tricks such as aliases, call operators and encoded commands. Add a new trick here.
- `guard_everyday101.tsv`: everyday commands. Only the two pushes may be flagged.
- `guard_beginner160.tsv`: realistic beginner commands. None may be blocked.
- `guard_tamper.tsv`: commands that try to switch the guard off.
- `guard_files.tsv`: Write, Edit and NotebookEdit calls.
- `guard_gaps.tsv`: known gaps. A gap row must stay allowed. Closing a gap is a deliberate change: move the row to `guard_evasion.tsv` with its new tier, and update the known gaps in `docs/how-it-works.md`.

A new block or ask must not flag any row of the everyday and beginner corpora, except the intended pushes. Run `selftest.py --only guard` after each rule change.

## 7. Hooks

A hook is one mode in `hooks/dispatch.py`. The mode runs a handler module in `hooks/handlers/`. The modes are `session-start`, `user-prompt`, `pre-tool`, `post-tool`, `stop` and `subagent-start`. The command line that Claude Code runs for each event is in `tools/hooks.json`.

- `PostToolUse` and `SubagentStart` print one JSON object.
- `SessionStart` and `UserPromptSubmit` print plain text, which becomes context.
- `Stop` prints nothing.
- Never print a permission `allow`. A test fails if the kit does.
- Keep the output under 9,000 characters.
- A start-up failure prints one line on stderr. It exits 0 for `pre-tool`, the guard, and 1 for the other hooks. It never exits 2.
- The median run time of each hook must stay under 250 milliseconds. The `perf` module checks this.

When you add or change a hook, update the launcher in `tools/hooks.json`, the hooks table in `docs/how-it-works.md`, and the hooks table in the repository's SECURITY.md. The table must say what each hook reads and writes. Then run `selftest.py --only hooks`, `--only prompts` and `--only perf`.

## 8. Using the kit in a project that already has files

The installer, `tools/install.py`, handles an existing project in these ways:

- It refuses a folder that has files but no project file, such as `.git`, `package.json`, `README` or `index.html`. The flag `--yes-this-is-my-project` overrides this.
- It lists everything in the project that can run code or change safety rules, such as allow rules, hooks and status lines. If there is any, it stops until you run again with `--accept-existing`.
- It copies only the kit files that are missing. A first install never overwrites an existing file.
- It merges `settings.json`. Objects are merged. Lists are joined without repeats. A value that already exists stays. A different kit value is reported as a warning. The kit's hooks are not merged this way. The old file is kept as `settings.json.tutor-backup`.
- It never edits the project's root `CLAUDE.md` or the root `.gitignore`.

On 2026-10-07 the builders ran this in a scratch folder with a `package.json`, a root `CLAUDE.md` and a `.claude/settings.json` that held an allow rule and an `outputStyle` of `Explanatory`. The installer refused until `--accept-existing` was given. After that run the root `CLAUDE.md` was unchanged. The allow rules, `defaultMode` and deny rules were merged in. The old settings file was kept as `settings.json.tutor-backup`. The `outputStyle` stayed `Explanatory`, and the installer warned about it. This was a check of the installer only. No session was opened with a real model.

Test any change to `install.py` or to the merge rules in this way, on a scratch copy.

For learners, the README section "Using the kit in a project that already has files" lists the practical cases. Three need care:

- The helper scripts run only when the session starts in the folder that holds `.claude`. The mock test M-21 checks this. No real-model run has been done.
- A project memory file can be `./CLAUDE.md` or `./.claude/CLAUDE.md`. The kit's rules sit in `.claude/CLAUDE.md`. Keep a root `CLAUDE.md` consistent with it.
- A tutor voice needs `outputStyle` set to `tutor`. The installer keeps an existing value and warns.

## 9. A checklist for each change

1. Run `validate.py`. Fix every ERROR. Read every WARN.
2. Run the self-test module for the part you changed.
3. Run the full self-test on your own machine. The CI runs it on three systems.
4. Regenerate the generated files in the order in section 1, and write the manifest last.
5. Run `doctor.py verify` on a copy of the kit. It should report no changed file.
6. Add a line to the change note. Name the observed failure that the change fixes.
