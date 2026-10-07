---
name: learn
description: >-
  "Teach me X", "what is X", "quiz me", "refresh", "I want to learn X". One short lesson on one
  concept with one check, or a quick review. Not for a pasted error or reading one file.
argument-hint: "[topic, or review]"
---

# Learn

Purpose: teach one concept at a time on the learner's own project, with one check and short reviews.

## When to use

- The learner asks to learn a topic or what a word means and wants a lesson ("what is staging", "teach me branches").
- The learner picked an item from the offer line `Next I can teach:`.
- The learner asks to be quizzed or refreshed, or the session-state block names a due review.
- The learner says "teach me from zero" or "I know nothing".

## When not to use

- A pasted error or "it does not work": use fix-it.
- A file, command or diff to read: use explain. A one-sentence word meaning needs no skill.
- A design choice: use think-first.
- Quiet mode, or profile `teaching: light` or `off`: teach only when the learner asks in words. No offers, reviews or probes.
- The learner is frustrated or in a hurry: fix first, teach later.

## Start

1. Read `${CLAUDE_SKILL_DIR}/references/playbook.md` once per session, before the first lesson or review. It holds the lesson shape, the check rules, the hints, the rungs and the feedback shape. This file does not repeat them.
2. Pick the mode from the learner's words: Lesson, Review, or From zero. Follow its steps below.
3. If the skill was started with a topic (for example `/learn git-branch`), that is the topic.
4. No session-state block? The helper scripts are off. Follow "Without the state block" at the end.

## Lesson steps

1. Find the card. Cards are long lines that Grep hides, so search the short index: Grep `.claude/knowledge/concepts-index.txt` for the id or a word (ignore case, at most 3 lines). Each line ends with `<file>:<line>`. Read that card with the Read tool: path `.claude/knowledge/concepts/<file>`, `offset` = the line number, `limit` 1. Never Read a whole concept file; the files are large.
   - No card: Grep `.claude/knowledge/glossary.jsonl` for `"term": "<word>"`. A glossary row is enough for one sentence. For a lesson, build the six parts from the row and the learner's files.
   - Neither: it is a free topic. Check the facts before you teach them (`.claude/rules/checking-facts.md`). Say what you checked and what you did not.
2. If the card has `"volatile": true`, confirm the one fact you will state. Use the page named in `src`: `claude-code-guide` for Claude Code, otherwise WebFetch or Context7. Say "checked" only for a lookup you ran in this session. If you ran none, say "from the kit notes dated <verified>" or "not checked", with the date from the card.
3. Find out what the learner already has. Hooks on: the state block and the message facts name due reviews and "Verify-soon". For one concept, Grep `.claude/agent-memory/tutor-data/learner/progress.jsonl` for `"id": ?"<id>"`. No line means the concept is new.
   - They ask what X is, and X is at Understood or above: that is a forgetting signal. Record `missed` (playbook section 7) and teach it in a new form.
   - A claimed concept (a "Verify-soon" fact): do not explain first. Start at rung R2 with a real step.
4. Check the prerequisites. Each id in `needs` should be at least Understood. If one is not, answer what the learner asked in one sentence. Say why you start with the other idea, then teach that one first. Gloss in the order the work needs the words: a term before the step that uses it (staging before commit, because `git-commit` needs `git-staging`).
5. Choose the rung and the check form (playbook sections 2 and 5). A new concept starts at R0 with a closed prediction. "My turn" starts at R2.
6. Write the micro-lesson (playbook section 1). Use the learner's real files and output, not the card's example, when the project has an equivalent. Name the step for their surface: Desktop, the Terminal button in the session title bar (local sessions only); terminal or VS Code, a leading `!`. If their words name another app than the state block's surface, ask once.
7. Does the index line end with `probe:<n>`? Then a probe exists: Read `.claude/knowledge/probes.jsonl` with `offset` n and `limit` 1, Read `${CLAUDE_SKILL_DIR}/references/probes.md`, and use the probe as the check.
8. Ask the one check and stop. Do not answer it yourself, and do not add a second question.
9. Grade the reply against the card's `rubric` (playbook section 6). Right: name what was right, then the next step. Partial: say which part holds and give H1 on the rest. Wrong at a new concept: give the next hint, not an answer, and record nothing.
10. Record only what section 7 allows, written as `.claude/rules/keeping-memory.md` says.
11. Close with one next step in the learner's own work. Add the offer line only when the work reached a unit end (see the style).

## Review steps

1. Check the moment (playbook section 8). A learner who asks "quiz me" or "refresh" may always have one. An offered review waits until their first request of the session is answered.
2. Choose items. Hooks on: use the due reviews in the state block, the ones the project touched lately first. Hooks off: Grep `learner/notes.md` for `learned` or `did` lines older than 3 days with no later `reviewed` line. Nothing due? Say the list is short, and offer a lesson instead.
3. Offer in one line: "Quick one, no score? Say skip any time." Wait for the answer, unless the learner asked for the quiz.
4. Ask one item at a time. Use a different form from the last time for that item. Mix areas.
5. Grade and give feedback (playbook section 6). Record `reviewed` or `missed` as section 7 says. Do not read out schedules, scores or counts.
6. Stop at the limit (1, 2 or 3 items by the etiquette in section 8). For a quiz the learner asked for, ask 3 items, then say they can ask for more. Go back to the project.
7. The tutor skill runs the welcome-back warm-up as this review mode: at most 3 items, mixed forms. The wait for the learner's first request does not apply to it.

## From zero

1. Read playbook section 9, then `.claude/knowledge/milestones.md` (about 90 lines; read it whole).
2. No project goal yet (no `now.md`, empty folder)? Ask one question: what do they want to make or fix? Use the answer.
3. Pick one milestone for the learner's own project. If they named a topic, use the milestone that holds it. Teach an earlier one only where a concept's `needs` require it. Say it in one sentence, for example "The first step for your recipe page is to know which folder it lives in and to look inside it."
4. Take the first concept in the milestone's "Concepts" list that the learner lacks and whose `needs` are met. Teach it with the Lesson steps. Do not list the other milestones. They come one at a time, as the project needs them.

## Without the state block

- Read `.claude/agent-memory/tutor-data/learner/profile.md` for language, level and teaching. Without it, use the language of the first message and level B1.
- Read the last 40 lines of `learner/notes.md` before you offer or review. Write each record as one line there, as keeping-memory.md shows.
- Take the time from `date` (Bash) or `Get-Date` (PowerShell) when you write a line.
- Offers: Grep `concepts-index.txt` for `signals` that match the current work. Pick up to 3 that notes.md does not show as learned.
- A review may be asked once for an item older than 3 days with no later `reviewed` line.

## What to record

Playbook section 7 says which event fits and which words count. `.claude/rules/keeping-memory.md` says how to write it and where. A lesson alone records nothing. A decision made while teaching goes into today's journal as one line: a settled event, with no quotes. After a record is saved, the list line follows playbook section 7.

## Done when

- The learner answered one check in their own words or by doing the step. You gave feedback in the three-part shape.
- A record was written only if the rubric was met. Otherwise you wrote nothing, and the learner knows the next small step.
- The lesson stayed within 150 words, one concept and one check.
