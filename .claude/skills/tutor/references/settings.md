# Settings reference for the tutor skill

What this is: the keys in `.claude/agent-memory/tutor-data/learner/profile.md` and what each one changes.
When to read it: when the learner asks to change how you teach and the change should last.

## How to change a key

1. Read the profile file. The keys sit between the two `---` lines, one `key: value` per line.
2. Edit one line with the Edit tool. Use exactly the words in the "Allowed values" column and at most 40 characters.
3. Keep every other line. Do not copy the comment block of the template.
4. An unknown value is rejected, and a warning appears at the next session start. Check the spelling before you save.
5. Say in one line what changed and that it starts with your next answer.

## The keys

| Key | Allowed values (default) | The learner may say | What it changes |
|---|---|---|---|
| language | a language name (the language of the first message) | "explain in Turkish", "Almanca anlat" | Replies, glosses and labels use this language. Commands, file names and error text stay in English. |
| level | auto, A2, B1, B2, C1 (auto) | "from now on, simpler", "from now on, more detail" | Sentence length and answer length. The numbers are in the Voice part of `.claude/output-styles/tutor.md`. "Simpler" is one step down and "more detail" one step up; auto counts as B1. Only a lasting request ("from now on", "always") is saved here. "Simpler words" alone is plain talk for this session. |
| teaching | normal, light, off (normal) | "only explain new words" is light; "stop teaching me, for good" is off; "teach me again" is normal | light: glosses only, no checks or reviews. off: no lessons at all. The change summary, risk heads-ups and safety stops stay. The progress skill notes that teaching is off. |
| comments | teaching, normal, minimal (teaching) | "fewer comments", "explain in the code" | How many comments Claude writes in files it creates. Comments in existing files are never changed. |
| tree | session, off (session) | "do not list my files" | Whether the session start shows the file list. Off hides it. |
| learn_first | domains, comma separated (empty) | "teach me git first" | Offers prefer these domains: term, files, git, gh, cc, prog, web, data, test, sec, arch, proj, ai. Set it only when the learner says what they want first. |
| answer_words | a number from 20 to 400 (empty) | "keep answers under 80 words" | Replaces the level's limit for the result part. Checks and explanations of new words stay. |
| chat_copy | off, on (off) | "save our conversation" | On: a copy of what the learner types, with secrets hidden, goes to `.claude/agent-memory/tutor-data/chat/` for 30 days. It needs the helper scripts. |
| call_me | a first name, letters and spaces, 30 characters (empty) | "call me Ada" | Used in greetings. It stays in this private file and never goes into committed files. |
| onboarded | yes, no | the learner never sets it | tutor-setup writes it. |

## Before you turn chat copy on

Say this first, in the learner's language: "I will keep a copy of what you type for 30 days. Keys and passwords are hidden in it. It stays in a private folder on this computer. Everything you type also goes to Anthropic. Claude Code keeps its own history, whatever I save." To delete the copies, the learner runs `python3 .claude/tools/doctor.py wipe chat` in their own terminal. On Desktop, that is the Terminal button in the session title bar (local sessions only). The safety guard asks before it runs.

## Labels by language

Use the labels of the learner's language. They are the same ones the helper scripts look for. For a language not listed, translate them closely.

| Language | Check labels | Offer label |
|---|---|---|
| English | `Check:` `Predict:` `Your move:` | `Next I can teach:` |
| Turkish | `Kontrol:` `Tahmin:` `Sıra sende:` | `Sıradaki konular:` |
| Spanish | `Comprueba:` `Predice:` `Tu turno:` | `Siguientes temas:` |
| German | `Prüfe:` `Vorhersage:` `Du bist dran:` | `Als Nächstes kann ich erklären:` |
| French | `Vérifie :` `Prédis :` `À toi :` | `Prochains sujets :` |

## Changes for one session only (no file edit)

- "Quiet mode", "no lessons": explanations stop for this session. The result, the safety lines and the save-point question stay; glosses, checks, offers and reviews go. "Teach me again" brings them back.
- "Just do it", "skip this": this request and the next two turns, without glosses, checks, offers or optional questions. The change summary and safety text stay. A yes before anything hard to undo, and the save point before a risky change, still come first. Quiet mode is not permission.
- "Simpler words", "my English is basic" (plain talk): shorter sentences and one level lower for the rest of the session.

## Helper scripts off, without Python

If the learner cannot run Python, the kill switch works without it. The learner saves a file named `settings.local.json` inside the `.claude` folder with exactly this content: {"disableAllHooks": true}. Only the learner creates it; the safety guard asks before anyone else edits that file. To turn the scripts on again, the learner deletes the file.

Steps to show, by system:
- Windows: open Notepad, type the line, choose File, Save As. Set Save as type to All files. Type the name settings.local.json without quote marks, because Windows does not allow them in a file name. Choose the `.claude` folder of the project. The All files choice stops Windows from adding `.txt`.
- macOS: the `.claude` folder is hidden; press Cmd+Shift+period in Finder to show it. In TextEdit choose Format, Make Plain Text, then save into that folder. If the name ends in `.txt`, rename it.
- Check the result: the file name must end in `.json`, not `.json.txt`.
