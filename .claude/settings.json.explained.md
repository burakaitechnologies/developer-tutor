# What is in settings.json, in plain words

`settings.json` is strict JSON, and JSON cannot hold comments. So this file explains it. Nothing here is read by Claude Code. You can delete this file; the kit still works.

If `settings.json` is broken (a missing comma, for example), Claude Code ignores the WHOLE file. The safety rules below then stop working. Run `py -3 .claude/tools/doctor.py check` on Windows, or `python3 .claude/tools/doctor.py check` on macOS and Linux, to find out. The tutor can run it for you: say "is it working".

## The five parts

| Part | What it does |
|---|---|
| `$schema` | Helps editors check the file. It changes nothing in Claude Code. |
| `outputStyle` | `tutor` is the way Claude talks and teaches in this project. Change it to `default` to get the normal Claude voice. |
| `permissions.defaultMode` | `acceptEdits`: Claude may change files in this project without asking each time. Commands that run programs still ask. |
| `permissions.allow` | The 11 skills of this kit start without a question. Nothing else is pre-approved. These rules apply only after you say yes to the trust question for the folder. |
| `permissions.deny` and `permissions.ask` | The safety floor. Explained below. |

About `defaultMode`: it sets the mode when a new local session starts. The Desktop app reads the same file. A mode you pick in its selector is remembered for that folder and wins over this line. The one exception is Plan, which lasts only for the current session. If you prefer to approve every change, choose Manual in that selector, or change this line to `"default"`.

## Deny: Claude Code refuses, and no one can click "yes"

1. **Reading secret files:** `.env` and `.env.*` (but not the example files `.env.example`, `.env.sample`, `.env.template`, `.env.dist`, `.env.defaults`), key and certificate files (`*.pem`, `*.key`, `id_rsa`, `id_ed25519`, and similar), password files for npm, pip, Git and databases, and the folders `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.kube`, `~/.config/gh`. Why: whatever Claude reads goes to Anthropic and into the chat. A secret should never get there.
2. **Force pushes:** eight rules that match the shapes `git push --force`, `-f` and `+branch`. A force push can erase other people's work online. `--force-with-lease` and a plain `git push` are not denied here (a plain push asks, see below).
3. **A few commands that destroy things:** `git clean -fdx`, `git filter-branch`, `git filter-repo`, `git reflog expire`, `git gc --prune=now`, `rm -rf` of the Git folder, your home folder or `/`, `chmod -R 777`, `gh repo delete`, `gh auth token`, and disk tools (`mkfs`, `fdisk`, `parted`, `diskpart`, `Format-Volume`, `Clear-Disk`).

## Ask: Claude Code stops and asks you first

These commands stop and ask you first:

- `git push` in any form, and `git remote add` or `set-url`.
- `git reset --hard`, `git clean -f`, `git branch -D`, `git checkout -- <file>`, `git stash drop` and `clear`.
- `sudo`, `chmod 777`, `npm install -g`, `docker compose down -v`, `docker volume rm`, `terraform destroy`, `kubectl delete`, a bare `bash` or `sh`, `Set-ExecutionPolicy` and `iex`.

Each of these can lose work, publish work or change your computer outside the project.

## Why every rule appears twice

On Windows, Claude can run commands through two tools: Bash (Git Bash) and PowerShell. A rule for one tool does not cover the other. So each rule exists as `Bash(...)` and as `PowerShell(...)`.

## What is NOT in this file, on purpose

- **No `hooks`.** The kit's helper scripts are off until you turn them on. That keeps the first hour free of error messages on a computer without Python. Turn them on by saying "turn on helper scripts". You can also run `enable-hooks`: `py -3 .claude/tools/doctor.py enable-hooks` on Windows, or `python3` on macOS and Linux. That command adds a `hooks` block to this file. It keeps the old file as `settings.json.tutor-backup`. Turn them off with `disable-hooks`, which removes the tutor's hook entries again. If something goes wrong and you cannot start a session, create the file `.claude/settings.local.json` with the single line `{"disableAllHooks": true}`.
- **No `env`, `statusLine` or `apiKeyHelper`.** A project file that can run programs or change where your key goes would be a risk for everyone who copies it. The tool `doctor.py audit` lists such things in any folder.
- **No "bypass" or "auto" modes.** They remove the questions above.

## Your own changes

Put personal settings in `.claude/settings.local.json`. Git ignores it (see `.claude/.gitignore`), and it wins over this file. The settings that apply right now are the merge of your user settings, this file and the local file.

## How far this protects you

The rules look at the text of a command. They stop accidents and obvious mistakes. They are not a sandbox. A determined person, or a hostile text that fools Claude, can find a way around them. With the helper scripts on, a second check (the guard) reads commands more carefully. The honest list of gaps is in `.claude/docs/how-it-works.md`.
