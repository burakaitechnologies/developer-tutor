"""subs.py - what each helper-agent (subagent) request of a run saved by run_case.py received.

  python subs.py RUN
For every request whose system prompt marks a subagent it prints: request number, tools offered, system size,
whether the CLAUDE.md block, the rules, the SubagentStart hook text and the output style reached it.
Read-only. Python 3.9 syntax, standard library only.
"""
from __future__ import annotations

import json
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import requests_view  # noqa: E402
import show  # noqa: E402


def main(argv):
    if not argv:
        sys.stdout.write(__doc__ or "")
        return 0
    rows = requests_view.load(show.run_dir(argv[0]))
    main_tools = []
    for row in rows:
        if "cc_is_subagent=true" not in requests_view.system_text(row["body"]) and row["body"].get("tools"):
            main_tools = [t.get("name") for t in row["body"]["tools"]]
            break
    for row in rows:
        body = row["body"]
        system = requests_view.system_text(body)
        if "cc_is_subagent=true" not in system:
            continue
        names = [t.get("name") for t in body.get("tools") or []]
        everything = json.dumps(body, ensure_ascii=False)
        line = "req%03d tools=%d %s | system=%dch | CLAUDE.md=%s rules=%s SubagentStart text=%s output style=%s" % (
            row["n"], len(names), names if len(names) <= 8 else "(missing vs main: %s)" % sorted(set(main_tools) - set(names)), len(system),
            "installed in this project" in everything, "rules" in everything and "Contents of" in everything,
            "The reader of your final report is a beginner" in everything, "# Output Style" in everything)
        sys.stdout.buffer.write((line + "\n").encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
