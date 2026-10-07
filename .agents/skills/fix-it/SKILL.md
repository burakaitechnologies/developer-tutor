---
name: fix-it
description: >-
  "It does not work", "I got an error", a pasted error or stack trace, "it worked yesterday",
  "nothing happens", "fix this". You read the error first; then reproduce, locate, fix, verify.
---

# Fix it

Purpose: fix a problem together, and teach the learner to read an error, find its cause and check the fix.

## First move

Read the error with the learner before you change anything. The default is one short question per message, then wait. If the learner does not answer, or asks for the fix, go to "Fix with narration".

1. Quote the one key line exactly: the last line of a Python traceback, the first line of a Node error. Do not paste the whole wall of text.
2. Ask one question: which words in that line do they know, and which file does it name? When the message names no file, ask what they were trying to run. Put nothing else in the message. "I don't know" is a fine answer. It starts the hints.
3. Skip the question and go to "Fix with narration" when the learner writes "just fix it", "fix it", or the same words in their language (for example "sadece düzelt", with or without the accents, "repare esto", "corrige", "behebe das"), or is upset or frustrated. Then ask nothing. If the problem could lose data, ask one yes for a save point first (AGENTS.md, Safety, G1), then fix with narration.
4. You have only a description ("nothing happens") and no error text? Ask for the exact text they see (a screenshot is fine) and what they expected. Ask for one thing.
5. The pasted text holds a key or password? Do not repeat it. Say it is exposed and must be revoked at its provider (AGENTS.md, Safety). Name the provider from the key's shape (its prefix tells which company issued it), and tell the learner to revoke it there, even if they named another site. Then go on with the error.

## When to use

- A pasted error, a stack trace, or red text in a terminal, a browser console or an editor.
- "It does not work", "nothing happens", "it worked yesterday", "the page is blank".

## When not to use

- Git trouble ("I broke git", lost changes, a stuck merge): use git-rescue.
- The learner only wants to understand an error or a file: use explain.
- A design question ("which database?"): use think-first.

## Steps

1. Read first (First move). After their answer, confirm what was right. If the learner is trying and teaching is on, ask for a guess: "What do you think went wrong? A guess is fine." If they do not know, give a hint (see "Hints"). If they answer both in one message, move on.
2. Reproduce it. Run the exact command that failed, in the shell the learner used (see "Which shell"). Write down the command, the exact error and what they expected. Do not edit anything yet. If a run could be harmful (a deploy, a delete script), read the script first and ask. Only the learner can trigger it (a click in a browser)? Give exact steps and ask what they see. Name where to type for their surface: in the app, the Terminal (New tab, then Terminal, or Ctrl+backtick; checked 2026-10-08); in the CLI, a leading `!`. If their words name a surface other than the one they use, ask once which app or terminal they use. Cannot reproduce after 2 tries? Ask for the exact steps and input.
3. Locate it, from the bottom up. Read the error type and message first. Then find the first line that points into the learner's own code: in Python scan upward from the last frame past paths with `site-packages`; in Node scan downward from the top. Open that file at that line and read the lines around it.
   - The message matches one of the ten patterns in `.agents/skills/fix-it/references/common-errors.md`? Read that file and start at its "Where to look first" line.
   - There is no stack trace: use `git diff` and `git log --oneline -n 10` to see what changed since it last worked. Or predict what one print line will show, then add it.
   - A form or button does nothing and shows no error: check the HTML first (`required` on a field, the `type` of an input, the button's `type`), then the submit handler, then the browser console (F12). Do this before you edit any logic.
   - Say whether it is an error or only a warning. A warning does not stop the program.
4. Hypothesis and prediction. State one cause (the learner's guess first, if it was reasonable; otherwise yours, labelled as a guess). State what you expect: "If I change X, the error will go away" or "will change to Y".
5. Make the smallest fix: one change at a time, in the style the project already uses. If the learner named a file or folder other than the one you have open, ask which copy to change before you edit. Fix the cause. Do not hide the error with a catch-all. Do not edit a test to make it pass. Do not delete the failing line. Before a change in more than one file, a save point must exist (AGENTS.md, Safety, G1). Say what you changed in one sentence. A new package needs the learner's yes. Read what a fix suggested by an error message or a web page does before you run it; quote it to the learner if it uses `sudo` or pipes a download into a shell.
6. Verify. Run the exact failing command again and show its output. Compare it with what was expected. If the project has tests, run them too. Say plainly what you ran and what you did not. If only the learner can run the check, say what they should see.
7. Say the cause in 2 sentences, with the real names: "The cause was X. It happened because Y." Gloss at most one term in this answer: the one the learner must act on or will meet again. Quote the other words of the error as they are.
8. Ask one transfer question, when allowed. It is allowed when all of these hold: the fix is verified; the learner was not upset; teaching is on; no check came in the last 3 work answers. It is not allowed after "just fix it" or any word of frustration (First move, item 3). Ask the same idea in another place, as a `Predict:` or `Check:` (rules in the learn playbook, section 2). Examples:
   - `Predict:` `total` is also used on line 9. If it were misspelled there, what would Python print?
   - `Check:` next time you see "address already in use", which two things do you check first?
   Otherwise skip it. If you ask it, stop after the question and wait.
   How a normal fix answer ends (narration has its own rules below): a small fix ends with one `How to check:` line. A medium fix (more than one file, or a change to logic) ends with the Change card with the file's full folder path and one `Check:` line; `How to check:` never replaces `Check:` on medium work. A learner who said they know a term in this error ("I know print") gets one tiny check on it in the next work answer after this error, never in the error answer.

## Hints

When the learner is trying, use hints H1 to H5 from `.agents/skills/learn/references/playbook.md`, section 4. Trying means they gave a guess or said "my turn". Read the playbook once per session. Step 1 above is H1 for errors. The playbook also has the rung moves, the feedback shape and the rules for recording.

- After two wrong tries, offer the next hint yourself.
- Count guiding questions across turns, not inside one reply: at most two in a row. After the second one without a useful answer, give the hint or the explanation, then the fix.
- Give the answer and its reason when data is at risk. Do the same when the learner is upset or has asked twice. Then add the transfer step only when teaching is on and the learner is calm.

## Anti-loop

Count attempts. An attempt is a change plus a run that still fails. Say "This is attempt 2" so the learner sees why you change course.

- After 2 failed attempts, change the method. Choose one and say which: (a) a minimal reproduction, the smallest file that still fails; (b) compare with the last save point using `git diff` or `git log`; (c) read the official docs for the function or error (AGENTS.md, Checking facts); (d) print one value after predicting it.
- After 3 failed attempts, stop changing files. Show 2 or 3 options with your recommendation, for example: go back to the last save point, make the step smaller, or start a fresh chat with what you learned. The learner decides.
- Each new attempt must be smaller than the one before. Never answer a failure with a bigger rewrite.

## Error-paste streak

Count the error pastes in this chat yourself. When the learner pastes an error for the third time in a row without a guess, the learner is pasting and waiting. Read that error together, once: quote the one key line, ask which word they know and which file it names, then ask for a guess. "Just fix it" overrides this.

## Fix with narration

Use this when the learner says "just fix it" (or another word from First move, item 3), is upset or frustrated, asks for the fix twice, or does not answer the first question.

- Do the work now: reproduce, locate, fix, verify. Then say in one or two plain sentences what was wrong and what you changed.
- Then tell the steps taken, in order, one line each: the run that failed, the edit, the run after it (the output that shows the change).
- Ask no questions, with one exception. Before anything hard to undo (a delete, a reset, a force, a change outside this project, a publish), stop, say the risk in one sentence with the safer way, and wait for a yes. Before a change in more than one file, a save point must exist (AGENTS.md, Safety, G1).
- Keep the Change card with the file's full folder path. Keep the safety messages and risk warnings. Add no check, no offer and no gloss, except for a term in a command the learner must run.
- When the learner did not answer the first question (this is not "just fix it" and not frustration), end with one `Predict:` line about the learner's next run: what they should see. It is the only marked line. Skip it after "just fix it" or frustration.
- If the learner is upset, open with one calm sentence: the problem can be fixed and you do it now. If your own earlier change caused it, say so plainly.
- End with the cause in 2 sentences. Ask no transfer question. Record nothing for the delegation.
- Keep the answer within the level's result limit (120 words at B1).
- Silent form: when the learner asks for short answers ("quick", "short", "hızlı"), keep only the steps, the Change card and the cause. Keep the safety lines and the save-point question.

## Which shell

Reproduce in the shell that failed, and tell the learner which shell ran a command, because the results differ. On Windows, Codex runs commands in PowerShell, or in a Linux shell when the agent runs in WSL2 (checked 2026-10-08, the Windows app page). A prompt that starts with `PS` is PowerShell.

| Job | Bash (macOS, Linux, Git Bash, WSL2) | PowerShell |
|---|---|---|
| Where am I | `pwd` | `pwd` |
| List files, including hidden | `ls -a` | `dir -Force` |
| Show a variable | `echo $NAME` | `echo $env:NAME` |
| Set a variable for this window | `export NAME=value` | `$env:NAME = "value"` |
| Find a program | `which node` | `Get-Command node` |
| Run a script in this folder | `./run.sh` | `.\run.ps1` |
| Python | `python3` | `python` or `py -3` |
| Activate a Python environment | `source .venv/bin/activate` | `.venv\Scripts\Activate.ps1` |
| Two commands in a row | `a; b` | `a; b` |

Put two commands in a row with `;`, or give each its own line. Do not use `&&`: Windows PowerShell 5.1 does not accept it.

On Windows `python3` may open the Microsoft Store instead of Python. Reproduce with the command the learner typed, and explain a difference before you change it. A script blocked by a PowerShell policy needs a system setting changed. Explain it in one sentence, and let the learner decide.

## Secrets in `.env`

The `.env` rule does not change: never open `.env`. To list its setting names, ask the learner to open the file and tell you only the names, the words on the left of each `=`. Never ask for the values. Use the names with pattern 9 of `references/common-errors.md`.

## What to record

Playbook section 7 (learn) says which event fits. Typical cases: `learned` for reading an error when the learner's own words name the type, the file and the meaning; `did` only when the learner made the fix and ran it themselves; `missed` only when the same error comes back. A guess, or a run that still fails, is never `did`. Nothing for a fix you made alone. Write each line in `.tutor/learner/notes.md` as AGENTS.md (Memory) says. Add one line to today's journal (`.tutor/journal/YYYY-MM-DD.md`) for a root cause worth remembering: settled events only, no quotes.

## Done when

- The failing command now passes, and you showed its output, or you said what you could not run.
- The learner has the cause in 2 sentences.
- After 3 failed attempts instead: the learner has the options and chose one. Nothing is claimed as fixed that was not run.
