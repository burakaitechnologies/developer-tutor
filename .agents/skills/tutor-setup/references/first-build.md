# First build and first learner step

What this is: what to build first, how to tell the learner where it is, and which step the learner does alone.
When to read it: step 5 of tutor-setup, before you write the first file.

## Three starter ideas (when the learner is unsure)

Fit them to what the learner told you. Each runs by opening one file, needs no install, no account and no real personal data.
1. A one-page web page about something they like or do: a hobby, a small business, a family recipe.
2. A one-page tool for a calculation they do by hand: a tip, a price with tax, a unit change.
3. An editable list page: books to read, places to visit, tasks for the week.

## First build by goal (always the smallest version, no design gate)

| Goal | First file | The learner sees |
|---|---|---|
| web page, menu, portfolio | `index.html` with the CSS inside | the page |
| calculator, converter, checklist | `index.html` with a few lines of JavaScript | the tool, with made-up numbers |
| game | `index.html` with a canvas | one shape that moves with one key |
| data clean-up, report | a small script and a made-up sample file, only if the Python check in tutor-setup step 1 passes; otherwise a page that shows the idea | printed or shown result |
| shop, booking, login, database, app with users | `index.html` with the main screen and made-up data | the shape only; say the design gate comes before the second step |
| bot, automation | a script that only prints what it would do, with made-up data | the printed plan |

Rules: no dependency, no network, no real names, e-mails or numbers. The file name states its purpose. Comments follow `comments:` in the profile. In the Change card, write `none` for packages or network only when no install or network command ran in this turn; otherwise name what ran.

## The answer that shows the first build

Four lines, nothing else. The result is about 100 words, so keep it short.

```
Done: I created index.html in <folder path>. It is a web page about <goal>. <One gloss: the word the learner will meet again, in one sentence.>
To see it, <open step for the surface>. You should see the heading "<heading>". The browser tab title is a separate change for later.
Your move: <the learner step from the table below>.
Change card: created 1 (<full path of index.html>), changed 0, deleted 0; new packages: none; network: none; check it with: <how to open it>.
```

The permission sentence (sample 3) is not part of this answer. It comes before the first step that may show a box (tutor-setup step 4).

Open step, by surface:
- App: open the file from the folder shown in Done, in File Explorer (Windows) or Finder (macOS). Do not send the learner to the app's review pane for this: the review pane needs a project inside a Git repository (checked 2026-10-08), and the first build is usually not in one yet.
- CLI (terminal): give the learner the full path from the Done line. They open the file from that folder in File Explorer or Finder.
- IDE extension: open the file from the editor's file list, or open it from the folder in File Explorer or Finder.

In every case, check that the folder the learner sees matches your Done line. If it shows another folder, say so before the learner edits anything.

## The learner step (the `Your move:` line)

Take the first row that fits.

| Situation | Step |
|---|---|
| App or IDE, file is not HTML (script, CSS, text) | Open the file in a text editor, change one word or number, save, then run it or reload it. |
| Windows, HTML file | In File Explorer right-click the file, choose Open with, then Notepad (or Choose another app, then Notepad). Change the heading, save with Ctrl+S, reload the page with F5, and say what changed. |
| The learner has a code editor | Open the file in it, change the heading, save, reload, say what changed. |
| Mac or Linux without an editor, or any learner who is afraid to edit | A read-only command. App: New tab, then Terminal, or Ctrl+backtick (local chats only). CLI: type `!` before the command. IDE: the terminal of the IDE window. Command: `ls` on macOS and Linux, `dir` on Windows. Say which file names you see. |

Why a command comes last: a terminal is new for many beginners. Editing one word needs only the file.

## After the learner reports

- Name what they did in one sentence: "You changed the heading yourself and saw the page change. That is the whole cycle: edit, save, check."
- "Ok" is not a report. Ask what they see, once.
- If it did not work, use hints H1 to H5 from `.agents/skills/learn/references/playbook.md`. Do not do the step for them unless they ask.
