# developer-tutor: Codex edition

developer-tutor is a set of text files for Codex, the coding agent made by OpenAI. Copy the files into your project folder. Codex then acts as a patient senior developer and tutor. It builds your real project with you, one small step at a time. It explains each choice in plain words. It asks you to do small steps yourself. It keeps a list of what you have done.

This branch holds the Codex edition. A Claude Code edition lives on the main branch.

## Who it is for

- People with little or no experience with programming, Git or GitHub.
- People who may never have opened a terminal.
- People who want to build something real and learn while they build it.

## Who it is not for

- Experienced developers who want a code generator.
- People who want Codex to do all the work, with no learning.
- People who skip the safety notes and expect a finished product.

## Start here

The desktop app needs no terminal. Steps 1 to 5 need no Git.

0. **Install Codex and sign in.** Pick one way:
   - **ChatGPT desktop app.** Download it from [chatgpt.com/download](https://chatgpt.com/download/). On Windows you can also run `winget install --id 9PLM9XGG6VKS -s msstore`. Open it and sign in with your ChatGPT account.
   - **Codex CLI (the terminal program).** On Windows, open a new PowerShell window. Run `powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"`. On macOS or Linux, run `curl -fsSL https://chatgpt.com/codex/install.sh | sh`. Then run `codex` and choose **Sign in with ChatGPT**.
   - Check the CLI with `codex --version`. It prints a version number (checked 2026-10-08).

1. **Download the ZIP of this branch.** On this repository's page, choose this branch. A branch is one line of versions in a Git repository. Click the green **Code** button, then **Download ZIP**. Unzip the file:
   - Windows: right-click the ZIP file and choose **Extract All**.
   - macOS: double-click the ZIP file in Finder.

2. **Make a new empty folder for your project.** Use letters, digits and dashes, with no spaces, such as `my-app`. Do not use Desktop, Downloads or Documents. Do not use a OneDrive, iCloud or Dropbox folder.
   - Windows: in File Explorer, open `C:\`, make a folder named `code`, and make `my-app` inside it.
   - macOS: in Finder, open your home folder, make a folder named `code`, and make `my-app` inside it.

3. **Copy three items into the folder.** Copy `AGENTS.md`, `.codex` and `.agents` from the unzipped folder into `my-app`. Copy nothing else.
   - macOS: in Finder, press Command, Shift and period together. This shows hidden folders.

4. **Open your new folder in Codex.**
   - App: choose **Codex** in the ChatGPT dropdown. Then open `my-app` as a project. On Windows, click **Add new project** or press Ctrl+O (checked 2026-10-08).
   - Terminal: open PowerShell (Windows) or Terminal (macOS, Linux). Type `cd C:\code\my-app` on Windows, or `cd ~/code/my-app` on macOS and Linux. Then run `codex`.

5. **Trust the folder, choose a mode, and say hello.**
   - If Codex asks whether to trust the folder, read the question. Choose trust only for your own project folder. Trust lets Codex load this folder's settings and rules.
   - Until you trust the folder, Codex may stay in read-only mode. In that mode it reads files but cannot change them.
   - In the app, choose **Ask for approval** under the chat box. It lets Codex work in the folder. It pauses before anything outside.
   - In the terminal, run `/permissions` and choose **Auto**. Auto lets Codex edit this folder and asks before it goes further.
   - Do not choose **Full access**. It turns the sandbox off.
   - Type `hello`. The tutor answers with a greeting and one question.

## Requirements

- A ChatGPT account with Codex access. Codex is included in the Free, Go, Plus, Pro, Business, Enterprise and Edu plans. Limits differ by plan (checked 2026-10-08).
- Adults only. OpenAI's terms set an age limit; check them. This kit cannot check your age.
- Codex, as the ChatGPT desktop app or the terminal program `codex`. No Codex version has been tested with this kit.
- Windows, macOS or Linux. On Windows, Codex runs commands in PowerShell. It uses a Windows sandbox, or it can run in WSL2 (checked 2026-10-08).
- Git, for save points. Git is optional until your first save point. A save point is a Git commit: a saved version of your project. On Windows, install Git with `winget install --id Git.Git`.

## What you get

- A tutor voice: short answers, plain words, and one check question at a time.
- Eleven skills. A skill is a set of instructions for one kind of task. Start one with its `$name`, or say a phrase from the table. Codex may also pick a skill by its description.
- Two read-only helpers, `architecture_reviewer` and `code_reviewer`. Codex starts them only when you ask, or when a skill tells it to. They read files and never change them.
- Safety rules in `.codex/rules/tutor.rules`. They ask before risky commands such as `git push`. They refuse a force push, which replaces the history on GitHub.
- Notes in `.tutor/`. Git ignores that folder.

| Skill | Say something like | What it does |
|---|---|---|
| `$tutor` | "what can you do", "quiet mode" | Shows the menu, settings and a health check |
| `$tutor-setup` | "hello" in a new folder | Welcomes you, asks a few questions, builds a first small version |
| `$learn` | "teach me Git" | Gives one short lesson with one check |
| `$progress` | "what have I learned" | Gives an honest picture of what you know |
| `$explain` | "what does this file do" | Reads the real file and explains it |
| `$think-first` | "should I use a database" | Decides how much planning a choice needs |
| `$new-project` | "I want to start a project" | Sets a goal, simple tools, a README and Git |
| `$fix-it` | "I got this error" | Reads the error with you, then fixes it |
| `$save-point` | "save my work" | Makes a Git save point, which is a commit, with a short note |
| `$before-push` | "put it on GitHub" | Checks secrets and visibility before you push |
| `$git-rescue` | "I broke Git" | Looks first, saves a copy, then makes one safe fix |

## What runs on your computer

- Nothing in this kit runs by itself. The kit is text: instructions in Markdown, settings in TOML, and rules in Starlark, a language that looks like Python.
- Codex runs commands in your project folder when it needs them. The sandbox is the limit on what Codex can touch. The approval mode decides when Codex asks you first.
- The kit has no scripts, no hooks and no network code of its own. A hook is a small program that runs at set points.
- Codex talks to OpenAI to answer you. Web search is on by default in cached mode (checked 2026-10-08). Treat web results as untrusted.

## How it teaches

- You do the small steps yourself. Each step changes one line, one file or one command.
- The tutor asks you to predict, explain or change something. Answer in your own words.
- Your list shows what you understand, what you have done and what you did alone. It stays in `.tutor/` on your computer.
- Say `quiet mode` to turn the explanations down for this session. The safety rules stay on. Ask the tutor to turn teaching off for good, or to teach again.

## Using the kit in a project that already has files

- Copy the three items into the top folder of the project, the folder that holds `.git`. Start Codex in that folder.
- A folder without Git counts as its own top folder. Codex then reads only the folder you start in. Start it in the folder that holds `AGENTS.md`.
- If the project already has an `AGENTS.md`, do not overwrite it. Ask the tutor to merge the two files with you.
- If a skill has the same name as one of yours, Codex keeps both, and both can appear in the list.
- Do not keep the project in OneDrive, iCloud or Dropbox. Sync can upload your notes and can damage the `.git` folder.

## Honest limits

- A language model can be wrong. Check what it says. Run the checks it suggests.
- This edition was ported from the main branch. Nobody has run it with Codex yet. The owner's live check is in [docs/test-report.md](docs/test-report.md).
- The rules are best effort. They match the start of a command. Codex calls rules experimental, and they can change.
- A command wrapped in another shell may not match a rule. The rules do not stop a determined or tricked agent.
- There is no command guard, no secret scanner and no hook in this edition.
- `AGENTS.md` is text that the model reads. It is advice, not a lock.

## Licence

There is no licence file yet. The owner has not chosen a licence. Until one is added, all rights stay with the owner. You may read the kit and try it on your own computer. Ask the owner before you share, sell or build on a copy.

## Links

- [Getting started](.agents/tutor/docs/getting-started.md)
- [Questions and answers](.agents/tutor/docs/faq.md)
- [Security](SECURITY.md)
- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)
- [Test report](docs/test-report.md)
