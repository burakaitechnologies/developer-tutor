---
name: before-push
description: >-
  push, publish, put it on GitHub, make it public, share my code, upload my project. Checks
  secrets, visibility, large files, personal data, README, tests; ends with go or no-go. Never
  force-pushes.
---

# before-push

Purpose: check what is about to leave the learner's computer, then give a go or no-go in plain words. Until the verdict, run only read-only checks and change nothing.

A push copies save points (Git commits) to GitHub. Only committed work goes. On a public repository, strangers can read and copy it quickly, and it cannot be unpublished. Answer in the learner's language and level. Keep commands, file names and error text exactly as they are.

This kit has no automatic secret check on push. You do the secret check yourself (step 5), and say so. Codex asks approval before a `git push`, because the push writes to `.git` and uses the network (checked 2026-10-08). Tell the learner that the question is coming. That is normal.

Codex asks before it changes Git; the sandbox keeps `.git` read-only (checked 2026-10-08). Say what each Git command does before it runs.

## When to use

- The learner says push, publish, put it on GitHub, make it public, share it, or upload it.
- The `$save-point` or `$new-project` skill hands over because the learner wants the work online.
- A private repository should become public: also read `.agents/skills/before-push/references/public-flip.md`.

Do not use it for these:
- Saving on this computer: the `$save-point` skill.
- A push that fails (rejected, "not allowed"): the `$git-rescue` skill.

## Hard rules

- Never run `git push --force`, `-f`, `+branch` or `--force-with-lease` (gate G6). A rejected push is a stop sign: the `$git-rescue` skill, recipe 8.
- Run `git push` only after a go and a yes from the learner. Tell them the approval question is coming; it appears for a push.
- Never print or repeat a secret. Name the file and the line number only.
- Unknown visibility counts as public.
- Never make a repository public yourself. The learner does that in GitHub's settings, after the checklist.
- A check that could not run is "not checked", with the reason. It never counts as passed.

## Steps

1. **Say what you will check.** Two sentences: where it goes, what goes, secrets, size, who can read it. You change nothing yet.
2. **Where it goes.** Run `git remote -v`. No remote: nothing can be pushed yet. If the learner wants a GitHub repository, create it PRIVATE with the `$new-project` skill, after a yes. Note OWNER and REPO from the address. If the learner has not said why they push, ask one question: a safe copy (private is right), friends who read the code (invite them to a private repository, or go public after the checklist), or a website (GitHub Pages needs a public repository on GitHub Free; card `gh-pages`, verify)?
3. **Who can read it.** Run `gh --version`. If it works: `gh repo view --json visibility --jq .visibility` prints `PUBLIC` or `PRIVATE` (`INTERNAL` for company accounts). `gh` uses the network, so Codex asks approval first; that is normal. If `gh` is missing or not signed in, ask the learner to read the label beside the repository name on github.com. A repository that does not exist yet will be private. Say the result in plain words. A private repository that should become public: read `.agents/skills/before-push/references/public-flip.md` and finish every part of it before the verdict.
4. **What goes.** Run `git branch --show-current`, `git status -sb`, and `git log --stat '@{u}..HEAD'`. Keep the quotes; PowerShell reads `@{` as something else. The error `no upstream configured` means a first push: run `git log --stat` instead, because everything goes. Tell the learner in plain words: how many save points, how many files, any file name that surprises you. Edits that are not committed do not go; say so if `git status` shows some, and offer the `$save-point` skill first. Run `git ls-files .tutor`: it must print nothing. The notes folder stays out of Git.
5. **Secrets.**
   1. `git check-ignore -v .env` should print a line that names `.gitignore`. It checks the name, so `.env` need not exist. Nothing printed has three possible causes: the file is not ignored; Git already tracks it (`git ls-files .env` prints `.env`, and ignore rules no longer apply to it); or `.gitignore` is missing or was saved as UTF-16 by a Windows redirect.
   2. `git ls-files .env '*.env' '*.pem' '*.key' 'id_rsa*' 'id_ed25519*' 'credentials.json'` should print nothing. `.env.example` is fine.
   3. Content, file names only (so no secret enters the chat):
      - `git grep -I -l -i -E 'api[_-]?key|secret|token|password|BEGIN [A-Z ]*PRIVATE KEY'` lists tracked files that mention such words. Most hits are harmless code. Open each hit yourself and look for a real value.
      - `git grep -I -l -E 'sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{30,}|xox[abprs]-[A-Za-z0-9-]{10,}'` lists files with key shapes.
      - `git log '@{u}..HEAD' --oneline --name-only -i -G'api[_-]?key|secret|token|password'` lists outgoing commits that touched such lines, even if a later commit removed them. First push: replace `'@{u}..HEAD'` with `--all`.
   4. Say the limits honestly: these checks find common shapes and words. They miss unusual passwords, secrets inside images, zip files, PDFs, databases or very big files. A clean result lowers the risk and does not prove there is none.
   5. Found something: the verdict is no-go. Follow "If you find a secret" below.
6. **Large files.** GitHub warns at 50 MiB per file and blocks the push at 100 MiB per file (kit note: docs.github.com, "About large files on GitHub", from the kit notes dated 2026-10-07; not checked today, so check the page again before you rely on it). List the big files that would be pushed:
   - Git Bash: `git rev-list --objects '@{u}..HEAD' | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | awk '$1=="blob" && $3>52428800 {print $3, $4}'`
   - PowerShell: `git rev-list --objects '@{u}..HEAD' | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' | ForEach-Object { $p = $_ -split ' ', 4; if ($p[0] -eq 'blob' -and [int64]$p[2] -gt 50MB) { '{0:N0} MB  {1}' -f ($p[2] / 1MB), $p[3] } }`
   - First push: use `HEAD` in place of `'@{u}..HEAD'`. Nothing printed means no file is over 50 MiB.
   - A big file is in an unpushed commit: do not push. Put its name in `.gitignore`. Then follow the "Not pushed yet" steps in `.agents/skills/before-push/references/secret-incident.md`; they remove any unwanted file from unpushed commits. A file that must stay big needs Git LFS; read its docs first.
7. **Personal data.** Never real client, patient, student or financial data in a project (gate G3).
   - `git grep -I -l -E '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}'` lists files with e-mail-like text. Open each hit and decide.
   - `git ls-files '*.csv' '*.xlsx' '*.sqlite' '*.sqlite3' '*.db' '*.sql'` lists data files. Ask what each one holds. Real people's data: no-go.
   - `git shortlog -sne --all` shows the names and e-mail addresses on commits. On a public repository these are public. For new commits suggest the GitHub no-reply address (card `git-identity`). Old commits keep the old address.
8. **README.** `git ls-files 'README*'`, then read it as a stranger: what it is, how to run it, no secrets, no personal paths. Public: required. Private: recommended.
9. **Licence (public only).** A licence is a text file, usually named `LICENSE`, that tells strangers what they may do with the code. With none, copyright law keeps all rights with the author: people may view and fork it on GitHub, but may not reuse it (GitHub docs). Ask the learner what they want: may others reuse it, even for money, or not? MIT and Apache-2.0 are common permissive choices. Point to choosealicense.com or GitHub's licence picker, and copy the exact text from there; do not retype a licence from memory. The copyright line holds the name that will be public; the learner chooses it (a GitHub username is fine). Say once: "This is general information, not legal advice." If money, a company or someone else's code is involved, tell the learner to ask a lawyer. The licence covers only the learner's own code (card `proj-license`).
10. **Tests.** Run the test command the project names (README, `package.json`, test config) and report exactly what it printed. None exist: "There are no tests; I only checked it by <what you really did>."
11. **Go or no-go.** First line: `Go`, `Go after fixes` or `No-go`, with one sentence of reason. Then one plain line each: where it goes, what goes, secrets, size, personal data, README, licence, tests, and a line `Not checked:` with anything you could not check. No-go: a secret, a file over 100 MiB, tracked private notes, or real people's data. Go after fixes: a missing README on a public repository, a file between 50 and 100 MiB, or personal data still to review. Go means "I found nothing", never "it is safe".
12. **Push.** Only after a go and a yes: `git push`, or `git push -u origin <branch>` the first time. Explain once what push does (card `git-push`). The first push may open a browser window to sign in to GitHub. That is normal: the learner signs in there, and you never ask for a password or token in the chat. Then run `git status -sb`; it should show no `ahead`. A rejection or a sign-in error: the `$git-rescue` skill, recipe 8 or 10.

## If you find a secret

Order: revoke first, remove second, rewrite history last, and the learner runs the rewrite. Read `.agents/skills/before-push/references/secret-incident.md` and follow the part that fits.
Name the provider from the key's shape: `sk-` is OpenAI or Anthropic (`sk-ant` is Anthropic), `ghp_` and `github_pat_` are GitHub, `AKIA` is AWS, `AIza` is Google, `xox` is Slack. Tell the learner to revoke the key at that provider, even if they found it on another site. Removing the key from the files does not stop it working: only revoking does.
- Only in a working file, never committed: move the value into `.env` (the learner pastes it), read it from the environment, add `.env.example` with fake values, and prove `git check-ignore -v .env`. Revoke it too if it was ever in the chat.
- In an unpushed commit: the "Not pushed yet" steps.
- Already pushed, private or public: the incident steps. Do not delete the repository, do not force-push, and do not repeat the secret.

## What to record

Follow AGENTS.md, Memory and Teaching moves. Append one journal line per push or visibility change: the repository's visibility and the verdict. Settled events only, paraphrased: no learner quotes. Never write a secret. A line in `.tutor/learner/notes.md` only from the learner's own words: `learned` when they explain in their words why `.env` stays out of Git or what public means; `did` when they ran a check themselves. Commands you ran give no credit. Then say: "Added to your list: <title>."

## Done when

- Every item has a result you ran, or an honest "not checked".
- The learner heard the verdict in plain words and decided.
- A push happened only after a go, and `git status -sb` shows it arrived.
