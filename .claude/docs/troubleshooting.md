# Troubleshooting

Facts about Claude Code and the Desktop app were checked 2026-10-07 against the official docs. Each section has four parts: what you see, the cause, the fix, and how to check.

Start with the health check when you are not sure what is wrong. Say "is it working" to the tutor. Or run the command below from your project folder. On Windows, use `py -3`. On macOS and Linux, use `python3`. In the Desktop app, open the terminal with the **Terminal** button in the session title bar, or with Ctrl+backtick. The terminal works only in local sessions.

```
py -3 .claude/tools/doctor.py check
```

If the command does not work, see [Which Python command to use](#which-python-command-to-use).

## How to install Python

**You see:** the check says it could not find a working Python. Or typing `python` opens the Microsoft Store.

**Cause:** Python is not installed, or only a Store shortcut is.

**Fix:** install Python 3.9 or newer from the official Python website, python.org.

- Windows: in the installer, tick **Add python.exe to PATH** before you press Install. Close the terminal and open a new one.
- macOS: install it, then open a new Terminal window.

Python is optional. The tutor works without it. Only the helper scripts need it.

**Check:** run `py -3 --version` on Windows, or `python3 --version` on macOS and Linux. It prints 3.9 or newer.

## Which Python command to use

**You see:** the terminal says the command is not found or not recognized.

**Cause:** each computer names the Python program differently.

**Fix:** use these names in this order. Use the first name that prints version 3.9 or newer. Then use that same name in every kit command.

- **Windows:** `py -3` first, then `python`.
- **macOS and Linux:** `python3` first, then `python`.

```
py -3 --version
```

```
python3 --version
```

**Check:** the first line of the check output shows the Python version it used.

## Python opens the Microsoft Store

**You see:** typing `python` opens the Microsoft Store. Or the message says "Python was not found".

**Cause:** Windows has a shortcut named `python` that opens the Store when Python is not installed. The `py` name can point to the same shortcut.

**Fix:** install Python (see [How to install Python](#how-to-install-python)). Then use `py -3` on Windows. To remove the shortcut, search Windows for "Manage app execution aliases" and turn off the Python entries.

**Check:** `py -3 --version` prints a version number.

## Python 3.9 or newer is required

**You see:** a hook error that says "tutor hooks need Python 3.9 or newer".

**Cause:** the Python on this computer is older than 3.9.

**Fix:** install Python 3.9 or newer (see [How to install Python](#how-to-install-python)). If you cannot do that now, turn the helper scripts off with the switch file in [docs/customize.md](customize.md#turn-the-helper-scripts-on-or-off).

**Check:** `py -3 --version` or `python3 --version` prints 3.9 or newer.

## Hook error lines on every message

**You see:** a red line that says "hook error" under each message.

**Cause:** the helper scripts cannot run on this computer. For example, Python is missing or too old.

**Fix:** turn the helper scripts off without Python. Create `.claude/settings.local.json` with the line `{"disableAllHooks": true}`. The steps are in [docs/customize.md](customize.md#turn-the-helper-scripts-on-or-off). Start a new session. After you fix Python, delete `.claude/settings.local.json`. Then run `enable-hooks` again.

**Check:** the red lines stop in a new session.

## A red hook error after a safety stop

**You see:** a red "hook error" line whose text starts with "Stopped on purpose by the tutor safety guard".

**Cause:** the safety guard stopped a risky command. This is normal, and it is not a setup error.

**Fix:** read the two sentences. They say what was risky and what the safe way is. Do not retry the same goal with other words. Ask the tutor for the safe way.

**Check:** the text says "This is a safety stop, not a setup error."

## The safety guard asks before a helper command

**You see:** Claude asks you to approve a command. The command is `doctor.py` with `enable-hooks`, `disable-hooks`, `share-notes` or `wipe`. Or it is `install.py` with `--update`, `--uninstall` or `--enable-hooks`.

**Cause:** these commands change `settings.json`, delete tutor data, send notes to GitHub, or remove kit files. The guard asks on purpose.

**Fix:** read the command first. Approve it only if you asked for that change. If you did not ask, say no. Then ask the tutor what the command does.

**Check:** the command runs only after you approve it. Run `check` afterwards to see the result.

## Started Claude Code in a sub-folder

**You see:** the tutor does not act like a tutor. It does not follow the project's settings.

**Cause:** Claude Code reads the project's `.claude/settings.json` from the folder where you start it. A sub-folder or a parent folder does not give it the right settings.

**Fix:** close the session. Start Claude Code again in the folder that contains `.claude`.

**Check:** type `pwd` in the terminal. The path ends with your project folder, and that folder contains `.claude`.

## I said no to the trust question

**You see:** the allow rules in `settings.json` do not apply. Some tutor behaviour is missing.

**Cause:** Claude Code applies the allow rules of a folder's settings only after you say yes to the trust question. The deny and ask rules still apply. The [FAQ answer on trust](faq.md#q-what-does-trust-this-folder-mean) explains more.

**Fix:** start the session again in the project folder. Answer yes. Say yes only for a folder you made or trust.

**Check:** the session starts in the project folder. The check's **Started in** line says OK.

## settings.json invalid

**You see:** the check says `settings.json` is not valid JSON. It may also say the file has comments in it.

**Cause:** the file is not valid JSON. A missing comma or a comment is a common reason. Claude Code then ignores the whole file.

**Fix:** rename the broken file to keep a copy. Copy `settings.json` from a fresh copy of the kit into `.claude`. Put your own changes in `.claude/settings.local.json`, not in `settings.json`.

**Check:** the check prints "settings.json is valid and uses only entries Claude Code knows."

## Safety rules missing from settings.json

**You see:** the check says force-push rules are missing from the deny list. Or it says the permission rules are gone.

**Cause:** the file was changed or copied from an older version. Rules were removed.

**Fix:** copy `settings.json` again from a fresh copy of the kit. Put your own changes in `.claude/settings.local.json`.

**Check:** the check prints a line that ends with "with all 8 force-push shapes."

## Output style does not match

**You see:** the check says no output style is chosen. Or it says the style has no matching file in `output-styles`.

**Cause:** `settings.json` names a different output style, or none.

**Fix:** open `settings.json` in a text editor. Set the line to `"outputStyle": "tutor",`. Keep the quotes and the spelling.

**Check:** the check prints "The output style 'tutor' is set and its file exists."

## Claude Code older than 2.1.288

**You see:** the check says your Claude Code is older than 2.1.288, the version this kit was checked on.

**Cause:** the installed Claude Code is older than that version.

**Fix:** for the Desktop app, update the app. Download the latest version at [claude.com/download](https://claude.com/download). For the terminal, run `claude update`.

**Check:** run `claude --version`. It prints 2.1.288 or newer.

## .env or the notes folder not ignored by Git

**You see:** the check says a file such as `.env` is not ignored by Git.

**Cause:** the `.gitignore` file in your project folder does not list it. Git would save your secrets if you committed the file.

**Fix:** open `.gitignore` in your project folder, next to `.claude`. Add a line with the word `.env`. Save the file as plain text in UTF-8. If the file does not exist, the save point creates it with your yes.

**Check:** run `git check-ignore -v .env`. It prints a line that names `.env`. If it prints nothing, Git does not ignore the file.

## .gitignore saved as UTF-16

**You see:** the check says `.claude/.gitignore` is saved as UTF-16. Git cannot read it.

**Cause:** some Windows tools save text as UTF-16. Git cannot read that format.

**Fix:** open the file in Notepad. Choose **File**, then **Save as**. Set the encoding to **UTF-8**. Save it with the same name. If you are not sure, run `install.py` with `--update`.

**Check:** the check no longer says UTF-16. Its Git ignore line says "Git ignores .env, the tutor notes and settings.local.json."

## Git name and e-mail not set

**You see:** the check says Git has no name or e-mail yet.

**Cause:** Git writes a name and an e-mail address into each save point. This computer has none set.

**Fix:** run these two commands. Use your own name. Use an address you are happy to show in public records.

```
git config --global user.name "Your Name"
```

```
git config --global user.email "you@example.com"
```

**Check:** `git config --global user.name` prints your name.

## Kit files differ from the release

**You see:** the check has a line that starts with **Kit files**. It says some kit files differ from the released version. Or the installer warns that the kit's own files do not match `MANIFEST.txt`.

**Cause:** you or a tool changed files in the `.claude` folder. Or the copy you have is not the release.

**Fix:**

1. Run the verify command below. It lists the changed files under "Needs attention". Its exit code is 1 when a kit file differs or is missing.
2. If you changed the files on purpose, that is fine. Nothing else is needed.
3. If you did not change them, copy the `.claude` folder again from the kit download. Then run verify again.
4. If verify still lists files after a fresh copy, stop. Tell the kit's owner which files are listed. The released copy may be wrong.

An update keeps the files you edited. Run `install.py` with `--update`. It saves the new version of each edited file next to it as `<file>.new`. Compare the two files, then keep what you want.

```
py -3 .claude/tools/doctor.py verify
```

**Check:** the Verdict line of verify says "all checks passed."

## Teaching numbers out of range

**You see:** the check shows an Info line about teaching numbers.

**Cause:** the tutor's own measures are outside their target range. This is information. It is not an error.

**Fix:** nothing is needed. To see the numbers, type `/progress numbers`.

**Check:** `py -3 .claude/tools/doctor.py progress numbers` shows the numbers.

## Windows long paths

**You see:** a command fails with an error about a path that is too long. Or the installer warns "The path of this folder is long".

**Cause:** some Windows tools fail when a full path is long.

**Fix:** move the project to a folder with a short path. For example, `C:\code\my-app`.

**Check:** `pwd` in the terminal shows a shorter path.

## Project in OneDrive, iCloud or Dropbox

**You see:** the installer warns "This folder is synced by" OneDrive, iCloud, Dropbox or Google Drive. The check does not test this. Look at the path yourself.

**Cause:** sync tools upload and change files. They can damage a Git folder. Git history is not a backup.

**Fix:** move the project to an unsynced folder, such as `C:\code\my-app`. Use GitHub as your backup.

**Check:** the path does not contain OneDrive, iCloud, Dropbox or Google Drive.

## Git for Windows is missing

**You see:** the message "Claude Code on Windows requires either Git for Windows (for bash) or PowerShell".

**Cause:** Claude Code did not find Git Bash or PowerShell. Git for Windows is optional. Without it, Claude Code uses PowerShell.

**Fix:** install Git for Windows from [git-scm.com/downloads/win](https://git-scm.com/downloads/win). Use the default options. Close the terminal and open a new one.

**Check:** `git --version` prints a version number.

## Desktop app says Git is required

**You see:** the Desktop app says "Git is required" when you start a session.

**Cause:** older Desktop versions asked for Git before any local session. On Windows, versions before 1.49585.0 did this. A session that uses the worktree option needs Git.

**Fix:**

1. Update the Desktop app. Download the latest version at [claude.com/download](https://claude.com/download). Restart the app.
2. If you use the worktree option, install Git from [git-scm.com/downloads](https://git-scm.com/downloads). On Windows, that is Git for Windows.
3. Last resort, if the message stays and you do not use worktrees: set `CLAUDE_CODE_GIT_BASH_PATH` to the path of `bash.exe`. The [environment variables page](https://code.claude.com/docs/en/env-vars) and the [setup page](https://code.claude.com/docs/en/setup) show the form. Ask the tutor first. Do not put it in the kit's `settings.json`.

**Check:** a new session starts without the message.

## Failed to load session

**You see:** "Failed to load session" in the Code tab.

**Cause:** the folder may no longer exist. Or a Git repository needs Git LFS, which is not installed. Or file permissions block access.

**Fix:** choose a different folder, or restart the app.

**Check:** the session opens and shows your files.

## I edited a file and nothing changed

**You see:** you asked Claude to change a file. The file in your folder looks the same.

**Cause:** the session works somewhere else. It may be a cloud session. The worktree option gives a session its own copy of the project. Or the session is in a different folder.

**Fix (Desktop app):** check three things. You are in the **Code** tab. **Environment** is **Local**. The project folder is the folder you open. If the **worktree** option was on, the changes are in a separate copy. Ask the tutor to show you where the changes are.

**Fix (terminal):** type `pwd`. Check that it shows the project folder.

**Check:** the file changes in the folder you open in File Explorer or Finder.

## Usage limit message

**You see:** "You've hit your session limit · resets 3:45pm", or a weekly limit message. The time is an example. Your message shows its own time.

**Cause:** your plan's usage allowance is used up. Claude Code stops requests until the reset time. A message that names one model, such as "Opus limit", may leave other models working.

**Fix:** wait until the time shown. To check your limits in the terminal, type `/usage`. In the Desktop app, click the usage ring next to the model picker. To try another model, use `/model` in the terminal or the model picker in the Desktop app.

**Check:** after the reset time, send a short message.

## Context limit reached

**You see:** "Context limit reached · /compact or /clear to continue", or "Prompt is too long".

**Cause:** the conversation is too long for Claude to use at once.

**Fix:** type `/compact` to summarize the conversation. Or type `/clear` to start a new one. The kit's rules stay. Your notes stay in `.claude/agent-memory`.

**Check:** the conversation continues.

## Not logged in or authentication required

**You see:** "Not logged in · Please run /login" in the terminal. Or "Authentication required · Sign in again to continue" in the Desktop app.

**Cause:** this session has no valid sign-in.

**Fix:** in the terminal, type `/login` and follow the steps. In the Desktop app, sign in again from the app.

If you set `ANTHROPIC_API_KEY`, that key is used instead of your subscription, even when you are logged in. Remove it from your environment, then run `/login`.

**Check:** the message is gone, and Claude replies.

## Error 403 in the Code tab

**You see:** "Error 403: Forbidden" or another sign-in error in the Code tab.

**Cause:** the app's sign-in is not valid, or your plan does not include Claude Code.

**Fix:**

1. Sign out, then sign in again from the app menu. This is the most common fix.
2. Check that you have an active Pro, Max, Team or Enterprise plan.
3. If the terminal works but the Desktop app does not, quit the app completely, not only its window. Open it and sign in again.
4. Check your internet connection and proxy settings.

**Check:** the Code tab starts a session.

## Claude will not change the .claude settings

**You see:** Claude says it will not change `settings.json`, `CLAUDE.md` or the rules. Or the safety guard asks you first.

**Cause:** this is on purpose. Only you should change the files that decide what Claude may do.

**Fix:** tell Claude what you want to change and why. Then make the change yourself in a text editor. Or ask again, and approve the change when the guard asks.

**Check:** the file has your change. Run `py -3 .claude/tools/doctor.py check`. On macOS and Linux, use `python3`.

## A permission box appears for every step

**You see:** Claude asks you to approve each file change and each command.

**Cause:** the permission mode is Manual. Manual asks before each change.

**Fix:** in the Desktop app, choose **Accept edits** in the mode selector next to the send button. In the terminal, press **Shift+Tab** until the mode is Accept edits. Each press moves to the next mode: Manual, Accept edits, then Plan. Commands still ask you first.

**Check:** the mode shows Accept edits. See [docs/customize.md](customize.md#permission-modes-in-plain-words).

## The tutor talks too much or too little

**You see:** too many explanations, or too few.

**Cause:** the level or teaching setting does not fit you.

**Fix:** say "quiet mode" for this session. Say "simpler" or "more detail". For a lasting change, see [docs/customize.md](customize.md#profile-settings).

**Check:** the next answer has the length you want.

## The tutor did not record anything

**You see:** no progress lines appear after your answers. `progress` shows nothing new.

**Cause:** the helper scripts are off. In that case, the tutor writes what you understood into `learner/notes.md` by itself.

**Fix:** nothing is broken. To record progress automatically, say "turn on helper scripts".

**Check:** the file `.claude/agent-memory/tutor-data/learner/notes.md` has new lines. Or `py -3 .claude/tools/doctor.py progress` shows them after the scripts are on.

## install.py refuses the folder

**You see:** the installer prints "Refused:" and stops. Its exit code is 2. Nothing is written.

**Cause:** the folder is not a place for one project. The installer checks the folder before it writes anything.

**Fix:** use the message to choose the right folder:

- "This is the top of a drive. The tutor needs a folder for one project." Make a folder for the project. Use its path.
- "This is your home folder. Make a new folder for one project, and install there." Make a new folder, then install there.
- "This is the .claude folder in your home folder. It holds Claude Code's own settings." Choose your project folder instead.
- "This folder is the tutor kit itself, or inside it. Install into your own project folder instead." Run the installer from the kit download, not from inside your project. Use your project folder as the path.
- "This is a system folder. Programs and the system live here, not projects." Choose a folder for your project.
- "this folder has no project file (like .git, package.json, README or index.html)." Choose your project folder. If it really is your project, run again with `--yes-this-is-my-project`.
- "The folder ... does not exist yet. Create it first." Make the folder, give it a name, then run the command again. The installer never creates a folder for you.
- "... is a link or not a folder. I never write through links." Use a real folder, not a shortcut or a link.
- "these items are not from the tutor. Look at them first." The installer lists the items that can run code. Read the list. If you know them, run again with `--accept-existing`.

**Check:** exit code 2 means refused. Nothing was written. Run the dry run first with `--dry-run`.

## install.py finished with a warning

**You see:** the installer ends with "Finished with 1 warning(s)." Its exit code is 1. The number can be higher.

**Cause:** the install worked, but a check printed a warning. The warnings you may see are:

- "The kit's own files do not match its MANIFEST.txt." See [Kit files differ from the release](#kit-files-differ-from-the-release).
- "This is your Desktop folder," or Documents, or Downloads. The tutor works best in a folder made for one project. Move the project to a new folder.
- "This folder is synced by" a sync service. See [Project in OneDrive, iCloud or Dropbox](#project-in-onedrive-icloud-or-dropbox).
- "The path of this folder is long." See [Windows long paths](#windows-long-paths).
- "The quick self-test failed." Read the lines above that warning. Then run the dry run again.

**Check:** run the verify command in [Kit files differ from the release](#kit-files-differ-from-the-release). Its Verdict line says "all checks passed."
