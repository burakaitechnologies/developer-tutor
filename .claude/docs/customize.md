# Customize the tutor

Facts about permission modes and built-in settings were checked 2026-10-07 against the official Claude Code docs.

Most changes need only one sentence in chat. The tutor makes the change in its settings file for you. This page explains each setting, so you can choose.

## Profile settings

The tutor keeps your settings in `.claude/agent-memory/tutor-data/learner/profile.md`. The file has a few `key: value` lines between two `---` lines. Ask the tutor to change a setting. Use the words in the table exactly.

| Setting | Allowed values (default) | Say this | What changes |
|---|---|---|---|
| `language` | a language name (the language of your first message) | "explain in Turkish" | Explanations and labels use this language. Commands, file names and error text stay in English. |
| `level` | auto, A2, B1, B2, C1 (auto) | "simpler" or "more detail" | Sentence length and answer length. `auto` works like B1. |
| `teaching` | normal, light, off (normal) | "only explain new words" (light) or "stop teaching me" (off) | `light` gives explanations of new words only, with no checks. `off` gives no lessons. |
| `comments` | teaching, normal, minimal (teaching) | "fewer comments" | How many comments Claude writes in files it creates. Existing files are never changed. |
| `tree` | session, off (session) | "do not list my files" | Whether the start of a session shows a list of your files. |
| `learn_first` | topic names, separated by commas (empty) | "teach me git first" | Offers prefer these topics. |
| `answer_words` | a number from 20 to 400 (empty) | "keep answers under 80 words" | Sets the word limit for the result part of an answer. A number outside 20 to 400 is ignored, with a warning. |
| `chat_copy` | off, on (off) | "save our conversation" | Saves a copy of what you type. See [Chat copy](#chat-copy-off-by-default). |
| `call_me` | a first name, up to 30 characters (empty) | "call me Ada" | The name used in greetings. It stays in your private notes. |

The tutor sets `onboarded` itself. You do not need to change it.

If a value is not allowed, the tutor shows a warning at the next session start. Check the spelling, then try again.

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

## Quiet mode or teaching off

- **"quiet mode"** stops lessons for this session only. Say "teach me" to bring them back.
- **"only explain new words"** sets `teaching` to `light`. You get glosses only, with no checks or reviews.
- **"stop teaching me"** sets `teaching` to `off`. You get no lessons.
- **"teach me again"** sets `teaching` back to `normal`.

In all three modes, you still get a change summary and safety notes. **Just do it** drops explanations, checks and optional questions for one piece of work. It does not give permission. Quiet mode does not give permission either. Claude still asks you before a step that is hard to undo.

## Chat copy (off by default)

When you turn it on, the tutor keeps a copy of what you type:

- Keys and passwords are hidden in the copy.
- The copy stays on your computer, in `.claude/agent-memory/tutor-data/chat/`.
- The copy is kept for 30 days. It needs the helper scripts.

Everything you type also goes to Anthropic. Claude Code also keeps its own record of your conversations. In the terminal, it deletes transcripts after 30 days by default. Desktop transcripts are kept at any age, unless you set `desktopSessionCleanupPeriodDays` in your settings. [Where Claude Code keeps data](https://code.claude.com/docs/en/claude-directory#cleaned-up-automatically) lists the rules. Your copy does not change either rule.

To turn it on, read this section, then say "save our conversation". To turn it off, say "chat copy off". To delete the copies, run the command below. On Windows, use `py -3`. On macOS and Linux, use `python3`. Type `DELETE` and press Enter when it asks.

```
py -3 .claude/tools/doctor.py wipe chat
```

## Share your notes in a private repository

Do this only if you want a backup of your notes on GitHub.

1. On GitHub, create a new repository. Set its visibility to **Private**.
2. Run this command from your project folder. On Windows, use `py -3`. On macOS and Linux, use `python3`.

```
py -3 .claude/tools/doctor.py share-notes on
```

The command asks GitHub, through the `gh` tool, whether the repository is private. It refuses when it cannot confirm that. Only if you have checked on github.com that the repository is private yourself, run it again with `--i-checked-it-is-private`. Claude asks you before it runs this command.

Shared: `now.md`, your journal and `learner/profile.md`.

Not shared: chat copies, progress, inbox files and the state files.

To stop sharing, run the same command with `off` in place of `on`, for example `py -3 .claude/tools/doctor.py share-notes off`.

## Add your own rule

Rules are short notes that every agent reads. To add one, put a new `.md` file in `.claude/rules/`.

- Start with a `#` heading.
- Keep one idea in each file. Keep it under 330 words.
- Every rule adds text that Claude reads in each request. Keep rules short.

Example: a file named plain-file-names.md in the rules folder, with this text:

```
# Plain file names

Name new files with lowercase letters, numbers and dashes.
Example: my-first-page.html.
```

## Add your own skill

A skill is a task the tutor can start. To add one, make a folder in `.claude/skills/` with the skill's name. Put a file named `SKILL.md` in it:

```
---
name: my-skill
description: >-
  "my phrase", "another phrase". What the skill does, in one sentence.
---
```

Follow these rules:

- The `name` must match the folder name. Use lowercase words and dashes.
- Keep `description: >-` as a folded block. Put the text on the next lines, indented.
- As a precaution, avoid double quotes and backslashes inside a plain `description`. This is a habit that keeps the text simple. It is not a rule the kit has tested with Claude Code.
- Keep the description under 210 characters. The kit's checks use this limit.

The repository's `CONTRIBUTING.md` file has more notes on writing skills.

## Turn the helper scripts on or off

- **On:** say "turn on helper scripts". Or run `enable-hooks`. On Windows, use `py -3 .claude/tools/doctor.py enable-hooks`. On macOS and Linux, use `python3 .claude/tools/doctor.py enable-hooks`.
- **Off:** run `disable-hooks` the same way, with `py -3` on Windows or `python3` on macOS and Linux.

If you cannot run Python, you can still switch the scripts off. Create one file, `.claude/settings.local.json`, that contains this line:

```
{"disableAllHooks": true}
```

On Windows, use Notepad:

1. Open Notepad. Type the line above.
2. Choose **File**, then **Save as**.
3. In **Save as type**, choose **All files**.
4. In **File name**, type `settings.local.json`. Type it with no quote marks. Windows does not allow quote marks in a file name.
5. Open the `.claude` folder of your project and save there.

On macOS, use TextEdit:

1. Press Cmd+Shift+period in Finder to show folders that start with a dot.
2. Open TextEdit. Choose **Format**, then **Make Plain Text**. Type the line above.
3. Save the file in the `.claude` folder with the name `settings.local.json`.
4. If the name ends in `.txt`, rename the file to remove `.txt`.

Check that the name ends in `.json`, not `.json.txt`.

To turn the helper scripts on again, delete this file. Only you create it. The safety guard asks before any other agent edits it.

## Updates keep your edits

Run `install.py` with `--update` (see the [README](../README.md)). It keeps every file you changed. It saves the new version next to your file as `<file>.new`. Compare the two files, then keep what you want. It never touches your notes or `settings.local.json`.

## Permission modes in plain words

A permission mode sets how often Claude asks before it acts.

| Mode | What Claude does without asking | Setting value |
|---|---|---|
| Manual | Asks before each file change and each command. | `default` |
| Accept edits | Changes files without asking. Still asks before other commands. | `acceptEdits` |
| Plan | Reads and explores. Proposes a plan. Does not edit your code. | `plan` |
| Auto | Runs without routine prompts. A background check looks at each action. Shows only when your plan and model allow it. | `auto` |
| Bypass permissions | Asks far less. It still asks for actions that no mode approves, some safety checks and some desktop actions. | `bypassPermissions` |

The official docs say to use Bypass permissions only in sandboxed containers or virtual machines. This kit does not turn it on. Do not use it on your own computer.

This kit starts in **Accept edits**: file changes in your project go through, and commands still ask. Choose **Manual** if you want to approve every change; the tutor then shows you each one before it happens. Do not use Auto or Bypass permissions in your first weeks.

Where to change the mode:

- Desktop app: use the mode selector next to the send button. The mode you pick stays for that folder. Plan applies only to the current session.
- Terminal: press **Shift+Tab** to move to the next mode. The order is Manual, then Accept edits, then Plan. Some plans show more modes.

The file `settings.json` has a line `permissions.defaultMode`. It sets the mode when a new local session starts. A mode you pick in the Desktop selector is remembered for that folder. It wins over `defaultMode` for that folder. Plan is the exception: it lasts only for the current session. [settings.json.explained.md](../settings.json.explained.md) explains the rest of the file.
