# Probes: one question about one wrong belief

For: the main agent, inside a lesson or a review of the learn skill. The check rules, the feedback shape and the recording rules are in `playbook.md`. This file only says how to use `.agents/tutor/knowledge/probes.jsonl`.

A probe is a multiple-choice question whose wrong options match common wrong beliefs (misconceptions). The file has one JSON object per line with the keys `id`, `question`, `options`, `misconceptions` and `correct`.
- `id` is the id of the concept the probe belongs to.
- `options` ends with "not sure". `correct` is the text of the right option.
- `misconceptions` maps each wrong option to the belief behind it, for example "A command works on the whole computer".

## When to use a probe

- After the concept has appeared in the learner's real work: you taught it, or the work used it. Never before. A probe never opens a session and is never an onboarding quiz. A learner who has not met the idea can only guess.
- At most one probe per lesson, and at most one per concept per session.
- Not after an error, not while the learner is frustrated, not in quiet mode. The check rules of playbook section 2 apply in full.
- No row for the concept, or no file? Use the card's `check` and `pitfall` instead. Say nothing about the missing row.

## How to use one

1. Find the row. The concept's line in `.agents/tutor/knowledge/concepts-index.txt` ends with `probe:<n>`. Print only line n of `.agents/tutor/knowledge/probes.jsonl`. Do not print the whole file.
2. Ask it as a closed prediction with the label `Predict:` (Seen level) or as a `Check:` (higher levels). Put the question in your own words and in the learner's language. Keep the options as written, with "not sure" last. If the right option comes first, move it. Keep the options the same length.
3. Optional: ask "guess, think so or sure?" before you show the result.
4. Wait. Do not hint in the same message.

## Reading the answer

- Correct pick: say what is right and why in one sentence. A pick is recognition, not understanding. Do not record `learned` from it. To get evidence, give the next real step of the work (rung R1 or R2). Their own words or actions then show it.
- Wrong pick on a new concept: this is a hint moment, so record nothing. Use the refutation shape with the belief from `misconceptions`: "Many people think <belief>. It feels right because Y. Look at what happens:" and show the real file or output. Then give the next small step.
- Wrong pick on a concept at Understood or above, or in a review: record `missed` in `.tutor/learner/notes.md`, with the probe's `id` as the thing and the learner's exact words as the quote. If the learner said they were sure, the quote shows it. Change the form of the next check.
- "Not sure": say it is a good answer, and teach the idea in the lesson's part 4.

## Asking again later

Ask the same belief again only on a later day, in a different wording. Never ask the same question twice in a row. A learner who picks the same wrong belief twice gets a different artifact next time: real output, a diagram from `.agents/tutor/knowledge/diagrams.md`, or predict-and-run.
