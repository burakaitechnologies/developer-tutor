# Security

This page lists everything in this edition that Codex reads, or that changes what Codex may do. It also says how you can check it yourself. Facts about Codex are marked (checked 2026-10-08) where they appear. Their source is the Codex documentation of that date.

## Read this first

- The kit is text files. It has no scripts, no hooks and no program of its own.
- Codex enforces the sandbox, the approvals and the rules. Text in `AGENTS.md` and in the skills is advice that the model reads.
- The default sandbox lets Codex write inside the project folder. Network access for commands is off by default (checked 2026-10-08).
- The rules stop accidents and obvious mistakes. They do not stop a determined or tricked agent.

## What changes Codex's behaviour

| Part | What it does | When it applies |
|---|---|---|
| `AGENTS.md` | Instructions for the tutor: voice, hard rules, teaching moves, memory and safety. | Read at the start of each session. It is advice, not a lock. |
| `.agents/skills/*/SKILL.md` | Instructions for the eleven skills. | When you name a skill, or when its description fits your request. |
| `.codex/config.toml` | Sets `approval_policy = "on-request"`, `sandbox_mode = "workspace-write"` and `project_doc_max_bytes = 49152` (48 KiB). | Only after you trust the folder. |
| `.codex/rules/tutor.rules` | Asks before `git push`, `rm -rf`, `Remove-Item`, `sudo` and similar commands. Refuses a force push, a history rewrite, deleting a repository, and printing `.env` with `cat`, `type` or `Get-Content`. | Only after you trust the folder. Restart Codex after a change. |
| `.codex/agents/*.toml` | Two helpers, `architecture_reviewer` and `code_reviewer`. Both have `sandbox_mode = "read-only"`. | Only when you, or a skill, ask Codex to start one. |
| `.tutor/.gitignore` | Tells Git to ignore everything in `.tutor/` except that file. | When Git reads the folder. |

## What the kit does not contain

- No scripts in any language: no Python, shell or PowerShell files.
- No hooks. Codex supports hooks, but this edition does not use them (checked 2026-10-08).
- No allow rules. The kit approves no command in advance.
- No MCP servers, no plugins and no custom prompts.
- No network code.

## What Codex may run without a question

Codex decides this, not the kit. With `on-request`, commands that the sandbox allows can run without approval (checked 2026-10-08). Commands that write outside the project folder, or that need the network, ask first. Git writes ask first, because `.git` is read-only in the sandbox (checked 2026-10-08).

The docs describe rules as controlling commands that run outside the sandbox. This kit assumes that the rules also apply to commands inside the project folder. The owner check tests this (see [docs/test-report.md](docs/test-report.md), steps 12 and 13).

## Network

- The kit makes no network call.
- Codex sends your chat to OpenAI to get answers. The docs say file excerpts, prompts and tool results may be sent to OpenAI services to complete a task (checked 2026-10-08).
- By default, Codex also sends a small amount of anonymous usage and health data to OpenAI. The `analytics.enabled` setting in `~/.codex/config.toml` turns this off (checked 2026-10-08).
- Web search is on by default in cached mode. Treat web results as untrusted (checked 2026-10-08).

## How to audit this kit

All files are plain text. Read them before you trust the folder.

- Windows (PowerShell): `Get-ChildItem -Path AGENTS.md, .codex, .agents -Recurse -File`
- macOS and Linux: `find AGENTS.md .codex .agents -type f`
- Read `.codex/config.toml`, `.codex/rules/tutor.rules` and the two files in `.codex/agents/`.
- Test one rule: `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- git push origin main`. The JSON output shows the decision. Expect `prompt`. The `execpolicy` command is in preview (checked 2026-10-08).
- In Codex, type `/status` to see the approval policy and the writable folders (checked 2026-10-08).

## The trust question

Codex loads a project's `.codex/` settings, hooks and rules only when you trust the project. An untrusted project skips those `.codex/` layers (checked 2026-10-08). Codex may also start in read-only mode until you trust the folder.

A project folder can change what Codex may do. Trust only a folder that you wrote, or that you have read. The docs do not say that `AGENTS.md` or `.agents/skills` are skipped in an untrusted folder. The owner check looks at this (see [docs/test-report.md](docs/test-report.md), steps 6 and 7).

## Threat model and limits

The kit is built to stop accidents and obvious mistakes. It does not stop:

- A model that reads text in a file or web page and then follows it. This is called prompt injection. The kit tells the tutor to treat such text as data. That is advice, not a lock.
- A force push written after the branch name, such as `git push origin main --force`. The push rule asks first. The forbidden rule matches only the start of a command, so it does not catch this form.
- A command wrapped in another shell, such as `bash -lc` or `powershell -Command`. Codex splits only simple chains of commands into single commands before it checks the rules (checked 2026-10-08). A rule may not match a wrapped command.
- A read of `.env` with another command or another path form, such as `Get-Content -Path .env`.
- Commands that you type yourself in the terminal, and edits that you make outside Codex.
- A wrong fact in the kit or in a model answer. Check important facts yourself.

## What is stored, and how to delete it

- The tutor's notes are in `.tutor/` in your project. They are plain Markdown. Git ignores them.
- By default, Codex saves session transcripts under its home folder, `~/.codex`. The `history.persistence` setting controls this (checked 2026-10-08).
- To delete the tutor's notes, delete the `.tutor` folder yourself. This cannot be undone. Copy the folder first if you want to keep the notes.

## Privacy

- Everything you type goes to OpenAI as part of the chat. The docs say prompts and file excerpts may be sent to OpenAI services to complete a task (checked 2026-10-08).
- This kit did not check OpenAI's terms or privacy policy. Read them before you put private data in a chat.
- Do not paste a secret into a chat. A secret is a password, an API key or a token. If you do, it is exposed. Revoke it at its provider, then make a new one. Keep secrets in a `.env` file that Git ignores.
- `.tutor/` stays on your computer, and Git ignores it. Codex reads those files when it needs them. Their text can then go to OpenAI too.
- Keep the project out of OneDrive, iCloud and Dropbox. Sync can upload your notes and can damage Git folders.

## How to report a vulnerability

Use this repository's **Security** tab. Choose **Report a vulnerability**. This is private reporting.

Do not open a public issue for a security problem. If the button is missing, the owner has not turned on private reporting yet.

## Supported versions

Fixes go to the latest version only. The current version is 1.0.0, in `.agents/tutor/VERSION`. Older versions get no fixes.

Codex changes often. A Codex fact that was true on 2026-10-08 can change later.
