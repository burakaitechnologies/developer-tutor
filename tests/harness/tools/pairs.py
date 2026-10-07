"""pairs.py - print tool call -> tool result pairs of a run saved by run_case.py (what the model was told after each call).

  python pairs.py RUN [max-characters-per-result]
Read-only. Python 3.9 syntax, standard library only.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import requests_view  # noqa: E402
import show  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.stdout.write(__doc__ or "")
        sys.exit(0)
    extra = ["--max", sys.argv[2]] if len(sys.argv) > 2 else []
    sys.exit(requests_view.main([show.run_dir(sys.argv[1]), "--pairs"] + extra))
