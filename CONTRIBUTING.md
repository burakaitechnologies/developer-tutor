# Contributing

Thank you for helping. Read this page before you change a file. The kit teaches beginners, and most rules here protect them. Skills, concept cards and rules each have a home. Put each fact in one place.

## Principles

- **Teaching first.** A change must help a beginner learn, or keep them safe while they work.
- **One home for each fact.** A fact lives in one file. Other files link to it.
- **Plain words.** Use short sentences. Explain each term the first time it appears.
- **No scripts, no hooks.** This edition has none. Adding one needs a decision record in `docs/decisions/` that says why (form: `.agents/tutor/templates/decision-record.md`).
- **Small instructions.** Keep `AGENTS.md` under 32 KiB, and ideally under 20 KB. Codex stops reading instruction files at 32 KiB in total (checked 2026-10-08).
- **Short skill descriptions.** Each `description` is at most 210 characters, with the trigger phrases first.
- **No personal data.** Use no names, e-mail addresses, handles or absolute machine paths.

## Check your change by hand

This edition has no automated tests. Run these checks yourself from the repository root. Write the results in [docs/test-report.md](docs/test-report.md), section 1.

1. **Rules.** Run `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- git push origin main`. The JSON output shows `prompt`. Run it again with `-- git push --force origin main`. It shows `forbidden`. The `execpolicy` command is in preview (checked 2026-10-08).
2. **TOML files parse.** Run `python -c "import tomllib; tomllib.load(open('.codex/config.toml','rb'))"`, then the same for each file in `.codex/agents/`. Python 3.11 or newer is needed. On Windows, use `py -3` if `python` is not found. No error means the file parses.
3. **Skill front matter.** Print the first 8 lines of each `SKILL.md`. Line 1 is `---`. Then comes `name:` with the folder name, then `description:`, then `---`. No other key is allowed. (PowerShell: `Get-Content -TotalCount 8 <file>`. Bash: `sed -n 1,8p <file>`.)
4. **AGENTS.md size.** Run `wc -c < AGENTS.md` (PowerShell: `(Get-Item AGENTS.md).Length`). The result must be under 32768. Ideally it is under 20480.
5. **No scripts.** Run `find . -type f \( -name "*.py" -o -name "*.sh" -o -name "*.ps1" -o -name "*.js" \)`. It must print nothing.
6. **Leftover words.** Run `grep -n -iE "claude|anthropic|\.claude|CLAUDE\.md|settings\.json|hook|doctor\.py|install\.py|validate\.py|selftest|state block|Shift\+Tab|/tutor|allowed-tools|argument-hint|CLAUDE_|agent-memory|tutor-data|inbox|ledger|helper script" <files>`. Every hit must be intentional. For example, a sentence that says this edition has no hooks is intentional.
7. **File bytes.** Check that a file has no carriage returns (`grep -c $'\r' <file>` prints 0) and no trailing spaces (`grep -n " $" <file>` prints nothing). Check the file starts without a byte-order mark.
8. **Skill list.** Start Codex in the project folder and type `/skills`. It must list eleven skills.

## Port a fix from the main branch

The Claude Code edition on the main branch is the source for teaching changes. To bring a fix here:

1. Read the change on the main branch with `git show <commit>`.
2. Skip the parts that exist only in the Claude Code edition: hooks, scripts, settings files, the output style, the state header, chat copies, the inbox and the self-tests.
3. Port the teaching text with the mapping below. Keep the meaning of the teaching the same.
4. Run the checks in the section above, including the leftover words check.
5. Add a line to [CHANGELOG.md](CHANGELOG.md).
6. If a Codex fact changed, update the table below and [docs/test-report.md](docs/test-report.md).

| In the Claude Code edition | In this edition |
|---|---|
| `CLAUDE.md`, `.claude/CLAUDE.md`, `.claude/rules/*` | `AGENTS.md`, with a named section |
| `.claude/skills/<name>/` | `.agents/skills/<name>/` |
| `/tutor`, `/save-point` | `$tutor`, `$save-point` |
| `.claude/knowledge/`, `.claude/templates/`, `.claude/docs/` | `.agents/tutor/knowledge/`, `.agents/tutor/templates/`, `.agents/tutor/docs/` |
| `.claude/agent-memory/tutor-data/` | `.tutor/` |
| `settings.json` permission rules | `.codex/config.toml` and `.codex/rules/tutor.rules` |
| Agents `architecture-reviewer`, `code-reviewer` | Custom agents `architecture_reviewer`, `code_reviewer` in `.codex/agents/` |
| Shift+Tab mode switch | `/permissions` in the terminal, the permissions control in the app |

## File rules

- Line endings are LF. Files are UTF-8 without a byte-order mark.
- No trailing spaces. No tabs.
- Write files with an editor that saves LF. Windows PowerShell redirection can save UTF-16, which Git cannot read.
- Headings use sentence case.

## Skill and custom agent rules

- A skill folder holds `SKILL.md`. Its front matter keeps only `name` and `description`.
- `description` is a folded block, `>-`, with the trigger phrases first.
- A custom agent file in `.codex/agents/` has `name`, `description` and `developer_instructions`. A reviewer also sets `sandbox_mode = "read-only"` (checked 2026-10-08).

## Release checklist

1. Choose the version. Update `.agents/tutor/VERSION` and [CHANGELOG.md](CHANGELOG.md).
2. Run the checks in the section above. Write the results in [docs/test-report.md](docs/test-report.md).
3. Check that the kit holds no notes. Only `.tutor/.gitignore` may be in `.tutor/`.
4. Check that the kit holds no secret and no personal data. Search for the at sign (`@`) and for the owner's own name.
5. Ask the owner to run the live check in [docs/test-report.md](docs/test-report.md), section 3. Record the result there. Until then, the status stays "ported, not tested".

## Version-fragile facts

Each Codex fact below lives in the place named in the right column. Check each one again when Codex changes. Update the place named when a fact changes.

| Fact the kit relies on | Where it is written down | Last checked |
|---|---|---|
| Skills live in `.agents/skills/`. They start with `$name` or `/skills`. Codex may pick one by its description. | README, `AGENTS.md` (Which skill to start) | 2026-10-08 |
| The skill list uses at most 2% of the context window, or 8,000 characters if the window is unknown. Long descriptions are shortened first. | This page, skill rules; `docs/test-report.md`, section 2 | 2026-10-08 |
| `AGENTS.md` is read up to 32 KiB in total. The limit is `project_doc_max_bytes`. | This page, principles; `.codex/config.toml` | 2026-10-08 |
| Project `.codex/` layers load only in a trusted folder. An untrusted folder may start read-only. | README step 5; [SECURITY.md](SECURITY.md), the trust question | 2026-10-08 |
| In the workspace sandbox, `.git`, `.codex` and `.agents` are read-only. `.tutor/` is writable. | [SECURITY.md](SECURITY.md); `AGENTS.md` (Surfaces) | 2026-10-08 |
| Rules are `prefix_rule` entries with `prompt` or `forbidden`. The strictest rule wins. Rules are experimental. | `.codex/rules/tutor.rules`; [SECURITY.md](SECURITY.md) | 2026-10-08 |
| `codex execpolicy check` tests a rule file. The command is in preview. | This page, check 1 | 2026-10-08 |
| The app shows Ask for approval, Approve for me and Full access. The terminal `/permissions` shows presets such as Auto and Read Only. | README step 5; `AGENTS.md` (Surfaces) | 2026-10-08 |
| Custom agents live in `.codex/agents/`. Codex starts one only when asked. | README (What you get); `AGENTS.md` (Helpers) | 2026-10-08 |
| Codex is included in the Free, Go, Plus, Pro, Business, Enterprise and Edu plans. | README (Requirements) | 2026-10-08 |
| Install commands for the app and the CLI, and `codex --version`. | README step 0 | 2026-10-08 |
| On Windows, Codex runs commands in PowerShell with a Windows sandbox, or in WSL2. | README (Requirements); [SECURITY.md](SECURITY.md) | 2026-10-08 |
| Codex supports hooks. This edition uses none. | [SECURITY.md](SECURITY.md), what the kit does not contain | 2026-10-08 |
| Web search is on by default in cached mode. Codex sends anonymous usage data by default. `analytics.enabled` turns that off. | [SECURITY.md](SECURITY.md), network | 2026-10-08 |
| Session transcripts are saved under `~/.codex` by default. `history.persistence` controls this. | [SECURITY.md](SECURITY.md), what is stored | 2026-10-08 |
