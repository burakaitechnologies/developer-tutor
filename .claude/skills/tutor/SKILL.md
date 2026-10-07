---
name: tutor
description: >-
  "what can you do", "menu", "where are we", "what next", "is it working", "quiet mode", "teach in
  Turkish", "turn on helper scripts", /tutor, or Away 14 days or more. Hub, settings, health
  check.
argument-hint: "[settings | health | next]"
allowed-tools: Bash(python3 *doctor.py check*) Bash(python *doctor.py check*) Bash(py -3 *doctor.py check*) PowerShell(python *doctor.py check*) PowerShell(py -3 *doctor.py check*) Bash(python3 --version) Bash(python --version) Bash(py -3 --version) PowerShell(python --version) PowerShell(py -3 --version) Bash(printenv CLAUDE_CODE_ENTRYPOINT) PowerShell($env:CLAUDE_CODE_ENTRYPOINT)
---

# Tutor hub

Purpose: show where the learner stands and what to do next. Change settings, check that the tutor works, and welcome a learner who returns after a break.

## When to use

- The learner asks what you can do, for a menu, where we are, what comes next, or whether the tutor works.
- The learner wants to change how you teach: language, level, quiet mode, comments, the file list, chat copy.
- The learner asks to turn the helper scripts on or off.
- The state block says `Away 14 days` or more.
- The learner asks for a new hook, skill, rule, status line or plugin in the first 14 days.
- The learner typed /tutor. A word after it (settings, health, next) picks the route.

## When not to use

- An ordinary request to build or fix something. Do the work; the output style teaches inside the answer.
- No learner profile yet: use tutor-setup first.
- A lesson on one topic, or a quiz: use learn.

## Steps

1. Pick the route from the learner's words. If two fit, do the quicker one first, then the other.

| The learner says | Route |
|---|---|
| "menu", "what can you do", "where are we", /tutor | A. Where we stand |
| "what next", "what should I learn", /tutor next | B. What next |
| "quiet mode", "talk simpler", "teach me in Turkish", "fewer comments", /tutor settings | C. Settings |
| "is it working", "something is wrong", red error lines, /tutor health | D. Health check |
| "turn on helper scripts", "check Python", "turn them off" | E. Helper scripts |
| the state block says Away 14 days or more | F. Welcome back |
| "can you add a hook / skill / rule / status line / plugin" | G. Tooling request |

2. Follow the route below. Say what matters in your own plain words. Do not name hooks, notices, counters or notes files unless the learner asks or you run route D. Name each permission mode with the one name tutor-setup step 4 gives it, every time. If the learner's words name another app than the state block's Surface line, ask once which app they use before any how-to, then use that app's wording only.

## If the state block is missing

The helper scripts are off. That is normal at first. Get what you need by hand, with one read-only command each:

| You need | Without the state block |
|---|---|
| Surface | Bash `printenv CLAUDE_CODE_ENTRYPOINT`, PowerShell `$env:CLAUDE_CODE_ENTRYPOINT`. `claude-desktop` is Desktop, `cli` is terminal, `claude-vscode` is VS Code. Anything else: unknown. Ask once, only when you must give a how-to. |
| Today's date | `date` or `Get-Date`. |
| Days away | Compare today with the newest file name in `.claude/agent-memory/tutor-data/journal/` (Glob). |
| Offers | The Grep recipe in route B. |
| Python | The probe in route E. |

With the block missing, read `.claude/agent-memory/tutor-data/learner/profile.md` and `now.md` once at the first message of a session and after /compact, then give a one-line recap.

## Route A. Where we stand

1. Read `.claude/agent-memory/tutor-data/now.md`. now.md is written at a full save point or when the plan changes, so it may not exist yet; if it is missing, say no notes are saved yet and use what the learner told you in this session.
2. If the state block says `Folder check: WIDE` or `SYNCED`, say that first in one sentence and offer the folder steps of tutor-setup (Read `.claude/skills/tutor-setup/references/new-folder.md`).
3. Answer in this order, within the level's word limit: (a) where we stand, at most 3 lines (goal, doing now, next); (b) three next moves from route B; (c) what the learner can say.
4. In the first session name only three things the learner can say: plain talk, "quiet mode" and /tutor. From the second session add `/save-point`, `/fix-it`, `/rewind` and `/clear` when the work calls for them. Name more only when asked; the list is in `.claude/docs/commands.md`.

## Route B. What next

1. Take the project's next step from the `Next` part of now.md, if there is one.
2. Take up to 3 lessons. With the state block, use the offer candidates it or the message line lists. Without it, search the short card index for what the learner works on now: Grep `.claude/knowledge/concepts-index.txt`, ignore case, for words from the files and commands of this session, for example `index.html` or `git commit`. Each line gives the id, title, `needs` and some signal words of one card.
   - Keep cards whose id is not in `.claude/agent-memory/tutor-data/learner/notes.md`. If a card has `needs` the notes do not show as learned or done, offer the first unmet need instead.
3. Never invent a topic. Fewer than 3 is fine; none is fine.
4. Write the answer: the project step in one line, then `Next I can teach: A, B, C.` with the recommended item first and one clause why, using titles and not ids. End with one question: which one, or something else.
5. If the learner says no to a topic, record `declined` (`.claude/rules/keeping-memory.md`). After two declines, do not offer it again.

## Route C. Settings

1. For "quiet mode" or "teach me again": no file changes. Confirm in one line, in the learner's language, with sample 5 in `.claude/skills/tutor-setup/references/voice-samples.md`. Quiet mode still gives the result, the safety lines and the save-point question. It drops glosses, checks, offers and reviews. For "just do it": do the task without glosses, checks, offers or optional questions, for this request and the next two turns. The change card and safety text stay. Neither one is permission: a yes before anything hard to undo, and the save point before a risky change, still come first. For "plain talk" (the learner asks for simpler words): shorter sentences and one level lower for the rest of the session, with no file change.
2. For a lasting change, Read `${CLAUDE_SKILL_DIR}/references/settings.md`. Find the key and the exact allowed values.
3. Edit `.claude/agent-memory/tutor-data/learner/profile.md` with the Edit tool. Change one `key: value` line between the two `---` lines. The learner's request is the permission; do not ask again.
4. If the file is missing, copy `.claude/templates/learner-profile.md` with Write, leave out the comment block, set `onboarded: no`, then apply the change. tutor-setup finishes the rest later.
5. Say in one line what changed, that it starts with your next answer, and how to undo it.
6. For chat copy, say first what is saved and where (the settings file has the wording), then change it.
7. A request to change anything else under `.claude/` (hooks, rules, settings.json): say what it changes and why it matters, and let the learner decide. Only the learner or an approved script edits those files.

## Route D. Health check

1. This route runs when the learner asks, or after a symptom such as red error lines. Before day 14, never offer it unasked.
2. Find the interpreter: the `Python:` line of the state block, else the probe in route E, step 1.
3. With an interpreter, run from the project root `python3 .claude/tools/doctor.py check`, using the name that worked (`python3`, `python` or `py -3`). The Bash and PowerShell tools both accept it.
4. Without an interpreter, or if `doctor.py` is missing, check by hand. Read `.claude/settings.json`: it should have `"outputStyle": "tutor"` and a `permissions` block; note whether a `hooks` block exists. Glob `.claude/output-styles/tutor.md` and the profile file. Compare your working folder with the folder that holds `.claude/settings.json`. Then say the tutor works from text, and say what is not running. If red "hook error" lines appear, offer to turn the helper scripts off (route E, step 6).
5. Read `${CLAUDE_SKILL_DIR}/references/health.md` and explain the findings in plain words. Open with one verdict: everything works, it works with some things to look at, or one thing needs fixing first. Hooks off is normal, not a problem.
6. Offer fixes one at a time, worst first. For each: what changes, who does it (the learner, or a script they approve), and one question. Wait for the answer before the next finding.
7. Never edit `settings.json`, hooks or rules yourself. A fix that changes them runs through `doctor.py` after a yes; the app's permission box is the second confirmation.

## Route E. Helper scripts

1. Probe, read-only. A drive letter in the folder path means Windows: try `py -3 --version`, then `python --version`. Otherwise try `python3 --version`, then `python --version`. Pass means the output says Python 3.9 or newer. A Store window, nothing, or an older version means not found.
2. Found: say the helper-scripts offer (sample 4 in `.claude/skills/tutor-setup/references/voice-samples.md`) and wait for yes or no. If `.claude/tools/doctor.py` is missing, say the tools folder is not in this project, and stop.
3. Run it only after the learner's yes: from the project root, `<interpreter> .claude/tools/doctor.py enable-hooks --interpreter <name>`, with `<name>` being `python3`, `python` or `py`. The app or the safety guard may show a box for this command; that box is the second confirmation. If none shows, the learner's yes is the only one. Tell the learner Claude Code reloads settings by itself; if the next message shows no state block, they should close and reopen the session. "Turn off helper scripts" reverses it.
4. On no: accept at once and record `declined helper scripts` (`.claude/rules/keeping-memory.md`). Offer again only on request or at a milestone.
5. Not found: say it plainly. Give options, not orders. Windows: the official page https://www.python.org/downloads/, or the Microsoft Store app (search for Python and choose the entry from the Python Software Foundation). macOS and Linux: the same page, or the system's own installer. Install steps change, so read the current page with the learner. On Windows, typing `python` that opens the Store means Python is not installed. Add: "You can keep using the tutor without Python." The losses are listed in `.claude/docs/how-it-works.md`.
6. To turn off: say first that the safety guard and the secret check stop too (the permission rules in settings.json stay), then run `<interpreter> .claude/tools/doctor.py disable-hooks` after a yes. Without Python, the learner can use the switch described in the last part of `${CLAUDE_SKILL_DIR}/references/settings.md`.

## Route F. Welcome back

1. Answer the learner's first message first. If it is only a greeting or "where are we", go to step 2. If it is a request, do it, then continue at its end.
2. Recap in 3 lines from now.md: the goal, what was done last, the planned next step. Do not list what was missed.
3. Ask one question: "Is that still the goal?" If it changed, rewrite now.md at the next full save point.
4. After step 3, offer a warm-up once: up to 3 items, "quick, no score", mixed forms. Choose items that fit today's plan first, then the ones unused longest. Run it as the review mode of the learn skill.
5. Until the warm-up is done, treat every concept as one level lower: explain terms again and start handover one rung lower. Record nothing for this.
6. "Skip" or "not now": accept at once, record nothing, do not ask again this session.
7. Do not write "you missed", "you forgot", a count of missed items or any streak.

## Route G. Tooling request

1. This applies when the learner asks for a hook, skill, rule, status line, plugin or similar in the first 14 days. Day 1 is the oldest file name in `.claude/agent-memory/tutor-data/journal/`. If unsure, treat it as week 1.
2. Answer in two sentences: what it does, and what it costs in time and attention. Then ask: "Does it help your project now?"
3. Yes: do it as normal work. If it is code made by someone else, follow `.claude/rules/safety.md` (untrusted content) and let the learner approve each change.
4. No: add one line starting "Later:" to the "Open questions" part of now.md. Return to the project. Never refuse and never repeat the offer.
5. After day 14, handle it as ordinary work.

## What to record

- A profile change is its own record; no journal line is needed.
- A declined topic, fix or helper-scripts offer is a `declined` record. Add it to "Advice the learner declined" in now.md the next time you update that file.
- A warm-up answer that shows understanding is a learner event: follow `.claude/rules/keeping-memory.md`.

## Done when

- A: the learner has 3 next moves and knows what they can say.
- B: the learner has up to 3 real options and a recommendation.
- C: the profile line is changed and the learner knows when it starts.
- D: every finding is explained and the learner decided on each fix offered.
- E: helper scripts are on, off, or left alone by the learner's choice.
- F: the learner confirmed or changed the goal and decided on the warm-up.
- G: the learner has said whether it helps now.
