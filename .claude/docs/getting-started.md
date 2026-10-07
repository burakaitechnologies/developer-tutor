# Getting started

Facts about the Desktop app and Claude Code were checked 2026-10-07.

A small first version comes a few minutes after your first answer. Installing takes extra time. Read one step, then do it.

## Before you start

You need a Claude plan that includes Claude Code. The free plan does not include it.

You need Claude Code. Use the Desktop app, the terminal program, or both.

- **Desktop app (Windows or macOS):** download it at [claude.com/download](https://claude.com/download). Open it and sign in.
- **Terminal program:** follow the official [setup guide](https://code.claude.com/docs/en/setup). On Windows, open PowerShell and run `irm https://claude.ai/install.ps1 | iex`.
- **Check it:** open a new terminal window. Run `claude --version`. It prints a version number.

Make a new empty folder for your project. Copy the `.claude` folder into it. The [README](../README.md) shows how.

## Part 1: Desktop app

1. Open the Claude Desktop app. Sign in.
2. Click the **Code** tab.
3. Click **+ New session** in the sidebar.
4. In the prompt area, choose your project folder.
5. Check **Environment**. Choose **Local**. Local means your own computer.
6. Look at the mode selector next to the send button. It shows how much Claude asks you first. This kit starts in **Accept edits**.
7. For your first week, keep **Accept edits**. Claude then changes files in your project folder without asking. It still asks before other commands. Choose **Manual** if you want to approve every change.
8. Type `hello`. Press **Enter**.

## Part 2: Terminal

1. Open a terminal in your project folder.
   - Windows: open the folder in File Explorer. Click the address bar. Type `powershell` and press Enter.
   - macOS: open Terminal. Type `cd`, a space, then drag your folder into the window. Press Enter.
2. Type `claude` and press Enter.
3. Type `hello` and press Enter.

In the terminal, press **Shift+Tab** to change how much Claude asks you. Each press moves to the next mode: Manual, Accept edits, then Plan. This kit starts terminal sessions in Accept edits.

## The trust question

Claude Code may ask if you trust this folder. Read the question first.

The question means the folder's settings can run programs. Say yes only for a folder you made or trust.

If you say no, the allow rules do not apply. The deny and ask rules still apply. The [FAQ answer on trust](faq.md#q-what-does-trust-this-folder-mean) explains more.

## What to type first

Type one sentence about what you want to make. For example: "I want a page with my favorite recipes."

You can also type `hello`. The tutor then asks you one or two questions.

## What Claude does next

- Claude asks one or two questions. Answer in your own words.
- A few minutes after your first answer, Claude builds a small version.
- Claude tells you where the file is and how to open it.
- Claude gives you one small step to do yourself. For example, change one word.

## How to read the tutor's answers

- **The result comes first.** Read it first.
- **Check:** asks a small question. Answer in your own words.
- **Predict:** asks what you think will happen before you run something.
- **Your move:** asks you to change one thing yourself.
- **How to check:** shows where to look to test the result.
- **Added to your list: <title>.** The tutor says this after a save. The first time, it also says the list is private. The list stays on this computer.
- **Change card:** lists what changed. Each file has its full folder path. For example: created 2, changed 1, deleted 0.
- **Next I can teach:** lists topics you can learn next. Pick one, or say no.
- Say **quiet mode** to get fewer lessons. Say **teach me** to get lessons back.
- Say **just do it** to get the fix now, with fewer questions. The tutor still asks before a step that is hard to undo.

## Later: turn on the helper scripts

The helper scripts are off at first. When they are on, they add three things. They add facts to each message. They add a safety guard that stops risky commands. They keep a record of what you understood.

To turn them on, say "turn on helper scripts" to the tutor. Or run `enable-hooks` from your project folder. It changes `.claude/settings.json`. It keeps a copy of the old file. To turn them off, run `disable-hooks`. The [README](../README.md#the-helper-scripts) has the exact commands.

## Remember these three things in week 1

1. Use plain words. Say "explain that more simply" when you are lost.
2. Say **quiet mode** when you want fewer lessons.
3. Type `/tutor` to see the menu and where you are.

## When you are stuck

1. Copy the exact error text. Paste it to the tutor.
2. Say which words you know. Say which file the error names.
3. Say "I am stuck" if you want a hint first. Say "just do it" if you want the fix now.

## How to stop

- Desktop app: click the **stop** button.
- Terminal: press **Esc**. Claude keeps the work it finished.

## Where to get help

- Type `/tutor`, then say "is it working". The tutor runs a health check.
- In the Desktop app, click **Terminal** in the title bar. Or press Ctrl+backtick. This works only in local sessions.
- [docs/faq.md](faq.md) answers common questions.
- [docs/troubleshooting.md](troubleshooting.md) lists problems and their fixes.
