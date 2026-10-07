---
name: git-rescue
description: >-
  I broke git, undo that, I lost my changes, wrong branch, bad commit, merge conflict, detached
  HEAD, stuck rebase, push rejected. Looks first, saves a snapshot, then one safe recipe.
argument-hint: "[what went wrong, in your words]"
allowed-tools: >-
  Bash(git status *) Bash(git log *) Bash(git reflog -n *) Bash(git stash list *)
  PowerShell(git status *) PowerShell(git log *) PowerShell(git reflog -n *) PowerShell(git stash list *)
---

# git-rescue

Purpose: get the learner's work back, or undo a Git mistake, without losing anything more. Look first and change nothing until you know what happened. Save a snapshot before any change.

The learner may write in any language and may be scared. Answer in their language and level. Keep commands, file names and error text exactly as they are. Without a state block at session start, work from text alone as `.claude/CLAUDE.md` says; nothing here needs the helper scripts.

## When to use

- Work seems lost, or the learner wants to undo something.
- Git shows a message they fear: conflict, detached HEAD, rebase in progress, rejected push, "not allowed".
- save-point, fix-it or before-push sent you here.

Do not use it for these:
- A normal save or push: save-point, before-push.
- A secret that is in a pushed commit: go straight to recipe 9 below.
- An error in the learner's own code: fix-it.

## Hard stops

Reason for all of them: they destroy work or break other people's copies, and they cannot be taken back.
- Never run `git push --force`, `-f`, `+branch` or `--force-with-lease` (rule G6). A rejected push is a stop sign: read it, do not force it.
- Never rewrite pushed history yourself: no amend, rebase or reset of a commit that is on GitHub. Use `git revert`. Only the secret incident (recipe 9) needs a rewrite, and the learner runs it. The one exception: a local `git reset origin/main` that keeps your files (recipe 3, after an amend that was already pushed), after a yes. It moves only your local copy. Rewriting what is on GitHub is never allowed.
- Never run `git gc`, `git prune`, `git reflog expire`, `git clean -fd` or `git filter-branch`.
- Run `git reset --hard`, `git restore .`, `git checkout -- .`, `git clean -f` and `git branch -D` only after the snapshot, after a yes, and after you said what each one deletes.
- Do not delete `.git`. Do not suggest "start again from a fresh clone" as the first answer.
- Never ask for a password or token in the chat. Sign-in happens in the browser (recipe 10).
- A public repository is already copied: treat anything pushed there as published.

## Steps

1. **Say what you will do.** One or two sentences: you look first and change nothing. Do not promise that everything can be recovered, because you do not know yet.
2. **Is this a Git project?** Run `git rev-parse --show-toplevel`.
   - "not a git repository": the learner may be in the wrong folder. Compare with the folder that holds `.claude/settings.json`. If the project has no Git, Git has no history to restore. Say so plainly, then try these: the editor's undo; `/rewind` (only files Claude edited with its file tools); version history of OneDrive or Dropbox if the folder is synced; the Recycle Bin or Trash. A repository with no commit yet has nothing to restore either; the new-project skill makes the first save point. Teach the save-point habit later, not now.
3. **Look (read-only).** Run `git status`, `git log --oneline -n 10`, `git reflog -n 15` and `git stash list`. Tell the learner in three short lines: which branch, what is changed or missing, what the last save points are. Quote the one key line of output, not the whole output.
4. **Ask only if still unclear.** One question: "What did you do right before, and what did you expect to see?" If two recipes fit, ask which result the learner wants.
5. **Pick the recipe** with the table below.
6. **Place the work on the ladder** below and say it in one sentence, for example: "Your change is saved on your computer but not online, so Git can bring it back."
7. **Snapshot first**, before any command that changes or discards. See "Snapshot".
8. **Read the recipe.** Read `${CLAUDE_SKILL_DIR}/references/recipes.md` (about 200 lines) and use the section you picked. It has the exact commands for PowerShell and Git Bash, what each one does, and how to verify.
9. **Tell the plan in plain words, then ask for one yes.** Say what each command does and what could still be lost. Name any command that will open a permission question, so the question does not look like an error.
10. **Run the recipe step by step.** After each command quote the key output line. Then run the verify command and show the result as evidence: "I checked: `git status` says the working tree is clean."
11. **Teach one idea, after the fix, when the learner is calm.** Reuse the `plain` text of one card: `git-reflog`, `git-restore`, `git-reset`, `git-revert`, `git-stash`, `git-conflict`, `git-four-places` (find the id in `.claude/knowledge/concepts-index.txt`, then Read that line of the card file with `limit` 1). For "where did my work go" use the picture "Git's four places" in `.claude/knowledge/diagrams.md`. Offer the next safe habit: a save point before a risky change (rule G1). A fixed mistake is a finished piece of work, so the style's rules for one check and one offer apply; an open error is not.
12. **Close.** Say where the work is now. Name the snapshot, and say it stays until the learner deletes it; offer to remove it in a later session. Do not delete it now.

## Which recipe

| The learner says or sees | Recipe |
|---|---|
| "undo my edits", "undo what Claude just did", "I want the old version of a file", a file shows `modified` | 1 (3 if it was committed) |
| "I committed on main", "wrong branch" | 2 |
| "my last commit is wrong", "wrong message", "forgot a file", "undo my commit" | 3 |
| "I deleted a file", "my commits are gone", after `reset`, deleted a branch | 4 |
| `CONFLICT`, `<<<<<<<`, `both modified`, "Automatic merge failed" | 5 |
| `HEAD detached` | 6 |
| "rebase in progress", "You have unmerged paths", `index.lock` | 7 |
| "I pushed the wrong thing", `rejected`, `non-fast-forward`, `fetch first` | 8 |
| a key, password or personal data reached GitHub | 9 |
| `Authentication failed`, `Permission denied`, `Repository not found`, `403`, `dubious ownership` | 10 |

No recipe fits: stay read-only, describe what you see in plain words, and check `git-scm.com/docs` for the command before you suggest it (`.claude/rules/checking-facts.md`).

## The ladder: where is the work safe?

| Where the work is | What can bring it back |
|---|---|
| Typed, not saved to disk | The editor's undo. Git and Claude cannot see it. |
| Saved, not committed | Only a snapshot made before the mistake. `reset --hard`, `restore` and `clean` erase it for good. |
| Committed on this computer | `git reflog` for 30 days or more (by default), or a backup branch. |
| Pushed to a private repository | The copy on GitHub; fix forward with `git revert`. Other people with access may have it. |
| Pushed to a public repository | It cannot be unpublished. Other people can copy it quickly. Revoke secrets first. |

## Snapshot

Say why in one sentence: a snapshot is a copy that stays in `.git`, so a wrong step can be undone.
- **Committed work at risk** (reset, rebase, branch changes): `git branch backup-before-rescue-<date>`. It costs nothing and moves nothing.
- **Uncommitted edits at risk:** `git stash push -u -m "snapshot before rescue" -- . ':(exclude).claude'`, then at once `git stash apply`. The stash is the copy; `apply` puts your edits back and keeps the copy. A plain `git stash push -u` would also move the untracked `.claude` folder out of the project for a moment; the exclude part prevents that. `-u` adds new files but not ignored ones such as `.env`; copy those by hand if they matter. "No local changes to save" means nothing needs a snapshot.
- **A merge, rebase or cherry-pick is in progress:** do not stash (Git refuses). The abort command in the recipe returns to exactly the state before; make only the backup branch.
- Recipes 9 and 10 change no files, and a look-only step needs no snapshot.

## What to record

Follow `.claude/rules/keeping-memory.md`. After a repair, append one journal line: what happened, what restored it, and the snapshot name. Settled events only, paraphrased: no learner quotes. Never write a secret in it. An inbox record only when the learner's own words show they did or understood something: `did` if they typed the verify command and explained the result, `learned` if they explain in their words where the lost work was. Commands you ran give no credit, and a failed run or a guess is not a record. When a record is saved, say the output style's line: "Added to your list: <title>."

## Done when

- The verify command ran and its output matches what the learner wanted.
- The learner can say in one sentence where their work is now.
- Any snapshot is named, with how to delete it later.
- Nothing that was pushed has been rewritten by you.
- The journal has its line.
