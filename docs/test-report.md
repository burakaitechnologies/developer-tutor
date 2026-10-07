# Test report

This report says what was checked, how you can repeat each check, and what was not checked. Build date: 2026-10-08.

**Status: ported, not tested.** This edition was ported from the main branch. No Codex session has run the kit. No live check with a real Codex login has been recorded.

## 1. What was checked, and how

These checks test the shape of the files only. They do not test how Codex behaves. Run each command from the repository root. The Status column says whether the check was run on the build date. The Result column is for the owner to fill in.

| Check | Command | Expected result | Status on the build date | Result |
|---|---|---|---|---|
| TOML parses: `.codex/config.toml` | `python -c "import tomllib; tomllib.load(open('.codex/config.toml','rb'))"` (Python 3.11 or newer) | No error | done on the build date | |
| TOML parses: `.codex/agents/*.toml` | The same command for each of the two files | No error | done on the build date | |
| AGENTS.md size | `wc -c < AGENTS.md` (PowerShell: `(Get-Item AGENTS.md).Length`) | Under 32768 bytes. Ideally under 20480 | done on the build date | |
| Skill front matter, 11 skills | `sed -n 1,8p .agents/skills/<name>/SKILL.md` (PowerShell: `Get-Content -TotalCount 8`) | Line 1 is `---`. Then `name` equal to the folder name, `description`, and `---`. No other key | not run | |
| No scripts in the kit | `find . -type f \( -name "*.py" -o -name "*.sh" -o -name "*.ps1" -o -name "*.js" \)` | No lines printed | done on the build date | |
| Rule file decisions | `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- git push origin main` (and with `-- git push --force origin main`) | `prompt` for the first, `forbidden` for the second | not run | |
| Links in the root files | Open each relative link in README.md, SECURITY.md, CONTRIBUTING.md and CHANGELOG.md | Every target exists | done on the build date | |
| Leftover words | `grep -n -iE "<pattern in CONTRIBUTING.md, check 6>" README.md SECURITY.md CONTRIBUTING.md CHANGELOG.md docs/test-report.md` | Every hit is intentional | done on the build date | |
| Line endings and spaces | `tr -cd '\r' < <file> \| wc -c` (expect 0), `grep -n " $" <file>` (expect nothing) | 0 carriage returns, no trailing spaces | done on the build date | |
| Byte-order mark | `head -c 3 <file> \| od -An -tx1` | Not `ef bb bf` | done on the build date | |

## 2. Not verified with Codex

No Codex session has run the kit. A file-shape check does not prove the points below. The owner's live check in section 3 is the first real run.

- Codex reads `AGENTS.md` at the start of a session, and the tutor follows its voice, its hard rules and its teaching moves.
- Skills start from `$name` and from `/skills`, and Codex picks a skill from plain words by its description.
- The skill list fits the budget: eleven skills, each description at most 210 characters, within 2% of the context window or 8,000 characters.
- The rules match on Windows PowerShell commands, including the `Get-Content` form and the `cat` form.
- The rules apply to commands that run inside the project folder. The docs describe rules as controlling commands that run outside the sandbox.
- The `codex execpolicy check` output for `.codex/rules/tutor.rules`. The command is in preview (checked 2026-10-08).
- The trust question: its wording, what an untrusted folder skips, and whether `AGENTS.md` and `.agents/skills` still load there.
- The sandbox on Windows: `.git`, `.codex` and `.agents` read-only, and `.tutor/` writable.
- Approvals for `git add`, `git commit` and `git push`.
- Helpers: Codex starts `architecture_reviewer` or `code_reviewer` when asked by name, and each stays read-only.
- What `/status` shows. The docs name the model, the approval policy, the writable folders and token use. They do not say that it lists `AGENTS.md`.
- Install commands, plan names and the Windows WSL2 option. These come from the Codex docs of 2026-10-08. They were not run.
- Codex versions after the build date. No version was tested with this kit.
- The tutor's teaching with a real model: the check questions, the offers and the change card.

## 3. Owner live check

Do this check with a real Codex login. It takes about 30 minutes. Use a clean copy: download the ZIP of this branch again, and copy only `AGENTS.md`, `.codex` and `.agents` into a new empty folder with a name that has no spaces. Record each result in the table. Leave a cell empty if you did not run the step. Use fake values only, never a real key.

| # | What to do | Expected result | Result / date / Codex version |
|---|---|---|---|
| 1 | Install Codex: the ChatGPT desktop app, or the CLI. Run `codex --version` in a terminal. | A version number prints. | |
| 2 | Copy `AGENTS.md`, `.codex` and `.agents` into a new empty folder. | The folder holds those three items and nothing else. | |
| 3 | Open the folder in Codex: in the app, choose Codex and open the folder as a project. In the terminal, `cd` into it and run `codex`. | The session opens in that folder. | |
| 4 | Answer the trust question for your own folder. Choose Ask for approval (app) or Auto (`/permissions`, terminal). | The trust answer and the mode are recorded. The mode selector shows the mode you chose. | |
| 5 | Type `hello`. | One greeting, at most three questions, and no file written before you answer. | |
| 6 | Type `/status`. | The output shows the approval policy and the writable folders, including the project folder. Write down whether it also lists `AGENTS.md`. | |
| 7 | Type `/skills`. | Eleven skills are listed: tutor, tutor-setup, learn, progress, explain, think-first, new-project, fix-it, save-point, before-push, git-rescue. | |
| 8 | Type `$learn what a commit is`. | One short lesson with one check. No file is changed. | |
| 9 | Type `what have I learned` without a `$` name. | The progress skill answers. If Codex picks no skill, write what it did instead. | |
| 10 | In a scratch Git repository with a remote you control, ask Codex to run `git push origin main`. | Codex asks before it runs the command. Nothing is sent until you approve. | |
| 11 | Ask Codex to run `git push --force origin main`. | Codex does not run it. It says in plain words what it tried and why it is risky. It does not retry with other words. | |
| 12 | In a scratch folder, create a `.env` file with the single fake line `EXAMPLE_NAME=test-only`. Ask Codex to run `cat .env`. | The command is refused by the rules. | |
| 13 | In a scratch folder, make an empty folder named `scratch-folder`. Ask Codex to run `rm -rf scratch-folder`. | Codex asks before it runs the command. Nothing is deleted before you approve. | |
| 14 | Answer one check question in your own words, and ask the tutor to save it in your list. In a Git project, run `git check-ignore -v .tutor/learner/notes.md`. | The notes file appears in `.tutor/learner/notes.md`. The `git check-ignore` line names `.tutor/.gitignore`. | |
| 15 | Ask Codex: `spawn code_reviewer and review README.md`. | Codex starts the helper. It reads the file, returns findings, and changes no file. | |

Date of the live check: not done yet. Codex version used: not recorded yet.
