# Developer tutor kit for Codex

This kit turns Codex into a patient developer and tutor. It builds your real project with you. It explains each step in plain words. It keeps short private notes about what you learned.

The kit is a set of text files. You copy them into a project folder. Codex reads them when it starts.

Codex facts here were checked on 2026-10-08 against the official docs. This edition has not been run with Codex yet. The section [How the kit was checked](how-it-works.md#how-the-kit-was-checked-and-what-that-does-not-prove) says what that means.

## What you need

- A ChatGPT account with access to Codex. The pricing page lists Codex on several plans, with different limits. Check it before you choose a plan (checked 2026-10-08).
- One Codex surface:
  - the ChatGPT desktop app. Download it from chatgpt.com/download.
  - the Codex IDE extension, in your code editor.
  - the Codex CLI, which runs in a terminal. Install it with `npm install -g @openai/codex`, or use the installer on the CLI page.
- Optional: Git. The tutor's save points need Git. On Windows, install Git with `winget install Git.Git`.

The kit needs no Python and no other program.

## Install in three steps

You do not need a terminal for the app.

1. Make a new, empty folder for one project. Use plain letters, for example `C:\code\my-app`. Do not use your Desktop, Downloads, Documents, OneDrive, iCloud, Dropbox or home folder.
2. Copy `AGENTS.md`, the `.codex` folder and the `.agents` folder into that folder. Copy nothing else. On macOS, press Cmd+Shift+period in Finder. This shows folders that start with a dot.
3. Open the folder in Codex, then say `hello`.
   - App: choose **Codex** in the ChatGPT dropdown, then open the folder.
   - CLI: open a terminal in the folder and type `codex`.
   - If Codex asks you to trust the folder, say yes only to a folder you made.

The tutor answers with a short welcome. It then asks what you want to build.

To check the install, type `$tutor`. The tutor lists what it can do.

## What is in the kit

| Item | What it is |
|---|---|
| `AGENTS.md` | The main instructions. Codex reads it when it starts. It sets the tutor's voice, rules and safety steps. |
| `.codex/config.toml` | Settings for this folder: sandbox mode and approval policy. Codex reads it only in a trusted folder. |
| `.codex/rules/tutor.rules` | Command rules. Each rule allows, asks about or forbids the start of one command. Trusted folders only. |
| `.codex/agents/` | Two read-only helpers, `architecture_reviewer` and `code_reviewer`. Codex starts one only when you ask. |
| `.agents/skills/` | Eleven skills. Each skill is a folder with a `SKILL.md` file. Start one with a dollar sign and its name, for example `$learn`. |
| `.agents/tutor/` | Knowledge cards, forms for notes, these docs and a version file. The tutor reads the cards one line at a time. |
| `.tutor/` | Your private notes and your list. The tutor creates it at the first note. The `.gitignore` file in it tells Git to skip the notes. |

## What runs on your computer

Nothing from the kit runs by itself. The kit is text. Codex runs commands itself, inside its sandbox. The sandbox limits which files and which network the commands can use. [How it works](how-it-works.md) explains the safety layers and their limits.

## Using the kit in a project that already has files

- **An existing AGENTS.md:** Codex reads one AGENTS.md per folder. Add the kit's text to your file. Put it before or after your own text. Codex stops reading instruction files at 32 KiB in total (checked 2026-10-08).
- **An existing .codex/config.toml:** merge the two files by hand. Keep one line for each setting.
- **An existing .agents/skills folder:** add the eleven skill folders. If two skills have the same name, Codex shows both. It does not merge them (checked 2026-10-08).
- **A folder without Git:** the kit works. Codex checks the folder you start in. The tutor sets up Git at the first save point, after a yes.
- **A monorepo, or a project in a sub-folder:** Codex reads AGENTS.md files from the repository root to your start folder (checked 2026-10-08). Start Codex in the folder with the kit. Or put the kit at the root.
- **A folder you did not make:** read its files first. Trust a folder only when you know what is in it.

## Update and remove by hand

The kit has no installer and no updater. You copy and delete the files yourself.

- **To update:** save a copy of any kit file you edited. Then copy the new `AGENTS.md`, `.codex` and `.agents` over the old ones.
- **To remove:** delete `AGENTS.md`, `.codex` and `.agents` from the project folder. Your project files stay. The `.tutor` folder stays too, unless you delete it.

## Docs in this folder

- [getting-started.md](getting-started.md): the first steps, in more detail.
- [commands.md](commands.md): what to say, and the Codex commands the kit uses.
- [customize.md](customize.md): settings, language, permission modes and your own rules.
- [troubleshooting.md](troubleshooting.md): problems and their fixes.
- [how-it-works.md](how-it-works.md): how the parts work together, and their limits.
- [faq.md](faq.md): common questions in plain words.
- [extending.md](extending.md): for people who change the kit.

## Honest limit

The sandbox, approvals and command rules stop accidents and obvious mistakes. They do not stop a determined person. A harmful file or web page can still trick Codex. Read [how it works](how-it-works.md) before you trust the kit with important work.
