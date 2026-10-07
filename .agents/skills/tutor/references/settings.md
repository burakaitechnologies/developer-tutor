# Settings reference for the tutor skill

What this is: the keys in `.tutor/learner/profile.md` and what each one changes.
When to read it: when the learner asks to change how you teach and the change should last.

## How to change a key

1. Read the profile file. The keys sit between the two `---` lines, one `key: value` per line.
2. Edit one line with apply_patch. Use exactly the words in the "Allowed values" column, and at most 40 characters.
3. Keep every other line. Do not copy the comment block of the template.
4. Nothing checks the value for you in this edition. Check the spelling before you save.
5. Say in one line what changed and that it starts with your next answer.

## The keys

| Key | Allowed values (default) | The learner may say | What it changes |
|---|---|---|---|
| language | a language name (the language of the first message) | "explain in Turkish", "Almanca anlat" | Replies, glosses and labels use this language. Commands, file names and error text stay in English. |
| level | auto, A2, B1, B2, C1 (auto) | "from now on, simpler", "from now on, more detail" | Sentence length and answer length. The numbers are in the Voice part of AGENTS.md. "Simpler" is one step down and "more detail" one step up. Auto counts as B1. Only a lasting request ("from now on", "always") is saved here. "Simpler words" alone is plain talk for this session. |
| teaching | normal, light, off (normal) | "only explain new words" is light; "stop teaching me, for good" is off; "teach me again" is normal | light: glosses stay, checks, offers and reviews go. off: no lessons at all. The change summary, risk heads-ups and safety stops stay. The progress skill names the setting when it is off or light. |
| comments | teaching, normal, minimal (teaching) | "fewer comments", "explain in the code" | How many comments you write in new code files. Comments in existing files are never changed. |
| learn_first | domain ids, comma separated (empty) | "teach me git first" | Offers prefer these domains. Use the domain ids from the third field of the lines in `.agents/tutor/knowledge/concepts-index.txt`, for example `git` or `web`. Set it only when the learner says what they want first. |
| call_me | a first name, letters and spaces, 30 characters (empty) | "call me Ada" | Used in greetings. It stays in this private file and never goes into committed files. |
| onboarded | yes, no | the learner never sets it | tutor-setup writes it. |

## Changes for one session only (no file edit)

- "Quiet mode", "no lessons": explanations stop for this session. The result, the safety lines and the save-point question stay. Glosses, checks, offers and reviews go. "Teach me again" brings them back.
- "Just do it", "skip this": this request and the next two turns, without glosses, checks, offers or optional questions. The change summary and safety text stay. A yes before anything hard to undo, and the save point before a risky change, still come first. Quiet mode is not permission.
- "Simpler words", "my English is basic" (plain talk): shorter sentences and one level lower for the rest of the session.

## Labels by language

Use the labels of the learner's language. They are the words the learner sees at the start of a check or an offer. For a language not listed, translate them closely.

| Language | Check labels | Offer label |
|---|---|---|
| English | `Check:` `Predict:` `Your move:` | `Next I can teach:` |
| Turkish | `Kontrol:` `Tahmin:` `Sıra sende:` | `Sıradaki konular:` |
| Spanish | `Comprueba:` `Predice:` `Tu turno:` | `Siguientes temas:` |
| German | `Prüfe:` `Vorhersage:` `Du bist dran:` | `Als Nächstes kann ich erklären:` |
| French | `Vérifie :` `Prédis :` `À toi :` | `Prochains sujets :` |
