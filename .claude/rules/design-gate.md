# Design gate

For: every agent. The main agent runs the procedure with the think-first skill.

Bad architectural choices are cheap to avoid before the code exists. Pick the size of the gate by the work:

- **No gate:** a small edit, a typo, a bug fix in one place, a test, one file or one static page with no data, accounts, money, secrets or new package. Say the choice in one sentence and build. The first thing built in a project is always this size.
- **Short gate:** up to three files, local only. Restate the goal, ask at most one question with options and your recommendation, get one yes.
- **Full gate** (use think-first): a new project; a choice of language, framework, database, login, payment or hosting; a change touching more than eight files or reorganising folders; real user data or money; an outward or irreversible action such as deploy or making public.

Write a decision record (`docs/decisions/`, form in `.claude/templates/decision-record.md`) only for a decision that is hard to undo. Smaller choices get one line in the README or the journal.

Defaults that protect beginners: well-known tools you can check in the docs today, at most one new or exciting tool per project; the smallest thing that works; no home-made login, password storage or encryption; settings and secrets outside the code; data with a backup; a reversible choice over an irreversible one.

A tripwire fact from a hook (new package, new folder, risky code pattern) needs one plain sentence to the learner. It needs a decision record only if it is a hard-to-undo choice.
