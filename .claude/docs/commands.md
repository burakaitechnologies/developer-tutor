# Commands and phrases

Facts about the built-in commands were checked 2026-10-07 against the official Claude Code docs.

You can type a command that starts with `/`. You can also say the same idea in plain words. Both work.

## Week 1

- **Plain talk.** Ask in your own words. For example: "explain this like I am new."
- **`/tutor`** shows the menu, where you are, and a health check.
- **"quiet mode"** stops most lessons until you say "teach me" again.

## Week 2

- **`/save-point`** saves your work with a Git commit. A save point is a checkpoint you can return to.
- **`/fix-it`** works through an error with you.
- **`/rewind`** (built into Claude Code) goes back to an earlier point. It can restore the conversation and the code.
- **`/clear`** (built into Claude Code) starts a new, empty conversation. Your notes stay.

## Later

These skills start when you type the command or say a matching phrase. The table comes from each skill's description. Do not edit it by hand.

<!-- skills:start -->
| Command | What it does |
|---|---|
| `/before-push` | Checks secrets, visibility, large files, personal data, README, tests; ends with go or no-go. |
| `/explain` | Reads the real thing first, then explains it. |
| `/fix-it` | You read the error first; then reproduce, locate, fix, verify. |
| `/git-rescue` | Looks first, saves a snapshot, then one safe recipe. |
| `/learn` | One short lesson on one concept with one check, or a quick review. |
| `/new-project` | The only skill that runs git init and writes .gitignore. |
| `/progress` | A short, honest picture of what you understand, did yourself and did alone, and what is next. |
| `/save-point` | Checks status and tests, commits specific files, says what is not saved. |
| `/think-first` | Sorts into no, short or full gate: options, plan, one yes. |
| `/tutor` | Hub, settings, health check. |
| `/tutor-setup` | Welcome, at most 3 questions, first small build. |
<!-- skills:end -->

## Built-in Claude Code commands worth knowing

These commands come with Claude Code. The kit does not add them. Some of them open a panel in the terminal. In the Desktop app they work differently, or are not there. Type `/` in the prompt box to see what the Desktop app offers. The Desktop guide lists the terminal-only dialogs.

- `/powerup`: short interactive lessons about Claude Code features.
- `/doctor`: checks your Claude Code install. It is not the kit's `doctor.py`.
- `/init`: writes a `CLAUDE.md` file for the project. This kit already has one in `.claude`. Ask the tutor before you run it.
- `/context`: shows what fills the conversation memory, as a grid.
- `/btw`: asks a side question that does not join the conversation.
- `/compact`: summarizes the conversation to free space. The kit's rules and the tutor style stay.
- `/output-style`: lists output styles or switches to one. The tutor style is set in `settings.json`.
- `/permissions`: manages allow, ask and deny rules in a dialog. In the Desktop app, edit `settings.json` instead.
- `/usage`: shows the session cost and your plan limits. In the Desktop app, click the usage ring next to the model picker.
- `/memory`: edits the `CLAUDE.md` files.
- `/model`: switches the model.
- `/resume`: picks an earlier conversation to continue.
- `/status`: shows the version, model, account and connection.
- `/login` and `/logout`: sign in or out of your Anthropic account.
- `/help`: lists the commands.

## Things you can just say

Each row lists plain phrases. Saying one of them starts the skill in the second column.

| Say something like | Starts |
|---|---|
| "what can you do", "menu", "where are we", "what next", "is it working", "quiet mode", "turn on helper scripts", `/tutor` | `tutor` |
| "hello", "I am new", "where do I start" (first message in a project) | `tutor-setup` |
| "teach me X", "what is X", "quiz me", "refresh" | `learn` |
| "what have I learned", "how am I doing", "my progress", "am I ready" | `progress` |
| "what does this do", "explain this file", "what did you change", "walk me through this diff" | `explain` |
| "build me an app with login or a database", "which framework", "should we use X", payments, user data, deploy | `think-first` |
| "start a project", "I have an idea for an app", "set up git", an empty folder | `new-project` |
| "it does not work", "I got an error", a pasted error, "nothing happens", "fix this" | `fix-it` |
| "save", "save my work", "commit", "wrap up", "I am done for today" | `save-point` |
| "push", "publish", "put it on GitHub", "make it public", "upload my project" | `before-push` |
| "I broke git", "undo that", "I lost my changes", "wrong branch", "merge conflict", "push rejected" | `git-rescue` |

## The doctor.py commands

`doctor.py` is the kit's helper. Put one of these verbs after the Python command and `.claude/tools/doctor.py`. For example, `check` gives `py -3 .claude/tools/doctor.py check` on Windows, or `python3 .claude/tools/doctor.py check` on macOS and Linux. The [Python command](#how-to-write-the-python-command) section explains which name to use.

| Verb | What it does |
|---|---|
| `check` [--strict] [--json] [--fix-interpreter [NAME]] | Checks that everything works. The Verdict line comes near the top, under the project folder path. `--strict` exits with code 1 when something needs attention. |
| `progress` [numbers] | Shows a short picture of what you understood and did. `numbers` adds the counters. |
| `enable-hooks` [--interpreter NAME] | Turns the helper scripts on. Adds a `hooks` block to `settings.json`. Keeps a copy of the old file as `settings.json.tutor-backup`. Moves older notes into your list, if you had any. Claude asks you before it runs this. |
| `disable-hooks` | Turns the helper scripts off. Removes the tutor's hook entries from `settings.json`. Your own hook entries stay. Claude asks you before it runs this. |
| `envcheck` [FILE] | Lists the names in your `.env` file and whether each one is set. It never shows the values. |
| `audit` [FOLDER] | Lists everything in a folder that can run code or change the safety rules. |
| `share-notes` on or off [--i-checked-it-is-private] | Keeps your notes in a private GitHub repository. `on` asks GitHub through the `gh` tool and refuses unless it can confirm the repository is private. Add the flag only after you have checked on github.com that the repository is private. Claude asks you before it runs this. |
| `wipe` chat, state or all [--yes] | Deletes tutor data on this computer. Without a terminal to answer, add `--yes`. In a terminal, the command asks you to type `DELETE` and press Enter. Claude asks you before it runs this. |
| `verify` | Checks the kit files against `MANIFEST.txt`, and runs the safety lint. It lists each changed file under "Needs attention". It exits with code 1 when a kit file differs or is missing. |

## How to write the Python command

The name of Python differs between computers. Try these names in this order:

- **Windows:** `py -3` first, then `python`.
- **macOS and Linux:** `python3` first, then `python`.

Use the first one that prints a version of 3.9 or newer. Check it with `--version`, for example `py -3 --version`. Then use that same name in every kit command.

If `python` opens the Microsoft Store, Python is not installed. See [How to install Python](troubleshooting.md#how-to-install-python).
