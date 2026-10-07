# Clear writing

For: every agent.

Write so that any reader understands each sentence in the same way, whatever their job or background.

- Use the language and level in `.claude/agent-memory/tutor-data/learner/profile.md`. Without a profile, use the language of the learner's first message, in simple English at about level B1.
- Plain words, sentences of about 20 words at most, one idea each. No idioms or slang. Numbers instead of vague words: "about 140 words", not "short".
- Explain a technical word in one plain sentence the first time it appears, and use the real word. In files, explain every term where it first appears. In the chat, explain only terms that are not on the learner's list.
- Keep commands, code, file names and error text exactly as they are.
- Show with real files and output. No metaphors. After a failed explanation you may use one analogy: say it is an analogy and where it stops being true.
- Do not write "easy", "just", "simply", "obviously" or "of course". No capitals or exclamation marks for emphasis.
- Product terms: a "save point" is a Git commit, and "your list" is the learner's progress. Define each once.
- If you write for a helper agent, say that the reader is a beginner, ask for plain words, and ask it to mark every unchecked statement UNVERIFIED.
