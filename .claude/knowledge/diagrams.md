# Diagrams: five pictures of how the machine works

Use these when a learner's confusion is about where things are or what moves where. They are notional machines: simple pictures of how the computer behaves, not exact descriptions of every detail.
How to use one: show only the diagram that fits the confusion, inside a code block so the spacing stays. Ask the learner to point at the arrow where their picture and the diagram differ. Redraw it with the learner's own file names, keeping it to 24 lines and 70 columns at most.
Related concept cards: (a) term-paths, term-cd. (b) files-code-editor, prog-program. (c) git-four-places, git-staging, git-restore, git-fetch-pull. (d) web-client-server-http, web-status-codes. (e) cc-context-window, cc-claude-md, cc-permission-modes, cc-hooks.

## a. Files and paths

```text
 One disk, one tree. The terminal stands in ONE folder at a time.

 /                          <- top of the disk (Windows: C:\)
 `-- projects
     |-- recipes            <- the project folder
     |   |-- README.md
     |   |-- index.html
     |   `-- css
     |       `-- style.css  <- the file we want
     `-- quotes-bot

 ABSOLUTE path = from the top. It works from any folder:
   /projects/recipes/css/style.css
   C:\projects\recipes\css\style.css   (same file, Windows style)

 RELATIVE path = from the folder you stand in now (pwd shows it):
   standing in /projects/recipes       ->  css/style.css
   standing in /projects/recipes/css   ->  style.css
   standing in /projects/quotes-bot    ->  ../recipes/css/style.css
   (.. = the folder one level up)

 cd = change the folder you stand in. It moves no file.
   cd css    go down into css        cd ..    go up one level
```

Read it like this: Each name in the tree sits inside the folder above it, and an absolute path lists every folder from the top down to the file. A relative path starts where you stand, so each arrow shows another text for the same file; two dots (..) mean one level up. cd only changes where you stand, which changes what every relative path means, and it never moves or copies a file.

Common wrong picture: The terminal can see every folder at once, so a file name always works. Correct: it stands in one folder, and standing in the wrong one is the usual cause of "No such file or directory".

## b. Memory and disk: why "I changed the file but nothing happened"

```text
 +-------------+    Save   +-------------+ (re)start +-------------+
 | 1 EDITOR    | Ctrl/Cmd+S| 2 DISK      | or reload | 3 RUNNING   |
 | the text    |---------->| the file as |---------->| PROGRAM or  |
 | you typed   |           | of the last |           | open page:  |
 | (maybe not  |           | SAVE        |           | a copy made |
 | saved yet)  |           |             |           | when it     |
 |             |           |             |           | started     |
 +-------------+           +------^------+           +-------------+
                                  |
 Claude Code edits the file ------+
 on the disk, not in the editor window.

 No change on screen? Ask in this order:
 1 Saved?    2 Restarted or reloaded?    3 Same file, same folder?
```

Read it like this: The editor shows a buffer, which is text in memory, and the file on disk changes only when you save. A running program or an open page reads the file when it starts or loads, and keeps that version until you restart or reload. Claude Code edits the file on disk directly, so you still restart or reload to see the change.

Common wrong picture: The editor, the saved file and the running program are one thing. Correct: they are three copies, and you move a change from one to the next by saving and then restarting or reloading (tools with auto-reload do the last step for you).

## c. Git's four places

```text
 1 WORKING FOLDER  2 STAGING AREA    3 LOCAL REPO      4 REMOTE
 +------------+    +------------+    +------------+    +------------+
 | your files |    | picked for |    | saved      |    | origin:    |
 | as you     |    | the next   |    | commits    |    | a copy on  |
 | edit them  |    | commit     |    | (history)  |    | GitHub     |
 +-----+------+    +-----+------+    +-----+------+    +-----+------+
       |                 |                 |                 |
       +-- git add ----->|                 |                 |
       |                 +- git commit --->|                 |
       |                 |                 +-- git push ---->|
       |                 |                 |<- git fetch ----+
       |<- git pull (fetch, then merge into your files) -----+
       |<----------------+  git restore <file>
       |                 |<----------------+  git restore --staged

 git diff = 1 vs 2      git diff --staged = 2 vs 3
 git status = 1 vs 2 and 2 vs 3 (plus ahead/behind origin)
```

Read it like this: Arrows to the right move work forward: add stages a file, commit saves the staged files, and push uploads the commits. Arrows to the left bring work back: fetch downloads new commits into your local repository and leaves your files alone, and pull also merges them in. git restore <file> puts the staged copy (the last commit's copy, if nothing is staged) over your file and loses your edits, and git restore --staged <file> only unstages.

Common wrong picture: git add saves my work and git commit uploads it. Correct: add copies a change into the staging area, commit records it in your local repository only, and only push sends it to the remote.

## d. Request and response

```text
 CLIENT                                    SERVER
 browser or your code                      runs on another computer
                                           or on yours: localhost
 +------------------+                      +------------------+
 | you open a URL,  |                      | finds recipe 42  |
 | or your code     |  1 REQUEST           | builds an answer |
 | calls one        |  GET /recipes/42     |                  |
 |                  |  Host: example.com   |                  |
 |                  |--------------------->|                  |
 |                  |                      |                  |
 |                  |  2 RESPONSE          |                  |
 | shows the page   |  200 OK              |                  |
 | or your code     |  body: HTML or JSON  |                  |
 | reads the data   |<---------------------|                  |
 +------------------+                      +------------------+

 Status code, first digit: 2 ok, 3 redirect, 4 your request was wrong,
 5 the server failed.   200 OK   404 not found   429 too many requests
```

Read it like this: The client sends one request that names what it wants, here GET /recipes/42 on the host example.com. The server answers each request with one response: a status code that says how it went, then a body such as HTML or JSON. In this simple picture the server only answers and sends nothing until a request arrives.

Common wrong picture: An error code means my internet is broken. Correct: you got an answer, so the connection worked; a 4xx code says the request was wrong, and a 5xx code says the server failed.

## e. The Claude Code loop

```text
 CLAUDE.md ----------+  loaded when a session starts,
 (your project notes)|  and read again after /compact
                     v
 +------------------------------------------------------------------+
 | CONTEXT WINDOW = everything Claude can see in this session:      |
 | your messages, files read, command output, CLAUDE.md             |
 +------------------------------------------------------------------+
   ^ everything below is added to the window
 1 YOU ask or correct. (Esc stops Claude at any moment.)
   v
 2 CLAUDE reads and searches files <--------------------------+
   v                                                          |
 3 CLAUDE proposes ONE step: edit a file or run a command     |
   v                                                          |
 4 HOOK before the step (a script, if set up; can block it)   |
 5 PERMISSION: your mode and rules decide if you are asked    |
 6 STEP RUNS. HOOK after it (a script, if set up) adds a note |
   v                                                          |
 7 RESULT is added to the context window. More to do?  -------+
   v done
 8 CLAUDE answers. YOU REVIEW the diff and the output. Back to 1.
```

Read it like this: After your request, Claude repeats a small loop on its own: read files, propose one step, run it, read the result. Hooks are scripts that run at fixed points, if you set them up; at the permission step you, or your mode, say yes or no. CLAUDE.md is loaded into the context window when a session starts, every result is added to it, and you review when Claude stops.

Common wrong picture: Claude remembers earlier sessions by itself, and CLAUDE.md is a lock. Correct: each session starts with an empty context window; CLAUDE.md is text Claude reads (and so is auto memory), while hooks and permission rules are what actually enforce a limit.
