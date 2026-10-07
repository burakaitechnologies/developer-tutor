# Questions beginners ask

These are the questions that new learners ask most often.
Facts about Codex in these answers were checked on 2026-10-08 against the official Codex docs.

**Getting started**

## Q: What is this kit, and what does it do for me?

The kit is a set of files: `AGENTS.md`, a `.codex` folder and a `.agents` folder. You copy them into a project folder.
Codex reads the files and acts as a patient developer and tutor for that project.
It builds the project with you, explains each step and keeps short notes for the next session.
Read more: [Getting started](getting-started.md).

## Q: Do I need to know programming before I start?

No. The tutor explains each new word once, when it first appears.
You need patience and a wish to read the results.
Say "simpler" at any time. The tutor then uses shorter sentences for the session.

## Q: Do I need to use a terminal?

No, not for the main path. The ChatGPT desktop app has a chat window and a way to open a folder.
The terminal is optional. It runs the Codex CLI. Both use the same kit files.
In the app, each chat has a terminal for its project. Use New tab, then Terminal, or Ctrl+backtick (checked 2026-10-08).

## Q: Which Codex surface should I use: the app, the IDE or the terminal?

Beginners should start with the ChatGPT desktop app. Choose Codex in the dropdown, then open your project folder.
Use the IDE extension if you already write code in an editor, such as VS Code.
Use the terminal (the Codex CLI) if you already type commands.

## Q: What does it cost, and which plan do I need?

The pricing page lists Codex on the Free, Go, Plus, Pro, Business, Edu and Enterprise plans. The limits differ (checked 2026-10-08).
Read the pricing page before you choose a plan. Prices and limits change.
In the CLI, `/status` shows the token use of the current chat (checked 2026-10-08).

**First build**

## Q: What do I say first to start a project?

Open a new, empty project folder. Then say `hello`.
The tutor asks what you want to make. It asks at most three questions, one at a time.
"Not sure" is a good answer.

## Q: Why does Codex ask me questions before it builds?

A few questions keep the choices yours. The tutor asks one question at a time.
For bigger choices, it shows options and a recommendation. You decide.
Read more: [How the tutor teaches](how-it-works.md#how-the-tutor-teaches).

## Q: Where is the file that Codex made?

The tutor names the folder and the file after each build. Its change card lists the files created and changed, with the full folder path.
In the app, the review pane shows the changed files (checked 2026-10-08).
In the terminal, type `/diff` to see the changes (checked 2026-10-08).

## Q: How do I open the file so that I can see it?

Windows: open File Explorer, go to the folder the tutor names, then right-click the file and choose a program.
macOS: open Finder, go to the folder, then double-click the file or choose Open With.
An HTML file opens in a web browser.

## Q: What is a folder, and why does it matter?

A folder holds files and other folders. Your project is one folder. Codex works inside it.
Keep each project in its own folder.
Do not use your Desktop, Downloads or home folder for a project. Those folders hold many unrelated files.

**Working**

## Q: What is "Check:" and do I have to answer it?

A line that starts with `Check:`, `Predict:` or `Your move:` asks you to do something.
Answer in your own words, or try the step in your project. "Not sure" is allowed.
You can skip a check. The tutor then records nothing.

## Q: What is a save point, or commit?

A save point is a saved copy of your project at one moment. Git calls it a commit.
Ask the tutor to make one, or to list them. In the terminal, `git log --oneline` lists them.
The sandbox keeps `.git` read-only, so a Git command that writes needs your approval (checked 2026-10-08).

## Q: What is Git, and do I need it?

Git is a program that keeps the history of your project on your computer. It needs no internet.
The save points need Git. The app also says that some features need Git on Windows (checked 2026-10-08).
On Windows, install Git with `winget install Git.Git`.

## Q: How do I undo a change?

Ask the tutor to show the save points. Then go back to the last good one, with Git.
In the app, the review pane can revert a file or the whole diff (checked 2026-10-08).
A revert throws the edit away. Read the diff first, and say which file you want back.

## Q: How do I see what Codex changed?

In the terminal, `/diff` shows the Git diff. It includes new files that Git does not track yet (checked 2026-10-08).
In the app, the review pane shows the changes. You can stage or revert them there.
Ask the tutor for the change card. It lists the files created, changed and deleted.

**Control**

## Q: How do I make the tutor quieter, simpler, or teach in my language?

Say it in plain words in the chat. The tutor applies it at once.
"quiet mode" keeps the result, the safety lines and the save-point question. It drops glosses, checks and offers.
"teach me again" turns lessons back on. "simpler" gives shorter sentences for the session.
Name a language, for example "explain in Turkish". Commands stay in English.

## Q: How do I stop Codex when it is doing something wrong?

In the terminal, press Ctrl+C or type `/exit` to close the session (checked 2026-10-08).
The docs I checked do not name the key that stops one answer. Ask Codex for it, and it can check the docs.
Stopping does not undo changes that are already made. Ask Codex to put them back, or use Git.

## Q: What do the permission questions mean?

Codex asks before some steps. Each question names the step.
Answer yes only when you know what the step does. Answer no to stop it.
Choose the narrowest answer that lets the task go on (checked 2026-10-08).

## Q: Why did Codex stop a command?

Either the sandbox blocked it, or a rule in `.codex/rules/tutor.rules` stopped it.
Read the message. It says what was blocked. Ask Codex for the safe way it names.
Do not approve a command you do not understand. Do not add a rule you do not understand.

## Q: What is the difference between Ask for approval and Full access?

Ask for approval keeps Codex inside the project folder. Codex pauses before it goes beyond that (checked 2026-10-08).
Full access runs without the sandbox and without approval questions (checked 2026-10-08).
Use Ask for approval for this kit. Do not use Full access on a personal computer.

**Trust**

## Q: What does "trust this folder" mean?

When you open a folder, Codex may ask whether you trust it. Codex loads a project's `.codex` settings and rules only in a trusted folder (checked 2026-10-08).
Until you trust it, Codex may start in read-only mode (checked 2026-10-08).
Say yes only to folders you made or know. Do not trust your Desktop, Downloads or home folder.

## Q: What can Codex read and change on my computer?

Codex works in the project folder and in temporary folders such as `/tmp`. It asks before it writes outside that space (checked 2026-10-08).
Network access is off by default. The kit does not turn it on.
Codex can read the files in the project. A written rule asks it not to open `.env` files. A written rule is not a lock.

## Q: Can Codex delete my files?

Yes. Codex can delete files inside the project folder when a step needs it.
The kit's rules say Codex must ask you first before any destructive command.
Command rules help, but they match only the start of a command. Save a point before a big change.

## Q: What is a .env file, and where do my secrets go?

A `.env` file holds secrets for your project, such as a key or a password. Each line has a name, an equals sign and a value.
Keep the file on your computer. Git must not track it. Ask the tutor to add it to `.gitignore`.
The tutor does not open `.env`. You open the file yourself and tell the tutor only the names.

## Q: What do I do if I pasted an API key in the chat?

Do not repeat it. Revoke it now, at the service that issued it. The start of the key often shows the service.
Then make a new key and put it in a `.env` file. Git must not track that file.
Deleting a chat copy does not make the old key safe again.

**Upkeep**

## Q: What does the tutor remember between chats?

The tutor keeps notes in the `.tutor` folder. They hold where the project stands, a daily journal, your settings and your list.
Your list shows what you did and understood. It is not a test, and it can be wrong.
To take an item off your list, say `forget` and its name. Read the notes if something seems wrong.

## Q: Where is my chat data kept, and can I delete it?

Codex saves local chat transcripts. By default they go to `history.jsonl` in your Codex home folder, usually `~/.codex` (checked 2026-10-08).
To stop saving them, set `persistence = "none"` in the `[history]` table of `config.toml` (checked 2026-10-08).
I did not find how long Codex keeps transcripts. To remove one, run `codex delete` with its session name in a terminal.

## Q: Can I share my project with someone?

Yes, but check it first. Ask Codex to run `$before-push` before you share anything.
The checklist looks for secrets, personal data, large files and the files that would be sent.
Share a private repository first. Make it public only when the checklist says it is safe.

## Q: How do I update Codex and this kit?

The CLI page explains how to upgrade Codex (checked 2026-10-08). Follow the steps for the way you installed it.
For the kit, save a copy of any file you edited. Then copy the new `AGENTS.md`, `.codex` and `.agents` over the old ones.
Your notes in `.tutor` stay.

## Q: How do I remove the kit from my project?

Close Codex. Delete `AGENTS.md`, the `.codex` folder and the `.agents` folder from the project folder.
Your project files and your Git history stay as they are.
Your `.tutor` folder stays too. Delete it as well if you want to remove your notes.
