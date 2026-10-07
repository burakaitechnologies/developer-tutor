# Questions beginners ask

These are the questions that new learners ask most often.
Each answer gives the Desktop app first, then the terminal, where they differ.

**Getting started**

## Q: What is this kit, and what does it do for me?

This kit is a folder called `.claude`. You add it to a project folder.
Claude Code is the program that lets Claude read and change the files in that folder.
With this kit, Claude works as a patient teacher and developer for that project.
It builds the project with you, explains each step, and keeps notes for the next session.

Read more: [Getting started](getting-started.md).

## Q: Do I need to know programming before I start?

No. The tutor explains each new word and each command when it first appears.
You need patience, and a wish to read the results.
Say "simpler" at any time. The tutor then uses shorter sentences, one level lower for the session.

Read more: [How the tutor teaches](how-it-works.md#how-the-tutor-teaches).

## Q: Do I need to use a terminal?

For the main path, no. You talk to Claude in the Desktop app, on the Code tab.
Some optional helper scripts need a terminal. In the Desktop app, use the Terminal button in the session title bar, or Ctrl+backtick. This works in local sessions only.
In a terminal, the scripts need Python 3.9 or newer. On Windows, type `py -3` first, then `python`. On macOS and Linux, type `python3` first, then `python`.

Read more: [Getting started](getting-started.md).

## Q: Which app should I use: the Desktop app or the terminal?

Beginners should start with the Desktop app. Open the Code tab and choose your project folder.
Use the terminal only if you already type commands. Both use the same kit and the same rules.

Read more: [Commands](commands.md).

## Q: What does it cost?

Claude Code needs a Pro, Max, Team, Enterprise or Console account.
The free claude.ai plan does not include Claude Code.
Prices and limits change, so read the plan page (checked 2026-10-07).

Read more: [Claude Code setup](https://code.claude.com/docs/en/setup) (checked 2026-10-07).

## Q: Is it safe to let Claude work on my computer?

It is safer with three habits. Keep each project in its own folder. Save points with Git before big changes. Read each question before you answer yes.
The kit stops many risky commands. It cannot stop every mistake, and it does not stop a determined attacker.

Read more: [The safety guard and its known gaps](how-it-works.md#the-safety-guard-and-its-known-gaps).

**First build**

## Q: Where is the file that Claude made?

The tutor names the folder and the file after each build. Its Change card lists the files created and changed, with their full folder path.
Desktop: the file path shows in the chat. Click it to open the file in the file pane.
Terminal: the tutor names the path. Look in that folder with File Explorer on Windows or Finder on macOS.

Read more: [Getting started](getting-started.md).

## Q: How do I open the file in a program that can show it?

Desktop: click the file path in the chat. Most files open in the file pane. HTML, PDF, image and video files open in the Browser pane.
Windows: right-click the file, then choose the program to open it.
macOS: double-click the file, or right-click it and choose Open With.

Read more: [Getting started](getting-started.md).

## Q: What is a folder, and why does it matter?

A folder holds files and other folders. Your project is one folder.
Claude works inside that folder. Keep each project in its own folder.
Do not use your Desktop, Downloads or home folder for a project. Those folders hold many unrelated files.

Read more: [Getting started](getting-started.md).

## Q: Why does Claude ask me questions before it builds?

A few questions save time and keep the choices yours. The tutor asks what you want to make.
It asks at most three questions before the first build, one at a time. "Not sure" is a good answer.
For bigger choices, it shows options and a recommendation. You decide.

Read more: [How the tutor teaches](how-it-works.md#how-the-tutor-teaches).

## Q: What is "Check:" and do I have to answer it?

A line that starts with `Check:`, `Predict:` or `Your move:` asks you to do something.
You answer in your own words, or you try the step in your project.
Answering helps you learn. "Not sure" is allowed. You can also skip a check. The tutor then records nothing.

Read more: [How the tutor teaches](how-it-works.md#how-the-tutor-teaches).

**Working**

## Q: How do I undo a change?

- Desktop: ask the tutor to undo it. Say what you want back.
- Git is the reliable undo. Go back to the last save point. Ask the tutor to show the save points.
- Terminal: `/rewind` undoes Claude's file edits. Pressing Esc twice on an empty prompt also opens it.
- `/rewind` does not undo changes made by shell commands, such as a delete or a move.

Read more: [Commands](commands.md).

## Q: What is a save point, or commit?

A save point is a saved copy of your project at one moment. Git calls it a commit.
Desktop: ask the tutor to list them. Terminal: this command lists them.

```
git log --oneline
```

Read more: [Commands](commands.md).

## Q: What is Git?

Git is a program that keeps the history of your project on your computer. It needs no internet.
It stores each save point, so you can compare changes and go back.
On Windows, Git for Windows is optional for the terminal. Desktop features that make a second copy of a project (worktree sessions) need Git (checked 2026-10-07).

Read more: [Getting started](getting-started.md).

## Q: What is GitHub, and how is it different from Git?

Git runs on your computer and keeps the history. GitHub is a website that keeps an online copy.
A repository is a project that Git tracks. A private repository is one that only you can see.
`git push` sends your save points to GitHub. The kit asks you before any push.

Read more: [Commands](commands.md).

## Q: Do I need a GitHub account?

No. The kit works without GitHub.
You need GitHub only to back up or share your project online. Start with a private repository.
Use the `before-push` checklist before you send anything.

Read more: [Commands](commands.md).

## Q: What is a .env file?

A `.env` file holds secrets for your project, such as a key or a password.
Each line holds a name, an equals sign and a value. Keep the file on your computer only.
The kit denies Claude reading `.env` files. The tutor adds `.env` to your project's Git ignore list, so Git does not send it online.

Read more: [Troubleshooting](troubleshooting.md).

## Q: What is an API key, and what do I do if I pasted one in the chat?

An API key is a secret password for a service. Anyone with it can use your account.
If you pasted one, do not repeat it. Revoke it now at the service that issued it. The start of the key often shows which service that is.
Then make a new key and put it in a `.env` file. A deleted chat copy does not make the old key safe.

Read more: [What is stored, and how to wipe it](how-it-works.md#what-is-stored-and-how-to-wipe-it).

## Q: What is localhost?

`localhost` is the name for your own computer. A web address such as `http://localhost:3000` opens a page on your computer.
Only your computer can see that page. The number after the colon is the port, a channel for one program.

Read more: [Troubleshooting](troubleshooting.md).

**Control**

## Q: How do I stop Claude when it is doing something wrong?

Desktop: click the stop button. Terminal: press Esc.
Stopping does not undo changes that are already made. Ask the tutor to put them back, or use Git.

Read more: [Commands](commands.md).

## Q: How do I make the tutor quieter, simpler, or teach in my language?

Say it in plain words in the chat. The tutor applies it at once.

- "quiet mode" keeps the result, the safety lines and the save-point question. It drops glosses, checks, offers and reviews.
- "teach me again" turns lessons back on. "simpler" gives shorter sentences and one level lower for the session.
- Name your language, for example "explain in Turkish". Commands stay in English.

Read more: [Customize](customize.md).

## Q: What do the permission questions mean?

Claude asks before some steps. Each question names the step.
Answer yes only when you know what the step does. Answer no to stop it.
Desktop: in Manual mode, each edit shows as a diff you can accept or reject. Terminal: the question waits for your answer in the terminal.

Read more: [What happens in each permission mode](how-it-works.md#what-happens-in-each-permission-mode).

## Q: Why was my command stopped on purpose?

The safety guard stopped it. The message starts with "Stopped on purpose by the tutor safety guard".
This is a safety step, not a setup error. The step is risky, for example a force push, or a delete of the whole project.
Read the two sentences. Ask Claude for the safe way the message names. Do not approve a step you do not understand.

Read more: [The safety guard and its known gaps](how-it-works.md#what-the-stop-message-means).

**Trust**

## Q: What does "trust this folder" mean?

When you open a folder, Claude Code asks whether you trust it.
Until you say yes, Claude Code holds back some of the folder's settings, such as its allow rules. The deny and ask rules still apply.
Say yes only to folders you made or know. Start Claude in the project folder, not in your home folder.

Read more: [What runs before you trust a folder](https://code.claude.com/docs/en/permissions#what-runs-before-you-trust-a-folder) (checked 2026-10-07).

## Q: What can Claude read on my computer?

Claude reads the files in your project folder when it needs them. It also reads what you paste.
The kit's settings deny reading `.env` files, key files and your `.ssh` folder.
A command that Claude runs can reach more than the project. The guard checks commands, but it has limits.

Read more: [What the guard cannot see](how-it-works.md#what-the-guard-cannot-see).

## Q: Is my data private?

Claude sends what it reads, and what you type, to Anthropic to get answers.
Claude Code keeps a transcript (a saved record) of each chat in your home folder. Terminal chats are deleted after 30 days by default. Desktop chats are kept at any age, unless `desktopSessionCleanupPeriodDays` sets a limit.
The kit's notes stay on your computer, and Git ignores them, so they do not go online. A folder that syncs to the cloud, such as OneDrive, can upload them anyway.

Read more: [What is stored, and how to wipe it](how-it-works.md#what-is-stored-and-how-to-wipe-it) and [Claude Code data retention](https://code.claude.com/docs/en/claude-directory#cleaned-up-automatically) (checked 2026-10-07).

## Q: Can Claude delete my files?

Yes. Claude can delete files in your project when a step needs it.
The kit asks before it deletes a folder with everything inside, or a file outside the project. It stops deleting your whole project or home folder.
A checkpoint (Claude Code's own undo for its file edits) does not undo a delete made by a command. A Git save point does. Save a point before big changes.

Read more: [Commands](commands.md).

## Q: Can I share my project with someone?

Yes. Ask the tutor to run the `before-push` checklist first.
The checklist checks visibility, secrets, personal data and the files that would be sent.
Share a private repository first. Make it public only when the checklist says it is safe.

Read more: [Commands](commands.md).

**Upkeep**

## Q: How do I update Claude Code and this kit?

The native installer updates itself in the background. WinGet and Homebrew installs do not. On Windows, run `winget upgrade Anthropic.ClaudeCode`. On macOS, run `brew upgrade claude-code` (checked 2026-10-07).
For the kit, run `install.py --update` in a terminal. It keeps your edits and notes.

Read more: [Customize](customize.md).

## Q: How do I remove the kit from my project?

Desktop: close the project. Delete the `.claude` folder inside the project folder. This also deletes your notes.
Terminal: `install.py --uninstall` removes the kit files that are unchanged, and keeps your notes.
To remove Claude Code itself, read the uninstall section of the setup page (checked 2026-10-07).

Read more: [The scripts and what each one is for](how-it-works.md#the-scripts-and-what-each-one-is-for).
