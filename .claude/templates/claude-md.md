<!-- WHAT: the shape of the project's root CLAUDE.md that the tutor-setup skill creates or extends.
Claude Code reads CLAUDE.md at the start of every session, and every agent gets it.
HOW: if CLAUDE.md does not exist, copy from "# Project" down and fill every part in angle brackets in plain
words, close to what the learner said. If it exists, append only a short "## Tutor" section and never remove
what is there. Ask the learner first. Keep it under 60 lines. Do not copy this comment. -->
# Project

## What this project is
<what the learner is building and why, in two or three plain sentences>

## How to run and test it
<the exact commands, once they exist>

## The learner
- Language and reading level: <for example "English, level B1"> (details: .claude/agent-memory/tutor-data/learner/profile.md).
- The goal of the project and the correct method weigh more than a first preference. The last decision is always the learner's.
- <one short line for each standing correction the learner gave, with its date>

## Tutor
This project uses the Developer Tutor (.claude/). Notes are in .claude/agent-memory/tutor-data/ and stay on this computer.
