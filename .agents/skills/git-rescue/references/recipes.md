# Git rescue recipes

Read the section for your situation. Make the snapshot from SKILL.md first, unless the recipe is read-only. Commands are the same in PowerShell and Git Bash unless a note says otherwise. The kit notes say these recipes were tested with Git 2.54 on Windows; wording of messages differs a little between versions.

Windows notes:
- PowerShell: put single quotes around any word that contains `@{`, for example `'HEAD@{1}'` and `'@{u}'`. Without quotes PowerShell cuts the word: `HEAD@{1}` became `HEAD@`, and `@{u}..HEAD` is a syntax error. In the old Command Prompt use double quotes.
- Windows PowerShell 5.1 saves a file written with `>` as UTF-16, which Git cannot read. Write files with apply_patch.
- Output that stops and waits is a pager: press `q`. An unfamiliar editor window (Vim) opened by a commit: press Esc, type `:q!`, press Enter, then use `-m` or `--no-edit` next time.
- `<id>` means the short commit id from `git log --oneline`, for example `4f3d043`. `<file>` is a real file name.

## Recipe 1: I edited a file and want the old version back

Look: `git diff <file>` shows the unstaged edits you would lose, and `git diff --staged <file>` shows the staged copy, if there is one.
- Want to discard my edits: `git restore <file>`. It brings back the staged copy if something is staged for that file; otherwise it brings back the last save point's version. This replaces the file. Edits that were never committed or stashed are gone for good.
- Want the version from an earlier save point:
  1. `git log --oneline -- <file>` lists the save points that touched it.
  2. `git show <id>:<file>` shows that old text. Nothing changes.
  3. `git restore --source=<id> -- <file>` puts the old text in the file. It shows as `modified`; commit it if you keep it.
- Staged by mistake (`git status` lists it under "Changes to be committed"): `git restore --staged <file>` unstages and keeps your edit.
Verify: `git status` and `git diff <file>`.
Git cannot restore a file that was never committed, or text that was never saved. Try the editor's undo, OneDrive or Dropbox version history, the Recycle Bin.

## Recipe 2: I committed on the wrong branch (not pushed yet)

- Edits not committed yet: `git switch -c <new-branch>`. The edits come along; main is untouched.
- Commits on main that belong on a new branch:
  1. `git log --oneline -n 5` and `git status -sb`. The status says `ahead N`: N is the number of commits to move.
  2. `git switch -c <new-branch>`. The new branch now holds the commits.
  3. `git branch -f main origin/main` moves main back to what GitHub has. With no remote, use `git branch -f main HEAD~N`. (Codex asks before this command; that is expected.)
- Commits that belong on an existing branch: `git switch <branch>`, then `git cherry-pick <id>` for each commit (oldest first), then `git branch -f main <oldest-id>~1` while you stand on that branch. Git refuses `branch -f` on the branch you stand on, so main must not be the current branch.
Verify: `git log --oneline --graph --all --decorate` shows main at the old place and the commits on the other branch.
Already pushed to main: recipe 8.

## Recipe 3: The last commit is wrong

| Situation | Use |
|---|---|
| Not pushed; wrong message or a forgotten file | amend |
| Not pushed; redo the content | `reset --soft` or `reset` |
| Not pushed; throw it away | backup branch, then `reset --hard` |
| Pushed anywhere, private or public | `revert` |

- Amend: `git commit --amend -m "New message"`. A forgotten file: `git add <file>` then `git commit --amend --no-edit`. It makes a new commit id and replaces the old one.
- Redo: `git reset --soft HEAD~1` undoes the commit and keeps the changes staged. `git reset HEAD~1` keeps them as plain edits. Then commit again.
- Throw away: `git branch backup-before-rescue-<date>`, then `git reset --hard HEAD~1`. This also erases uncommitted edits. The backup branch keeps the commit.
- Pushed: `git revert --no-edit HEAD` adds a new commit that cancels the old one, then a normal `git push`. For a merge commit add `-m 1` (keep parent 1), or Git refuses.
- I amended after pushing: `git status -sb` says `ahead 1, behind 1` and `git push` is rejected. Do not force. After a yes: run `git branch backup-amended`, then `git reset origin/main`. Your files stay as they are; `git status` shows your changes as edits. Commit them as a normal new commit and push. GitHub keeps the pushed commit; only your local copy changes.
- A file that should never be tracked (a build folder, a database; not a secret): after a yes, `git rm --cached <file>` (for a folder add `-r`) removes it from Git and keeps it on disk. Add its name to `.gitignore` with apply_patch, then `git add .gitignore` and commit. Old commits still contain it. If it was a secret: recipe 9.
Verify: `git log --oneline -n 3` and `git status -sb`.

## Recipe 4: I deleted a file, or commits are gone

- Deleted, not committed yet: `git restore <file>`. For a whole folder, `git ls-files --deleted` lists what is missing and `git restore <folder>` brings back that folder only. Do not use `git restore .`: it also discards edits elsewhere.
- Deleted and the deletion is committed:
  1. `git log --diff-filter=D --oneline -- <file>` shows the commit that deleted it.
  2. `git restore --source=<id>~1 -- <file>` brings it back from the commit before. It shows as new; `git add <file>` and commit.
- Commits gone after `reset --hard`, a deleted branch, or leaving a detached HEAD:
  1. `git reflog -n 15` lists where HEAD pointed, newest first. Find the line from before the mistake.
  2. `git branch rescued <id>` makes a branch at that commit and leaves everything else alone. (`git switch -c rescued 'HEAD@{1}'` also works: `HEAD@{1}` is "one move ago".)
  3. A branch removed with `git branch -D` printed `(was 084fee0)`: `git branch <name> 084fee0`.
Verify: `git log --oneline -n 5 rescued`, then open the file.
Limits: the reflog lives only in this repository on this computer. Git keeps entries for 90 days. Entries for commits that are no longer on a branch, the ones you want back, last 30 days (git-scm.com/docs/git-reflog). Edits that were never committed are not in it.

## Recipe 5: Merge conflict

Git could not combine two changes to the same lines. Nothing is broken. `git merge --abort` returns to before the merge.
1. `git status` lists `both modified` files. `git diff --name-only --diff-filter=U` lists only those.
2. Open each file. Git wrote both versions between markers:
```
<<<<<<< HEAD
body { color: green; }
=======
body { color: red; }
>>>>>>> theme-red
```
   Above `=======` is the branch you stand on (HEAD). Below is the other branch (here `theme-red`). During a rebase the two sides swap places.
3. Decide with the learner: keep one side, keep both, or write a mix. Edit the file so it holds only the final text and none of the three marker lines. To take a whole side: `git restore --theirs <file>` or `git restore --ours <file>`.
4. Check that no marker is left: `git grep -n -E '^(<<<<<<<|=======|>>>>>>>)'` prints nothing.
5. `git add <file>`, then `git commit --no-edit`.
Verify: `git status -sb` shows no `UU` lines and no merge message.
A conflict from `git stash pop` is resolved the same way: edit the file, then `git add <file>`. No commit is needed. The stash stays in the list until you run `git stash drop`. Committing with markers still in the file is the usual mistake.

## Recipe 6: HEAD detached

`git status` says `HEAD detached at <id>`: you stand on an old commit, not on a branch. Commits made here belong to no branch.
- Only looking around: `git switch main`, or `git switch -` to return to where you were.
- Made commits or edits you want to keep: `git switch -c <new-branch>` before you leave. They stay.
- Already switched away: Git printed a warning with the id. Run `git branch <new-branch> <id>`, or use `git reflog -n 15` (recipe 4).
Verify: `git status -sb` shows a branch name.

## Recipe 7: Stuck in a rebase, merge, cherry-pick or revert

`git status` names the state at the top ("rebase in progress", "You have unmerged paths", "All conflicts fixed but you are still merging") and prints the way out.
- Go back to exactly before: use the abort that matches. `git merge --abort`, `git rebase --abort`, `git cherry-pick --abort`, `git revert --abort`. You lose only the half-finished operation, not earlier commits. Parts of the conflict you already resolved are lost; redo them later.
- Finish instead (all conflicts resolved): `git add <file>`, then `git commit --no-edit` (merge) or `git rebase --continue`.
- `Unable to create '.git/index.lock': File exists`: another Git program may be running. Close editors with Git panels and wait a minute. Look for a running Git process (Windows Task Manager, PowerShell `Get-Process git -ErrorAction SilentlyContinue`, or `ps aux` on macOS and Linux). If none runs, delete that one file, `.git/index.lock`, after a yes.
Verify: `git status -sb` shows a plain branch line.

## Recipe 8: I pushed the wrong thing, or the push was rejected

First ask: private or public? Run `gh repo view --json visibility --jq .visibility` (needs `gh`), else ask the learner to read the word beside the repository name on github.com. Unknown counts as public.
- Private, plain mistake (wrong file, broken code): fix forward. `git revert --no-edit <id>` (add `-m 1` for a merge), then `git push`. History keeps both commits; that is fine.
- Public: same fix, but strangers may have copied it. If it is a secret or personal data: recipe 9. Say plainly that a public push cannot be taken back.
- Never reset, amend or rebase and then force-push. Other copies break, and GitHub keeps what was pushed.
- Rejected push (`fetch first`, `non-fast-forward`): GitHub has commits you lack. Do not force.
  1. `git fetch`, then `git status -sb` (`ahead N, behind M`).
  2. `git log --oneline HEAD..origin/main` lists what you lack.
  3. Only behind: `git pull --ff-only`. Both ahead and behind: `git merge origin/main --no-edit`. A conflict: recipe 5; `git merge --abort` undoes the merge.
  4. `git push`.
Verify: `git status -sb` shows no `ahead` or `behind`. Add `git log --oneline --graph -n 6`.

## Recipe 9: I pushed a secret

Do not repeat the secret. Name the provider from the key's shape (`sk-` is OpenAI or Anthropic, `sk-ant` is Anthropic, `ghp_` or `github_pat_` is GitHub, `AKIA` is AWS). Tell the learner to revoke the key at that provider first: removing it from the files does not stop it working. Remove it second, and rewrite history last (only the learner does that). Follow `.agents/skills/before-push/references/secret-incident.md`.

## Recipe 10: "Git says I'm not allowed"

Read the exact message, then look: `git remote -v` (does the address start with `https://` or with `git@`?), `gh auth status` (which account, signed in?), `git config user.name`.

| Message | Meaning and fix |
|---|---|
| `Authentication failed`, `could not read Username`, `403` over HTTPS, "password authentication was removed" | A password no longer works. The learner runs `gh auth login`: GitHub.com, HTTPS, answer `Y` to authenticate Git, "Login with a web browser". The sign-in happens in the browser. Windows with an old saved login: Control Panel, User Accounts, Credential Manager, find the GitHub entry and delete it, then push again. |
| `Repository not found`, `404` | The address is wrong, or the repository is private and this account cannot see it. Copy the address from github.com, compare with `git remote -v`, fix with `git remote set-url origin <address>`. |
| `Permission to ... denied to <user>` | You are signed in as another account than the owner. Run `gh auth status`, then sign in as the owner. |
| `Permission denied (publickey)` | The remote is an SSH address (starts with `git@`) and no key matches. Simplest fix: `git remote set-url origin https://github.com/OWNER/REPO.git`, then `gh auth login`. |
| `detected dubious ownership` | The folder belongs to another Windows or Linux user (copied from another drive or computer). If the learner made this folder, they run the `git config --global --add safe.directory '<path in the message>'` command that the message prints. It changes their global Git settings, so ask first. |
| `Unable to create ... index.lock` | Recipe 7. |
| `Protected branch update failed` | GitHub rules block direct pushes to this branch. `git switch -c <name>`, `git push -u origin <name>`, then open a pull request. |
| Secrets detected, push blocked | Do not bypass. Use recipe 9. |
| `exceeds GitHub's file size limit of 100.00 MB` | A big file is in a commit. Use the before-push skill, step "Large files". |

Never paste a token into the chat. Never run `gh auth token` or `gh auth status --show-token`. Never put a token inside a remote address. Never switch off certificate checks.
