"""handlers - one module per hook event. dispatch.py imports exactly one of them per run.

Each module offers handle(data): data is the JSON object Claude Code sends on stdin.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
