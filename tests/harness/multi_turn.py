"""multi_turn.py - several user messages in ONE Claude Code process (needed to test /compact).

What: run_multi() sends the prompts as stream-json user messages on stdin of a single `claude -p` process and
returns the same Run object as mockcli.run_claude(). main() runs a compaction demo: hello, /compact, one more message,
and prints, for each request the mock received, whether CLAUDE.md, the output style, the skill list and the
hook-made state capsule were in it.
Why: two separate `claude -p --resume` calls do not compact the way one long session does; the SessionStart(compact)
hook and the loss of the skill list can only be seen inside one process.
How it fails safely: same isolation as mockcli (private config folder, placeholder key, loopback mock, scratch
project removed at the end). Skips with a plain message when `claude` is not on PATH. Python 3.9 syntax, stdlib only.
Use:  python multi_turn.py [--hooks] [--model NAME] [--product DIR]
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, List, Optional, Sequence

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mockcli as m  # noqa: E402


def run_multi(project: str, prompts: Sequence[str], **kw: Any) -> "m.Run":
    """Alias of mockcli.run_claude_stream: one process, one user message per prompt."""
    return m.run_claude_stream(project, prompts, **kw)


def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    hooks = "--hooks" in args
    model = args[args.index("--model") + 1] if "--model" in args else "claude-sonnet-4-5"
    product_arg = args[args.index("--product") + 1] if "--product" in args else None
    if not m.have_claude():
        m.say("SKIP: claude is not on PATH")
        return 0
    proj = m.make_project(m.find_product(product_arg), hooks=hooks)
    try:
        run = run_multi(proj, ["hello first", "/compact", "second question after the compact"], model=model)
        m.say("exit %s, %.1fs, %d requests; hook events: %s" % (run.returncode, run.seconds, len(run.requests), run.hook_summary()))
        for i, body in enumerate(run.model_requests):
            text = json.dumps(body, ensure_ascii=False)
            m.say("request %d: %6d chars | CLAUDE.md=%s style=%s skill list=%s state capsule=%s" % (
                i + 1, len(text), "installed in this project" in text, "# Output Style: tutor" in text,
                "The following skills are available" in text, "=== Tutor session state ===" in text))
    finally:
        m.cleanup_project(proj)
    return 0


if __name__ == "__main__":
    sys.exit(main())
