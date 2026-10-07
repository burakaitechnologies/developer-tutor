# Extending the kit

This page is for people who change the kit itself: the skills, the concept cards, the command rules and the custom agents. Learners do not need it.

Facts about Codex on this page were checked on 2026-10-08 against the official Codex docs. Keep that date in the change note when you check a new fact.

## Checks you can run

This edition has no test scripts and no validator. Check each change by hand. Then run these commands from the project folder:

- Find every mention of a word you changed. In PowerShell: `Select-String -Path .agents\tutor\docs\*.md -Pattern "word"`. Update each file that matches.
- Check the size of `AGENTS.md` in bytes: `(Get-Item AGENTS.md).Length`. Codex reads at most 32 KiB, which is 32768 bytes (checked 2026-10-08).
- Count the lines of a page: `(Get-Content .agents\tutor\docs\faq.md).Count`.
- Test a command rule: `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- git status`.
- Check that each line of a card file is valid JSON: `Get-Content .agents\tutor\knowledge\concepts\git.jsonl | ForEach-Object { $_ | ConvertFrom-Json | Out-Null }`. An error names the bad line.

After a change to a rule, a skill or an agent file, restart Codex and open a new chat. Codex detects skill changes by itself, but a skill that does not appear needs a restart (checked 2026-10-08).

The live check for the whole kit is in `docs/test-report.md` in the repository. Run it after any change to the instructions.

## Add a skill

A skill is one folder: `.agents/skills/<name>/SKILL.md`. It may have a `references/` folder beside the file. Nothing else goes in the skill folder.

- The front matter needs two keys: `name` and `description` (checked 2026-10-08).
- Use the same `name` as the folder.
- Write `description` as a folded block, `description: >-`. Put the trigger phrases first. Keep it at most 210 characters. This is a kit rule.
- Codex shows every skill's name and description in a list. The list uses at most 2 percent of the context window (checked 2026-10-08). If the window size is unknown, the limit is 8,000 characters. Long descriptions are shortened first, so keep them short.
- Learners start a skill with `$name`. Codex can also pick a skill by its description (checked 2026-10-08).
- A skill has no slash command. Do not add one.
- Keep the steps in `SKILL.md`. Put long tables in `references/`. Give the path from the project root, for example `.agents/skills/learn/references/playbook.md`.
- Add the skill to the "Which skill to start" list in `AGENTS.md`. Then update the README and the FAQ if they name the skill.

Keep `SKILL.md` at most 300 lines.

## Add a concept card

A concept card is one JSON object on one line. Cards live in `.agents/tutor/knowledge/concepts/<domain>.jsonl`. The domain is the file name without `.jsonl`, for example `git.jsonl` for the `git` domain. Write UTF-8 with LF line endings.

Each card has the same 16 keys, in this order:

| Key | Rule |
|---|---|
| `id` | Lower case words joined by hyphens. It starts with the domain and a hyphen, for example `git-repo`. It is unique across all files. |
| `title` | A short name. Not empty. |
| `domain` | The domain code. It must match the file name. |
| `tier` | `1` or `2`. |
| `needs` | Up to 3 card ids that must come first. No cycles. |
| `terms` | A list of words. The first word is the main term. The rest are aliases. |
| `signals` | Lower case text, at least 4 characters. The tutor matches them against commands, file names and the learner's words. Do not use generic words alone. |
| `plain` | At most 35 words in plain language. It names the real term. It uses no metaphor. |
| `check` | One question that ends with a question mark. It is not a yes or no question. |
| `check_type` | `explain`, `predict`, `do`, `debug` or `review`. |
| `rubric` | Two or three short bullets. Each one says what a good answer shows. |
| `try` | One safe, reversible step. Give the exact command and what the learner should see. |
| `pitfall` | The wrong belief, and the correct idea. |
| `volatile` | `true` for product behaviour that changes over time. Otherwise `false`. |
| `src` | Needed when `volatile` is `true`: a link that starts with `http` to the main document. Empty otherwise. |
| `verified` | The date the facts were checked, as `YYYY-MM-DD`. Needed when `volatile` is `true`. Empty or a date otherwise. |

After you add a card:

1. Add its id to the `Concepts:` line of at least one milestone in `knowledge/milestones.md`.
2. Add one line to `knowledge/concepts-index.txt`. The format is `id | title | domain | t1 or t2 | needs: ids or - | terms: a, b | signals: a, b | file.jsonl:line`. The last part gives the file name and the line number of the card.
3. Run the JSON check in [Checks you can run](#checks-you-can-run).

Jargon with no card goes in `knowledge/glossary.jsonl`. Its keys are `term`, `aliases`, `plain` (1 to 25 words), `domain` and `jargon` (true). A term lives in a card or in the glossary, never in both.

## Add a command rule

Command rules live in `.codex/rules/tutor.rules`. Each rule is one `prefix_rule()` call. These fields are used (checked 2026-10-08):

- `pattern` is the start of the command, as a list of words, for example `["git", "push"]`. A list inside the list gives alternatives at one position.
- `decision` is `allow`, `prompt` or `forbidden`. Always write it. If you leave it out, the rule allows the command.
- `justification` is one plain reason. When you forbid a command, name a safe alternative in it.
- `match` and `not_match` are example commands. Codex checks them when it loads the rules, so a mistake shows before the rule takes effect.

Rules to follow:

- Never write `allow` with a short pattern such as `["git"]`. That allows every Git command.
- Use `prompt` for a command that writes, sends or deletes.
- Test each change with `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- <command>`. Add the same command to `match` or `not_match`.
- Rules load only in a trusted folder. Restart Codex after a change.

## Add a custom agent

A custom agent is one TOML file in `.codex/agents/`. Codex loads it by the `name` field. The file name should match the name (checked 2026-10-08). These fields are used:

- `name` (required): the name Codex uses to refer to the agent.
- `description` (required): when Codex should use the agent. Keep it short.
- `developer_instructions` (required): what the agent does and what it must not do.
- `sandbox_mode` (optional): `read-only` for a reviewer.

```toml
name = "code_reviewer"
description = "Read-only reviewer of one change. Use it when the learner asks for a review."
sandbox_mode = "read-only"
developer_instructions = """
Read the change. Report problems with file names and line numbers.
Do not edit files. The reader is a beginner: use plain words.
"""
```

Codex starts a custom agent when you ask for it in a direct request, such as "spawn code_reviewer" (checked 2026-10-08). An agent does not see the voice in `AGENTS.md`. Tell it that the reader is a beginner.

## The 32 KiB budget

Codex stops adding instruction files once their combined size reaches 32 KiB (`project_doc_max_bytes`, checked 2026-10-08). The whole chain counts, including a learner's own global file in `~/.codex`. The kit's `AGENTS.md` is about 18 KB when this page was written.

Every new paragraph in `AGENTS.md` uses some of the budget. Move detail into a docs page or a skill reference. Then link to it from `AGENTS.md`.

## No hooks in this edition

This kit ships no hooks. Read [why this edition has no hooks](how-it-works.md#why-this-edition-has-no-hooks) first.

If you add a hook anyway, do these things:

- Codex reads hooks from a `hooks.json` file or a `[hooks]` table in `config.toml` (checked 2026-10-08).
- Each hook must be reviewed and trusted with `/hooks` before it runs (checked 2026-10-08).
- A file check matches `apply_patch`, `Edit` or `Write` (checked 2026-10-08).
- Update the section on hooks in `how-it-works.md`, the FAQ and the change note. Then test the hook with the live check.

## Writing rules for the kit

- UTF-8 without a byte order mark. LF line endings. No tabs. No trailing spaces.
- Plain words. Sentences of about 20 words at most. Pages that a new learner reads first use 12 words at most.
- Write a Codex fact that can change with the date, for example "(checked 2026-10-08)". If you cannot confirm the fact in the docs, leave it out or say how the learner can find out.
- Do not name another edition of the kit in a learner-facing page.
- Keep commands, file names and error text exactly as they are.
- Do not write "easy", "just", "simply", "obviously" or "of course".

## Change checklist

1. Make the change. Search for every mention of it, and update each one.
2. Check the size of `AGENTS.md` against the 32 KiB budget.
3. Check each new card line, command rule and agent file as described above.
4. Keep the FAQ at 30 questions, five in each theme. Keep each answer at most 6 lines. Keep each heading at most 90 characters.
5. Run the live check in `docs/test-report.md` and write down what you saw.
6. Add one line to `CHANGELOG.md` in the repository. Name the failure the change fixes.
