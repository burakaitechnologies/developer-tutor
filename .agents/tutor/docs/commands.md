# Commands and phrases

Facts about Codex commands in this page were checked 2026-10-08 against the official Codex docs.

There are two kinds of commands you can type in the message box:

- A **slash command** starts with `/`. Codex has it built in. Example: `/status`.
- A **skill** starts with `$`. A skill is a saved set of instructions for one kind of task. Example: `$tutor`.

You can also say the same idea in plain words. Both work. Type `/` in the message box to see the slash commands the app offers.

## Week 1

- **Plain talk.** Ask in your own words. For example: "explain this like I am new."
- **`$tutor`** shows the menu, where you are, and a health check.
- **"quiet mode"** stops most lessons until you say "teach me" again.

## Week 2

- **`$save-point`** saves your work with a Git commit. A commit is a saved checkpoint of your files.
- **`$fix-it`** works through an error with you.
- **`/diff`** shows which lines changed in your files. Use it to read what Codex changed.
- **`/clear`** starts a new, empty chat. Your notes in `.tutor` stay. The tutor reads its notes again after `/clear`, `/new` or `/compact`.
- **Esc, then Esc again**, with an empty message box, edits your last message. Codex then starts a new chat from that point. This copy of the chat is called a fork.

## Later

Each skill has its own file in `.agents/skills/`. The table shows a short summary of each one. Type `/skills` in the terminal to see the list.

| Skill | Say something like | What it does |
|---|---|---|
| `$tutor` | "where are we", "is it working", "quiet mode" | The menu, your settings and a health check. |
| `$tutor-setup` | "hello" in a new project | Welcome, up to three questions, and the first small build. |
| `$learn` | "teach me Git", "quiz me" | One short lesson with one check, or a quick review. |
| `$progress` | "what have I learned", "am I ready" | A short, honest picture of what you know and what you did alone. |
| `$explain` | "what does this do", "walk me through this diff" | Reads the real file or change first, then explains it. It changes nothing. |
| `$think-first` | "should we use a database", "build me a login" | Decides how much planning a choice needs. Gives options and asks for one yes. |
| `$new-project` | "start a project", "set up Git" | Goal, tools, README, Git setup and the first save point. |
| `$fix-it` | "I got an error", "it does not work" | Reads the error first, then finds the cause and checks the fix. |
| `$save-point` | "save my work", "I am done for today" | Checks the status, saves chosen files with a commit, and says what is not saved. |
| `$before-push` | "push", "put it on GitHub" | Checks secrets, visibility, large files, personal data and the README. Ends with a go or no-go answer. |
| `$git-rescue` | "I broke Git", "undo that" | Looks first, saves a copy, then runs one safe recipe. |

Skills that use Git ask before each Git change. That is normal. The `.git` folder is read-only for Codex, so each Git write needs your yes.

## Built-in Codex commands worth knowing

These commands come with Codex. The kit does not add them.

| Command | What it does |
|---|---|
| `/permissions` | Changes how much Codex asks before it acts. |
| `/status` | Shows your folder, your approval mode and the folders Codex can write to. |
| `/diff` | Shows your changes, including new files that Git does not track yet. |
| `/review` | Asks Codex to review your changes and list the problems it finds. |
| `/plan` | Asks Codex to propose a plan before it changes anything. |
| `/skills` | Lists the skills. Pick one to use it. |
| `/clear` | Starts a new, empty chat in the same session. |
| `/new` | Starts a new chat in the same session, without clearing the screen first. |
| `/compact` | Summarizes the chat so far, to free space for more work. |
| `/resume` | Opens a saved chat, so you can continue it. |
| `/usage` | Shows your usage and limits. |
| `/mention` | Adds a file to the chat. You can also type `@` and then part of a file name. |
| `/copy` | Copies the latest finished answer. `Ctrl+O` does the same. |
| `/init` | Makes an `AGENTS.md` file. This project already has one. Ask `$tutor` before you run it. |
| `/exit` | Closes Codex. Save your work with `$save-point` first. |

## Keys in the terminal

- `@` opens a file search. Pick a file to add its path to your message.
- `!` before a command runs it in your own shell. It runs under the current approval and sandbox settings. The sandbox is explained in `customize.md`.
- `Tab` while Codex works queues your next message. It runs after the current step.
- `Enter` while Codex works adds new instructions to the current step.
- `Up` and `Down` show the messages you typed before.
- `Ctrl+C` or `/exit` closes Codex.

## Things you can say

| Say something like | Starts |
|---|---|
| "what can you do", "menu", "where are we", "what next", "is it working", "quiet mode", "explain in Turkish", `$tutor` | `$tutor` |
| "hello", "I am new", "where do I start" (first message in a project) | `$tutor-setup` |
| "teach me X", "what is X", "quiz me", "refresh" | `$learn` |
| "what have I learned", "how am I doing", "am I ready" | `$progress` |
| "what does this do", "explain this file", "what did you change", "walk me through this diff" | `$explain` |
| "build me an app with login or a database", "which framework", "should we use X", payments, user data, deploy | `$think-first` |
| "start a project", "I have an idea for an app", "set up Git", an empty folder | `$new-project` |
| "it does not work", "I got an error", a pasted error, "nothing happens", "fix this" | `$fix-it` |
| "save", "save my work", "wrap up", "I am done for today" | `$save-point` |
| "push", "publish", "put it on GitHub", "make it public", "upload my project" | `$before-push` |
| "I broke Git", "undo that", "I lost my changes", "wrong branch", "merge conflict", "push rejected" | `$git-rescue` |
