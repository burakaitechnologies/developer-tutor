---
name: save-point
description: >-
  "save", "save my work", "make a save point", "commit", "wrap up", "I am done for today", or
  before a risky change. Checks status and tests, commits specific files, says what is not saved.
---

# Save point

Purpose: make a save point (a Git commit) and leave notes, so that the next session starts where this one stopped.

A save point is a Git commit: a saved copy of the files that you can return to. Say this once at first use. Codex asks before it changes Git, because the sandbox keeps `.git` read-only (checked 2026-10-08). That is normal: say what each Git command does before it runs. Sentences in quotes below are English: say them in the learner's language and at their level. For the time, run one read-only command: `date "+%Y-%m-%d %H:%M"` (Git Bash) or `Get-Date -Format "yyyy-MM-dd HH:mm"` (PowerShell).

## When to use

- The learner says save, wrap up, or stop for today.
- A piece of work is finished.
- A multi-file or risky change is about to start (gate G1 in AGENTS.md, Safety): do the quick version.

Do not use it for these:
- A project with no commit yet: the `$new-project` skill makes the first one.
- Trouble with Git: the `$git-rescue` skill.
- Sending work online: the `$before-push` skill.
- A question about Git: the `$explain` or `$learn` skill.

## Two sizes

- **Quick save point** (before a risky change, or "checkpoint"): steps 1, 2 (status only), 5, 6 and one line of step 8. Message: `Save point before <change>`. No tests, no notes.
- **Full save point** (end of work or session): all steps.

Quiet mode ("just do it"): cut the explanations, glosses, checks, offers and optional questions. Keep these: the commit question of step 5, asked in one line unless the learner already said save; the result with a line `How to check:`; and the "not saved" line of step 8 at a full save point. Quiet mode is never a yes for anything else. After the learner answers, commit and give a one-line summary with a line `How to check:` that names one command the learner can run.

## Steps

1. **Is it a Git project with a commit?** Run `git rev-parse --is-inside-work-tree`, `git rev-parse --show-toplevel` and `git rev-parse --verify HEAD`.
   - Not a Git project, or the `git` command is missing: use "No Git yet" below.
   - The top folder is not this folder: a parent folder is a Git project. Stop, explain, ask.
   - No commit yet: start the `$new-project` skill (steps 5 to 9 make the first save point). Come back for steps 7 and 8.
   - Merge or rebase in progress, or a detached HEAD in the status text: start the `$git-rescue` skill.
2. **Look.** Run `git status --short --branch`, `git diff --stat` and `git diff --cached --stat`. Say in plain words which files are new, changed or deleted, by name; group them if there are many. Show a raw diff only when asked.
   - Names that must not be saved: `.env`, keys, `.sqlite` files, `node_modules`, `dist`, `__pycache__`, files over 5 MB, anything under `.tutor/`. Do not stage them. A missing `.gitignore` line: add it with apply_patch after a yes (new-project step 8 explains the file).
   - A deleted file the learner did not mention: ask before you stage it.
   - The `.agents` and `.codex` folders and `AGENTS.md` show as new: they hold the tutor's own files. Offer once to save them (new-project step 10). Until then leave them out and do not mention them again.
   - Nothing changed: say "Nothing to save since the last save point", then do step 7 if something was decided today.
3. **Tests.** Use only the test command the project itself names (README, `package.json` scripts, test config). Read what that command runs before you run it. Install nothing. Report exactly what you ran and what it printed. No tests: say "No tests exist yet. I checked it by <what you really did>."
   - A save point does not need green tests. If they fail, the message says so ("WIP: ... tests fail"). Recommend the `$fix-it` skill first, unless this is a checkpoint before a risky change.
   - If new behaviour is in this save point, name one command the learner can run to see it.
4. **Decision records.** Read `docs/decisions/README.md` if it exists. When a line's "revisit when" could be true after today's work, prepare ONE question for the closing message: "ADR 0003 said revisit when more than one person saves data. Is that true now?" Yes: start the `$think-first` skill. Nothing fits: say nothing.
5. **Stage by name.** Run `git add <file> <file>` with the real names. Never `git add .`, `git add -A` or `git commit -a` unless the learner asks after seeing the list. Reason: they stage everything that is not ignored, including a forgotten key or build folder. Explain staging once (card `git-staging`): it means choosing what goes into the next save point. More than about 12 files: stage by folder and read `git status --short`. Two unrelated parts: two save points, one part at a time (card `proj-small-commits`). A secret-looking name staged by mistake: `git restore --staged <file>` keeps the file; then fix `.gitignore`.
   Then run `git diff --cached --stat` and ask in ONE message, for example: "I will save 3 files: index.html (changed), style.css (new), README.md (changed). Message: Add ingredient list. Say yes, or give other words." The learner decides what the message says. Skip this question only when the learner already said save.
6. **Commit.** Run `git commit -m "<subject>"`, and a second `-m "<body>"` when the reason is not obvious.
   - Subject: imperative, about 50 characters, no full stop: "Add recipe list page". It says what changed.
   - One logical change per save point. No "wip" or "fix" alone. No secrets or personal data in the message: history is permanent.
   - Language: the one the earlier `git log` messages use; in a new log, English unless the learner prefers another. Avoid the characters $ ! % & and quote marks inside the text, because PowerShell and Bash read them. If the message has non-English letters, check `git log -1 --format=%s` shows them right; if not, use ASCII words.
   - "My turn", or the learner wants to type it: offer the learner the keyboard. Give the exact command. Codex CLI (terminal): a leading `!` runs it in the learner's own shell. App, local chat: New tab, then Terminal, or Ctrl+backtick (the key left of the 1 key). IDE extension: the editor's own terminal. Wait, then read the output together.
   - Then run `git log --oneline -n 3` and `git status --short`. If a safety stop blocks the commit, follow the two-sentence rule in AGENTS.md (Hard rules, rule 2) and fix the file, not the rule.
7. **Notes** (full save point; one step; do not describe it to the learner). Write the files in the same turn, in the learner's language. AGENTS.md, Memory, allows at most three small file writes per turn.
   1. `.tutor/now.md`, rewritten whole from `.agents/tutor/templates/now.md`, at most 60 lines. Directly under `Updated:` put a `## Handoff` heading and three lines: `Done: ...`, `Next: ...`, `Blocked: ...`, each under 20 words, with the short commit id. The next session reads the first 12 lines first, so the handoff goes first. Keep Goal, Next, "Waiting for the learner" and Open questions. Keep the last five "Done recently" lines and the declined-advice lines. Add today's decisions under "Decisions to remember" with the record path.
   2. Journal: append one entry to `.tutor/journal/YYYY-MM-DD.md`. Read the file first, then add the entry with apply_patch; a new day gets a new file. Form: `.agents/tutor/templates/journal-entry.md`. Settled events only: decisions agreed, work done with the short commit id, facts checked, ideas rejected and why, changes of plan. Paraphrase what the learner did; do not copy their words. Write no "Answered:" or "Not changed:" lines. No secrets.
8. **Close in plain words.** Four things, in this order, with no more than one question mark in the message:
   - What is saved: the short id and the message.
   - What is NOT saved: ignored files such as `.env` and databases (back the values up elsewhere, for example in a password manager); files left out on purpose (name them); your private notes about this project (on this computer only, not in Git). Give no file path for the notes.
   - The online copy: run `git remote -v`. No remote means "no online copy exists, so a broken computer loses the project". With a remote, run `git rev-list --count "@{u}..HEAD"` (keep the quotes: PowerShell reads `@{` as something else). A number above 0 means "N save points are not online yet"; an error about no upstream means nothing was pushed. State it and add "say push when you want it online". Never run `git push` here: the `$before-push` skill does it, with a checklist.
   - The closing ask, at most one: the decision-record question from step 4 if you prepared one. Otherwise, in a project with no Git, the "No Git yet" offer, once. If this session added a new package or a new folder, say so in one plain sentence now.
   - Length: the whole close is under 120 words. If the learner only says thanks or "see you", answer in two or three sentences: the short id, what is not saved in a few words, and one next step. Keep the no-backup line when there is no online copy.
9. **First-save-point extras.** After the first commit, or in a project that has Git but no `.gitignore` or no project section in AGENTS.md: offer the missing part with the `$new-project` skill (step 8 for `.gitignore`, step 10 for the project section). One offer per message, each with a one-sentence reason and a yes. A refusal is final for that session; record `declined` after two.

## No Git yet

The folder is not a Git project, so there is no history to save into.
1. Git missing: say what it is, point to `git-scm.com/downloads`, and let the learner install it.
2. Git present: offer the git steps of the `$new-project` skill. Give one reason ("a history you can return to, and the way to put your project online") and ask for a yes. Ask this once at wrap-up; a no ends the question for this session.
3. The learner says no: use a copy. Say honestly what it is: a manual save point. It cannot show what changed. It uses disk space. It does not remember why. A copy on the same disk, or in the same synced folder, is lost together with the original. An editor's undo is not a backup either: it covers only recent edits in that editor.
4. How: the learner copies the project folder in File Explorer or Finder, next to it, and adds the date to the name (`recipe-site-backup-2026-10-07`). If you do it, the target is outside the project folder, so ask first and name the path. Windows: `robocopy "<project>" "<copy>" /E /XD node_modules .venv`. macOS and Linux: `cp -R "<project>" "<copy>"`.
5. Then do the tests (step 3) and notes (step 7). In step 8 say that nothing is in a history yet.

## What to record

The notes are step 7. For anything else follow AGENTS.md, Memory and Teaching moves: a line in `.tutor/learner/notes.md` in the form `YYYY-MM-DD | event | thing | "exact words"`. Use `did` only when the learner typed the commit and told you what happened, in their own words. Use `learned` when they explain a save point in their words. Use `declined` for an offer they refuse. Then say: "Added to your list: <title>."

## Done when

- A commit exists, or the learner chose not to save, or nothing had changed.
- `git status` shows what remains, and you listed it.
- `.tutor/now.md` has the three-line handoff and the journal has today's entry (full save point).
- The learner heard what is not saved and where the only copy is.
