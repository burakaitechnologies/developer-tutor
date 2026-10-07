# A secret got out

Use this when a key, token, password, private key or database address with a password was committed, pushed or pasted into the chat. Order: revoke first, remove second, rewrite history last. The learner runs the rewrite. You explain it and never run it.
Do not repeat the secret. Do not delete the repository, because clones and forks survive. Do not force-push. Do not put the value in a file, command or search.

## 1. Where is it?
- Only in a working file: move it to `.env` (SKILL.md, "If you find a secret").
- In a local commit, not pushed: part A. Revoking is optional but cheap: the value sat on this computer, maybe in the chat.
- Pushed, private or public: parts 2 to 6. Public is urgent: bots scan new commits for keys within minutes.
- Pasted in the chat only: parts 2 and 3. Session files on this computer also hold what was typed.

## 2. Revoke or rotate (the learner, at the provider)
Name the provider from the key's shape (`sk-ant` is Anthropic, `ghp_` or `github_pat_` is GitHub, `AKIA` is AWS), even if the learner found the key on another site. Revoke it on that provider's page: delete it there and create a new one. Page names change: search the provider's docs for "revoke API key". A GitHub token: GitHub settings, Developer settings. A database password: change it in the database. Never ask the learner to paste the old or the new value.

## 3. Check for misuse
The learner opens the provider's usage or billing page and the security log. They look for activity they do not know and set a spending limit (card `arch-anti-paid-api-loop`).

## 4. New value in `.env`
The learner pastes the new value into `.env` in their editor, and into the host's settings. You may write `.env.example` with fake values. Check `git check-ignore -v .env` prints a rule.

## 5. Remove it from the current files
Code reads the value from the environment. If Git tracks the file, after a yes: `git rm --cached <file>`, put its name in `.gitignore` (Write or Edit tool), `git add .gitignore`, commit, `git push`. Old commits still hold the value; that is acceptable once it is revoked.

## 6. Rewrite history (last, optional, the learner runs it)
Needed when the repository is public or the data cannot be revoked (personal data). Not needed for a revoked key in a private repository nobody else cloned. Read each command before you run it: the command guard does not catch every form of these commands. Kit note: from the kit notes dated 2026-10-07 (docs.github.com, "Removing sensitive data from a repository"); not checked today. Not run on the build machine: the learner reads that page and the git-filter-repo manual first.
1. Revoke first (part 2).
2. Install git-filter-repo, version 2.47 or newer (needed for `--sensitive-data-removal`); its README shows how.
3. In their own terminal (Desktop app, local session: the Terminal button in the session title bar), in a new folder: `git clone https://github.com/OWNER/REPO`, then `cd REPO`.
4. Remove a file from all history: `git-filter-repo --sensitive-data-removal --invert-paths --path <file>`. Replace text instead: the learner writes the text in a file OUTSIDE the project, then `git-filter-repo --sensitive-data-removal --replace-text <that file>`. The tool removes the `origin` remote by default: check `git remote -v` and add it back (manual).
5. Check: `git log --all --oneline --name-only -G'<the variable name>='`. Only `.env.example` may appear.
6. Push everything rewritten: `git push --force --mirror origin` (the step GitHub's page names). Pull request references are read-only and fail; that is expected. Only the learner types this.
7. Ask GitHub Support to clear cached views and pull request references; give the repository name and the first changed commits that git-filter-repo printed.
8. Everyone with a clone re-clones, or rebases (not merges). Forks keep the old data.
Simpler for a private repository nobody else uses: a clean copy with new history (public-flip.md, part H).

## A. Not pushed yet (also for a big file in unpushed commits)
1. `git log --stat '@{u}..HEAD'` shows which outgoing commit holds it. First push: `git log --stat`. Note the last commit before it entered.
2. `git branch backup-before-secret-fix`. It still holds the secret: delete it at the end with `git branch -D backup-before-secret-fix` (Claude Code asks first).
3. Remove the value from the files; after a yes, put the file name in `.gitignore`.
4. After a yes: `git reset --soft <that commit id>` (`origin/main` to collapse everything outgoing). All later changes become staged. In the very first commit: ask the learner; a clean copy (public-flip.md, part H) is simplest.
5. `git restore --staged <file>`, `git add .gitignore`, check `git status -sb`, then one new commit.
6. Check `git log --oneline --name-only -G'<the variable name>='` lists only `.env.example`. Delete the backup. The old commits stay in this computer's reflog up to 30 days and never left it.

## Prevent a repeat
`.gitignore` and `git check-ignore -v .env` before the first `git add`; fake values in `.env.example`; one key per purpose with the least access and a spending limit. GitHub push protection covers public repositories, not a private one on a free personal account (card `gh-security-alerts`).
After: one journal line without the value ("A key for <provider> was exposed and revoked").
