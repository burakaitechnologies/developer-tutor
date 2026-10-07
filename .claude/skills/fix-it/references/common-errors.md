# Common beginner errors: where to look first

For: the main agent, in step 3 of the fix-it skill. Ten patterns. Each has the shape of the message, where to look first, and the usual cause. Read the learner's real message first; the wording differs by language and tool. The concept ids point to cards in `.claude/knowledge/concepts`. Never read `.env`; never fix with `sudo`, administrator rights or `chmod -R 777`.

## 1. File not found
- Looks like: `FileNotFoundError: [Errno 2] No such file or directory: 'data.csv'` · `Error: ENOENT: no such file or directory` · `Cannot find path ... because it does not exist.`
- Where to look first: the file name in the message. Then the folder the program runs in (`pwd`). Then whether the file is in that folder (`ls` or `dir`).
- Usual cause: a different folder, or a different name. Windows hides extensions, so `data.csv.txt` can look like `data.csv`. Concepts: `term-paths`, `term-look-around`.

## 2. Command not found
- Looks like: `command not found` · `'node' is not recognized as an internal or external command` · `The term 'node' is not recognized as the name of a cmdlet`
- Where to look first: the spelling, then a new terminal window (a window reads PATH when it starts), then `which node` or `Get-Command node`.
- Usual cause: the tool is not installed, or the window is older than the install. On Windows `python3` may open the Microsoft Store: try `python` or `py -3`. Concept: `term-path-not-found`.

## 3. Permission denied
- Looks like: `PermissionError: [Errno 13] Permission denied` · `EACCES: permission denied` · `./run.sh: Permission denied` · `Access to the path ... is denied.`
- Where to look first: the path in the message. Is it a folder where a file is expected? Is the file open in another program (Windows locks open files)? Is it a script that is not marked as runnable? Is it a system folder?
- Usual cause: the program points at a folder or a locked file. Install into the project, not into a system folder. Concept: `term-sudo-admin`.

## 4. Module not found
- Looks like: `ModuleNotFoundError: No module named 'requests'` · `Error: Cannot find module 'express'`
- Where to look first: the module name, then the list file (`requirements.txt`, `package.json`), then which Python or Node runs (`python -c "import sys; print(sys.executable)"`).
- Usual cause: the package was never installed, or it went to another Python. A file of the learner named like a library (`random.py`) can also hide the real one. Check the name before you install (concept `sec-supply-chain`), and ask first. Concepts: `prog-imports`, `prog-dependencies`.

## 5. Syntax error
- Looks like: `SyntaxError: invalid syntax` · `SyntaxError: Unexpected token` · `IndentationError` · `Unexpected end of JSON input`
- Where to look first: the line number in the message, and the line above it. A missing bracket, quote or colon is often right above the line that is reported.
- Usual cause: unmatched `( ) [ ] { }` or quotes, mixed tabs and spaces, or curly quotes pasted from a document. Conflict markers (pattern 7) left in the file also cause it. Concept: `prog-errors`.

## 6. Port already in use
- Looks like: `Address already in use` · `Error: listen EADDRINUSE: address already in use :::3000` · `[WinError 10048] Only one usage of each socket address`
- Where to look first: another terminal tab or window that still runs the same program. Stop it there with Ctrl+C. Then find the owner: `netstat -ano | findstr :3000` (Windows) or `lsof -i :3000` (macOS, Linux).
- Usual cause: the program started twice. Ask before you stop a program you did not start. Or use another port and open the new address. Concept: `web-localhost-ports`.

## 7. Merge conflict markers
- Looks like: `CONFLICT (content): Merge conflict in site.txt` · lines `<<<<<<< HEAD`, `=======`, `>>>>>>> branch-name` inside a file.
- Where to look first: `git status` (it lists "both modified"), then open that file and find the three marker lines.
- Usual cause: two branches changed the same lines. Keep the right lines, delete all three marker lines, then `git add` the file and commit. `git merge --abort` returns to before the merge. Deep in a Git mess: use git-rescue. Concept: `git-conflict`.

## 8. Wrong folder
- Looks like: `fatal: not a git repository` · `npm ERR! enoent ... package.json` · `can't open file 'app.py'` · Claude Code settings that seem ignored.
- Where to look first: `pwd`, and the project's top folder (`git rev-parse --show-toplevel`). Do they name the same folder?
- Usual cause: the terminal, or Claude Code itself, started in a subfolder, the home folder or an older copy of the project. Restart in the project's top folder. Concepts: `cc-start-in-project-root`, `files-project-structure`.

## 9. Missing .env value
- Looks like: `KeyError: 'API_KEY'` · `undefined` where a key should be · `Missing API key` · `401 Unauthorized` · `Incorrect API key provided`
- Where to look first: does `.env` exist in the project's top folder, and does it have that variable NAME? You never read `.env`, and you never run a command that reads it. Ask the learner to run `doctor.py envcheck .env` in their own terminal (with the interpreter that works) and paste the output, which shows names only. If they cannot, ask them to read you the names, never the values.
- Usual cause: no `.env`, a misspelled name, or a value in quotes or with spaces. The program may also not load `.env` at all. Concepts: `sec-secrets`, `term-env-vars`.

## 10. CORS or fetch failed
- Looks like: `Access to fetch at ... has been blocked by CORS policy` · `TypeError: Failed to fetch` · `net::ERR_CONNECTION_REFUSED` · `NetworkError when attempting to fetch resource`
- Where to look first: the browser's developer tools (F12), the Console and Network tabs. Read the full message. Is the server running, and does the address and port match?
- Usual cause: `ERR_CONNECTION_REFUSED` means nothing answers at that address. A CORS message means the server did not allow the page's address; the fix belongs on the server, never in switching off browser security. Concepts: `web-devtools`, `web-client-server-http`, `web-localhost-ports`.
