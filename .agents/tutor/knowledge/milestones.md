# Milestones: a menu, not a syllabus

Read this file when the learner asks "what should I learn?" or when the current work touches a milestone.
Codex facts in this file (commands, approval modes) were checked 2026-10-08.
Offer one or two milestones, one sentence each, and let the learner choose. The learner's real project decides the order.
There are no progress bars and no percentages. A milestone is a group of skills to pull in when the work needs them; it is not something to finish.
A skill counts as learned when the learner shows its "Alone when" signals unprompted, in their own words or actions. "Ok" and "I understand" are not signals.
Look for each signal again in a later session before you treat it as learned. Each concept id is a card: search `.agents/tutor/knowledge/concepts/` for `"id": "<id>"`.

Order
- A complete beginner usually starts with M1, M2, M3. Skip what the learner already shows.
- Pull a milestone forward when the work needs it. A first API key pulls M5 before M9.
- The `.gitignore` part of M5 comes before the first push in M4 (gate G2).
- Needs: M3 needs M2. M4 needs M3. M7 needs M6. M8 needs M5 and M7. M9 needs M7, and M8 if the API has a key. M10 needs M7. M11 needs M3 (the pull request needs M4). M12 needs M4, M5 and M8, and M10 if the app stores data.

## M1 Terminal basics and folders
Project: recipe page. Make a folder `recipe-page`, open a terminal in it, list the files, go into a sub-folder and come back.
Concepts: term-terminal, term-look-around, term-cd, term-paths, term-command-anatomy, term-stop-program, term-file-ops, files-project-structure, files-hidden-dotfiles, cc-start-in-project-root, cc-what-is-claude-code, cc-install-login, cc-surfaces, cc-trust-dialog, cc-slash-commands, cc-shell-mode, term-shell, term-help, ai-llm, arch-folders-by-purpose, term-install-git-python
Alone when: you say which folder the terminal is in without looking it up; you move into a sub-folder and back; you list the files and name two; you explain why `css/style.css` works in one folder and fails in another.
Stumbling: wrong folder ("No such file or directory"); backslashes on Windows; PowerShell, Command Prompt and Bash use different commands; fear that `ls` or `cd` can break something (they change nothing); Codex started in a sub-folder.

## M2 First project and README
Project: recipe page. Build `index.html` and `README.md` in the project folder and open the page in a browser.
Concepts: arch-goal-success-test, arch-mvp-scope, proj-folder-layout, proj-readme, files-markdown, files-extensions-types, files-code-editor, web-html, web-css, cc-prompting-well, cc-claude-md, cc-permission-prompts, cc-permission-modes, ai-prompting, web-website, web-javascript-browser, web-url, web-client-server-http, web-localhost-ports, files-cloud-sync, test-manual-checklist
Alone when: you write one sentence that says what the page does and how you will check it; you open the page in the browser yourself; you edit the README in your own words; you say which file holds the recipe text; you read a permission prompt and say what it asks for.
Stumbling: a file saved as `index.html.txt` because extensions are hidden; a first request for a whole website instead of one page; the project inside OneDrive; "I changed the file but the page is the same" (see diagrams.md, picture b); approving prompts unread.

## M3 Save points with Git (init, add, commit)
Project: recipe page. Commit the first version, change one ingredient, look at the change, commit again, then undo a new edit.
Concepts: git-version-control, git-init, git-status, git-four-places, git-staging, git-commit, git-commit-message, git-diff, git-log, git-restore, git-identity, proj-small-commits, cc-rewind-checkpoints, git-repo
Alone when: you run `git status` before a commit and say what it shows; you stage named files, not everything; your commit message says why; you read `git diff`, then undo an uncommitted edit with `git restore`; before a change to several files you ask for a save point (gate G1).
Stumbling: "Author identity unknown"; believing `git add` saves or uploads; an editor opens for the commit message; line-ending warnings; `git restore` loses edits for good; `/fork` copies the chat; it is not a file backup, so Git is the safer save point.

## M4 GitHub account, remote, push
Project: recipe page. Create a private repository on GitHub, connect the folder to it, push, and open it on github.com as a stranger would.
Concepts: gh-account, sec-two-factor, gh-repo, gh-visibility, gh-cli, gh-auth, git-remote, gh-connect-local-repo, git-push, git-fetch-pull, git-clone
Alone when: you create the account and two-factor sign-in yourself (the tutor never types or sees your credentials); you say the difference between Git and GitHub; you say what `git push` sent and where; you read a "rejected" message and stop instead of forcing it (gate G6); you clone the repository into a temporary folder to test it.
Stumbling: a push rejected because the remote has commits you do not; sign-in and permission errors; `master` vs `main`; a repository made public by accident; the wrong e-mail address in commits.

## M5 .gitignore and secrets
Project: quote-of-the-day bot. It needs a made-up key. Put the key in `.env`, ignore `.env`, add `.env.example`, then run a leak drill with the fake key.
Concepts: git-ignore, sec-secrets, sec-secrets-and-ai, sec-rotate-leaked-key, git-secret-pushed, arch-config-vs-code, arch-anti-frontend-secrets, sec-personal-data, prog-variables, prog-data-types, prog-operators, prog-conditions, prog-loops, prog-lists
Alone when: `git status` does not list `.env` and you can say why; `.gitignore` exists before the first push and before the first real key (gate G2); you say where the key lives and who can read it; in the drill you say "revoke first, then clean up"; you never paste a key into the chat.
Stumbling: `.env` committed before it was ignored (ignoring does not untrack a file Git already tracks); "deleting the line removes the key" (it stays in history); a key in browser JavaScript; a key in a screenshot.

## M6 Reading errors and debugging
Project: todo list. The "Add" button does nothing (a planted bug). Find out why.
Concepts: test-read-error, prog-errors, prog-stack-trace, test-reproduce, test-print-debugging, test-bisect, web-devtools, git-log, cc-btw, cc-clear, cc-resume, cc-context-window
Alone when: you copy the exact error text, not a screenshot; you say which file and line it names; you state a guess before you ask Codex; you change one thing and run it again; you write the cause in one sentence.
Stumbling: "it does not work" with no error text; a warning mistaken for an error; a "fix" that hides the error; several changes at once; the top lines of a trace point into a library, not your file; a long chat where Codex loses early details (start fresh with `/clear`).

## M7 Running and testing code
Project: quote-of-the-day bot. Run it from a fresh terminal, then write 3 tests: a normal quote, an empty list, a missing file.
Concepts: prog-program, prog-functions, prog-input-output, prog-file-io, prog-json, term-exit-codes, term-path-not-found, test-run-suite, test-unit-test, test-edge-cases, test-regression, ai-verify-output, cc-verification, ai-hallucination, arch-simplicity-size, prog-comments-naming
Alone when: you start the program and stop it with Ctrl+C; you run the tests yourself and read one failing test; you ask for a failing test before you accept a fix; you name one thing your tests do not cover; you do not accept "done" until you saw the check pass.
Stumbling: `python` vs `python3` vs `py` and "command not found"; tests that check nothing; Codex "fixes" a test instead of the code; tests that are not found because of file or folder names; a program run from the wrong folder.

## M8 Dependencies and environment variables
Project: quote-of-the-day bot. Add one small, well-known library. Read a setting such as `QUOTE_LANGUAGE` from `.env`.
Concepts: prog-imports, prog-dependencies, term-package-managers, sec-supply-chain, arch-dependency-cost, arch-build-vs-use, term-env-vars, arch-config-vs-code, test-works-on-my-machine, proj-environments, arch-boring-technology
Alone when: you read an install command in a permission prompt and say which package it fetches and why; you find the file that lists the dependencies; a fresh clone in a temporary folder runs when you follow only the README; `.env.example` lists names only.
Stumbling: the dependency folder (`node_modules`, a virtual environment) committed to Git; a variable set in one terminal but missing in another; `.env` not found because the program starts in another folder; a misspelled package name.

## M9 HTTP and APIs basics
Project: quote-of-the-day bot. Fetch one quote from a public API that needs no key (read its terms first), print it, and handle a 404 and a lost connection.
Concepts: web-url, web-client-server-http, web-status-codes, web-api-endpoint, prog-json, prog-dicts, arch-error-handling, arch-anti-paid-api-loop, sec-https, cc-usage-limits
Alone when: you send one request by hand (address bar or a command) and read the JSON; you name two fields in it; you change a query parameter and say what changed; you trigger a 404 on purpose and say what it means; you say what 429 means.
Stumbling: API vs website; JSON vs a dictionary in code; a CORS error when a web page calls an API; the API changes its answer or is down; a retry loop with no limit.

## M10 A small database
Project: todo list. Keep the items after a restart in SQLite (a database in one file). Use made-up items only (gate G3).
Concepts: data-files-vs-db, data-tables, data-sql-basics, data-sqlite, data-backup-restore, data-csv-json, arch-data-model-first, arch-where-state-lives, arch-anti-sql-strings, arch-anti-no-backup, proj-backups, sec-input-validation
Alone when: you run a SELECT and read the rows; before Codex runs an UPDATE or DELETE you say which rows will change; you say what DELETE without WHERE does; a backup copy exists before a structure change; the database file is listed in `.gitignore`.
Stumbling: the database file committed to Git; "database is locked" when two programs open it; a CSV file mistaken for a database; real people's data in test data; SQL built by joining strings; a structure change that loses rows.

## M11 Reviewing AI-made changes
Project: todo list. Ask for a "mark as done" feature on a new branch, review the diff with a checklist, open a pull request and merge it.
Concepts: proj-code-review, git-diff, git-branch, git-switch, git-merge, git-conflict, gh-pull-request, gh-review-pr, cc-plan-mode, cc-subagents, proj-small-commits
Alone when: before you accept a change you name the files created, changed and deleted; you ask about at least one thing (a new dependency, a deleted file, a key, an unrelated change) or accept it for a stated reason; you write the pull request description yourself; you say what a merge does; you use plan mode (`/plan`) before a change to several files.
Stumbling: approving a long diff unread; one huge change instead of small ones; conflict markers (`<<<<<<<`) that look like damage; Git branch vs the `/fork` command (it copies the conversation, not the code); Codex changing a test so it passes.

## M12 Deploying and sharing safely
Project: recipe page. Publish it as a static site (for example GitHub Pages) and open the link on your phone. Read the host's current free-plan terms on the day.
Concepts: proj-environments, proj-deployment, proj-hosting-types, gh-pages, web-hosting-dns, sec-https, sec-least-privilege, arch-security-by-default, arch-anti-custom-auth, arch-reversible-decisions, gh-security-alerts, proj-license
Alone when: you answer the deploy checklist in your own words (who can read this data, who can change it, what happens with bad input, where the keys are; gate G4); the public link works on a phone; secrets are only in the host's settings; you went back to an earlier version once; a fresh clone runs by the README.
Stumbling: it works on your computer but not online (capital letters in file names, a missing variable, the wrong build command); a public repository with a secret in its history; a login or a form for strangers added too early; free-plan limits; domain changes that take time.

## Hard gates (they hold in every milestone, in any order)
- G1 Save point before a multi-file change: commit or branch first. details: AGENTS.md, section Safety.
- G2 `.gitignore` in place and no keys in files or chat before the first push and before the first API key. details: AGENTS.md, section Safety.
- G3 No real regulated or private data (patients, clients, students, money): use made-up data. details: AGENTS.md, section Safety.
- G4 Run the deploy checklist before anything is shared with strangers. details: AGENTS.md, section Safety.
- G5 No full-access mode on a personal computer. details: AGENTS.md, section Safety.
- G6 A rejected push is a stop sign: read the message, never force it. details: AGENTS.md, section Safety.
