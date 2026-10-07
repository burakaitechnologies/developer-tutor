---
name: learn
description: >-
  "Teach me X", "what is X", "quiz me", "refresh", "I want to learn X". One short lesson on one
  concept with one check, or a quick review. Not for a pasted error or reading one file.
---

# Learn

Purpose: teach one concept at a time on the learner's own project, with one check and short reviews.

## When to use

- The learner asks to learn a topic or what a word means and wants a lesson ("what is staging", "teach me branches").
- The learner picked an item from the offer line `Next I can teach:`.
- The learner asks to be quizzed or refreshed, or a review is due (see "Review steps").
- The learner says "teach me from zero" or "I know nothing".

## When not to use

- A pasted error or "it does not work": use fix-it.
- A file, command or diff to read: use explain. A one-sentence word meaning needs no skill.
- A design choice: use think-first.
- Quiet mode, or profile `teaching: light` or `off`: teach only when the learner asks in words. No offers, reviews or probes.
- The learner is frustrated or in a hurry: fix first, teach later.

## Start

1. Read `.agents/skills/learn/references/playbook.md` once per session, before the first lesson or review. It holds the lesson shape, the check rules, the hints, the rungs and the feedback shape. This file does not repeat them.
2. Read the profile and the notes (see "Profile, notes and offers" at the end). They give the language, the level and what the learner already did.
3. Pick the mode from the learner's words: Lesson, Review, or From zero. Follow its steps below.
4. If the skill was started with a topic (for example `$learn git-branch`), that is the topic.

## Lesson steps

1. Find the card. Cards are long lines, so search the short index first: search `.agents/tutor/knowledge/concepts-index.txt` for the id or a word (`rg -i "<word>"`; PowerShell: `Select-String -Pattern "<word>"`). Show at most 3 lines. Each line ends with `<file>:<line>`. Print only that line of the card file in `.agents/tutor/knowledge/concepts/` (Bash: `sed -n '<line>p' <file>`; PowerShell: `Get-Content -Path <file> -TotalCount <line> | Select-Object -Last 1`). Never print a whole concept file; the files are large.
   - No card: search `.agents/tutor/knowledge/glossary.jsonl` for `"term": "<word>"`. A glossary row is enough for one sentence. For a lesson, build the six parts from the row and the learner's files.
   - Neither: it is a free topic. Check the facts before you teach them (AGENTS.md, Checking facts). Say what you checked and what you did not.
2. If the card has `"volatile": true`, confirm the one fact you will state. Use the page named in `src`: for Codex, the Codex docs (their index is `https://learn.chatgpt.com/llms.txt`, checked 2026-10-08); for another tool, its own documentation. Say "checked" only for a lookup you ran in this session. If you ran none, say "from the kit notes dated <verified>" or "not checked", with the date from the card.
3. Find out what the learner already has. Search `.tutor/learner/notes.md` for the concept id (for example `git-staging`). No line means the concept is new. A `learned` line means Understood, a `did` line means Practiced, and an `alone` line means Independent. A `claimed` line means the learner said they know it.
   - They ask what X is, and X has a `learned`, `did` or `alone` line: that is a forgetting signal. Record `missed` (playbook section 7) and teach it in a new form.
   - A claimed concept (a `claimed` line): do not explain first. Start at rung R2 with a real step.
4. Check the prerequisites. Each id in `needs` should be at least Understood. If one is not, answer what the learner asked in one sentence. Say why you start with the other idea, then teach that one first. Gloss in the order the work needs the words: a term before the step that uses it (staging before commit, because `git-commit` needs `git-staging`).
5. Choose the rung and the check form (playbook sections 2 and 5). A new concept starts at R0 with a closed prediction. "My turn" starts at R2.
6. Write the micro-lesson (playbook section 1). Use the learner's real files and output, not the card's example, when the project has an equivalent. Name the step for their surface: in the app, the Terminal (New tab, then Terminal, or Ctrl+backtick; checked 2026-10-08); in the CLI, a leading `!`. If their words name a surface other than the one they use, ask once.
7. Does the index line end with `probe:<n>`? Then a probe exists: print line n of `.agents/tutor/knowledge/probes.jsonl` (one JSON object per line), read `.agents/skills/learn/references/probes.md`, and use the probe as the check.
8. Ask the one check and stop. Do not answer it yourself, and do not add a second question.
9. Grade the reply against the card's `rubric` (playbook section 6). Right: name what was right, then the next step. Partial: say which part holds and give H1 on the rest. Wrong at a new concept: give the next hint, not an answer, and record nothing.
10. Record only what playbook section 7 allows, as one line in `.tutor/learner/notes.md` (AGENTS.md, Memory). Then say the list line (playbook section 7).
11. Close with one next step in the learner's own work. Add the offer line only when the work reached a unit end (AGENTS.md, Teaching moves).

## Review steps

1. Check the moment (playbook section 8). A learner who asks "quiz me" or "refresh" may always have one. An offered review waits until their first request of the session is answered.
2. Choose items from `.tutor/learner/notes.md`. Search it for `| learned |` and `| did |` lines. Take the oldest one that is more than 7 days old (compare with today's date from `date` or `Get-Date`) and has no later `reviewed` line for the same concept id. Use the topic the learner named, if any. Prefer a topic the project touched in the last 21 days (playbook section 8). Nothing due? Say the list is short, and offer a lesson instead.
3. Offer in one line: "Quick one, no score? Say skip any time." Wait for the answer, unless the learner asked for the quiz.
4. Ask one item at a time. Use a different form from the last time for that item. Mix areas.
5. Grade and give feedback (playbook section 6). Record `reviewed` or `missed` as section 7 says. Do not read out schedules, scores or counts.
6. Stop at the limit (1, 2 or 3 items by the etiquette in playbook section 8). For a quiz the learner asked for, ask 3 items, then say they can ask for more. Go back to the project.
7. The tutor skill runs the welcome-back warm-up as this review mode: at most 3 items, mixed forms. The wait for the learner's first request does not apply to it.

## From zero

1. Read playbook section 9, then `.agents/tutor/knowledge/milestones.md` (about 90 lines; read it whole).
2. No project goal yet (no `.tutor/now.md`, or an empty folder)? Ask one question: what do they want to make or fix? Use the answer.
3. Pick one milestone for the learner's own project. If they named a topic, use the milestone that holds it. Teach an earlier one only where a concept's `needs` require it. Say it in one sentence, for example "The first step for your recipe page is to know which folder it lives in and to look inside it."
4. Take the first concept in the milestone's "Concepts" list that the learner lacks and whose `needs` are met. Teach it with the Lesson steps. Do not list the other milestones. They come one at a time, as the project needs them.

## Profile, notes and offers

- Read `.tutor/learner/profile.md` for language, level and teaching. Without it, use the language of the first message and level B1.
- Before you offer or review, read the last 40 lines of `.tutor/learner/notes.md` (PowerShell: `Get-Content -Path .tutor/learner/notes.md -Tail 40`; Bash: `tail -n 40 .tutor/learner/notes.md`). Write each record as one line there (AGENTS.md, Memory).
- Get the time with `date` (Bash) or `Get-Date` (PowerShell) when you write a line.
- Offers: search `.agents/tutor/knowledge/concepts-index.txt` for `signals` that match the current work. Each line lists its signals after `signals:`. Pick up to 3 whose id does not show as learned in `notes.md`. Never invent a topic.

## What to record

Playbook section 7 says which event fits and which words count. AGENTS.md (Memory) says how to write the line. Each line has this form: `YYYY-MM-DD | event | thing | "exact words"`. The thing is the concept id from `concepts-index.txt`; with no card, up to three words of the topic. The quote is copied exactly from the learner's last three messages.

A lesson alone records nothing. A decision made while teaching goes into today's journal (`.tutor/journal/YYYY-MM-DD.md`) as one line: a settled event, with no quotes. After you write a record, say the list line as playbook section 7 says.

## Done when

- The learner answered one check in their own words or by doing the step. You gave feedback in the three-part shape.
- A record was written only if the rubric was met. Otherwise you wrote nothing, and the learner knows the next small step.
- The lesson stayed within 150 words, one concept and one check.
