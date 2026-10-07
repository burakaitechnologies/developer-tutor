# New-folder flow

What this is: the steps for moving the learner to a folder made only for this project.
When to read it: the folder check says WIDE or KIT, or SYNCED and the learner wants to move. The explanation text is sample 2 in `voice-samples.md`.

## 1. Choose the place

- Default: `<Documents>\<project>`. Find the real Documents path with one read-only command: PowerShell `[Environment]::GetFolderPath('MyDocuments')`, or on macOS and Linux `echo "$HOME/Documents"`.
- If that path contains OneDrive, iCloud, Dropbox or Google Drive, use `<home>\code\<project>` instead (on macOS and Linux, `<home>/code/<project>`). A synced folder is the problem we are leaving.
- `<project>`: lowercase letters and digits, no spaces, no accents, taken from the goal (for example `recipes`). Say the full path and get a yes.

## 2. Create it

Tell the learner first that Codex asks before it writes outside the current folder, so a box will show for each step. That is normal.

1. Create the folder and copy the kit. Copy only these items: `AGENTS.md`, the folders `.codex` and `.agents`, and the single file `.tutor/.gitignore`. Do not copy any other file from `.tutor/`, so no notes travel with the copy. PowerShell, one command per line:
   - `New-Item -ItemType Directory -Path "<dest>"`
   - `Copy-Item -Path "AGENTS.md" -Destination "<dest>"`
   - `Copy-Item -Path ".codex", ".agents" -Destination "<dest>" -Recurse`
   - `New-Item -ItemType Directory -Path "<dest>/.tutor"`
   - `Copy-Item -Path ".tutor/.gitignore" -Destination "<dest>/.tutor"`

   macOS and Linux, one command per line: `mkdir -p "<dest>/.tutor"`, `cp AGENTS.md "<dest>/"`, `cp -R .codex .agents "<dest>/"`, `cp .tutor/.gitignore "<dest>/.tutor/"`.

   If `.tutor/.gitignore` is missing in the current folder, say so. The health check explains why it is needed before the first save point.
2. Copy nothing else, and do not run Git in either folder.
3. With apply_patch, create `<dest>/.tutor/now.md` from `.agents/tutor/templates/now.md`, and fill only the Goal, in the learner's words. The new session then does not ask for the goal again.

## 3. Tell the learner how to open it

- App: open `<dest>` as a folder or project in the app, and start a new chat there. The old chat stays in the list; do not use it for this project.
- CLI (terminal): 1. Type `/exit`. 2. Type `cd "<dest>"`. 3. Type `codex`.
- IDE extension: open `<dest>` as the folder in your IDE, then open the Codex panel in that window. If the menu names differ from these words, ask the learner what they see.
- Every surface: Codex may ask whether to trust this folder. For a folder you made, you can choose to trust it. Then the learner types `/status` and checks that the writable roots list `<dest>`.
- If their screen looks different, ask them to say what they see and adapt. The wording changes between versions.

## 4. If the learner wants to stay

After the first no, say in one sentence what could go wrong (changes to personal files, Git seeing everything). If they insist a second time, stay. Put every new file into one new subfolder named after the project, touch nothing else, and say so.

## 5. Synced folder, learner stays

Add a line to the "Open questions" part of `.tutor/now.md`: "Folder is inside <name>: check before the first git init." If `.tutor/now.md` does not exist yet, create it from `.agents/tutor/templates/now.md` with that one line in its Open questions part. The new-project skill reads it.
