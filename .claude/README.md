# Developer tutor kit

This folder, `.claude`, is a tutor kit for Claude Code. It turns Claude into a patient teacher who builds your real project with you. It explains each step in plain words and keeps short private notes about what you learned.

Facts about Claude Code and the Desktop app were checked 2026-10-07 against the official docs. The kit was built and checked on Claude Code 2.1.288. Its owner has not yet run it with a real model.

## What you need

- A Claude plan that includes Claude Code: Pro, Max, Team, Enterprise or Console. The free plan does not include Claude Code.
- Claude Code: the Claude Desktop app (Code tab) or the `claude` terminal program. Version 2.1.288 or newer is the version the kit was built on.
- A computer with Windows 10 (version 1809 or newer) or Windows 11, macOS 13 or newer, or a current Linux. The steps below are written for Windows and macOS; on Linux they work the same way with `python3`.
- Optional: Python 3.9 or newer. The helper scripts need it. The tutor works without it.
- Optional: Git. Git for Windows gives Claude the Bash tool. Without it, Claude uses PowerShell. The kit's save points need Git. The Desktop app needs Git only for sessions that use the worktree option.

The install and check commands were run on Windows 11. The Desktop app steps and the macOS steps are not yet checked on a real computer.

## Before you start: install Claude Code

Use the Desktop app, the terminal program, or both.

- **Desktop app (Windows or macOS):** download it at [claude.com/download](https://claude.com/download). Open it and sign in.
- **Terminal program:** follow the official [setup guide](https://code.claude.com/docs/en/setup). On Windows, open PowerShell and run `irm https://claude.ai/install.ps1 | iex`. The [terminal guide](https://code.claude.com/docs/en/terminal-guide) shows how to open a terminal.
- **Check the terminal program:** open a new terminal window and run `claude --version`. It prints a version number.

## Install in three steps

The Desktop app path needs no terminal.

1. **Make a new, empty folder for one project.** Use plain letters, for example `C:\code\my-app` on Windows or `~/code/my-app` on macOS. Do not use your Desktop, Downloads, Documents, OneDrive, iCloud, Dropbox or home folder.
   - Windows: open File Explorer and go to `C:\`. Click **New**, then **Folder**, and name it `code`. Open `code`, then make a folder named `my-app` the same way.
2. **Copy only the `.claude` folder into the new folder.** Unzip the kit download, then copy its `.claude` folder. Copy nothing else. On macOS, press Cmd+Shift+period in Finder to show folders that start with a dot.
3. **Open the new folder in Claude Code.** Answer the trust question, then say hello.
   - Desktop app: open the Code tab, choose the folder in the prompt area, and type `hello`.
   - Terminal: open a terminal in the folder, type `claude`, press Enter, then type `hello`.
   - Say yes to the trust question only for a folder you made or trust.

[docs/getting-started.md](docs/getting-started.md) explains the first steps in detail.

## Using the kit in a project that already has files

- **A new empty folder** installs with no flag.
- **A folder with a project file** installs with no flag. Project files are `.git`, `package.json`, `pyproject.toml`, `requirements.txt`, `Cargo.toml`, `go.mod`, a `.sln` file, `index.html` or a README.
- **Any other folder** needs the flag `--yes-this-is-my-project`. Use it only for a folder you know is your project.
- **A folder with items that can run code** stops the installer. The installer lists them. Read the list. Add `--accept-existing` only if you know those items.
- **Your own `CLAUDE.md`:** Claude Code reads project instructions from `./CLAUDE.md` or from `./.claude/CLAUDE.md`. If your project has both, both may apply. Ask the tutor to check that they do not conflict. The installer never edits your root `CLAUDE.md` or `.gitignore`.
- **An existing `.claude` folder:** the installer adds the kit files it does not have. It never overwrites a file it does not know. It merges the tutor's entries into `settings.json` and keeps the old file as `settings.json.tutor-backup`.
- **A monorepo or a sub-folder:** Claude Code reads the project's `.claude/settings.json` from the folder where you start it. Install the kit in the folder where you start Claude Code. A session started in a parent folder does not use a `.claude` folder in a sub-folder.
- **Your own `.claude/CLAUDE.md`:** the installer keeps yours and prints a warning. The kit's `CLAUDE.md` holds the skill table. Run the install again with `--update` to get the kit's file saved next to yours as `CLAUDE.md.new`, then copy its lines into yours.
- **A folder that is not a Git repository** works. The tutor sets up Git at your first save point, after you say yes.
- **Test first:** run the dry run below. It writes nothing.

## What is in this folder

| Item | What it is |
|---|---|
| `CLAUDE.md` | The short contract that Claude reads at the start of every session. |
| `settings.json` | Project settings: the tutor style, the permission default and the safety rules. Strict JSON, no comments. |
| `settings.json.explained.md` | Plain-words explanation of `settings.json`. Nothing reads this file. |
| `output-styles/` | The tutor's voice: how it explains, checks and offers. |
| `rules/` | Six shared standards: writing, facts, safety, design gate, memory and tidy project. |
| `skills/` | Eleven ready-made tasks, such as `learn`, `fix-it` and `save-point`. See [docs/commands.md](docs/commands.md). |
| `agents/` | Two helpers that review a plan or a change. They only read. |
| `hooks/` | Optional helper scripts. They are off until you turn them on. |
| `knowledge/` | Short lesson cards and a glossary. Claude looks up one line at a time. |
| `templates/` | Empty forms for notes, decisions and your learner profile. |
| `tools/` | Command-line helpers: `doctor.py` (health check) and `install.py` (install, update, remove). The files `validate.py` and `selftest*.py` are checks for the kit's authors. You do not need them. |
| `docs/` | The guides listed at the end of this page. |
| `agent-memory/` | Created later. Your private notes and your list. Git ignores `agent-memory/tutor-data/`. It is not in the download. |
| `.gitignore` | Tells Git which files to leave out, such as your notes and `settings.local.json`. |
| `VERSION` | The kit version number. |
| `MANIFEST.txt` | A list of the kit files with checksums. `doctor.py verify` uses it to spot changed files. |
| `CHANGELOG.md` | What changed in each kit version. |

## What runs on your computer

Nothing runs until you use Claude Code. The kit is text files. The helper scripts are off at first. When they are on, they run small Python programs on each message. The helper scripts make no network calls. One command, `share-notes`, asks GitHub through the `gh` tool. It runs only when you type it.

## The helper scripts

The helper scripts add three things:

- Facts for each message, such as the date, the folder check and your progress.
- A safety guard that stops risky commands before they run.
- A record of what you understood or did.

Without them, the tutor works from text only. [What you lose without Python](docs/how-it-works.md#what-you-lose-without-python) lists the differences.

Turn them on by saying "turn on helper scripts" to the tutor. Or run the command below from your project folder. On Windows, use `py -3`. On macOS and Linux, use `python3`.

```
py -3 .claude/tools/doctor.py enable-hooks
```

```
python3 .claude/tools/doctor.py enable-hooks
```

The command changes these things:

- It adds a `hooks` block to `.claude/settings.json`.
- It keeps a copy of the old file as `.claude/settings.json.tutor-backup`.
- If you had notes from before, it moves them into your list and renames `notes.md`.

Claude asks you before it runs this command. Approve it only if you asked for the helper scripts.

To turn them off, run `disable-hooks` in the same way. It removes the tutor's hook entries from `settings.json` and keeps your own entries. The emergency switch in [docs/customize.md](docs/customize.md#turn-the-helper-scripts-on-or-off) works without Python.

## Install, update and remove (terminal)

Run these commands from the folder that holds the new kit `.claude`, which is the kit download. Do not run them from inside your project. Replace `<project-folder>` with the path of your project folder, for example `C:\code\my-app`. On Windows, use `py -3`. On macOS and Linux, use `python3`. If that does not work, try `python`. See [Which Python command to use](docs/troubleshooting.md#which-python-command-to-use).

The folder must already exist. If it does not, the installer says so. Create it first, then run the command again.

Dry run first. It writes nothing and prints what it would do:

```
py -3 .claude/tools/install.py <project-folder> --dry-run
```

Install:

```
py -3 .claude/tools/install.py <project-folder>
```

Update later. Your edited files stay. New versions are saved as `<file>.new`:

```
py -3 .claude/tools/install.py <project-folder> --update
```

Remove the kit files that you did not change. Your notes stay:

```
py -3 .claude/tools/install.py <project-folder> --uninstall
```

The install command ends with an exit code. 0 means done. 1 means done with warnings. 2 means refused. When it refuses, it writes nothing. [Install script refusals](docs/troubleshooting.md#installpy-refuses-the-folder) explains each refusal.

## Is it working?

Ask the tutor "is it working". Or run this command from your project folder:

```
py -3 .claude/tools/doctor.py check
```

On macOS and Linux, use `python3` instead of `py -3`.

The Verdict line is near the top, under the project folder path. The lines after it give each check. `--strict` exits with code 1 when something needs attention.

In the Desktop app, open the terminal with the **Terminal** button in the session title bar, or press Ctrl+backtick. The terminal works only in local sessions.

## Your notes

Your notes and your list are in `.claude/agent-memory/tutor-data/` on your computer. Git ignores that folder. The list stays private on this computer.

To delete the chat copies, run this command. Use `py -3` on Windows, or `python3` on macOS and Linux:

```
py -3 .claude/tools/doctor.py wipe chat
```

The command asks you to type `DELETE` and press Enter. Any other answer cancels it. Use `state` or `all` instead of `chat` to delete other notes. `all` also deletes your list and your journal. Claude asks you before it runs `wipe`. [docs/customize.md](docs/customize.md) explains the chat copy setting.

## Docs

- [docs/getting-started.md](docs/getting-started.md): the first steps.
- [docs/commands.md](docs/commands.md): what to say, and the commands that exist.
- [docs/customize.md](docs/customize.md): settings, language, permission modes and your own rules.
- [docs/troubleshooting.md](docs/troubleshooting.md): problems and exact fixes.
- [docs/how-it-works.md](docs/how-it-works.md): how the parts work together, and the honest limits.
- [docs/faq.md](docs/faq.md): common questions in plain words.
- [settings.json.explained.md](settings.json.explained.md): what each part of `settings.json` does.
- [CHANGELOG.md](CHANGELOG.md): what changed in each version.

## Honest limit

The safety rules stop accidents and obvious mistakes. They do not stop a determined person or a hostile text that fools Claude. Read [docs/how-it-works.md](docs/how-it-works.md) before you trust the guard with important work.
