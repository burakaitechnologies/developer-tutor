# How the tutor kit works

This page explains each part of the kit and how the parts work together.
It also says what the kit cannot do. Read it when you want to check a claim.

## The layers

The kit has several layers. Each layer does one job. Some layers stay after a long chat. Others need the helper scripts to be on.

```
your-project/.claude/
  CLAUDE.md          short contract every agent reads
  output-styles/     the tutor voice and teaching moves
  rules/             six shared standards
  skills/            eleven procedures, started by name
  agents/            two read-only helpers
  knowledge/         concept cards, read on demand
  hooks/             facts, safety guard, records
  settings.json      permission rules: deny, ask, allow
  agent-memory/      your notes, kept private
```

| Layer | What it does | Who sees it | Survives /compact |
|---|---|---|---|
| `CLAUDE.md` | A short contract. It names the skills and the hard rules. | Every agent except the built-in Explore and Plan helpers | Yes. Claude Code loads it again from disk. |
| Output style `tutor` | The voice, the answer shape and the teaching moves. | The main agent only | Yes. The style still applies. |
| Rules (6 files) | Standards for clear writing, facts, safety, design choices, notes and tidy projects. | Every agent except Explore and Plan | Yes. Unscoped rules load again from disk. |
| Skills (11) | One procedure each, such as `learn`, `fix-it` or `save-point`. | The main agent, and you by name | The text of a skill used earlier comes back. The list of skills may not. |
| Agents (2) | Read-only second opinions on a plan or a change. | The main agent | Each helper starts fresh when it is called. |
| Knowledge | Concept cards and a glossary. The tutor looks up one card at a time. | Read on demand | Files on disk. They are never loaded whole. |
| Hooks | Facts before each message, a check before each tool call, and records after. | The model, through short text | By design, the start hook prints its header again after /compact. Not yet checked with a real model. |
| Settings | Permission rules: deny, ask and allow. | Claude Code, not the model | Yes. It is a file on disk. |

Explore and Plan are built-in helpers. They skip CLAUDE.md to stay fast, so they do not see the rules or the state block (checked 2026-10-07). The kit's reminder for helpers comes from a SubagentStart hook, and that hook also runs for Explore and Plan.

## How the tutor teaches

The tutor builds your real project and teaches while it works. Each work answer shows the result and where it is. It explains a little, and it sometimes asks you one thing to do.

The loop has six steps:

1. Build your real project. The tutor shows where the result is and how to check it.
2. Explain a new word once, at its first use, in one sentence. Only a word you must act on, or will meet again, gets an explanation. In your first three sessions the tutor explains one word per answer. Later it explains one to three, depending on your level.
3. Ask one marked check after bigger work. A check starts with `Check:`, `Predict:` or `Your move:`. You must produce something. It is never a yes or no question. There is at most one check per three work answers, and none after an error, when you seem frustrated, or in quiet mode.
4. Offer the next lessons only at the end of a finished piece of work. The offer starts with `Next I can teach:`. It comes at most once per three work answers, and not again after you decline.
5. Review older topics now and then. A review is an offer, and you can skip it.
6. Give you more of each step over time, using the rungs below.

Every work answer keeps a fixed shape:

- Quick answer: a short answer within the word limit for your level. A new term is explained.
- Small work, such as one file: one line of result, and a line `How to check:`.
- Medium or large work: the result, the explanations, a `Check:` line and a Change card. The Change card is one line: files created, changed and deleted, new packages, network, and the command that checks it. It gives the file's full folder path. A fix also gets a Change card.
- A lesson, when you ask for one: up to 150 words, one concept, one step and one check.
- An error: the tutor first asks one short question about what you know or which file it names. If you say "just fix it", or you seem frustrated, it fixes the error at once and says what it did in one or two sentences.

When the tutor gets something wrong, it says what is right, corrects the one wrong part with the real file or output, and gives a hint before the answer. Before it corrects something it said earlier, it re-reads its last replies.

The rungs describe who does each step:

| Rung | Who does the step | Who does the last part |
|---|---|---|
| R0 Narrate | The tutor does it and explains | Nobody. You watch and answer the check. |
| R1 Predict | The tutor does it after you predict | You guess the result first |
| R2 Complete | The tutor writes most of it | You write or run the last part |
| R3 Do | You do it. The tutor gives the goal. | You, with hints only if you ask |
| R4 Alone | You do it on a later day | You, with no hint |
| R5 Teach | You explain it to someone else | You |

The tutor moves up one rung after a clean success. It moves down one rung after two failures, or after two or more hints at rung 3 or higher. Say "let us make this smaller" if a step is too big.

The hints get more direct at each step. H1 says where to look. H2 names the idea. H3 gives two choices. H4 gives part of the answer. H5 gives the answer, the reason, and a second file to try the same idea on. Using a hint is not a failure. The list does not record hints.

Levels describe what the tutor believes you can do. Each level needs different evidence.

| Level | What it means | Evidence |
|---|---|---|
| Seen | You met the idea. | The tutor showed it, or you said you know it ("told me"). |
| Understood | You can explain it in your own words. | Your own words, from one of your last three messages. |
| Practiced | You ran or changed it yourself. | You ran the step and told what happened. Steps Claude ran do not count. |
| Independent | You did it alone, on a later day. | A step you ran with no hint, on a later day than your last step. Only skill topics count. |

Two rules keep the levels honest:

- A claim does not raise a level above Seen. "I know Git" is a claim. The tutor checks it at the first real use.
- Same-day work stops at Practiced. Independent needs a later day.

Claimed, learned and did mean different things. Claimed means you say you know it. Learned means you explain it in your own words. Did means you ran or changed it yourself. "Ok", "yes" and "I understand" prove nothing, so the tutor records none of them.

Why the tutor sometimes asks you to do a step: you learn a step by doing it. When Claude runs the same command many times for you, the tutor may offer you a turn. Say "my turn" to type a step yourself. Say "you do it" to let the tutor run a step without a lesson.

Quiet mode and skipping:

- Say "quiet mode" to turn lessons off. Quiet mode still gives the result, the safety lines and the save-point question. It drops glosses, checks, offers and reviews.
- Say "teach me again" to turn lessons back on.
- Say "just do it" to drop explanations, glosses, checks, offers and optional questions for this request and the next two turns. It never drops a yes before something hard to undo, the save point before a risky change, the Change card, or safety text.
- Quiet mode is not permission. Anything hard to undo still needs your yes.
- Say "simpler" for shorter sentences and one level lower for the session.

## What the tutor remembers

The tutor keeps notes in one private folder inside `.claude`. The notes let the next session continue. The tutor writes some notes. The helper scripts write others.

| File | What it holds | Who writes it |
|---|---|---|
| `now.md` | Where the project stands: the goal, what is done, what is next. At most 60 lines. | The tutor, at each full save point |
| `journal/YYYY-MM-DD.md` | One file per day: settled events only. Decisions, work done, facts checked, and ideas rejected with the reason. No quotes from you. | The tutor |
| `learner/profile.md` | Your settings: language, level, teaching mode, comments, chat copy. | The tutor, when you change a setting |
| `learner/progress.jsonl` | Your list: one line per learning event. Each line says where it came from: `inbox` (your words, checked), `hook` (a concept met), or `notes` (imported text-only notes, not checked yet). | The scripts only |
| `learner/notes.md` | Learning lines, used only when the scripts are off. | The tutor, in text-only mode |
| `inbox/*.md` | Short files that record one learning event. | The tutor writes them. The scripts read and delete them. |
| `chat/YYYY-MM-DD.md` | An optional copy of your messages. Off by default. Only your own words turn it on. | The scripts, when you turn it on |
| `state/` | Counters, the activity log, the ledger and the error log. | The scripts only |

Your list follows what you did and said. It is not an exam. A level tells the tutor what to explain next. It is not a grade, and it can be wrong.

To take an item off your list, say `forget` and its name, for example "forget HTML". The tutor records a forget line only when your last message asks for it.

The inbox works like this:

1. The tutor writes a small file with one learning event and your exact words.
2. A script reads the file. It checks that your words come from one of your last three messages.
3. The words need at least 12 characters and 3 words. A question, or a filler such as "ok", does not pass.
4. A passing line goes into `learner/progress.jsonl`. The tutor sees `Saved:` and says once: "Added to your list: <title>." The first time in a project, it also says that the list is private and stays on this computer.
5. A failing line is deleted. The tutor sees `Refused:` with the reason, and writes a new file with corrected lines. After two refusals in one message, the tutor stops writing for that message.

The tutor records at most two lines per message, or six in your first session. If there are more, the rest go in later messages. The tutor does not record a failed run or a guess.

Project decisions do not go in these notes. They go in `docs/decisions/` in your project, outside `.claude`. Each decision file has a "Revisit when" line. Claude Code's own auto memory is a separate feature, and the tutor does not write there.

## The hooks, one table

Hooks are small scripts that Claude Code runs at fixed moments. They are off until you turn them on. Hooks print facts or write records. Only the safety guard can stop an action.

| Event (when it runs) | Matcher (which tools) | Reads | Writes | Can block? | Time limit |
|---|---|---|---|---|---|
| SessionStart (a new, resumed, cleared, compacted or forked session) | `startup\|resume\|clear\|compact\|fork` | `state.json`, `profile.md`, `settings.json`, `now.md`, decision titles, Git state (read only), the folder layout, your list, the newest ledger row and hook errors | `state/state.json`. At startup and clear, deletes chat copies older than 30 days. | No | 15 s |
| UserPromptSubmit (each message you send) | none | Your message, `profile.md`, `state.json`, the last 10 rows of the ledger, `progress.jsonl`, `activity.jsonl`, concept cards | `state/recent-user.json` (your last 5 messages, redacted), `state/activity.jsonl` (a prompt marker), `state/state.json`. `chat/` only when the chat copy is on. | No | 10 s |
| PreToolUse (before a tool call) | `Bash\|PowerShell\|Write\|Edit\|NotebookEdit` | The planned call, `guard-messages.json`, `state.json`, a script the command runs inside the project (up to 64 KB), `package.json`, `.gitignore`, read-only Git, and the files a commit or push would send | `state/state.json` guard counters only | Yes. A deny stops the call. An ask lets you decide. A warning adds a note for the tutor. | 8 s |
| PostToolUse (after a tool call) | `Bash\|PowerShell\|Write\|Edit\|NotebookEdit` | The finished call, the inbox folder, the file a Write or Edit changed (for tripwire checks only), `recent-user.json`, `ledger.jsonl` | `progress.jsonl` (only the inbox lines that pass the checks), `state/activity.jsonl`, `state/state.json`. It deletes the inbox files it read. | No | 10 s |
| Stop (end of an answer) | none | The final answer (in memory only), `profile.md`, `activity.jsonl`, `progress.jsonl` | `state/ledger.jsonl` (cut back when it grows large), `state/state.json`, `progress.jsonl` (concepts met), `chat/` only when the chat copy is on | No | 15 s |
| SubagentStart (a helper starts) | none | The helper's type name, from its input | Nothing. It prints one reminder for the helper. | No | 5 s |

Every hook except the guard and SubagentStart creates the tutor-data folders when they are missing, unless the project is a wide folder such as your home folder. The guard never creates them. Hook errors go to `state/hook-errors.log`, with the error type, the module and the line only.

Every hook runs through one launcher. The launcher is the command in `.claude/tools/hooks.json`. Only the last word changes, for example `pre-tool`:

```
python3 -I -B -X utf8 -c "import os,sys,runpy; (sys.version_info>=(3,9) or sys.exit('tutor hooks need Python 3.9 or newer')); p=os.path.join(os.environ.get('CLAUDE_PROJECT_DIR','.'),'.claude','hooks','dispatch.py'); (os.path.isfile(p) or sys.exit(0)); sys.argv=[p]+sys.argv[1:]; runpy.run_path(p,run_name='__main__')" pre-tool
```

The launcher is written this way for four reasons:

- `-I` ignores the environment and the current folder on the import path. A file named `json.py` or `random.py` in your project cannot replace the standard library.
- `-B` stops Python from writing cache files into your project. `-X utf8` makes text use UTF-8, which `-I` does not set on its own.
- If `dispatch.py` is missing, the launcher exits with 0, so Claude Code is not blocked.
- The project folder comes from `CLAUDE_PROJECT_DIR`. Claude Code sets this variable for hooks (checked 2026-10-07).

On Windows the launcher can use `py` with `-3` instead of `python3`. The doctor script tries `python3`, then `python`, then `py -3`, and writes the first one that works on your computer.

Failure rules:

- A hook that fails prints one line to the error stream and exits with 1. Claude Code treats that as a non-blocking error, and the work goes on.
- The safety guard fails open. If its own code breaks, the action goes on. A command with a danger word still becomes an ask.
- A deny is the only way a hook stops an action. It uses exit code 2.

## What you lose without Python

The tutor works from text alone. The output style, the rules, the skills, the permission rules and your written notes all work without Python. The hooks add facts, a guard and records. Without Python, the tutor is weaker at checking and counting.

| Part | With the helper scripts on | Without Python |
|---|---|---|
| State header at the start of a session | Printed by the start hook: date, folder check, profile, due reviews, offers | The tutor reads `profile.md` and `now.md`, and gives a one-line recap. It runs one read-only command for the date. |
| Time in each message | Printed in each message | The tutor runs `date` (macOS or Linux) or `Get-Date` (Windows) when it needs a time. |
| Safety guard before commands and file writes | Denies or asks, with a plain reason | Only the permission rules in `settings.json` and the written rules. |
| Secret check before commit and push | Reads what the commit or push would send | Not run. The `before-push` skill checks the files by hand with `git grep`. |
| Tripwires after an edit (new package, risky code pattern) | One nudge after the edit | Not shown. The tutor checks its own work, and can ask the `code-reviewer` helper to review a change. |
| Quote check for your words | Checks that your words come from your last three messages. The tutor sees `Saved:` or `Refused:`. | Not checked by a script. The tutor writes lines to `learner/notes.md`, copying words only from your last three messages. That is a rule the tutor follows, not a check. The scripts import the lines later as not checked yet. |
| Your list: levels, reviews and offers | Computed by a script | The tutor searches the card index and writes the lines by hand. |
| Length and jargon notices | Measured after each answer. A notice when answers grow too long. | Not measured. The tutor keeps to the level's limits itself. |
| Error and frustration facts | Printed in each message | Not printed. The tutor reads your message itself. |
| Chat copy (optional) | Written when you turn it on | Not written |
| Folder check for OneDrive, iCloud, Dropbox or a wide folder | Printed at the start | The tutor judges the path by reading it, and can run one read-only command to look at the folder. |
| `doctor.py check` and `progress` | Run by you or the tutor | The tutor reads the files by hand. |

What stays without Python: the output style, the rules and the eleven skills. The two helper agents stay, and so do the concept cards, which the tutor searches with Grep. The permission rules in `settings.json` stay. Your notes stay, and so do the Git and GitHub advice and the safety gates in `rules/safety.md`.

Turn the scripts on later with `doctor.py enable-hooks`. See "The scripts and what each one is for".

## The safety guard and its known gaps

The kit has three safety layers. Each layer catches a different kind of mistake. None of them is a sandbox.

| Layer | What it is | Needs Python? | What it reads |
|---|---|---|---|
| 1. Permission floor | Deny, ask and allow rules in `settings.json` | No | The start of each command and file name |
| 2. Guard hook | A script that reads each command before it runs, and each file write | Yes, and hooks on | Pipes, quotes, wrapper commands, scripts in the project (one level), and what a commit or push would send |
| 3. Written rules | `rules/safety.md` and the output style | No | Nothing. The model follows them. They are not enforced. |

The written rules set six gates. G1: save a point before a change to several files. G2: a `.gitignore` file, and no keys, before the first push. G3: use made-up data, not real client, patient, student or money data. G4: run a deploy checklist before you share. G5: never use bypass mode on a personal computer. G6: never force a push that was rejected.

The guard reacts in three ways: it stops a step, it asks you, or it warns the tutor. Examples:

| What Claude tries | What happens | Why, in plain words |
|---|---|---|
| Deleting the project folder, your home folder, a drive or `.git` (for example `rm -rf`) | Stopped. No yes button. | It would delete your work or your saved history. |
| Running a downloaded script at once (for example `curl ... \| sh`) | Stopped | You cannot see what the script does before it runs. |
| `git push --force` | Stopped | It can erase other people's work on GitHub. |
| Rewriting Git history (for example `git filter-repo`) | Stopped | It changes the saved history of the project. |
| Printing a secret file such as `.env` | Stopped | The secret would enter the chat, and the chat is stored. |
| `git push` (any form) | Asks you | Your work leaves your computer. You decide. |
| Deleting a folder with everything inside it (for example `rm -r src`) | Asks you | The folder and its contents are gone. Build folders such as `node_modules` are not asked about. |
| Deleting a file or folder outside the project | Asks you | It may belong to another project, or to you personally. |
| Writing to `.claude/settings.json` or `.claude/hooks/` | Asks you | It changes the safety rules. Only you should do that. |
| Running a helper script that changes hooks, sends notes or wipes data (`doctor.py enable-hooks`, `disable-hooks`, `share-notes`, `wipe`) | Asks you | It rewrites settings, sends notes out or removes data. |
| Starting Claude Code with hooks or permission prompts off (for example `claude --bare` or `--dangerously-skip-permissions`) | Asks you | The new session would not run this project's guard. |
| `git add .` before a `.gitignore` exists | A warning | Every file in the folder would go into Git, including secrets. |

A command longer than 20,000 characters asks you, and so does a tool call over 16 MB, because the check cannot read all of that text. A deny-level pattern in a long command still stops it.

Some folders are never flagged, because tools rebuild them: `node_modules`, `dist`, `build`, `__pycache__`, `.venv` and similar. Example files such as `.env.example` are never flagged either.

The secrets engine finds keys, passwords, private key blocks, database addresses with a password, and card numbers. It hides them before the kit's own copies are saved. The guard and the commit scanner use the same rules.

Its limits:

- It does not recognise a secret with an unknown shape. A password with only lower-case letters and no name in front is not hidden.
- When it redacts long text, it checks only the first 256 KB and replaces the rest with a note. A file write over 4 MB is asked about instead, because the check cannot read all of it.
- It does not change what Claude Code has already saved in its own transcripts.

The commit and push scanner runs before `git add`, `git commit`, `git push`, `gh repo create --push` and `gh pr create`. It reads what the command would send. If it finds a secret, a file with a secret-like name, or your private notes, it stops. If it cannot finish its check, it asks you.

### What the stop message means

When the guard stops a step, the message starts with "Stopped on purpose by the tutor safety guard" and names the rule in brackets. An ask shows the same kind of text in the permission prompt. The message names a rule, explains the risk, and gives a safe way to reach the goal.

- This is a safety stop. It is not a setup error.
- Read the two sentences. Ask Claude for the safe way the message names.
- The tutor must not retry the same goal with other words.
- If you do not know what the step does, answer no.

### What the guard cannot see

The test suite confirms that these tricks pass the guard today. The list of command-guard gaps is in the file `tests/guard-known-gaps.txt` in the kit's repository. That file is not in the `.claude` folder you copy, and it does not cover the commit and push scanner or the things the guard cannot see at all. The list below is a shorter summary of all of them, so you know the limits.

- Deleting many files from a list the guard cannot see, such as `find ... | xargs rm`. Only recursive deletes are asked about.
- Emptying or overwriting a project file with a redirect, `truncate` or `cat /dev/null >`. Overwriting is normal work.
- A file name built while the command runs: a glob such as `cat .e[n]v`, `$(echo .env)`, or a path built from pieces inside code.
- `grep -r` with a secret name and no file name.
- Code run by `python3 -c` or `perl -e` that sends or deletes files, except the simple download-and-run shape. Code that runs another file one level deeper is not read either.
- Aliases, `awk` programs, commands inside a container (for example `docker exec`), and compiled programs.
- Code compiled while the command runs (for example PowerShell `Add-Type`), and COM objects such as `Scripting.FileSystemObject`.
- `chmod -R 000` on the project folder, which locks it.
- A script that an earlier command downloaded. Each command is judged alone.
- A Python script that Claude wrote. The guard reads scripts written for the shell, PowerShell, batch files, Makefiles and `package.json`, but not Python files.
- For the commit and push check: a file that an earlier step of the same command creates, Git run from a script, `make` or an IDE, commit messages and tags, a secret split over two lines, and a change that exists only in a merge commit.

The guard also cannot see scripts that Claude did not write. It cannot see MCP tools, web addresses or edits made outside Claude Code. Commands you type yourself with `!` in the terminal are not checked either. A hook timeout or a broken `settings.json` also gets past it. A broken `settings.json` turns off every permission rule.

The honest line is this. The guard stops accidents and obvious mistakes. It does not stop a prompt-injected or determined agent.

Native Windows has no operating-system sandbox for commands. The built-in Bash sandbox runs on macOS, Linux and WSL2 (checked 2026-10-07). This kit does not turn it on.

## What happens in each permission mode

Claude Code has several permission modes. A mode sets what runs without a question. The guard is a PreToolUse hook, so it runs before the permission rules decide (checked 2026-10-07). The kit's code also handles the two modes where nobody can answer a question.

The mode names differ by surface. Desktop shows names such as Manual and Accept edits in the mode selector next to the send button. The terminal uses config values such as `default` and `acceptEdits`. The terminal also cycles modes with Shift+Tab (checked 2026-10-07).

| Mode (Desktop name, terminal value) | Runs without asking | What the guard still does | Our suggestion |
|---|---|---|---|
| Manual, `default` | Reading files only. Edits and commands ask you. | Shows its asks and stops its denies. | Good for the first week. You see every change. |
| Accept edits, `acceptEdits` | File edits in the project, and common file commands such as `mkdir`, `touch`, `rm`, `mv` and `cp` when they stay inside the project. Other commands ask. | Same. Its asks still show. Denies still stop. | The kit's starting mode in terminals. |
| Plan, `plan` | Reading and planning. Edits wait until you approve the plan. | Still runs before each command. | Use it to look at a project before a change. |
| Auto, `auto` (only when it is available) | Most actions, with a second model that reviews them. | Still runs. Hook prompts still show. | Not tested with this kit. Use with care. |
| Don't ask, `dontAsk` (terminal only) | Only pre-approved actions. Anything that would ask is denied. | The guard turns its asks into denials itself. | For scripts, not for learning. |
| Bypass permissions, `bypassPermissions` | Almost everything, without asking. Some actions still ask, such as explicit ask rules and deletes of critical paths. | The guard turns its asks into denials itself. Denies still stop. | Never on a personal computer (gate G5). |

Notes on the table:

- In Don't ask and Bypass mode nobody can answer a question. So the guard turns its asks into denials in its own code, and Claude reads the reason instead of running the step.
- Desktop: the mode you choose in the selector is remembered for that folder. It beats `defaultMode` in `settings.json`. Plan applies only to the current session. Don't ask is not in the selector. Auto appears only when it is available. Bypass needs the "Allow bypass permissions mode" setting on Pro and Max plans (checked 2026-10-07).
- Terminal: `settings.json` sets the starting mode, and Shift+Tab changes it during the session. The kit's `settings.json` sets `acceptEdits`. Without a setting, newer terminal versions start in Auto mode when it is available (checked 2026-10-07).

## What is stored, and how to wipe it

The tutor stores its notes in one folder. Git ignores that folder. Claude Code keeps its own record of each chat, and that record is separate from the kit's notes.

```
.claude/agent-memory/tutor-data/
  now.md                  where the project stands
  journal/                one file per day
  inbox/                  short files, read and then deleted by the scripts
  learner/
    profile.md            your settings
    progress.jsonl        your list (scripts only)
    notes.md              learning lines when the scripts are off
  chat/                   optional copy of your messages (off by default)
  state/                  counters, activity, ledger, recent messages, error log
```

The file `.claude/.gitignore` makes Git ignore the `tutor-data` folder, `settings.local.json`, backups and Python cache files.

How long things are kept:

| Item | How long | Where |
|---|---|---|
| Chat copy | 30 days, and only if you turn it on. Old copies are deleted when a session starts (startup or clear). | `chat/` |
| Your last messages (for the inbox check) | The last 5 messages, redacted, up to 4,000 characters each | `state/recent-user.json` |
| Ledger of answers | Grows until it passes about 160 KB. Then it is cut back to the last 200 rows. | `state/ledger.jsonl` |
| Activity log | Grows until it passes about 120 KB. Then it is cut back to the last 300 rows. | `state/activity.jsonl` |
| Hook error log | About 200 KB at most | `state/hook-errors.log` |
| Inbox files | Deleted after the scripts read them | `inbox/` |
| Your list, journal and `now.md` | Until you wipe them | `learner/`, `journal/`, `now.md` |
| Claude Code transcripts | Terminal: 30 days by default (`cleanupPeriodDays`). Desktop: kept at any age unless `desktopSessionCleanupPeriodDays` is set (checked 2026-10-07). | Your home folder, under `.claude/projects/` |

Privacy statements:

- Everything you type goes to Anthropic, so that Claude can answer. Claude Code also keeps a transcript of the chat as a file in your home folder.
- The kit's redaction hides secrets only in the kit's own copies. It does not change Claude Code's transcript. If you paste a key, rotate it at the provider. Deleting a copy does not make a key safe again.
- The chat copy is off by default. A project in a synced folder (OneDrive, iCloud, Dropbox or Google Drive) can upload the notes.
- The kit's scripts make no network calls of their own. One exception: `share-notes on` asks GitHub, through the GitHub tool `gh`, whether your repository is private.
- The hook error log holds the error type, the module and the line number. It never holds your message or a command.

Wipe the kit's data with the doctor script. The script first lists what would go. Then it asks you to type DELETE. Add `--yes` to skip the typing. Windows:

```
py -3 .claude/tools/doctor.py wipe chat
```

```
py -3 .claude/tools/doctor.py wipe chat --yes
```

macOS:

```
python3 .claude/tools/doctor.py wipe chat
```

```
python3 .claude/tools/doctor.py wipe chat --yes
```

`chat` deletes the optional chat copies. `state` deletes counters, logs and the ledger. `all` deletes everything in `tutor-data`, including your list and journal.

To wipe by hand, close Claude Code first. Then delete the `tutor-data` folder inside `.claude/agent-memory/`. The tutor creates it again when it needs it. Claude Code's own transcripts are in your home folder. The kit does not delete them, and you can remove them yourself.

## The scripts and what each one is for

The four scripts you use are in `.claude/tools/`. The tutor can run the health check for you. Hooks need no script to run.

| Script | What it is for | Who runs it |
|---|---|---|
| `doctor.py` | Health check, your list, turning hooks on or off, settings backups, the wipe, and a check of the kit's files | You, after a yes from the tutor. The tutor runs `check` and `progress`. |
| `install.py` | Copies the kit into a project folder, updates it, or removes it | You, from a terminal. The README's main path needs no terminal. |
| `validate.py` | Checks the kit's own files: links, sizes, skill files and the manifest | Maintainers of the kit |
| `selftest.py` | Runs the kit's offline tests | Maintainers, or you, to check the kit |

The doctor commands:

- `check` checks Python, Claude Code, settings, output style, safety rules, Git ignore lines and the kit files.
- `progress` shows your list in plain words. `progress numbers` adds the counters.
- `enable-hooks` adds the hook entries to `settings.json`, keeps a backup copy in `.claude/settings.json.tutor-backup`, and moves any text-only notes into your list. `disable-hooks` removes the hook entries again.
- `envcheck` lists the names in `.env`, never the values. `audit` lists everything in a folder that can run code.
- `share-notes on` or `off`. `on` lets Git track your notes, and only when GitHub, asked through `gh`, says the repository is private. `off` puts the ignore lines back.
- `wipe chat`, `state` or `all` deletes tutor data. `verify` checks the kit files and the safety lint.

Doctor commands on Windows use `py -3`. On macOS they use `python3`. Example for the check:

```
py -3 .claude/tools/doctor.py check
```

```
python3 .claude/tools/doctor.py check
```

Turning hooks on. In the Desktop app, type "turn on helper scripts" in the chat. The tutor asks yes or no first. In the terminal, use the interpreter name that passed the check:

```
py -3 .claude/tools/doctor.py enable-hooks --interpreter py
```

```
python3 .claude/tools/doctor.py enable-hooks --interpreter python3
```

Emergency switch. To turn every hook off without Python, save a file named `settings.local.json` inside `.claude`, with exactly this text: `{"disableAllHooks": true}`. Only you should create it. Remove that line or the file to turn the hooks back on.

`install.py` takes a project folder and these options: `--dry-run`, `--update`, `--uninstall`, `--enable-hooks`, `--interpreter NAME`, `--accept-existing`, `--yes-this-is-my-project` and `--skip-selftest`. Run `--dry-run` first. It shows what would change and writes nothing. Exit code 2 means the install was refused.

`selftest.py` takes `--quick`, `--security`, `--only NAME`, `--list`, `--verbose` and `--jobs N`. A full run takes a minute or more, depending on the computer.

## How the kit is tested, and what that does not prove

The kit's checks run at four levels, and each level checks something different. None of them proves how a real model behaves.

- Static checks: `validate.py` checks files, links, sizes and the manifest. `selftest.py` runs the offline tests of the scripts and the guard.
- The mock harness: the real Claude Code program runs against a fake model server. It checks what the model receives, which hooks run, and which prompts appear.
- Simulated sessions: the real hooks run with two simulated people, a tutor and a novice. A rubric judges the result.
- The owner's live check: a real account, in the Desktop app and in the terminal. The test report lists its steps. It has not been run yet, so this version has no real-model result.

What these tests do not prove:

- They do not prove how a real model answers. The simulated sessions are not a real model.
- They do not prove that the Desktop app shows every prompt as described.
- Python 3.9 is checked by a code scan. The repository's CI file has Python 3.9 and 3.13 jobs. They had not run for this build when this page was written. The macOS and Linux branches are not checked on a real machine yet.

The test report is in the repository's `docs` folder, in the file `test-report.md`. It says what was checked with a real model, and what was not.

## Limits of the design

The kit reduces mistakes. It does not remove them, and the limits below stay.

- A model can still do wrong. It can ignore a fact, judge a check badly, or write a claim as if it were proof.
- Hooks supply facts. The model decides what to say. A fact the model ignores changes nothing.
- Your notes are text, and a note can be wrong. Read `profile.md` and `now.md` when something seems off.
- The guard reads the text of a command. It does not run a script to see what the script does.
- Python is needed for the guard, the records and the checks. Without Python, the guard does not run.
- Claude Code, Desktop and GitHub change often. The kit checks facts when it teaches them, but a card can be out of date.
- The kit was built and checked against Claude Code 2.1.288, with offline tests on Python 3.12 and 3.14. No real model has run the whole kit yet. Newer or older versions may behave differently. Python 3.9 is the minimum the code is written for.

To check a fact, read the official pages. The Claude Code docs are at code.claude.com/docs. The GitHub docs are at docs.github.com. The Git docs are at git-scm.com/docs. The kit's rule `.claude/rules/checking-facts.md` explains how the tutor checks facts.
