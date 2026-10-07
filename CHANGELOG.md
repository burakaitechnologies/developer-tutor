# Changelog

All notable changes to developer-tutor (Codex edition) are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-10-08

Ported from the Claude Code edition on the main branch. Facts about Codex were checked in its documentation on 2026-10-08. The owner sets the release date when the kit is published.

### Added

- The teaching design of the Claude Code edition: voice, levels, checks, offers, handover, design gate, safety gates and concept cards.
- Eleven skills, started with `$name`: `$tutor`, `$tutor-setup`, `$learn`, `$progress`, `$explain`, `$think-first`, `$new-project`, `$fix-it`, `$save-point`, `$before-push` and `$git-rescue`.
- Two read-only custom agents in `.codex/agents/`: `architecture_reviewer` and `code_reviewer`.
- `.codex/config.toml`, with the approval policy `on-request`, the sandbox `workspace-write` and a 48 KiB limit for instructions.
- `.codex/rules/tutor.rules`, with prefix rules that ask before or refuse risky commands.
- `.tutor/`, the notes folder, with a `.gitignore` that Git reads to ignore its contents.
- Concept cards, a glossary, stack notes, milestones, diagrams and forms under `.agents/tutor/`.
- Guides under `.agents/tutor/docs/`.
- Repository files: README, SECURITY, CONTRIBUTING, this changelog and the test report.

### Changed

- The kit's instructions are one file, `AGENTS.md`, with named sections.
- `.claude/skills/` became `.agents/skills/`. Skill front matter keeps only `name` and `description`.
- `.claude/agent-memory/tutor-data/` became `.tutor/`.
- `settings.json` became `.codex/config.toml` and `.codex/rules/tutor.rules`.
- Skills are started with `$name`, not with slash commands.
- The two agents became custom agents in TOML files, with read-only sandboxes.
- The tutor keeps its notes by hand, as Markdown.

### Removed

- Hooks, and the helper scripts that the hooks needed: the installer, the doctor, the validator and the self-tests.
- The command guard, the secret scanner, the verified quotes, the state header, chat copies and the inbox.
- The output style file, the manifest and the permission rules of `settings.json`. The Codex rules file replaces the permission rules.

### Known issues

- Not tested with Codex. Nobody has run the kit in a Codex session. The owner's live check is in [docs/test-report.md](docs/test-report.md).
- Rules match the start of a command. A force push written after the branch name is asked, not refused. A command wrapped in another shell may not match a rule.
- Codex calls rules experimental, and they can change (checked 2026-10-08).
- There is no command guard and no secret scanner. Reads of `.env` are refused only for the common commands.
- When many skills are loaded, Codex may shorten or leave out some descriptions. Then the tutor may not start a skill from plain words.
- `AGENTS.md` is advice to the model. It is not a lock.
- There is no licence file yet.
