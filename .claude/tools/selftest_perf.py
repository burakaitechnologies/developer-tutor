"""selftest_perf.py - hook speed: the median run time of each hook, through the exact launcher, must stay under 250 ms.

What: run() -> failure messages. Starts each hook 9 times (3 with --quick) in a scratch project with a little
history and checks the median. median_ms() is also used by hand to measure 20 runs (see the test report).
Why: a hook runs on every message and every tool call; a slow hook is felt by the learner (SPEC 0, gate G0).
The limit can be raised on a very slow computer with the environment variable TUTOR_SELFTEST_LATENCY_MS.
How it fails safely: scratch folders only; no network.
Who calls it: tools/selftest.py.
"""
from __future__ import annotations

import os
import statistics
import sys

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import testkit  # noqa: E402


def payloads(session_id):
    return {
        "session-start": {"hook_event_name": "SessionStart", "source": "startup", "session_id": session_id},
        "user-prompt": {"hook_event_name": "UserPromptSubmit", "prompt": "Please change the title of my page", "prompt_id": "perf1",
                        "session_id": session_id, "permission_mode": "default"},
        "post-tool": {"hook_event_name": "PostToolUse", "tool_name": "Bash", "tool_input": {"command": "ls"},
                      "tool_response": {"stdout": "x"}, "session_id": session_id, "prompt_id": "perf1"},
        "stop": {"hook_event_name": "Stop", "last_assistant_message": "I changed the title. Check: what does the title look like now?",
                 "session_id": session_id, "prompt_id": "perf1"},
        "subagent-start": {"hook_event_name": "SubagentStart", "agent_type": "general-purpose", "session_id": session_id},
        "pre-tool": {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "git status"}, "session_id": session_id},
    }


def median_ms(project, mode, data, runs):
    times = []
    for _ in range(runs):
        r = testkit.launch(project, mode, data)
        times.append(r.ms)
    return statistics.median(times), min(times), max(times)


def run():
    failures = []
    limit = float(os.environ.get("TUTOR_SELFTEST_LATENCY_MS", "250"))
    runs = 3 if testkit.quick() else 9
    base = testkit.temp_base()
    try:
        proj = testkit.make_project(base)
        sid = "perf-session"
        s = testkit.Session(proj, sid)
        s.start()
        s.prompt("hello")
        s.stop("Hi. Check: what is a page?")
        testkit.launch(proj, "session-start", payloads(sid)["session-start"])   # warm the file cache
        for mode, data in payloads(sid).items():
            if mode == "pre-tool" and not os.path.exists(os.path.join(testkit.PRODUCT_DIR, "hooks", "handlers", "pre_tool.py")):
                continue
            med, lo, hi = median_ms(proj, mode, data, runs)
            if med > limit:
                failures.append("%s: median %.0f ms over the %.0f ms limit (min %.0f, max %.0f, %d runs)" % (mode, med, limit, lo, hi, runs))
    finally:
        testkit.remove_tree(base)
    return failures
