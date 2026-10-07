# What the health check says, in plain words

Use these lines to explain each result of the simple checks in tutor route D. Problems first, then notes, then one line for "everything else is fine".

Facts about Codex in this file were checked on 2026-10-08. If a result does not match these lines, say what you saw and do not guess the cause.

- Codex version (`codex --version`) prints a version number. The kit does not name a minimum version. Not found: the CLI is not installed, or it is not on the PATH. The app has its own copy, so ask which one the learner uses. For an install, read the current install page from `https://developers.openai.com/codex/llms.txt` and follow its steps. Do not guess them.

- `/status` shows the approval policy and the writable roots. The writable roots should list this project folder. If they do not, the folder is not trusted yet, or the sandbox is read-only. Codex may start in read-only until the folder is trusted (checked 2026-10-08). Say: trust the project folder when Codex asks, or choose **Ask for approval**. In the app and IDE that is the permissions control under the message box. In the CLI it is `/permissions`.

- `AGENTS.md` is missing from the project root: the kit file was not copied, or Codex was started in a sub-folder. Codex reads `AGENTS.md` from the project root, which is the folder that holds `.git`. With no project root, it reads only the current folder (checked 2026-10-08). Say: open the project folder itself and start again. If the file is missing, copy it from the kit.

- `.agents/skills` is missing: the skills, including `$tutor`, do not appear. Say: copy the folder from the kit. If a skill still does not appear after that, restart Codex (checked 2026-10-08).

- `.codex/config.toml` or `.codex/rules/tutor.rules` is missing, or the folder is not trusted: the project settings and the command rules do not load (checked 2026-10-08). The command rules stop some risky commands before they run. Say: trust the folder, then restart Codex after any change to a rules file (checked 2026-10-08).

- `.tutor/` is missing: no problem before the first note. The tutor creates the folder when it writes the first file in it.

- `.tutor/.gitignore` is missing: a problem. Git could commit the private notes. Say: copy `.tutor/.gitignore` from the kit before the first save point, after a yes. This is a file copy, not a Git command.

- Not a Git project (`git status` says it is not a repository): nothing is wrong yet. Git is set up later, by new-project, after a yes.

- Git name and e-mail not set: the first save point asks for them. Not urgent.

- `.gitignore` is missing the `.env` line or the `.tutor/` line: a secret or a private note could be committed. Fix: new-project adds the missing lines, after a yes.

- `.gitignore` saved as UTF-16: Git cannot read it. Save it again as UTF-8.

- Git approvals: Codex asks before `git add`, `git commit` or `git push`. That is normal, because `.git` is read-only in the sandbox (checked 2026-10-08). Say what the command does before it runs.

- Instruction files too large: Codex reads instruction files up to a total of 32 KiB by default, including the learner's own `~/.codex/AGENTS.md` (checked 2026-10-08). Codex stops adding files when the total reaches the limit, so a large personal file can leave out the kit's `AGENTS.md`. Say: keep the personal file short. Raising `project_doc_max_bytes` in the config is the learner's choice.

- Lesson data missing (for example `.agents/tutor/knowledge/concepts-index.txt`, or a skill's references): restore the `.agents` folder from the kit.

- Kit files changed by the learner: fine if the change is on purpose. This edition has no installer. A newer kit file is copied by hand, after the learner has compared the two.

- Everything else is fine: say so in one line.
