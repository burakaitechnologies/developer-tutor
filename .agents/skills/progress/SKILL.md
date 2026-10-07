---
name: progress
description: >-
  "what have I learned", "how am I doing", "my progress", "what can I do alone", "am I ready", $progress.
  A short, honest picture of what you understand, did yourself and did alone, and what is next.
---

# Progress

Purpose: give the learner a short, honest picture of what they know and can do. They should see real growth and know what to do next.

Start with step 1 and read the notes. Do not write the picture from memory.

## When to use

- The learner asks what they have learned, how they are doing, what they can do alone, or whether they are ready for something.
- The learner typed `$progress`.

## When not to use

- A quiz or a refresher on one topic: use learn.
- A summary of the project's work: use the tutor skill, route A.
- A go or no-go for publishing: use before-push.

## Data

This skill reads two files only: `.tutor/learner/notes.md` and `.tutor/learner/profile.md`. It keeps no counts. Each line of the notes is one record in this form: `YYYY-MM-DD | event | thing | "exact words"`.

## Steps

1. Read `.tutor/learner/notes.md`, all of it. Skip a line that does not have four fields separated by `|`, and do not mention it unless the learner asks. If the file is missing or has no records, go to step 4 and say there is no data yet. Read `.tutor/learner/profile.md` for the `teaching` and `language` keys.

2. Fold the records into one picture per `thing`. Keep the date order; for the same date, keep the line order. Use this table:

| Event in the notes | What it does to the picture |
|---|---|
| `claimed` | A claim. It is shown as "you told me" until a `learned`, `did` or `alone` line for the same thing appears. A claim is never a strength. |
| `learned` | Understood. |
| `did` | Practiced. |
| `alone` on a later day than the last `did` or `learned` for that thing | Independent in the data, but shown as "alone once" until a review has passed. |
| `alone` with no earlier `did` or `learned`, or on the same day as the last one | Practiced. |
| `reviewed` (a review the learner passed) after an `alone` that is shown as "alone once" | Independent. Any other `reviewed` line gives Understood at least. |
| `missed` | Lowers the thing by one level, never below Seen. Never listed, never named as a failure. |
| `declined` | Counts for the offers only. No level. |
| `forget` | Removes the thing. Earlier lines stop counting, and later lines start again. |

Rules for the picture:
- Evidence on one day counts as Practiced at most. Independent needs an `alone` on a later day.
- Write "Independent" only after a passed review. Before that, write "alone once".
- Seen appears only as "you told me", from a claim. The notes do not record terms that were only shown.
- Use the four level words: Seen, Understood, Practiced, Independent. Never write L1 to L4 or IL.
- A thing with several lines is one thing. Repeat lines are practice: say the learner did it again, and count it once in the picture.

3. Write the picture in at most 200 words, in the learner's language and level. In another language, translate the level words once and keep them the same. Count the words before you send it. If it is too long, cut quotes first, then the lowest items. Use these parts, in this order:
   - **Strengths first.** At most 5 items, grouped by area (Git, terminal, web and so on), highest level first. Each item has its title and its level word: Understood, Practiced, alone once or Independent. Use the title from `.agents/tutor/knowledge/concepts-index.txt` when the `thing` matches a card. Otherwise use the learner's own three words. Add a short quote of the learner's own words, or the action they did, when there is one.
   - **Told me.** One line for the things the learner said they know (the claims) that the work has not shown yet. Write "you told me" and nothing that sounds like a test. Do not write "prove it" or "show me". A claim is not a level.
   - **Signs of independence.** At most 2 items, from the `alone` lines, with their quote. For example, "you did the last step without help". If there are none, skip this part.
   - **Rusty.** This edition does not work out rusty items from the notes. Skip this part. Do not write the word "rusty".
   - If `teaching` in the profile is `off` or `light`, one factual line: "Teaching is off." or "Teaching is light."
   - One sentence at the end: the picture comes from the notes file, which the tutor writes itself and no script checks.

4. If the learner asked about a goal, such as "am I ready to put it online", say which parts of it the picture shows and which it does not. Then name what comes next: up to 3 lessons, one recommended, with one clause why. Get the lessons by following route B of the tutor skill (`.agents/skills/tutor/SKILL.md`). This skill does not read the card index. End with one question: which one, or something else.
   - If there is no data yet: say so in one sentence. Name one thing you saw the learner do in this session, if there was one. Then go to the lessons.

5. If the learner asks for numbers or counts: say in one sentence that this edition keeps no counts, and offer the picture instead. Do not invent a count, a percentage, a bar or a streak.

6. If the learner disputes an item, say that the list follows what they did and said, and that new evidence changes it. To remove an item, the learner can say "forget <topic>". Then add one `forget` line to `.tutor/learner/notes.md`, with the learner's exact words (AGENTS.md, Memory).

## What to record

Nothing, except a `forget` line when the learner asks for one, as step 6 says.

## Done when

- The picture is 200 words or fewer. Strengths come first, and claims are shown apart as "you told me".
- Every quote and date comes from the notes file.
- The next options are 3 or fewer, with one recommended.
- No percentage, bar, count, streak or "rusty" appears, and no guilt wording appears anywhere.
