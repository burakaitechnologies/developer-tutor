"""lastuser.py - print the text blocks of the first user message of a run saved by run_case.py, except the
CLAUDE.md / attribution blocks. For a slash command or a skill this is the expanded text the model received.

  python lastuser.py RUN [max-characters]
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
    limit = int(argv[1]) if len(argv) > 1 else 1800
    rows = requests_view.load(show.run_dir(argv[0]))
    if not rows:
        sys.stdout.write("(NO REQUEST REACHED THE MODEL)\n")
        return 1
    message = rows[0]["body"]["messages"][0]
    content = message["content"]
    for block in (content if isinstance(content, list) else [{"type": "text", "text": content}]):
        text = block.get("text", "")
        if "Codebase and user instructions" in text or "Attribution for git" in text:
            continue
        sys.stdout.buffer.write((text[:limit] + "\n").encode("utf-8", errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
