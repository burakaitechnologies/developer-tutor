# Troubleshooting

Facts about Codex in this page were checked 2026-10-08 against the official Codex docs. Items marked "general Windows advice" are not in the Codex docs.

Each problem has four parts: what you see, the cause, the fix, and how to check. If you are not sure what is wrong, type `$tutor` and say "is it working". In the terminal, you can also type `/status`.

## Codex cannot change files

**You see:** Codex says it cannot write files, or it only reads them.

**Cause:** Codex may start in read-only mode until you trust the folder, or the permission is set to Read Only.

**Fix:** Trust the project folder. Then choose **Ask for approval**. In the app, use the control below the message box. In the terminal, type `/permissions`.

**Check:** Type `/status` in the terminal. Your project folder appears in the list of folders Codex can write to.

## Codex works in the wrong folder

**You see:** new files appear in a folder you did not expect, or the tutor does not find its notes.

**Cause:** Codex started in a different folder from your project.

**Fix:** Close Codex with `/exit`. In the terminal, go to the project folder with `cd`, then run `codex` again.

**Check:** Type `/status`. The project folder is listed as a writable folder.

## A command was refused by a rule

**You see:** Codex says a command is forbidden, or it asks you to approve a command you did not expect.

**Cause:** A rule in `.codex/rules/tutor.rules` matches the start of the command. If the message names no rule, the sandbox refused the command.

**Fix:** Read the reason in the message. It may name a safer command. Ask the tutor for the safe way. Do not try again with other words.

**Check:** Run `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- <the command>`. Put the command in place of `<the command>`. The output shows the decision.

## Codex asks before every Git command

**You see:** each `git add`, `git commit` or `git push` asks for approval.

**Cause:** The `.git` folder is read-only in the default sandbox. Also, the rules file asks before every `git push`.

**Fix:** This is normal. Read the command in the prompt. Say yes only when you want that step. Do not choose Full access to stop the questions.

**Check:** Codex does not run a Git command until you say yes. If a Git command runs without a question, stop and ask the tutor.

## Skills do not show up

**You see:** `$tutor` or your own skill does nothing, or `/skills` does not list it.

**Cause:** Codex reads skills when it starts. It needs a folder with a `SKILL.md` file, and that file needs `name` and `description` lines at the top.

**Fix:** Restart Codex. Check that the file is at `.agents/skills/<skill-name>/SKILL.md` in the project folder. Check that the file starts with `---`, then `name:` and `description:` lines, then `---`.

**Check:** In the terminal, type `/skills`. The skill name appears in the list.

## AGENTS.md seems ignored or cut short

**You see:** the tutor forgets its rules, or Codex says it cannot find the instructions.

**Cause:** Codex reads `AGENTS.md` from the project root down to the folder you started in. The project root is the folder that holds the `.git` folder. If there is no `.git` folder, Codex reads only the folder you started in. Codex also stops at a size limit. The default limit is 32 KiB, and your own `~/.codex/AGENTS.md` counts too. In each folder, a file named `AGENTS.override.md` is used instead of `AGENTS.md`. Look for one in your project folder, in folders above it, and in `~/.codex`.

**Fix:** Start Codex in the project folder. Trust the folder, so the larger limit in `.codex/config.toml` applies. If an `AGENTS.override.md` file exists, ask the tutor before you rename or delete it. Keep your own `~/.codex/AGENTS.md` short.

**Check:** Ask Codex "List the instruction sources you loaded." Codex should name `AGENTS.md`. Then type `/status` and confirm the folder is your project folder.

## The rules file seems ignored

**You see:** a command you expected to be stopped runs without a question.

**Cause:** The folder is not trusted, Codex was not restarted after the change, or the file has a syntax error. Rules load only for a trusted folder.

**Fix:** Trust the folder. Save the file as UTF-8 text. Restart Codex. Check each line for matching quote marks, commas and brackets. Ask the tutor to check the file.

**Check:** Run `codex execpolicy check --pretty --rules .codex/rules/tutor.rules -- git push`. The output shows `prompt`, because the kit asks before every `git push`.

## PowerShell blocks scripts

**You see:** a message says "running scripts is disabled on this system". It may name a file such as `npm.ps1`.

**Cause:** The Windows execution policy blocks scripts in PowerShell.

**Fix:** Read Microsoft's guide first: [about_execution_policies](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies). The Codex docs suggest `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned`. The kit's rules file asks you before it runs `Set-ExecutionPolicy`. Ask the tutor before you run it.

**Check:** Run `Get-ExecutionPolicy`. It prints the current policy.

## The Windows sandbox is degraded

**You see:** when you type `/`, the command `/setup-default-sandbox` appears.

**Cause:** Codex is using the degraded Windows sandbox, which is weaker. The elevated sandbox is the stronger one.

**Fix:** If you have administrator rights, type `/setup-default-sandbox` and follow the steps. The setup asks for administrator rights, so only you can accept it. Ask the tutor what it changes first. The Codex docs also show a `[windows]` setting, `sandbox = "elevated"`, in `config.toml`. Ask the tutor before you edit that file.

**Check:** Type `/` again. The `/setup-default-sandbox` command should no longer appear.

## Windows: long folder paths

**You see:** a command fails with an error about a path that is too long.

**Cause:** Some Windows tools fail when a full path is long. This is general Windows advice, not a Codex rule.

**Fix:** Move the project to a folder with a short path, for example `C:\code\my-app`.

**Check:** Run `pwd` in PowerShell. It prints a shorter path.

## Windows: project in OneDrive or another sync folder

**You see:** files change by themselves, fail to save, or Git shows changes you did not make.

**Cause:** A sync service, such as OneDrive, can move or lock files while Codex and Git work. Your Desktop folder can be synced by OneDrive too. This is general Windows advice, not a Codex rule.

**Fix:** Move the project to a folder that is not synced, for example `C:\code\my-app`.

**Check:** The full path of the project folder does not contain `OneDrive`.

## Git is not installed (Windows)

**You see:** some features in the app do not work, or `git` is not recognized in PowerShell.

**Cause:** Git for Windows is not installed. The Codex docs say the app needs it for some features.

**Fix:** In PowerShell, run `winget install --id Git.Git`. Then close the terminal and open a new one.

**Check:** Run `git --version`. It prints a version number.

## git says "not a repository"

**You see:** `fatal: not a git repository` when you run a Git command.

**Cause:** The folder has no `.git` folder yet, or you are in a different folder.

**Fix:** Run `pwd`. If it shows the wrong folder, go to the project folder. If it shows the right folder, type `$new-project` to set up Git. That skill starts Git only after you say yes.

**Check:** Run `git status`. It prints `On branch` and, for a new project, `No commits yet`.

## Git asks for your name and email

**You see:** a save point fails, and Git asks you to set a name and an email address.

**Cause:** Git writes your name and email into each save point. This computer has none set.

**Fix:** Run these two commands. Use your own name. Use an email address you are happy to show in public records.

`git config --global user.name "Your Name"`

`git config --global user.email "you@example.com"`

**Check:** Run `git config --global user.name`. It prints your name.

## .env is not ignored by Git

**You see:** `git status` lists `.env` as a file that could be saved.

**Cause:** The `.gitignore` file in the project folder does not list `.env`. Git would save the file if you committed it.

**Fix:** Ask Codex to add the line `.env` to `.gitignore`, then check the file. Do not open `.env` in the chat. If `.env` was already saved in a commit, stop. Ask `$git-rescue` first. Ignoring the file now does not remove it from the history.

**Check:** Run `git check-ignore -v .env`. It prints a line that names `.env`. If it prints nothing, Git does not ignore the file.

## A secret was pasted or saved

**You see:** you pasted a key, token or password into the chat, or a file holds one.

**Cause:** Anyone who sees the secret can use it. The kit cannot take it back.

**Fix:** Do these steps in this order.

1. Revoke or replace the secret at its provider first. A key that starts with `sk-` comes from OpenAI or Anthropic. A key that starts with `ghp_` comes from GitHub. A key that starts with `AKIA` comes from AWS.
2. Remove the secret from the files. Put secrets in a `.env` file, and keep `.env` out of Git.
3. Do not paste the secret into the chat again. Ask `$git-rescue` to explain how to remove it from the Git history. Do this step last.

**Check:** The provider's key list no longer shows the key as active.

## Login problems

**You see:** Codex asks you to sign in again, or the browser step never finishes.

**Cause:** The sign-in is not complete, or an old sign-in is stored on this computer.

**Fix:** In the terminal, run `codex login`, then finish the browser step. If it fails again, run `codex logout`, then `codex login`. In the app, select **Continue to sign in**, then finish the browser step.

**Check:** Type `hello`. Codex answers.

## Usage limit message

**You see:** a message says you reached a usage limit.

**Cause:** Your plan has used its allowance for this period. Limits differ by plan.

**Fix:** Wait for the reset time. Check your usage on the dashboard at https://chatgpt.com/codex/settings/usage. In the terminal, type `/usage` or `/status`. Use smaller steps until the limit resets.

**Check:** The dashboard shows the limit and the reset time.

## The tutor talks too much or too little

**You see:** too many explanations, or too few.

**Cause:** The level or teaching setting does not fit you.

**Fix:** Say "quiet mode" for this session. Say "simpler" or "more detail". For a lasting change, edit `level` or `teaching` in `.tutor/learner/profile.md`. The file `customize.md` lists the allowed values.

**Check:** The next answer has the length you want.

## The tutor wrote nothing in .tutor

**You see:** `.tutor/learner/notes.md` has no new lines, and the tutor does not say "Added to your list".

**Cause:** Codex cannot write to the folder. The project may not be trusted, or the permission may be Read Only. The folders `.codex` and `.agents` are read-only, so the notes cannot live there.

**Fix:** Trust the folder and choose **Ask for approval**. Keep the `.tutor` folder in the project folder, not inside `.codex` or `.agents`.

**Check:** The file `.tutor/.gitignore` exists in your project folder. Then type `$tutor` and say "where are we".
