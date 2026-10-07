# Stacks: boring defaults by project type

Read this file when a learner starts a project or changes a technical choice (skills new-project and think-first).
It gives a default for each project type, not an order. Recommend one default, give one reason, and let the learner decide.
A stack is the set of tools a project uses: language, framework, database and host.

(verify) marks a claim about a product that can change. Check the current docs before you say it to the learner.
Facts marked "checked 2026-10-07" were read in the vendor docs on that day. Re-check them when you teach.

## How to use this file
1. Find the project type. If the idea mixes two types, use the type of the part the learner builds first.
2. Ask the three questions of that type, one per message, with a suggested answer.
3. Recommend the default. Name the "next step up" as a later option. Show the anti-picks only when the learner or the AI proposes one of them.
4. Never write version numbers, prices, free-tier limits or licence terms from memory. Read the docs at decision time and cite the page.
5. Record the choice in a decision record (concept arch-decision-record) with the date and the pages you read.

## Rules for every type
- Boring first (concept arch-boring-technology): a tool with many users, clear docs and a long record.
- One innovation token per project: the learner may choose one new tool to learn, and the decision record names it. Everything else stays boring.
  The idea comes from Dan McKinley's essay "Choose Boring Technology". It says a company gets about three tokens; a beginner project gets one.
  Example: the learner wants to learn FastAPI. Then the database, the host and the page templates stay with well-known defaults.
- The AI must be able to check its own work. Prefer tools that start on the learner's computer with one command and show a result the learner can see.
- One program, one database, one place where it runs, until a measured problem says otherwise (concept arch-anti-overbuilt-stack).
- Docs-first protocol:
  1. Confirm the tool exists and is maintained: date of the last release, activity in its repository, who uses it.
  2. Read the docs for the exact version you will install.
  3. Check the licence and the cost, including what the free plan does not include.
  4. Build a small test version (a spike) before you commit to the tool.
  5. Write the decision record.
  6. Pin the versions you tested, in the lock file or the requirements file.
- Secrets live in environment variables or the host's secret store, never in code. Ignore `.env` before the first commit (concept arch-config-vs-code).
- Real personal data stays out of the project until the learner has a plan to store, protect and delete it (gate G3 in milestones.md).
- Hosts and paid services: look for a hard spending cap or prepaid credit, set a budget alert, and learn what the free plan stops doing, such as sleeping apps or disks that are reset on redeploy (verify).
- If the project already uses a tool, keep it. Do not switch tools for taste.

## 1. Static site (portfolio, landing page, small docs site)
- Default: plain HTML, CSS and a little JavaScript. No build step.
- Why it suits a beginner with an AI agent: the site is a few files you can read. Opening the file in a browser is the test. Very little can break.
- Verify at decision time:
  - the host's current free terms: is commercial use allowed, are there size, traffic or build limits, must the repository be public;
  - how HTTPS and a custom domain are set up, and which folder or branch the host publishes.
- GitHub Pages notes (checked 2026-10-07, verify):
  - on GitHub Free the repository must be public;
  - the terms say Pages is not meant to run an online business or a shop;
  - size, traffic and build limits exist; read the numbers on the day.
- Next step up: a static site generator (for example Eleventy, Hugo or Astro; verify which are current) when about 10 or more pages share one layout. Add a small server only when pages must differ for each visitor.
- Anti-picks: a single-page-app framework, a build toolchain with many plugins, a database for pages that rarely change, copied templates with tracking scripts nobody read.
- First three questions:
  1. Who visits, and what should they find or do in the first 10 seconds?
  2. How many pages are there, who changes them, and how often?
  3. Where will it live (domain, host), and may the code be public?

## 2. Small web app (accounts, data, forms)
- Default: one server-rendered program (a monolith). In Python, use Django.
  - Django includes a database layer (ORM), an admin site, URL routing, templates and a user login system.
  - It has built-in protection against SQL injection, cross-site scripting, CSRF and clickjacking, if you use its features as its security page describes (checked 2026-10-07, verify for the version you install).
- A smaller start in Python: Flask. It has no database layer and no form validation built in, so you must choose and learn add-ons (checked 2026-10-07, verify).
- Database: SQLite while you build. Use a managed PostgreSQL when many people write at the same time or you need more than one server.
  - SQLite's own guide says it allows many readers but only one writer at a time.
  - It also says SQLite normally works fine behind a website, except write-heavy or multi-server sites (checked 2026-10-07, verify).
- Pages: server templates and a little JavaScript. Tests: one smoke test per feature.
- For JavaScript learners: Next.js, or Express or Fastify with PostgreSQL. Fastify is a Node tool and is not the Python FastAPI. Verify the current router model and major version of Next.js first.
- Why it suits a beginner with an AI agent: login, forms and stored data are where mistakes hurt most. The framework ships tested versions of them, so there is less risky code to write by hand.
- Verify at decision time:
  - supported Python or Node versions and the framework's deployment and security pages for the version you install;
  - whether the host keeps local files (a SQLite file can be lost on restart) and offers database backups;
  - the rules for storing personal data in the learner's country.
- Next step up: managed PostgreSQL, background jobs for slow work such as email or reports, and a separate frontend only when a phone app needs the same data (then see type 3).
- Anti-picks: your own login code, microservices, GraphQL, state-management libraries, separate frontend and backend repositories, a serverless database as the first choice.
- First three questions:
  1. Who logs in, and what may each kind of user see or change?
  2. What are the three main things the app stores (the data model)?
  3. Where will real user data live, who backs it up, and what happens if it leaks?

## 3. API or backend service
- Default: FastAPI in Python. It checks requests with Python type hints and builds interactive API docs by itself (checked 2026-10-07, verify). Other good choices: Express or Fastify (two Node tools; Fastify is not FastAPI), or the Go standard library.
- Database: PostgreSQL. SQLite is fine for a first prototype.
- Describe the API in OpenAPI so the contract is written down (concept arch-interfaces-contracts).
- Login: use a tested library or an identity service, never your own token scheme (concept arch-anti-custom-auth).
- Why it suits a beginner with an AI agent: the learner and the AI can test each endpoint by clicking in the generated docs page, so "it works" is something you can see.
- Verify at decision time:
  - the docs of the login library, and the CORS and rate-limit settings of the framework;
  - the hosting model (always-on server or serverless): time limits, slow first requests, cost per request;
  - prices and free-plan limits of the host.
- Next step up: Django REST framework if you also want an admin site and login. Add background workers and caching when you measure a need. Add an API gateway only after you measure a problem.
- Anti-picks: a home-made token scheme, public endpoints that call a paid API without login or a cap, CORS that allows every site together with credentials, microservices.
- First three questions:
  1. Who or what calls this API: a web page, a phone app or another program?
  2. What are the main things (resources) and what can callers do with them?
  3. Who may call it, and what stops one caller from using it a million times?

## 4. Command-line tool or script
- Default: Python 3 with only the standard library: argparse for options, pathlib for paths, csv, json and sqlite3 for data. One file until about 300 lines.
- For chores of a few lines: a shell script on macOS and Linux, PowerShell on Windows. Say which shell the script needs.
- Anything that deletes or changes files gets a `--dry-run` option that only prints what it would do.
- Why it suits a beginner with an AI agent: nothing to install, and `--dry-run` lets the learner check AI-written code before it touches real files.
- Verify at decision time:
  - the Python version on the computer that will run it (`python --version`; macOS and Linux often need `python3`);
  - how other people will install it (for example pipx or uv; verify);
  - differences between Windows, macOS and Linux: paths, line endings, quoting.
- Next step up: split the file into modules and add tests. Use Typer or Click when the options grow (verify). Package it for others.
- Anti-picks: web frameworks, plugin systems, new configuration languages, destructive commands without a dry run, shell scripts that parse complicated text.
- First three questions:
  1. What goes in and what comes out (files, text, a table)?
  2. What could it delete or overwrite, and how will you preview that first?
  3. Who runs it, on which computer, and how often?

## 5. Data analysis
- Default: Python with pandas (or polars) in a notebook (Jupyter or VS Code) for exploring. Move steps you repeat into a script. Charts with matplotlib or plotly.
- Pin library versions in `requirements.txt` or a lock file. Keep raw data in a read-only folder and never edit it by hand. R with tidyverse is a good alternative.
- Why it suits a beginner with an AI agent: each step shows a result at once, and unchanged raw data means every result can be repeated.
- Verify at decision time:
  - the docs for the library versions you pinned;
  - the data's licence, and whether it holds personal data (if yes, stop and plan first);
  - file size against memory on the learner's computer;
  - clear notebook outputs before a commit, because outputs can hold personal data.
- Next step up: SQLite or DuckDB for files too big for memory (verify), a scheduled script, a dashboard tool (verify its hosting terms).
- Anti-picks: committing big or personal data files, a notebook as the only record of the steps, editing raw data by hand, big-data tools for small files.
- First three questions:
  1. What question should the data answer, and what will the answer look like (number, table, chart)?
  2. Where does the data come from, may you use it, and does it contain personal data?
  3. How big is it (rows, MB), and does it change over time?

## 6. Game
- Default: a 2D browser game with HTML5 Canvas and plain JavaScript, or a small game library such as Phaser (verify). For Python learners: Pygame (verify).
- Keep one game loop and one scene at first.
- Why it suits a beginner with an AI agent: you share it with a link, and the success test is playing it. No store and no installer.
- Verify at decision time:
  - the version and licence of the library or engine, and its export terms;
  - the licence of every picture and sound file;
  - browser support on the devices you aim at.
- Next step up: Godot (an open-source engine) when you need scenes, physics or export to many platforms.
  - Unity (C#) if the learner wants a large commercial engine; check its licence and fees on the day.
  - A small server only for scores or saved games.
- Anti-picks: online multiplayer, your own game engine, committing engine cache folders and big asset files, art or sound with an unclear licence.
- First three questions:
  1. What does the player do in the first 30 seconds, and what ends a round?
  2. On which device is it played, and with what controls (keyboard, touch, controller)?
  3. Which art and sound do you have the right to use?

## 7. Mobile app
- Default: a responsive web app first. It works in phone browsers and may be installable as a PWA (verify per phone system).
- If a store app is required: React Native with Expo (JavaScript or TypeScript), or Flutter (Dart). Choose by the language the learner will keep using. Expo describes itself as a React Native framework (checked 2026-10-07, verify).
- Why it suits a beginner with an AI agent: one codebase, a fast test loop, and no store account or fee while you learn.
- Verify at decision time:
  - store developer account fees and review rules;
  - the current SDK versions of Expo or Flutter;
  - how to test on a real phone and in an emulator;
  - whether the phone features you need (camera, location, push messages, offline use) work in a web app.
- Next step up: your own backend only when data must sync between devices. Native code only when no library can do the job. Then the store release.
- Anti-picks: a backend before you need one, native modules in week one, two codebases (iOS and Android) at once, publishing to stores before the web version works.
- First three questions:
  1. Who uses it, on which phones, and could a web page do the job?
  2. Which phone features do you need?
  3. Does it need accounts and data shared between devices, or can it work alone on one phone?

## 8. Bot or automation
- Default: a small Python script that uses the platform's official or well-known client library (or the `gh` command for GitHub tasks).
- Run it on a schedule with GitHub Actions, or with the computer's scheduler (cron on macOS and Linux, Task Scheduler on Windows).
- Tokens live in environment variables or the host's secret store.
- The script is safe to run twice (idempotent), logs what it did, has `--dry-run`, and has a hard cap on calls.
- Why it suits a beginner with an AI agent: you run it by hand first and read the log. The schedule is a few lines added last.
- Verify at decision time:
  - the platform's terms of service and rate limits;
  - token scopes: give the smallest permission that works;
  - scheduler rules. GitHub Actions scheduled workflows (checked 2026-10-07; read the current numbers):
    - have a shortest allowed interval, and can start late or be dropped when GitHub is busy;
    - run on the default branch;
    - in public repositories, are switched off after a long time without repository activity;
  - the cost per run of any paid API (concept arch-anti-paid-api-loop).
- Next step up: a small always-on host or worker with a queue, and alerts when a run fails.
- Anti-picks: scraping against a site's terms, unattended loops over paid APIs, running 24 hours a day on a laptop, tokens with full-account permission.
- First three questions:
  1. What starts it, and what is the one action it takes?
  2. What is the worst thing it could do if it runs wrong or twice, and how do you test that with a dry run?
  3. Which accounts and tokens does it need, with which smallest permission, and who is told when it fails?

## When the idea fits no type, or two types
- Ask what the learner wants to see working first, and use the type of that part.
- Mixed example: a web app plus a nightly bot. Build type 2 first. Add type 8 only when the app works and has a backup (concept arch-anti-no-backup).
- If the learner asks for a tool that is not named here, apply the docs-first protocol. Do not refuse it, and do not praise it. Show the trade-off (concept arch-tradeoffs).
