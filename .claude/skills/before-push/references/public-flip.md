# Before a private repository becomes public

Use this with the main checklist when a private repository should become public, and before a first push to a new public one. Public means everyone on the internet can read the code, fork it and keep a copy. Making it private again does not take those copies back. Treat the change as one-way.
Kit note: from the kit notes dated 2026-10-07 (docs.github.com, "Setting repository visibility"); not checked today. Re-read it on the day; names in the settings pages change.

## What the change does (GitHub's list)
- The code is visible to everyone who can visit github.com, and anyone can fork it.
- The changes are published as activity, and Actions history and logs become visible.
- Stars and watchers are erased, push rulesets are disabled, and the repository gains GitHub Advanced Security features.
- Back to private later: public forks are not made private, they are detached. A Pages site on a free account is unpublished.

## The whole history becomes public, not only today's files
A. **Secrets in history.** Names only, so no value enters the chat: `git log --all --oneline --name-only -i -G'api[_-]?key|secret|token|password|BEGIN [A-Z ]*PRIVATE KEY'` and `git grep -I -l -E 'sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_|AKIA[0-9A-Z]{16}'`. Open each hit. A real value, even if deleted in a later commit: revoke it first (`.claude/skills/before-push/references/secret-incident.md`), and choose part H.
B. **People.** `git shortlog -sne --all` lists the names and e-mail addresses on commits. They become public. New commits can use the GitHub no-reply address (card `git-identity`). Old commits keep their address unless history is rewritten.
C. **Files.** `git ls-files` for data files (`*.csv`, `*.xlsx`, `*.sqlite`, `*.db`, `*.sql`), photos of people, exported chats. Real people's data: no-go (rule G3). Pictures and sounds: licence or permission.
D. **Tutor notes.** `git ls-files .claude/agent-memory` must print nothing. If the learner shared notes earlier (step 13 of SKILL.md), turn sharing off first: the learner approves `<interpreter> .claude/tools/doctor.py share-notes off`, then `git rm --cached -r .claude/agent-memory` and commit. Old commits still hold the notes. They show the learner's goal and progress, so use part H for that repository.
E. **README and licence.** SKILL.md steps 8 and 9. A stranger must understand what it is and how to run it. No licence means all rights stay with the author.
F. **Automation.** Open `.github/workflows` if it exists: no tokens written in the files; know what runs when strangers open pull requests. Check Settings, Actions for secrets stored there.
G. **Web pages.** A Pages site or a deploy that reads this repository: the learner knows what becomes visible, and the site shows no private data.
H. **Or publish a clean copy.** When history holds a secret, personal data, private notes or messy commits, do not flip this repository. Create a new empty repository and copy the current files into a new folder without `.git` (File Explorer or Finder). Run `git init -b main`, write `.gitignore` first, prove `git check-ignore -v .env`, commit, and push with the new-project skill. Keep the old repository private as the archive. A key that was ever in the old history must still be revoked.

## Do the change (the learner, not you)
In the browser: the repository, Settings, General, Danger Zone, Change repository visibility, Make public. GitHub asks to type the repository name. Say that you never click this for the learner.

## After the change
- Open the repository in a private browser window, as a stranger: README, files, licence.
- Settings, Code security: read which of secret scanning and push protection are on, and turn on what is offered (card `gh-security-alerts`; the names change).
- Expect copies. A key that leaked in the first minutes needs the incident steps even if nothing looks wrong.
- Journal line: the date, the checks done, any part H decision.
- Verdict in plain words: Go, Go after fixes or No-go.
