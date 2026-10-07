# developer-tutor

developer-tutor is a folder named `.claude`. You copy it into your own project folder. Claude Code then acts as a patient tutor. It builds your real project with you, one small step at a time. It explains each choice in plain words. It asks you to do small steps yourself. It keeps a list of what you have done.

## Who it is for

- People with little or no programming, Git, GitHub or Claude Code experience.
- People who may never have opened a terminal.
- People who want to build something real and learn while they build it.

## Who it is not for

- Experienced developers who want a code generator.
- People who want Claude to do all the work, with no learning.
- People who skip the safety notes and expect a finished product.

## Start here

Steps 1 to 5 need no terminal and no Git. Step 0 needs a paid Claude plan and an account.

0. **Install Claude.** You need a paid plan that includes Claude Code: Pro, Max, Team, Enterprise or Console. The free plan does not include Claude Code. Then choose one way to install:
   - **Desktop app (the easier way).** Download it from the official page, [claude.com/download](https://claude.com/download). Install it, open it and sign in. Use its **Code** tab in step 4.
   - **Terminal program `claude`.** Use the official install command:
     - Windows: open **PowerShell**, not Command Prompt, and run `irm https://claude.ai/install.ps1 | iex`. You can also run `winget install Anthropic.ClaudeCode`.
     - macOS or Linux: run `curl -fsSL https://claude.ai/install.sh | bash`.
   - Check the install: open a new terminal window and run `claude --version`. It prints a version number. If it says the command is not found, open a new terminal window and try again. The official setup guide is [Set up Claude Code](https://code.claude.com/docs/en/setup).

1. **Download the ZIP.** On this repository's page, click the green **Code** button, then **Download ZIP**. Unzip the file:
   - Windows: right-click the ZIP file and choose **Extract All**.
   - macOS: double-click the ZIP file in Finder.

2. **Make a new empty folder for your project.** Use letters, digits and dashes only, with no spaces (`my-app`, not `my app`), in a place such as `C:/code/my-app` on Windows or `~/code/my-app` on macOS and Linux. Do not use Desktop, Downloads, your Documents folder itself, your home folder itself, or a OneDrive, iCloud or Dropbox folder.
   - Windows: in File Explorer, open `C:\`. Make a folder named `code`, open it, right-click an empty space, choose **New**, then **Folder**, and name it `my-app`.
   - macOS: in Finder, open your home folder and make a folder named `code`. Open it and make `my-app` the same way (**File**, then **New Folder**).

3. **Copy only the `.claude` folder into it.** Copy the `.claude` folder from the unzipped folder into `my-app`. Copy nothing else.
   - Windows: the folder shows normally in File Explorer.
   - macOS: in Finder, press Command, Shift and period together. This shows hidden folders.
   - Do not use the unzipped folder as your project. Work in your own new folder.

4. **Open your new folder in Claude Code.**
   - Desktop app: open the **Code** tab. Choose `my-app` as the project folder.
   - Terminal: open a terminal in `my-app`. In PowerShell on Windows, type `cd C:\code\my-app` first. Then run `claude`.

5. **Trust the folder and say hello.** If Claude Code asks whether you trust the folder, read the question. Choose yes only for your own project folder. Then type `hello`. The tutor answers with a greeting and one question.

## Requirements

- A paid Claude plan that includes Claude Code: Pro, Max, Team, Enterprise or Console. The free plan does not include Claude Code.
- Adults only. Anthropic's terms require users to be adults.
- The Claude desktop app (Code tab), or the terminal program `claude`.
- Claude Code 2.1.288. The kit was built and checked with this version. No run with a real model exists yet, and newer versions are untested.
- An operating system from the official list: macOS 13.0 or newer; Windows 10 version 1809 or newer, or Windows 11; Ubuntu 20.04 or newer, Debian 10 or newer, or Alpine Linux 3.19 or newer. At least 4 GB of memory. The builders checked the kit on Windows 11. The self-tests also run in CI on Ubuntu, Windows and macOS.
- Python 3.9 or newer. You need Python only for the optional helper scripts. The kit works without it. To get it, use [python.org/downloads](https://www.python.org/downloads/). On Windows, tick **Add python.exe to PATH** in the installer, then open a new terminal and run `py -3 --version` to check.
- Git, for save points. Git for Windows is optional now.

## What you get

- A tutor voice: short answers, plain words, and one check question at a time.
- Eleven skills. You start each one by saying a phrase, as in the table below.
- Two read-only helpers: an architecture reviewer and a code reviewer. They read files. They never change them.
- A safety floor in `.claude/settings.json`. It denies or asks before risky commands, such as a force push. This works without Python.
- Memory across sessions. This needs the helper scripts. With them on, your notes and progress stay in `.claude/agent-memory/tutor-data/`. Without them, the tutor keeps notes by hand and cannot check quotes. The kit's `.gitignore` lists only `agent-memory/tutor-data/` and `settings.local.json` (and two more local-only patterns, `*.tutor-backup` and Python caches), so Git ignores those and nothing else under `agent-memory`.
- Helper scripts. They need Python 3.9 or newer, and they stay off until you turn them on. They add a session-state header, save records with checked quotes, and run a safety guard that checks each command before it runs.

| Skill | Say something like | What it does |
|---|---|---|
| tutor | "what can you do", "quiet mode" | Shows the menu, settings and a health check |
| tutor-setup | "hello" in a new folder | Welcomes you, asks a few questions, builds a first small version |
| learn | "teach me Git" | Gives one short lesson with one check |
| progress | "what have I learned" | Gives an honest picture of what you know |
| explain | "what does this file do" | Reads the real file and explains it |
| think-first | "should I use a database" | Decides how much planning a choice needs |
| new-project | "I want to start a project" | Sets a goal, simple tools, a README and Git |
| fix-it | "I got this error" | Reads the error with you, then fixes it |
| save-point | "save my work" | Makes a Git save point, which is a commit, with a short note |
| before-push | "put it on GitHub" | Checks secrets and visibility before you push |
| git-rescue | "I broke Git" | Looks first, saves a copy, then makes one safe fix |

## What runs on your computer

- Until you turn on the helper scripts, the kit is only text files. No program of the kit runs.
- The helper scripts are Python files. They run when Claude Code starts a session, sends a message or uses a tool.
- The helper scripts make no network calls. One command, `share-notes on`, asks GitHub through your own `gh` program. See [SECURITY.md](SECURITY.md).

## How it teaches

- You do the small steps yourself. Each step changes one line, one file or one command.
- The tutor asks you to predict, explain or change something. You answer in your own words.
- Your list shows what you understand, what you have done and what you did alone.
- You can turn the teaching down. Say `quiet mode` to stop the explanations for this session. Say `stop teaching me, for good` to set teaching to off in your profile, and say `teach me again` to bring the lessons back. Either way the safety rules stay in force. The change summary, the safety stops and the design check before a big change stay too.

## For people who use a terminal

Use this section if you want a repeatable install from the terminal. Otherwise steps 0 to 5 above are enough.

### Which Python command to type

Use one order on every page. On Windows, type `py -3`. If that does not work, type `python`. On macOS and Linux, type `python3`. If that does not work, type `python`. The examples below use `py -3` on Windows and `python3` on macOS and Linux.

### Install with the installer

Run these from the folder that holds this repository, the unzipped folder. The first command only shows what would happen. It writes nothing.

Windows:

```
py -3 .claude/tools/install.py C:/code/my-app --dry-run
```

macOS and Linux:

```
python3 .claude/tools/install.py ~/code/my-app --dry-run
```

When the dry run looks right, run the same command without `--dry-run`.

The installer does these things, in this order:

1. It checks the folder. The folder must already exist, because the installer never creates one. It refuses your home folder, the top of a drive, system folders, `~/.claude` and the kit's own folder. A folder with files but no project file, such as `.git`, `package.json`, `README` or `index.html`, needs the extra flag `--yes-this-is-my-project`. An empty folder needs no flag. A folder that holds only `.git`, `README`, `LICENSE`, `.gitignore` or `.claude` counts as a new project.
2. It lists anything already in the project that can run code or change safety rules, such as allow rules or hooks. If it finds any, it stops. Read the list, then run again with `--accept-existing`.
3. It copies the kit into `.claude` and checks every copied file byte for byte. A first install never overwrites a file that already exists. It merges `.claude/settings.json`, keeps the old file as `settings.json.tutor-backup`, and creates `.claude/.gitignore`.
4. It runs the quick self-test on a temporary copy. This takes about half a minute.
5. It prints `Finished.`, or `Finished with N warning(s).` Read the lines above that line. Exit code 0 means done. Exit code 1 means done with warnings. Exit code 2 means refused, and nothing was copied.

The installer writes only inside `.claude`. It does not edit your project's root `.gitignore` or `CLAUDE.md`. Your notes in `.claude/agent-memory` are never touched.

- `--update` brings a newer kit into a project. A file you edited stays, and the new version is saved next to it as `<file>.new`.
- `--uninstall` removes the kit files you have not changed. Your notes stay.
- `--enable-hooks` turns the helper scripts on during the install. The installer needs a working Python for this.

### Turn the helper scripts on or off

Windows: `py -3 .claude/tools/doctor.py enable-hooks`

macOS and Linux: `python3 .claude/tools/doctor.py enable-hooks`

The command edits `.claude/settings.json` and keeps a backup copy whose name ends in `.tutor-backup`. To turn the scripts off again, run `disable-hooks` the same way.

### Using the kit in a project that already has files

- Open Claude Code in the folder that holds `.claude`. The helper scripts run only when the session starts in that folder. If you start Claude Code in a subfolder, the hooks and the tutor voice do not run there. The kit's mock test M-21 checks this. No run with a real model has been done.
- In a monorepo, install the kit in the folder you open in Claude Code, and open Claude Code in that folder.
- If your `.claude/settings.json` already sets `outputStyle` to another style, the installer keeps your value and shows a warning. To use the tutor voice, set `"outputStyle": "tutor"` yourself.
- The installer never edits your root `CLAUDE.md`. Claude Code reads a project memory file from `./CLAUDE.md` or from `./.claude/CLAUDE.md`. Run `/context` to see which files loaded. Keep the two files consistent with each other.
- If your project already has its own `.claude/CLAUDE.md`, the installer keeps yours and prints a warning. The kit's own `CLAUDE.md` holds the skill table, so run the install again with `--update` to get the kit's file saved next to yours as `CLAUDE.md.new`, then copy its lines into yours.
- A folder without Git works. Save points need Git, and the tutor offers to set it up when you ask to save your work.
- A folder inside OneDrive, iCloud, Dropbox or Google Drive gets a warning. A sync service can damage the `.git` folder.
- The full guide for each file is in `.claude/README.md`. Contributors who change the kit itself read `.claude/docs/extending.md`.

## Honest limits

- A language model can be wrong. Check what it says. Run the checks it suggests.
- The safety guard stops accidents and obvious mistakes. It does not stop a determined or tricked agent. Windows has no sandbox for Claude Code commands.
- The helper scripts do nothing until you turn them on. Without Python they stay off.
- Real model behaviour is checked only by the owner's live checklist, with a real login. No live check with a real model has been recorded yet. The checklist and the results to date are in [docs/test-report.md](docs/test-report.md).

## Licence

There is no licence file yet. The owner has not chosen a licence. Until one is added, all rights stay with the owner: you may read the kit and try it on your own computer, but ask the owner before you share or sell a copy or build on it.

## Links

- [Kit guide: .claude/README.md](.claude/README.md)
- [Getting started: .claude/docs/getting-started.md](.claude/docs/getting-started.md)
- [Questions and answers: .claude/docs/faq.md](.claude/docs/faq.md)
- [Extending the kit: .claude/docs/extending.md](.claude/docs/extending.md)
- [Security: SECURITY.md](SECURITY.md)
- [Contributing: CONTRIBUTING.md](CONTRIBUTING.md)
- [Test report: docs/test-report.md](docs/test-report.md)
