---
name: progress
description: >-
  "what have I learned", "how am I doing", "my progress", "what can I do alone", "am I ready". A
  short, honest picture of what you understand, did yourself and did alone, and what is next.
argument-hint: "[numbers]"
allowed-tools: Bash(python3 *doctor.py progress*) Bash(python *doctor.py progress*) Bash(py -3 *doctor.py progress*) PowerShell(python *doctor.py progress*) PowerShell(py -3 *doctor.py progress*)
---

# Progress

Purpose: give the learner a short, honest picture of what they know and can do. They should see real growth and know what to do next.

Start with step 1 and get the data. Do not write the picture from memory.

## When to use

- The learner asks what they have learned, how they are doing, what they can do alone, or whether they are ready for something.
- The learner asks "how well is the tutor teaching me" or for the numbers. That adds the counters part (step 6).
- The learner typed /progress. The word "numbers" after it adds the counters part.

## When not to use

- A quiz or a refresher on one topic: use learn.
- A summary of the project's work: use save-point or the tutor skill (where we stand).
- A go or no-go for publishing: use before-push.

## Steps

1. Get the data. From the project root run `python3 .claude/tools/doctor.py progress` (add the word `numbers` when step 6 applies). Use the interpreter named in the `Python:` line of the state block. Without it, use the first of `python3`, `python`, `py -3` that prints 3.9 or newer. The Bash and PowerShell tools both accept the command.
2. No interpreter, or the script is missing: read the notes yourself. Read the last 40 lines of `.claude/agent-memory/tutor-data/learner/notes.md` (PowerShell `Get-Content <file> -Tail 40`, Bash `tail -n 40 <file>`). If `learner/progress.jsonl` exists, read its last 40 lines the same way. Read nothing else. Say in one sentence that the picture comes from notes, not from the full list.
   - Map events to words: `learned` is Understood, `did` is Practiced, `alone` on a later day than the last `did` is "alone once", `claimed` is "told me". Never write Independent from notes alone.
3. Read the output as data. It should list, for each concept, the level, a quote of the learner's words, how often Claude ran it and whether it is rusty. With `numbers` it also holds the outcome numbers, and without it one sentence names any measure outside its target. If its shape differs, use what is there. Never invent a level, a date or a number.
   - Each row has a `src`: `inbox` (the learner's own words, checked by the hook), `hook` (a term the hook saw in the work, so it counts as Seen only) or `notes` (imported from an old notes file). No source is "verified": never write that the learner verified something, and never call a `hook` row something the learner said.
   - A concept with several rows is one concept. Repeat rows are practice: say the learner did it again, and count it once in the picture.
   - No data yet: say so in one sentence, name what you saw the learner do in this session, and go to step 5.
4. Write the picture in at most 200 words in the learner's language and level. In another language, translate the four level words once and keep the same words. Count the words before you send it. If it is too long, cut quotes first, then the lowest items. Use these parts, in this order:
   - Strengths first. At most 5 items, grouped by area (Git, terminal, web, and so on), highest level first. Each item has the concept title and its level word. Add a short quote of the learner's own words, or the action they did, when there is one. Level words are Seen, Understood, Practiced, Independent. Never write L1 to L4 or IL. "Independent" appears only after one review passed; before that write "alone once".
   - Told me. One line for the things the learner said they know (the `claimed` rows) and the work has not shown yet. Write "you told me" and nothing that sounds like a test. Do not write "prove it" or "show me". Do not count a claim again as a level or as a repeat.
   - Things I did for you. For each concept with Claude's runs at 3 or more and a level of Understood or lower, at most 2 items: "I ran <title> for you <n> times; you have not done it yet. Want to type it? Say 'my turn'."
   - Rusty. Items the output marks as rusty: "a little rusty: <title>; a short look would help." No guilt words.
   - Signs of independence you actually see in the output or the journal, at most 2, for example "you named the files you changed". If you see none, skip this part.
   - If `teaching` in the profile is `off` or `light`, one factual line: "Teaching is <off|light>."
5. If the learner asked about a goal, such as "am I ready to put it online", say which parts of it the picture shows and which it does not. Then end with what comes next: the project step from now.md `Next` and up to 3 lessons with one recommended and one clause why. Take the lessons from the output's offer list. Without it, use route B of `.claude/skills/tutor/SKILL.md`. End with one question: which one, or something else.
6. Counters, only when the learner asks, or when one band is out of range.
   - Asked: name each measure in plain words with its number and its target. The measures: a real check question after most medium or large changes (target 70% or more); new terms explained at first use (target 90% or more); the result part within the level's word limit (typical answer); sentence length (average 15 words or fewer at level B1); review answers right (target 60% to 90%); learner steps per 10 answers.
   - Not asked, one band out of range: say it in one plain sentence with no number, for example "I have asked fewer real questions after bigger changes than I should; I will fix that." Say nothing about bands that are in range.
7. If the learner disputes an item, say the list follows what they did and said, and that new evidence changes it. To remove an item they can say "forget <topic>"; then write a `forget` record (`.claude/rules/keeping-memory.md`).

## What to record

Nothing. This skill only reads. A correction or a `forget` request is the one exception, and the rule above says how to write it.

## Done when

- The picture is 200 words or fewer, strengths come first, and claims are shown apart as "told me".
- Every number and quote comes from the output or the notes.
- The learner has 3 next options or fewer, with one recommended.
- No percentage, bar or streak appears outside step 6, and no guilt wording anywhere.
