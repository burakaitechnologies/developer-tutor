"""scenario_core_12turn.py - a scripted 12-turn session against the REAL hooks (gate G0 check 3, hook side).

What: a novice (scripted messages) and a tutor (scripted answers and tool calls) play 12 turns through
tests/sim_session.py's engine. The script checks what the hooks must do: every final answer gets one ledger
row (the count equals a hand count), true quotes become verified progress rows, a forged quote is refused,
a check line is recorded on the medium work answers, offer lines are counted, and the per-message line always starts with the time.
Why: the model cannot be tested here, but the loop around it can. A real tutor agent and a novice agent
judged by a rubric are run separately (see docs/test-report.md); this script is the deterministic part.
Usage: python scenario_core_12turn.py [--product DIR] [--keep]   (exit 0 = all checks passed)
How it fails safely: it only writes into a scratch folder under the system temp folder.
Who calls it: people and CI.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))


def find_product(argv):
    given = argv[argv.index("--product") + 1] if "--product" in argv else None
    for c in ([given] if given else [os.path.join(HERE, "..", ".claude"), os.path.join(HERE, "..", "..", ".claude")]):
        if c and os.path.isfile(os.path.join(c, "hooks", "dispatch.py")):
            return os.path.abspath(c)
    raise SystemExit("cannot find the product folder; use --product DIR")


# (learner message, [tool actions], tutor final answer)
# tool actions: ("write", relative path, content) or ("bash", command)
TURNS = [
    ("Hello, I want to make a page with my pasta recipe", [],
     "Hello. A recipe page is a good first project. What kind of pasta is the recipe for?"),
    ("Spaghetti with tomato sauce", [("write", "index.html", "<html>\n<head><title>Pasta</title></head>\n<body>\n<h1>Spaghetti</h1>\n</body>\n</html>\n")],
     "I made index.html with the title and a heading. Open the file in your browser to see it.\n\n"
     "HTML (the language that describes a web page) is what the file is written in.\n\n"
     "Change card: created 1, changed 0, deleted 0; new packages: none; network: none; check it with: open index.html.\n\n"
     "Check: Which line of index.html would you change to rename the page title?"),
    ("the title line, the one with the title tag, because that is where the page title is written",
     [("write", ".claude/agent-memory/tutor-data/inbox/t3.md",
       "learned web-html | the title line, the one with the title tag, because that is where the page title is written\n")],
     "Yes, the title tag holds the page title. I added this to your list."),
    ("Add the ingredients list", [("write", "index.html", "<html>\n<body>\n<ul>\n<li>spaghetti</li>\n<li>tomatoes</li>\n</ul>\n</body>\n</html>\n")],
     "The ingredients list is in index.html. Reload the page to see it.\n\nChange card: created 0, changed 1, deleted 0; new packages: none; network: none; check it with: reload the page."),
    ("Add the steps too", [("write", "index.html", "<html>\n<body>\n<ol>\n<li>boil</li>\n<li>mix</li>\n</ol>\n</body>\n</html>\n"), ("write", "style.css", "body { font-family: sans-serif; }\n")],
     "The steps and a small style file are ready. Reload the page.\n\nChange card: created 1, changed 1, deleted 0; new packages: none; network: none; check it with: reload."),
    ("ok", [], "Good. Next I can teach: what a save point is, what a repository is"),
    ("make a save point", [("bash", "git init -b main"), ("bash", "git add index.html style.css"), ("bash", "git commit -m \"first version\"")],
     "I made your first save point. A commit (a saved snapshot of your files) is what Git calls it.\n\n"
     "Change card: created 0, changed 0, deleted 0; new packages: none; network: none; check it with: git log --oneline.\n\n"
     "Predict: What will git log --oneline print?\n\nNext I can teach: what a branch is"),
    ("it prints one line with my message first version",
     [("write", ".claude/agent-memory/tutor-data/inbox/t7.md", "learned git-commit | it prints one line with my message first version\n")],
     "Right, one line with your message. I added this to your list."),
    ("what is a branch?", [], "A branch is a separate line of saved work. Your project has one branch named main."),
    ("I know css already", [],
     "Thank you. I will check it with one small step when the work needs it."),
    ("change the font color to green", [("write", "style.css", "body { font-family: sans-serif; color: green; }\n")],
     "The text is green now in style.css. Reload the page to see it."),
    ("thanks bye", [], "Bye. Your work is saved in the last save point."),
]
FORGED = ("learned git-branch | a branch is where the commits are copied to the cloud automatically", "t9.md")


def main(argv):
    product = find_product(argv)
    sys.path.insert(0, os.path.join(product, "tools"))
    import testkit
    base = testkit.temp_base("tutor-12turn-")
    env = {"TUTOR_FAKE_NOW": "2026-10-07T10:00:00+03:00"}
    problems = []

    def check(cond, msg):
        print(("ok    " if cond else "FAIL  ") + msg)
        if not cond:
            problems.append(msg)

    try:
        proj = testkit.make_project(base, product=product)
        s = testkit.Session(proj, env=env, product=product)
        r = s.start()
        check(r.out.startswith("=== Tutor session state ==="), "session start prints the capsule (%d characters)" % len(r.out))
        answers = 0
        refused = saved = 0
        times = []
        for i, (message, actions, answer) in enumerate(TURNS, 1):
            r = s.prompt(message)
            times.append(r.ms)
            check(r.rc == 0 and r.out.startswith("Now: "), "turn %d: the per-message line starts with the time" % i)
            for act in actions:
                if act[0] == "write":
                    r2 = s.write(act[1], act[2])
                else:
                    r2 = s.bash(act[1])
                times.append(r2.ms)
                ctx = r2.context()
                saved += ctx.count("Saved:")
                refused += ctx.count("Refused:")
            if i == 9:   # a forged quote in the middle of the session
                r2 = s.write(".claude/agent-memory/tutor-data/inbox/" + FORGED[1], FORGED[0] + "\n")
                refused += r2.context().count("Refused:")
            r3 = s.stop(answer)
            times.append(r3.ms)
            answers += 1
            check(r3.rc == 0 and r3.out == "", "turn %d: stop prints nothing" % i)
        rows = testkit.read_jsonl(proj, "state", "ledger.jsonl")
        check(len(rows) == answers, "the ledger has one row per final answer (%d rows, hand count %d)" % (len(rows), answers))
        progress = [e for e in testkit.read_jsonl(proj, "learner", "progress.jsonl") if e.get("src") == "inbox"]
        check(len(progress) >= 2, "at least 2 verified progress rows from true quotes (%d)" % len(progress))
        check(refused >= 1, "the forged quote was refused (%d refusals)" % refused)
        check(not any(e.get("id") == "git-branch" for e in progress), "the forged quote left no progress row")
        medium = [r_ for r_ in rows if r_["work_size"] in ("medium", "large")]
        with_check = [r_ for r_ in medium if r_["check_marker"]]
        print("      medium or large work answers: %d, with a marked check: %d" % (len(medium), len(with_check)))
        check(len(medium) >= 3, "the script contains medium work answers (%d)" % len(medium))
        check(any(r_["check_marker"] for r_ in medium), "a check line is recorded on a medium work answer")
        offers = [i for i, r_ in enumerate(rows, 1) if r_["offer_line"]]
        print("      offer lines on answers: %s" % offers)
        check(len(offers) <= 4, "offers are rare: at most one per 3 answers (%d in %d answers)" % (len(offers), answers))
        check(max(times) < 4000, "no hook took 4 seconds (slowest %.0f ms)" % max(times))
        st = s.state()
        check(st.get("session_count") == 1 and st.get("prompt_n") == len(TURNS), "state counts: session_count=%s prompt_n=%s" % (st.get("session_count"), st.get("prompt_n")))
        errors = testkit.read_data(proj, "state", "hook-errors.log")
        check(errors.strip() == "", "no hook errors were logged: %r" % errors[-200:])
    finally:
        if "--keep" not in argv:
            testkit.remove_tree(base)
        else:
            print("scratch kept at", base)
    print("RESULT: %s" % ("all checks passed" if not problems else "%d check(s) failed" % len(problems)))
    return 0 if not problems else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
