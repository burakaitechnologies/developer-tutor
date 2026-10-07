# Customize the tutor

Facts about Codex settings in this page were checked 2026-10-08 against the official Codex docs.

Most changes need one sentence in chat. The tutor makes the change in its file for you. This page explains each setting, so you can choose.

## Profile settings

The tutor keeps your settings in `.tutor/learner/profile.md`. The file has a few `key: value` lines between two `---` lines. Ask the tutor to change a setting. Use the words in the table exactly.

| Setting | Allowed values (default) | Say this | What changes |
|---|---|---|---|
| `language` | a language name (the language of your first message) | "explain in Turkish" | Explanations and labels use this language. Commands, file names and error text stay in English. |
| `level` | auto, A2, B1, B2, C1 (auto) | "simpler" or "more detail" | Sentence length and answer length. `auto` works like B1. |
| `teaching` | normal, light, off (normal) | "only explain new words" (light) or "stop teaching me" (off) | `light` gives explanations of new words only, with no checks. `off` gives no lessons. |
| `comments` | teaching, normal, minimal (teaching) | "fewer comments" | How many comments the tutor writes in new code files. Existing files are never changed. |
| `learn_first` | topic names, separated by commas (empty) | "teach me Git first" | Offers prefer these topics. |
| `call_me` | a first name (empty) | "call me <your first name>" | The name used in greetings. It stays in your private notes. |

The tutor sets `onboarded` itself. You do not need to change it.

Use only the allowed values. Check the spelling after you edit the file by hand.

## Change the language

Say "explain in" and a language, such as "explain in German". Explanations change. Commands, file names and error text stay in English.

The short labels change too. These are the labels for each language.

| Language | Check | Predict | Your move | Offer |
|---|---|---|---|---|
| English | `Check:` | `Predict:` | `Your move:` | `Next I can teach:` |
| Turkish | `Kontrol:` | `Tahmin:` | `Sıra sende:` | `Sıradaki konular:` |
| Spanish | `Comprueba:` | `Predice:` | `Tu turno:` | `Siguientes temas:` |
| German | `Prüfe:` | `Vorhersage:` | `Du bist dran:` | `Als Nächstes kann ich erklären:` |
| French | `Vérifie :` | `Prédis :` | `À toi :` | `Prochains sujets :` |

## Quiet mode, light mode and teaching off

- **"quiet mode"** stops lessons for this session only. Say "teach me" to bring them back.
- **"only explain new words"** sets `teaching` to `light`. You get explanations of new words only. There are no checks and no reviews.
- **"stop teaching me"** sets `teaching` to `off`. You get no lessons.
- **"teach me again"** sets `teaching` back to `normal`.

In every mode you still get the result and the safety notes. "Just do it" drops explanations, checks and optional questions for one piece of work. It does not give permission. Quiet mode does not give permission either. Codex still asks you before a step that is hard to undo.

## Permissions in plain words

A permission setting decides how often Codex asks you before it acts. The sandbox is the boundary around files and commands. It is a limit that your computer enforces on what Codex can touch.

| Mode | What Codex does without asking | Where to set it |
|---|---|---|
| **Ask for approval** | Works inside the project folder. Asks before it goes outside the folder. | App: the control below the message box. Terminal: `/permissions`. |
| **Approve for me** | Sends some approval requests to an automatic reviewer. Automatic review can add to your usage. | App: the control below the message box. |
| **Full access** | Is not limited to the project folder. | App: the control below the message box. |

The terminal picker may use other names, such as **Auto** and **Read Only**. Auto edits files in the folder and asks before it goes outside the folder. Read Only lets Codex read files, but not change them.

For week 1, keep **Ask for approval**. Never choose **Full access** on a personal computer. Ask the tutor before you choose **Approve for me**.

## The safety rules file

The file `.codex/rules/tutor.rules` lists rules for commands. A rule matches the start of a command. It can say:

- `prompt`: Codex asks you before it runs the command.
- `forbidden`: Codex refuses the command.

If two rules match, the stricter rule wins. The rules use Starlark, a small language that looks like Python. Rules are best effort. They stop accidents, but they are not a full lock.

The rules file loads only for a trusted folder. Rules are experimental and may change (checked 2026-10-08).

To change a rule:

1. Open `.codex/rules/tutor.rules` in a text editor. Codex keeps the `.codex` folder read-only, so you edit it yourself.
2. Save the file as UTF-8 text.
3. Restart Codex. Codex reads the rules at start.
4. Test the rule. Run `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- git push`. The output shows the decision: `allow`, `prompt` or `forbidden`.

Ask the tutor before you weaken a rule. A rule that asks you first is there to protect your work.

## The settings file: .codex/config.toml

The file `.codex/config.toml` holds the settings for this project. Codex reads it only after you trust the folder. It sets three things:

- `approval_policy = "on-request"`: Codex asks you when an action needs approval.
- `sandbox_mode = "workspace-write"`: Codex can write inside the project folder. The `.git`, `.codex` and `.agents` folders stay read-only.
- `project_doc_max_bytes = 49152`: Codex may read up to 48 KiB of instruction files. The default is 32 KiB. A KiB is 1,024 bytes.

Your own settings for all projects live in `~/.codex/config.toml`. On Windows, `~` means your user folder. Settings in the project file win over your own settings, when the folder is trusted.

Start Codex again after you edit a settings file. For Windows, see the sandbox entry in `troubleshooting.md` before you change `[windows]` settings.

## Add your own section to AGENTS.md

The file `AGENTS.md` in the project folder tells Codex how to work. The kit wrote it. You can add facts about your project at the end, under the heading `## This project`.

Add that section only after your first build, and only with your yes. The template is `.agents/tutor/templates/project-section.md`. Keep the section under 40 lines. Keep the kit's text as it is.

Check the result: ask Codex "List the instruction sources you loaded." Codex should name `AGENTS.md`.

## Add your own skill

A skill is a folder with one file named `SKILL.md`. The folder name is the skill's name. For example, `.agents/skills/my-skill/SKILL.md`.

The top of the file, between two lines of dashes, is called the front matter. Codex reads it first.

```
---
name: my-skill
description: Use when I say "my phrase". Explains what this skill does, in one sentence.
---

Steps for Codex to follow, one step per line.
```

Follow these rules:

- `name` and `description` are required.
- Put the trigger words first in `description`. Codex matches a task to a skill with this text.
- Keep `description` to one or two sentences. Codex shortens long descriptions first.
- Keep one job in each skill.

To write a skill with help, type `$skill-creator`. You can also write the file yourself. Codex keeps `.agents` read-only, so create the folder and file in a text editor.

Check the result: in the terminal, type `/skills`. Your skill should appear in the list. If it does not, restart Codex.

## Optional: a lock on .env files (beta)

A `.env` file holds secrets, such as keys and passwords. A permission profile can block Codex from reading `.env` files in the project. This is a beta feature. Beta means it can change. Codex docs call permission profiles beta (checked 2026-10-08).

Use this only after you read the rules above. It replaces the `sandbox_mode` setting. Codex uses the older setting if any loaded file still has `sandbox_mode`.

1. Remove the line `sandbox_mode = "workspace-write"` from `.codex/config.toml`. Also remove any `sandbox_mode` line from `~/.codex/config.toml`.
2. Add this text at the end of `.codex/config.toml`:

```toml
default_permissions = "project-edit"

[permissions.project-edit]
extends = ":workspace"

[permissions.project-edit.filesystem]
glob_scan_max_depth = 3

[permissions.project-edit.filesystem.":workspace_roots"]
"**/*.env" = "deny"
```

3. Start Codex again. Type `/debug-config`. It shows which settings files Codex loaded.

This profile starts from the workspace profile. It blocks reads of any `.env` file under the project folder. On Windows, Codex may refuse this profile when the sandbox is the weaker unelevated kind. See `troubleshooting.md` if that happens.

Do not ask Codex to open a `.env` file to test this. Keep secrets in `.env`, and keep `.env` out of Git.

## Where your notes are, and how to delete them

The tutor keeps its notes in the `.tutor` folder in your project:

- `now.md`: where you are now.
- `journal/`: dated notes about decisions and work.
- `learner/profile.md`: your settings.
- `learner/notes.md`: your list, with what you learned and did.

Git ignores everything in `.tutor` except its own `.gitignore` file. Your list stays on this computer.

Codex also keeps its own chat history, separate from the tutor notes. It is in `~/.codex/sessions`. Deleting `.tutor` does not delete it.

To delete the tutor notes by hand:

1. Close Codex.
2. Copy the `.tutor` folder somewhere, if you want a backup.
3. In File Explorer, open `.tutor`. Delete the files and folders inside it, except `.gitignore`.

There is no undo. Keep `.tutor/.gitignore`. It keeps your notes out of Git. Without it, a later save point could include them.

To delete one Codex chat, type `/delete` in that chat. It removes the chat and closes Codex. It cannot be undone.
