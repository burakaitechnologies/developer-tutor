# Getting started

Facts about Codex here were checked 2026-10-08 in the official docs.

Read one step, then do it. Start with the ChatGPT desktop app. Use the terminal only if you like typing commands.

## Before you start

You need a ChatGPT account. Codex is included in ChatGPT plans, including Free. Limits differ by plan.

Make a new empty folder for the project. For example, name it `my-recipes`. Do not use Desktop, Downloads or Documents as the project folder.

## Part 1: The ChatGPT desktop app

1. Download the app at https://chatgpt.com/download/.
   On Windows, you can also use this command in PowerShell:
   `winget install --id 9PLM9XGG6VKS -s msstore`
2. Open the app. Sign in with your ChatGPT account.
   If you see Continue to sign in, select it. Finish the sign-in in your web browser.
3. Choose a folder. Start a chat, create a project, or open a folder. Choose your project folder.
   Codex can read and change files in the folder you choose.
4. Choose Codex. Select **Codex** in the ChatGPT dropdown. Then start a **New chat**.
5. Choose the permission. Select **Ask for approval**. It is the control below the message box.
   The next part explains why.
6. Type `hello` in the message box. Press Enter.

To open a terminal inside the app, select **New tab**, then **Terminal**. You can also press Ctrl+backtick. Each chat has its own terminal for its folder.

## Part 2: The Codex CLI

CLI means command-line interface. It is Codex in a terminal window, where you type commands.

1. Install Codex.
   On Windows, open a new PowerShell window. Run this command:
   `powershell -ExecutionPolicy ByPass -c "irm https://chatgpt.com/codex/install.ps1 | iex"`
   On macOS or Linux, run this command:
   `curl -fsSL https://chatgpt.com/codex/install.sh | sh`
2. Check the install. Run `codex --version`. It prints a version number.
3. Open a terminal in your project folder. Run `codex`.
4. The first time, choose **Sign in with ChatGPT**. Finish the browser step.
5. Type `hello` and press Enter.

## Part 3: The IDE extension

An IDE is a code editor with extra tools. Visual Studio Code is one example. The Codex IDE extension runs Codex inside your IDE.

Use the same steps as above. Trust the folder, choose Ask for approval, and type hello.

## The trust question

Codex may ask if you trust this folder. Until you trust it, Codex may start in read-only mode.

Read-only mode means Codex can read files, but it cannot change them.

Trusting a folder lets Codex load the settings in its `.codex` folder. Those settings can include rules for commands. Trust only a folder you made, or a folder you know well.

## Choose Ask for approval

An approval is your yes before a risky step. Codex stops and asks you first.

Ask for approval is the best start. Codex works inside the project folder. It asks before it goes outside that folder.

In the terminal, type `/permissions`. A preset is a ready-made setting. Choose the preset that asks before it goes outside the folder. The Codex docs call it **Auto**. Your picker may show another name.

Do not choose **Full access** on a personal computer. Full access is not limited to your project folder.

**Approve for me** sends some requests to an automatic reviewer. Start with Ask for approval.

## Why Codex asks before Git commands

Git is a tool that keeps a history of your project files. A save point is a Git commit. It is one saved entry in that history.

The `.git` folder keeps the history of your project. Codex asks before commands like `git commit`, because they write there.

This is normal. Say yes only when you want that step.

## What to type first

Type `hello`. Codex asks up to three short questions. Answer in your own words.

You can also type one sentence about what you want to make. For example: "I want a page with my favorite recipes."

## What Codex does next

- Codex asks up to three short questions.
- Codex builds a small first version in your folder.
- Codex tells you which file to open, and how to open it.
- Codex gives you one small step to do yourself.

## How to read the answers

- **The result comes first.** Read it first.
- **Check:** asks you a question. Answer in your own words.
- **Predict:** asks what you think will happen. Answer before you run anything.
- **Your move:** asks you to change one thing yourself.
- **How to check:** shows where to look to test the result.
- **Change card:** lists the files Codex created, changed or deleted. It also says whether Codex added packages or used the network. A package is code that someone else wrote.
- **Next I can teach:** lists up to three topics. Pick one, or say no.
- **Added to your list: <title>.** Codex writes this after you learn something or finish a step. Your list is your progress. The first time, Codex also says the list is private. It stays on this computer, in the `.tutor` folder.

## Quiet mode

Say **quiet mode** to get fewer lessons. Codex still gives the result and the safety notes. Say **teach me** to get the lessons back.

## When you are stuck

1. Copy the exact error text. Paste it into the chat.
2. Say which words you know. Say which file the error names.
3. Ask for a hint first. Or say "Just do it" to get the fix now. Codex still asks before a step that is hard to undo.

## How to stop

- Terminal: press Ctrl+C, or type `/exit`. Save your work first if you can.
- App: look near the message box for a stop control.

Before you stop, type `$save-point`. It saves your work with a Git commit.

## Where to get help

- Type `$tutor`, then say "is it working". The tutor checks the setup.
- Type `/status` in the terminal. It shows your folder and approval mode. It also lists the folders Codex can write to.
- Read `.agents/tutor/docs/troubleshooting.md` for common problems and fixes. Read `.agents/tutor/docs/faq.md` for common questions.

## Remember these three things in week 1

1. Use plain words. Say "explain that more simply" when you are lost.
2. Say "quiet mode" when you want fewer lessons.
3. Type `$tutor` to see the menu and where you are.
