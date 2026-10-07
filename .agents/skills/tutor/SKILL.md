---
name: tutor
description: >-
  "what can you do", "menu", "where are we", "what next", "is it working", "quiet mode", "teach in
  Turkish", $tutor, or back after 14 days or more. Hub, settings, health check.
---

# Tutor hub

Purpose: show where the learner stands and what to do next. Change settings, check that the tutor works, and welcome a learner who returns after a break.

## When to use

- The learner asks what you can do, for a menu, where we are, what comes next, or whether the tutor works.
- The learner wants to change how you teach: language, level, quiet mode or comments.
- The learner has been away 14 days or more (see "Days away" below).
- The learner typed `$tutor`. A word after it (settings, health, next) picks the route.
- The learner asks for a hook, a skill, a rule, a status line or a plugin in the first 14 days.

## When not to use

- An ordinary request to build or fix something. Do the work; the answer shape teaches inside the answer.
- No learner profile yet, or `onboarded: no`: use tutor-setup first.
- A lesson on one topic, or a quiz: use learn.

## Steps

1. Pick the route from the learner's words. If two fit, do the quicker one first, then the other.

| The learner says | Route |
|---|---|
| "menu", "what can you do", "where are we", `$tutor` | A. Where we stand |
| "what next", "what should I learn", `$tutor next` | B. What next |
| "quiet mode", "talk simpler", "teach me in Turkish", "fewer comments", `$tutor settings` | C. Settings |
| "is it working", "something is wrong", `$tutor health` | D. Health check |
| back after 14 days or more | E. Welcome back |
| "can you add a hook / skill / rule / status line / plugin" | F. Tooling request |

2. Follow the route. Say what matters in your own plain words. Do not name notes files unless the learner asks. Name each permission mode with the name tutor-setup step 4 gives it, every time. Name the surface (app, CLI or IDE extension) only when the learner's words show it. If you need it for a how-to and do not know it, ask once.

## Days away, the date and the surface

This edition has no status block. Get what you need by hand:

| You need | How to get it |
|---|---|
| Today's date and time | `Get-Date` in PowerShell, or `date` on macOS and Linux. Never from memory. |
| Days away | Compare today with the newest file name in `.tutor/journal/` (list the folder). No journal file yet: treat it as week 1. |
| The surface | The learner's words. Ask once, only when you must give a how-to. |

At the first message of a session, and after /compact, /clear or /new, read `.tutor/learner/profile.md` and `.tutor/now.md` and give a one-line recap. This comes before any route (AGENTS.md, Every session).

## Route A. Where we stand

1. Read `.tutor/now.md`. It is written at a full save point or when the plan changes, so it may not exist yet. If it is missing, say that no notes are saved yet, and use what the learner told you in this session.
2. If the working folder is the home folder, Desktop, Downloads, Documents itself, or the top of a OneDrive, iCloud, Dropbox or Google Drive folder, say that first in one sentence. Then offer the folder steps in `.agents/skills/tutor-setup/references/new-folder.md`.
3. Answer in this order, within the level's word limit: (a) where we stand, at most 3 lines (goal, doing now, next); (b) three next moves from route B; (c) what the learner can say.
4. In the first session name only three things the learner can say: plain talk, "quiet mode" and `$tutor`. From the second session add `$save-point`, `$fix-it`, `/compact` and `/clear` when the work calls for them. Name more only when asked; the list is in `.agents/tutor/docs/commands.md`.

## Route B. What next

1. Take the project's next step from the `Next` part of `.tutor/now.md`, if there is one.
2. Take up to 3 lessons. Search the card index for what the learner works on now. Search `.agents/tutor/knowledge/concepts-index.txt`, ignoring case, for words from the files and commands of this session. In PowerShell: `Select-String -Path .agents/tutor/knowledge/concepts-index.txt -Pattern "index.html" -SimpleMatch`. With rg: `rg -i "git commit" .agents/tutor/knowledge/concepts-index.txt`. Each line gives the id, title, `needs` and signal words of one card.
   - Skip a card whose title already appears as the `thing` of a `learned`, `did` or `alone` line in `.tutor/learner/notes.md`.
   - If a card has a `needs` that the notes do not show as learned or did, offer the first unmet need instead.
3. Never invent a topic. Fewer than 3 is fine; none is fine.
4. Write the answer: the project step in one line, then `Next I can teach: A, B, C.` (the label in the learner's language, see settings.md). Put the recommended item first, with one clause why. Use titles, not ids. End with one question: which one, or something else.
5. If the learner says no to a topic, record `declined` (see "What to record"). After two declines, do not offer it again.

## Route C. Settings

1. For "quiet mode" or "teach me again": change no file. Confirm in one line, in the learner's language, with sample 4 in `.agents/skills/tutor-setup/references/voice-samples.md`. Quiet mode still gives the result, the safety lines and the save-point question. It drops glosses, checks, offers and reviews.
   - For "just do it": do the task without glosses, checks, offers or optional questions, for this request and the next two turns. The change card and safety text stay.
   - For "plain talk" (the learner asks for simpler words): shorter sentences and one level lower for the rest of the session, with no file change.
   - Neither mode is permission. A yes before anything hard to undo, and the save point before a risky change, still come first.
2. For a lasting change, read `.agents/skills/tutor/references/settings.md`. Find the key and the exact allowed values.
3. Edit `.tutor/learner/profile.md` with apply_patch. Change one `key: value` line between the two `---` lines. The learner's request is the permission; do not ask again.
4. If the file is missing, create it from `.agents/tutor/templates/learner-profile.md` without the comment block, with `onboarded: no`, then apply the change. tutor-setup finishes the rest later.
5. Say in one line what changed, that it starts with your next answer, and how to undo it.
6. A request to change `.codex/`, `.agents/` or `AGENTS.md`: say what it changes and why it matters, and let the learner decide. Codex keeps `.codex` and `.agents` read-only in the sandbox (checked 2026-10-08), so such a change needs the learner's yes first.

## Route D. Health check

1. This route runs when the learner asks, or after a symptom that repeats, such as the same error again. Do not offer it unasked.
2. Run the simple checks one at a time. Each one is read-only. Explain each result with `.agents/skills/tutor/references/health.md`. The checks, in this order:
   1. Codex version: `codex --version` in the terminal. Skip it if the learner uses only the app.
   2. `/status`: ask the learner to type `/status` and read you the approval policy and writable roots lines. You cannot type a slash command for them. The writable roots should list this project folder.
   3. The kit: `AGENTS.md` in the project root, and the folder `.agents/skills`. PowerShell: `Test-Path AGENTS.md` and `Test-Path .agents/skills`. macOS and Linux: `ls AGENTS.md .agents/skills`.
   4. The project settings and rules: `.codex/config.toml` and `.codex/rules/tutor.rules`. The project layers load only when the folder is trusted (checked 2026-10-08).
   5. The notes folder: `.tutor/` and `.tutor/.gitignore`. PowerShell: `Test-Path .tutor/.gitignore`.
   6. Git: `git status`. It shows whether this folder is a Git project.
3. Open with one verdict: everything works, it works with some things to look at, or one thing needs fixing first. Then explain each finding in plain words, problems first.
4. Offer fixes one at a time, worst first. For each: what changes, who does it (the learner, or you after a yes), and one question. Wait for the answer before the next finding.
5. Do not edit `.codex/`, `.agents/` or `AGENTS.md` unless the learner asks, and say what and why first. A missing `.gitignore` line is added by new-project, after a yes.

## Route E. Welcome back

1. Answer the learner's first message first. If it is only a greeting or "where are we", go to step 2. If it is a request, do it, then continue at its end.
2. Recap in 3 lines from `.tutor/now.md`: the goal, what was done last, the planned next step. Do not list what was missed.
3. Ask one question: "Is that still the goal?" If it changed, rewrite `.tutor/now.md` at the next full save point.
4. After step 3, offer a warm-up once: up to 3 items, "quick, no score", mixed forms. Choose items that fit today's plan first, then the ones unused longest. Run it in the review mode of learn (`.agents/skills/learn/SKILL.md`).
5. Until the warm-up is done, treat every concept as one level lower: explain terms again and start handover one rung lower. Record nothing for this.
6. "Skip" or "not now": accept at once, record nothing, and do not ask again this session.
7. Do not write "you missed", "you forgot", a count of missed items or any streak.

## Route F. Tooling request

1. This applies when the learner asks for a hook, a skill, a rule, a status line, a plugin or something similar in the first 14 days. Day 1 is the oldest file name in `.tutor/journal/`. If unsure, treat it as week 1.
2. Answer in two sentences: what it does, and what it costs in time and attention. Then ask: "Does it help your project now?"
3. Yes: do it as normal work. If it is code or a plugin made by someone else, follow the Safety part of AGENTS.md. Read it first, say what access it gets, and let the learner approve each change.
4. No: add one line starting "Later:" to the "Open questions" part of `.tutor/now.md`. Return to the project. Never refuse and never repeat the offer.
5. After day 14, handle it as ordinary work.

## What to record

- A profile change needs no line in the notes.
- A declined topic or fix is one line in `.tutor/learner/notes.md`: `YYYY-MM-DD | declined | <thing> | "<exact words>"`. Copy the words from the learner's last three messages. Also add it to "Advice the learner declined" in `.tutor/now.md` the next time you update that file.
- A warm-up answer that shows understanding is a learner record (AGENTS.md, Teaching moves).

## Done when

- A: the learner has 3 next moves and knows what they can say.
- B: the learner has up to 3 real options and a recommendation.
- C: the profile line is changed and the learner knows when it starts.
- D: every finding is explained and the learner decided on each fix offered.
- E: the learner confirmed or changed the goal and decided on the warm-up.
- F: the learner has said whether it helps now.
