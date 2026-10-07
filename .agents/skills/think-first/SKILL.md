---
name: think-first
description: >-
  Before work that is not small: "build me an app with login/database", "which framework", "should
  we use X", payments, user data, deploy. Sorts into no, short or full gate: options, plan, one
  yes.
---

# Think first

Purpose: avoid a choice that is hard to undo before any code exists. Match the effort to the work, and show the learner how the choice was made.

AGENTS.md, section Design gate, says when a gate applies. This skill says how to run it. Voice, check lines and answer shape come from AGENTS.md. Every step here uses file reads, `rg` (PowerShell: `Select-String`) and commands the learner could run too. Sentences in quotes below are English: say them in the learner's language and at their level.

## When to use

- A new project, or a choice of language, framework, database, login, payment, hosting or deploy.
- A change to more than eight files, or one that moves folders.
- Real user data, money, or anything that becomes public.
- A new package is about to be added: give one plain sentence first. Run this skill only if the package is a framework, database, login, payment or hosting choice.

Do not use it for a typo, a bug fix in one place, a test, or a style change. Do not use it for the first thing built in a project: that is always Tier 0. If the first request asks for login, stored data or hosting, build only the visible shape with made-up data, then run the gate before the next step.

## First: sort the work into a tier

| Tier | The work | What you do |
|---|---|---|
| 0, no gate | One file, one static page or one script. No stored data, accounts, money, secrets or new package. Runs only on the learner's computer. | Say the choice in one sentence ("One HTML file, no tools to install."). Build. |
| 1, short gate | Up to 3 files, local only. For 4 to 8 files with no Tier 2 trigger, do the same and add a numbered plan. | Restate the goal in one sentence. Ask at most ONE question: options, your recommendation first. Wait for one yes. |
| 2, full gate | Any trigger in AGENTS.md, Design gate: a stack, language, framework, database, login, payment or hosting choice; more than 8 files; real user data or money; deploy or going public. | Run the full gate below. |

If two tiers fit, take the lower one and say what would move it up. A gate that takes longer than the build teaches that thinking is a cost. "Just do it" shortens a Tier 2 gate: you answer the questions yourself and show the plan and the two options, not the reasoning. It never removes the one yes, the G1 save point, or safety text: the choice is hard to undo, so the learner still gives it. It may drop the why question and the offers.

## The G1 check (a fixed step)

Run this at the first change to more than one file, in every tier. It is step 1 of a Tier 2 gate. Ask at most once per session.

1. Run `git status`. A Git project with a commit and nothing unsaved: go on. Unsaved changes: run the `$save-point` skill (quick save point) first. No commit yet, or no Git project: go to step 2.
2. Say this one sentence, then wait for the answer: "Before I change several files, I suggest a save point: Git keeps a history you can go back to. Shall I set up Git?"
   - Yes: run the `$new-project` skill, steps 5 to 9.
   - No: say once that there is no history to go back to yet. Then go on, and use the copy steps in the `$save-point` skill ("No Git yet") before the next multi-file change.

## The full gate (Tier 2)

1. **G1 check.** Run the G1 check above before the first change.
2. **Restate.** Write the goal and the success test in two lines. The success test is something the learner can run or click and see. Ask for a correction only if a part is unclear.
3. **Look first.** Read the README and the top folders. Read `docs/decisions/README.md` if it exists. Ask yourself: is this a real problem, does a tool already do it, is there a simpler way? Tell the learner only what changes the plan.
4. **Ask up to three decision questions**, one per message. Each has options, and your recommendation comes first with one reason. Never ask a yes-or-no question alone: give at least two options. Take the project type and its three first questions from `.agents/tutor/knowledge/stacks.md` (search the type heading, read only that section). Before you name a tool, version, price or limit, read its docs page this session and say which page (AGENTS.md, Checking facts). Say "checked this session: <page>" only for a lookup you ran now. Otherwise say "from the kit notes dated <date>" or "not checked". Never write a version number from memory. The learner may pick one new tool to learn; the rest stays well known.
   - **Access question first.** If people log in to see or change records (a family list, customers, orders), ask this one before you write any access rule (row level security, roles, sharing). It is one of the three questions: "Should each person see only their own records, or all records?" Options: own records only, the recommended default for personal data; or all records for the group. Then state the consequence of open sign-ups in one sentence: "If sign-ups stay open, anyone who finds the address can make an account and see what the rules allow."
   - **Login:** recommend a proven login, the framework's or the host's. Never a home-made login (gate.md, anti-pattern 3). The choice goes into the decision record.
5. **Run the 10 questions.** Read `.agents/skills/think-first/references/gate.md`. The decision ladder below says who answers. Show the learner the three answers that decided, each with the cost of the shortcut in one sentence. Keep the other seven for yourself: ten answers in a row are skipped. Questions 5 and 6 (who can read or change, and what a stranger sees) are the access question of step 4. Put them to the learner at every gate level.
6. **Two options.** Exactly two, with trade-offs and "what would change my mind" (format in `gate.md`). Recommend one. The learner decides.
7. **Plan.** Number 3 to 8 steps. For each: what is made, where to find it, how we check it. Mark steps the learner could do themselves. Include the check that proves the success test.
   - Hosting: if the success test needs the app online or on another device, the plan has a hosting step: where it runs, how it gets online, and who runs the deploy. Otherwise say plainly: "The success test (for example, using it from a phone) is out of scope for now."
   - For a plan over three steps, put the plan hint (see "Plan hint" below) in the same message as the plan.
8. **Second opinion** (only for a hard-to-undo decision; see below). Optional.
9. **One yes.** Write: "Say yes and I build steps 1 to N and check each one, or tell me what to change." Do not build before it. After the yes, and before step 1, ask the why question once, in one line: "In your own words, why this choice?" Accept a short answer or "not sure" at once. Then write the decision down (below) and start step 1.

Build in small steps. After each numbered step, run its check yourself and show the command and its output. Offer a save point (`$save-point` skill) at the end of each finished piece. If a step proves wrong, stop, say so in one sentence, change the plan, and add "Changed from:" to the journal entry.

## Plan hint (surface-correct)

`/plan` switches the chat to plan mode, where Codex proposes an execution plan before implementation work starts (checked 2026-10-08: the developer commands page). Say it once, for a plan over three steps, with the wording for the surface:
- Terminal (Codex CLI): type `/plan` and press Enter before you ask for the plan.
- App or IDE extension: I did not find a plan control in the app pages I checked (2026-10-08). Say: "I will propose the plan first and change no files until you say yes." Do not name a button.
- Unknown surface: skip the hint. Do not ask only for this.

## Decision ladder: the learner does more each time

Count the full gates so far. Search the journal folder (`.tutor/journal/`) for `Design gate:` and count the matching lines. Count the lines of `docs/decisions/README.md` that start with a number. Take the larger of the two. If both are empty and the folder already has files, or the learner says they chose tools before, ask once: "Have we chosen tools like this together: never, a few times, or many times?" Read never as 0, a few as 3, many as 6. This gate is number n + 1.

- **Gates 1 and 2:** you answer the ten questions, except questions 5 and 6, which the learner answers (step 4). Show the three that decided and the cost of each shortcut.
- **Gates 3 to 5:** before you answer, ask: "Which of these five worries you most here, and why?" The five: who uses it, how many at once, what must never be lost, what if it is wrong, how hard it is to undo. Start your answers with the one they name. If they say "not sure", choose for them and say why.
- **Gate 6 and later**, or when `.tutor/learner/notes.md` has an `alone` line about architecture trade-offs or reversible decisions: ask for two options and a pick BEFORE you show yours. Then compare (format in `gate.md`).

Reason: the learner takes over the thinking in steps, as in the handover rungs of AGENTS.md. Go back one stage after 14 or more days away, or when the learner says "not sure" twice in the same gate. Add a `learned` line to `.tutor/learner/notes.md` for an architecture concept only when the learner's words meet the card's rubric (search the id in `.agents/tutor/knowledge/concepts-index.txt`, then print only that one line of the card file).

## Second opinion with architecture_reviewer

Use it only when the plan holds a decision from the list under "Decision record", or when the learner asks.
1. Say in one line: one helper, `architecture_reviewer`, reads the files and does not change them. It has no web access. Codex starts a helper only when asked, so ask for it.
2. Ask Codex to spawn `architecture_reviewer`. Give it: the goal and success test, the plan in 5 lines, the two options, the file names to read. No secrets, no personal data. Say the reader is a beginner, to use plain words (AGENTS.md, Writing and tidiness), and to mark every unchecked statement UNVERIFIED.
3. It answers in about 350 words: verdict, top 3 risks, a simpler alternative, what to decide now or later, 2 questions, and a list "to verify online".
4. Verify each "to verify online" item yourself in the docs. Keep what you confirmed. Mark the rest as unchecked or drop it.
5. Tell the learner in 3 to 5 plain lines: the verdict, the main risk and why, the simpler alternative, your answer to its questions. Do not paste the report. If the verdict is "stop", do not build; change the plan or ask the learner.

## Decision record (only for decisions that are hard to undo)

Write one only for a choice that is hard to undo (the rule in AGENTS.md, Design gate). Typical examples: language, framework, database, login approach, hosting, data model, paid service, repository layout. The list gives examples, not a trigger: a choice from it that is easy to change gets one line in the README or the journal. A Tier 0 or Tier 1 choice never gets a record: write one line in the README.
1. Search `docs/decisions/*.md` for the next number (0001 first).
2. Read `.agents/tutor/templates/decision-record.md`. Fill every heading in plain words, on one page. Visibility (who can see and change what) and the login approach go under their own headings. Put what you checked and where in "What to check later", with the dates.
3. Write `docs/decisions/NNNN-short-title.md` (ASCII, lowercase, hyphens). "Reasoning in plain words" is the learner's reasoning rewritten: no name, no quotation marks. This file is committed and may become public, so it holds no secrets, names, quotes or personal goals.
4. Add one line to `docs/decisions/README.md`: `0001 Title - status - date - revisit when ...`. Create the file with a one-line heading if it is missing.
5. Tell the learner in one sentence where it is and that the `$save-point` skill will ask about "Revisit when" later.

## What to record

- Journal entry titled `Design gate: <decision in a few words>` for each full gate. It is also the gate counter. Form: `.agents/tutor/templates/journal-entry.md`. Settled events only, paraphrased: no learner quotes. Rules for notes: AGENTS.md, Memory.
- The decision record and its index line, when one applies.
- A line in `.tutor/learner/notes.md` for `learned` or `declined`, copied from the learner's own words (AGENTS.md, Teaching moves: Record). `declined` covers optional advice only, such as the second opinion. When it is saved, say: "Added to your list: <title>."
- `.tutor/now.md` is updated by the `$save-point` skill, which adds the line under "Decisions to remember".

## Done when

- The learner said yes to a numbered plan, or chose another route and you said what changes.
- The access question was asked before any access rule, if the project keeps records that people log in to see or change.
- The G1 check ran before the first multi-file change.
- The why question was asked once, and the learner answered or said "not sure".
- The decision is written down: journal entry, plus a decision record if it is hard to undo.
- Step 1 of the build has started, or the learner knows what happens next.
