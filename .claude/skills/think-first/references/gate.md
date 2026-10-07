# The gate: 10 questions, 23 anti-patterns, two options

Read this file at step 5 of the full gate in think-first. The learner sees the three answers that decided, not all ten. Questions 5 and 6 are always put to the learner, at every gate level: they are the access question of think-first step 4.

## The 10 questions

Each line has the question, why it matters, and a beginner answer for a family recipe site. Cards with plain explanations are in `.claude/knowledge/concepts/arch.jsonl` (find the id in `.claude/knowledge/concepts-index.txt`, then Read that line with `limit` 1).

1. **Who uses it, and what can they do when it works?** Why: without a user and a visible result, nobody can tell when you are done. Answer: "My family reads and adds recipes. Done when my aunt finds one on her phone." (arch-goal-success-test)
2. **What is the thinnest version that works from start to end, and what do we leave out for now?** Why: a small first version shows early whether the idea works. Answer: "A page that lists recipes from a file. Not now: login, photos, search." (arch-mvp-scope)
3. **Does a built-in feature, a framework feature or a hosted service already do this?** Why: code you do not write cannot break. Answer: "A shared document may be enough. A site is worth it if the family wants search." (arch-build-vs-use)
4. **Is the tool well known, and did we read today's docs for this version? What is the one new thing you want to learn here?** Why: known tools have more correct examples, so the AI makes fewer mistakes. Answer: "Django. Docs page checked this session: <page name>. New thing to learn: none." (arch-boring-technology)
5. **Where does the data live, who can read or change it, and how is it backed up and restored?** Why: data is the one thing you cannot rebuild. Answer: "A SQLite file in the project folder, copied to a USB stick weekly; I restored it once to test." (arch-where-state-lives, arch-anti-no-backup)
6. **Who can open it? Is the login a proven one? What does a stranger who finds the address see?** Why: a home-made login is easy to get dangerously wrong. Answer: "Only family, with the framework's login. A stranger sees a login page." (arch-anti-custom-auth)
7. **Which keys or paid services are involved, where are they stored, and what is the spending limit?** Why: a leaked key or a loop that calls a paid service costs real money. Answer: "No keys yet. A photo service later: key in `.env`, limit set in its dashboard." (sec-secrets, arch-anti-paid-api-loop)
8. **If this code is wrong, what is the worst thing that happens, and what limits the damage?** Why: the worst case tells you how much care a step needs. Answer: "A recipe is lost. The weekly copy limits that." (arch-security-by-default)
9. **How will we know it works, and how will we know when it breaks?** Why: without a check, the first person to find a problem is a user. Answer: "Add a recipe, reload, see it again. Errors go to a log file I can open." (arch-logging, test-manual-checklist)
10. **Is it saved in Git, can we go back, and how costly is it to change our mind?** Why: a choice that is hard to undo needs a decision record now. Answer: "Saved in Git. Moving to PostgreSQL later takes about a day; that goes in the record." (arch-reversible-decisions, arch-decision-record)

Which three decided? Pick the answers that changed the plan most, or the riskiest for this project. For each, add the cost of the shortcut in one sentence: "Skipping the backup is faster today. If the file is lost, the recipes are gone."

## The five worries (gates 3 to 5)

The learner picks the one that worries them most, and says why. Start your own answers with it. If they say "not sure", choose for them and give the reason.
- Who uses it: questions 1 and 6.
- How many at once: questions 5 and 6.
- What must never be lost: questions 5 and 7.
- What if it is wrong: question 8.
- How hard it is to undo: question 10.

## 23 anti-patterns: what hurts, and the safer default

Use the list to check a plan or a diff. Name at most the top two problems to the learner, with the safe default. Cards exist for rows 1, 3, 6, 7, 13 and 15 (`arch-anti-*`).

1. **Many small services (microservices).** Each one is another thing to break and to learn. Default: one program, one database, one place it runs.
2. **A tool stack bigger than the problem.** Every library is code you do not understand. Default: the smallest tool that does the job.
3. **Home-made login.** It looks easy and is easy to get wrong. Default: the framework's login or an identity service.
4. **Home-made encryption.** Encoding is not encryption, and your own scheme has holes you cannot see. Default: a well-known library.
5. **Passwords saved as plain text.** A copied database then opens the user's other accounts. Default: the framework's password hashing.
6. **SQL built by gluing text together.** A user can type commands into a name box. Default: queries with placeholders, or the framework's database layer.
7. **Secrets in browser code.** Anyone can read what the browser receives. Default: keys only on the server, in `.env`.
8. **No Git and no tests.** You cannot go back or see what broke. Default: Git before the first change that touches more than one file (the first save point comes after the first build, per tutor-setup); one smoke test per feature.
9. **One giant file.** You and the AI cannot review 2,000 lines without mistakes. Default: one job per file.
10. **Copy-pasted blocks.** A bug must be fixed in every copy. Default: share the code after the third copy.
11. **Layers and helpers nobody needs yet.** Abstractions cost reading time. Default: concrete code first, abstract after real repetition.
12. **A trendy tool the AI cannot check.** It may write code for a version that does not exist. Default: a well-known tool, docs read today, one new thing at most.
13. **No backup of data.** A backup you never restored is a hope. Default: a written backup and restore step, tested once.
14. **Surprise hosting bills.** Some services charge per request. Default: a spending cap, a budget alert, and knowing what the free plan stops doing.
15. **Loops that call a paid service without a limit.** One bug can spend your balance overnight. Default: a maximum number of calls, a dry-run mode, a limit in the provider's dashboard.
16. **Databases and ports open to the internet.** Scanners find them within minutes. Default: listen on 127.0.0.1, publish only the web port.
17. **Trusting what users type.** Input can carry commands or scripts. Default: check input on the server and let the framework escape output.
18. **Errors swallowed silently.** Small bugs become mysteries. Default: show clear errors in development, log them, set time limits on network calls.
19. **Too many dependencies.** Each one adds breakage and risk. Default: few, popular, maintained, with the lock file saved.
20. **Hiding a button instead of checking permission.** The address still works. Default: the server checks whose record it is.
21. **Test and live share one database or key.** A test can delete real data. Default: separate databases and keys.
22. **Login tokens in `localStorage`.** Any script on the page can read them. Default: cookies set by the server, marked HttpOnly and Secure.
23. **A text file as a database with several writers.** Two saves at once can corrupt it. Default: SQLite before anything bigger.

## Two options, with trade-offs

Show exactly two real options. A third that is clearly better replaces the weaker one. Compare both on the same points: effort now, cost, risk, how hard to undo, what you give up. Then recommend one, tied to facts of this project, and say what would change your mind. The learner decides.

Example, after reading the docs on the day:
- **Option 1: a SQLite file.** One file, nothing to install. Fine while one person saves at a time. Gives up: many people saving at once.
- **Option 2: PostgreSQL.** A separate server. Fine for many writers. Gives up: setup time and a hosting bill. Harder to undo.
- **I recommend 1**, because only your family saves recipes and you can move later in about a day.
- **What would change my mind:** more than a few people saving at once, or the host deleting local files on restart.
- Checked this session: the SQLite "appropriate uses" page (name the page and today's date). Not checked: your host's backup rules. If you did not run that lookup now, write "from the kit notes dated <date>" instead of "checked".

When the learner names the options first (gate 6 and later), ask for two options and a pick, then show yours. Compare: where you agree, where you differ, and what each pick costs. Do not grade.
