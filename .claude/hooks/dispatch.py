"""dispatch.py - the one entry point of every hook: python dispatch.py <mode> (SPEC 4.1).
Why: the launcher in tools/hooks.json stays short and every mode shares the same safe start.
Fails safe: a start-up problem is one stderr line and exit 1 (never 2); no pre-tool handler = silent exit 0."""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MODE = sys.argv[1] if len(sys.argv) > 1 else ""
if MODE == "pre-tool" and not os.path.isfile(os.path.join(HERE, "handlers", "pre_tool.py")):
    sys.exit(0)  # no guard installed: print nothing
try:
    from lib import hookio
    if MODE == "session-start":
        from handlers import session_start as mod
    elif MODE == "user-prompt":
        from handlers import user_prompt as mod
    elif MODE == "pre-tool":
        from handlers import pre_tool as mod
    elif MODE == "post-tool":
        from handlers import post_tool as mod
    elif MODE == "stop":
        from handlers import stop as mod
    elif MODE == "subagent-start":
        from handlers import subagent_start as mod
    else:
        raise ValueError("unknown mode")
except Exception as exc:  # start-up failure: never block the user
    sys.stderr.write("tutor hook %s could not start: %s\n" % (MODE[:20], type(exc).__name__))
    if "hookio" in globals():
        hookio.log_note(MODE, "could not start: " + type(exc).__name__ + " " + str(getattr(exc, "name", "") or "")[:60])
    sys.exit(0 if MODE == "pre-tool" else 1)
hookio.run(MODE, getattr(mod, "handle", None) or getattr(mod, "main", None) or (lambda: None))
