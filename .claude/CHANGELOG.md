# Changelog

All notable changes to developer-tutor are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [1.0.0] - 2026-10-08

Build date. The owner sets the release date when the kit is published.

### Added

- Tutor output style and six rules: clear writing, checking facts, safety, the design gate, keeping memory and tidying the project.
- Eleven skills: tutor, tutor-setup, learn, progress, explain, think-first, new-project, fix-it, save-point, before-push and git-rescue.
- Two read-only helper agents: architecture-reviewer and code-reviewer.
- Learner records in `.claude/agent-memory/tutor-data/`, which Git ignores. They hold the profile, notes, progress and a journal.
- A permission floor in `settings.json`: deny and ask rules for secret files, force pushes and destructive commands, and allow rules for the eleven skills.
- Optional helper scripts (hooks). They are off until you turn them on. They add facts to each message and a safety guard.
- `tools/doctor.py` with the commands check, progress, enable-hooks, disable-hooks, envcheck, audit, share-notes, wipe and verify.
- `tools/install.py` for a terminal install, with --dry-run, --update and --uninstall. It installs into an empty folder without a flag.
- `tools/validate.py` and `tools/selftest.py` for the kit's own checks.
- Concept cards, a glossary, stack notes, milestones and ASCII diagrams in `knowledge/`.
- Documentation in `.claude/docs/` and `.claude/README.md`, including a getting-started guide and a troubleshooting guide with exact fixes.
- Repository files: README, SECURITY, CONTRIBUTING, a CI workflow, and the test report.

### Known issues

- Real-model behaviour was not verified by the builders. The owner's live checklist is in the file docs/test-report.md in the repository root, outside this folder. Until its rows are filled in, treat the tutor's behaviour as untested with a real model.
- The mock Claude Code runs had 3 failing scenarios (M-4, M-11 and M-16). In a 200K context window, some skills may be listed by name only, without a description. Then the model may not choose a skill from plain words. Shorter skill descriptions, or a larger `skillListingBudgetFraction` in `settings.json`, may help. Check this on the live checklist.
- When both an ask rule in `settings.json` and the safety guard apply to a command such as `git push`, the permission floor may answer first. You still get asked. The guard's longer explanation may not show. The rules in `rules/safety.md` carry that teaching.
- The install and check commands were run on Windows 11. The Desktop app steps and the macOS and Linux steps are not yet checked on a real computer.
- If the installer or `doctor.py verify` reports kit files that differ from `MANIFEST.txt`, follow [Kit files differ from the release](docs/troubleshooting.md#kit-files-differ-from-the-release).
- The Python 3.9 run in CI is the first real Python 3.9 run of the whole suite.

### Not in 1.0.0

- Coach mode, a status line, pre-compact, session-end and subagent-stop hooks, helper records, a handoff file, a weekly digest, a notices store, an exposure store, an injection-scan hook, tier-3 concepts, a misconceptions file, a fact-checker agent and a ConfigChange hook. These are planned for a later version.
