"""scenario.py - run a short scripted conversation through the real Claude Code CLI and the mock API, then show it.

What: copies the product into a scratch project (a space and a Turkish letter in the name, decoy random.py and
json.py in the root), optionally switches the hooks on, sends one prompt per --prompt (the second and later ones
resume the same session), and prints the stream summary plus what the mock received for each turn.
Why: a quick manual look before or after the automated scenarios (qa-scenario.sh of the first experiments, made
portable). With --multi all prompts go into ONE process (stream-json input), which is how /compact can be tried.
How it fails safely: the product is copied, never changed; a private config folder and a placeholder key are used;
the scratch folder is removed at the end unless --keep. Skips with a plain message when `claude` is not on PATH.
Python 3.9 syntax, standard library only.
Use:
  python scenario.py --prompt "hello" --prompt "RUN: echo hi" [--hooks] [--multi] [--model NAME]
                     [--mode default|acceptEdits|plan] [--allow Bash,Write] [--keep] [--product DIR]
Directives for the fake model are listed in mock_api.py (RUN: PS: READ: WRITE: TOOL: TOOLS: SKILL: AGENT:).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import List

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import mockcli as m  # noqa: E402
import stream_summary  # noqa: E402


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Scripted conversation through the real CLI and the mock API.")
    ap.add_argument("--prompt", action="append", default=[])
    ap.add_argument("--hooks", action="store_true", help="merge tools/hooks.json into the scratch copy of settings.json")
    ap.add_argument("--multi", action="store_true", help="send all prompts in one process (stream-json input)")
    ap.add_argument("--model")
    ap.add_argument("--mode", default="default")
    ap.add_argument("--allow", default="", help="comma separated tools for --allowedTools")
    ap.add_argument("--keep", action="store_true")
    ap.add_argument("--product")
    ap.add_argument("--git", action="store_true")
    args = ap.parse_args(argv)
    if not m.have_claude():
        m.say("SKIP: claude is not on PATH")
        return 0
    if not args.prompt:
        args.prompt = ["hello"]
    product = m.find_product(args.product)
    proj = m.make_project(product, hooks=args.hooks, git=args.git)
    allowed = [x for x in args.allow.split(",") if x]
    try:
        m.say("project: %s (settings source: %s)" % (proj, proj.settings_source))
        if args.multi:
            run = m.run_claude_stream(proj, args.prompt, permission_mode=args.mode, allowed_tools=allowed or None, model=args.model)
            runs = [run]
        else:
            sid = str(uuid.uuid4())
            runs = []
            for i, prompt in enumerate(args.prompt):
                runs.append(m.run_claude(proj, prompt, permission_mode=args.mode, allowed_tools=allowed or None, model=args.model,
                                         session_id=sid if i == 0 else None, resume=sid if i else None))
        for i, run in enumerate(runs):
            m.say("---- call %d: exit %s, %.1fs, %d requests reached the mock" % (i + 1, run.returncode, run.seconds, len(run.requests)))
            stream_summary.summarize(run.stdout.splitlines(), "call %d" % (i + 1))
            if run.stderr.strip():
                m.say("  stderr: %s" % " ".join(run.stderr.split())[:300])
            for j, body in enumerate(run.model_requests):
                text = json.dumps(body, ensure_ascii=False)
                m.say("  model request %d: %d chars | CLAUDE.md=%s style=%s skill list=%s state capsule=%s" % (
                    j + 1, len(text), "installed in this project" in text, "# Output Style: tutor" in text,
                    "The following skills are available" in text, "=== Tutor session state ===" in text))
    finally:
        if args.keep:
            m.say("kept: %s" % proj.base)
            if proj.base in m._BASES:
                m._BASES.remove(proj.base)
        else:
            m.cleanup_project(proj)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
