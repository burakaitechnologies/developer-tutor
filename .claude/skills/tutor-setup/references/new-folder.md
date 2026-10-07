# New-folder flow

What this is: the steps for moving the learner to a folder made only for this project.
When to read it: the folder check says WIDE, or SYNCED and the learner wants to move. The explanation text is sample 2 in `voice-samples.md`.

## 1. Choose the place

- Default: `<Documents>\<project>`. Find the real Documents path with one read-only command: PowerShell `[Environment]::GetFolderPath('MyDocuments')`, Bash `echo "$HOME/Documents"`.
- If that path contains OneDrive, iCloud, Dropbox or Google Drive, use `<home>\code\<project>` instead. A synced folder is the problem we are leaving.
- `<project>`: lowercase letters and digits, no spaces, no accents, taken from the goal (for example `recipes`). Say the full path and get a yes.

## 2. Create it

Tell the learner first that the app will show a box for each step, because the new folder is outside the current one.

1. Create the folder and copy the tutor. PowerShell: `New-Item -ItemType Directory -Path "<dest>"` then `Copy-Item -Path ".claude" -Destination "<dest>" -Recurse`. Bash: `mkdir -p "<dest>" && cp -R .claude "<dest>/"`.
2. Glob `<dest>/.claude/agent-memory`. If it exists, the copy holds the learner's notes. Remove only that copy, after a yes. The original stays.
3. Copy nothing else, and do not run Git in either folder.
4. With the Write tool, create `<dest>/.claude/agent-memory/tutor-data/now.md` from `.claude/templates/now.md` and fill only the Goal, in the learner's words. The new session then does not ask for the goal again.

## 3. Tell the learner how to open it

- Desktop app, Code tab: 1. Click New session (Ctrl+N on Windows, Cmd+N on Mac). 2. Keep Local selected. 3. Click Select folder and choose `<dest>`. 4. Type "hello". The old chat stays in the sidebar; do not use it for this project.
- Terminal: 1. Type /exit. 2. Type `cd "<dest>"` (in cmd on another drive, `cd /d "<dest>"`). 3. Type `claude`.
- VS Code: File, Open Folder, choose `<dest>`. Then open the Claude Code panel in that window.
- Every surface: Claude Code may ask whether you trust the folder. For a folder you made, choose Yes.
- If their screen looks different, ask them to say what they see and adapt. The app's wording changes between versions.

## 4. If the learner wants to stay

After the first no, say in one sentence what could go wrong (changes to personal files, Git seeing everything). If they insist a second time, stay. Put every new file into one new subfolder named after the project, touch nothing else, and say so.

## 5. Synced folder, learner stays

Add a line to the "Open questions" part of now.md: "Folder is inside <name>: check before the first git init." The new-project skill reads it.
