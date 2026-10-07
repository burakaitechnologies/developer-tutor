# Tidy project

For: every agent that creates or changes files.

Keep the project fit to show anyone at any moment.

- **Look first.** Read the structure and the README. Does something with the same purpose exist? Improve it instead of adding a second one, and delete a replaced file in the same step after telling the learner. Search for everything that mentions what you change, and update it too.
- **Use the file tools** (Write, Edit) to change files, not shell redirection, so the learner sees each change. Create `.gitignore` and `.env.example` with Write; Windows PowerShell redirection can save UTF-16, which Git cannot read.
- One purpose per file and folder. Names say the purpose, in the style the project already uses. One fact in one place.
- No temporary, half-finished or unused files. Do not rewrite the learner's README or other documents unasked.
- **Files that teach.** Comment depth follows `comments:` in the profile. `teaching`: start each new code file with a short header (what it is, why it exists, which files it works with) and comment the first use of a construct the learner has not met, at most one comment per five lines. `normal`: the header, and comments only where the reason is not obvious. `minimal`: what a professional would write. Never edit comments in existing project files.
- Commit messages: a summary line in the imperative ("Add login form"), and a body line when the reason is not obvious.
- After a change, the README, docs and tests agree with the code. New behaviour gets a test or a command the learner can run; say so when you skip one. Say what changed in two or three lines.
