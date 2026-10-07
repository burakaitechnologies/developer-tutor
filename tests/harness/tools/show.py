"""show.py - inspect the requests saved by run_case.py (a thin front for harness/requests_view.py).

  python show.py RUN                      overview of every request
  python show.py RUN -r 1 --system        the system prompt of request 1
  python show.py RUN -r 1 --msgs          all messages of request 1 (--max N cuts each block)
  python show.py RUN -r 1 --blocks        one line per text block of request 1
  python show.py RUN -g TOKEN1 TOKEN2     where each token appears
  python show.py RUN --pairs              tool call -> tool result pairs of the longest conversation
Other helpers in this folder: pairs.py RUN, lastuser.py RUN, subs.py RUN.
Read-only. Python 3.9 syntax, standard library only.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
sys.path.insert(0, HARNESS)

import requests_view  # noqa: E402

RUNS = os.path.join(HARNESS, "runs")


def run_dir(name: str) -> str:
    return name if os.path.isdir(name) else os.path.join(RUNS, name)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stdout.write(__doc__ or "")
        sys.exit(0)
    sys.exit(requests_view.main([run_dir(sys.argv[1])] + sys.argv[2:]))
