"""run_case.py - run ONE headless `claude -p` case against the mock API and keep every request it sent.

What: the portable form of the command line tool of the first experiments. It starts the mock on a free port,
runs the real CLI in the given folder with a private config folder and a placeholder key, and saves
runs/<name>/req-NNN.json (what the model would have received), requests.jsonl, stdout.txt, stderr.txt and cmd.txt.
Why: scripted scenario files ("the model" calls these tools in this order) are handy for one-off probes, and other
test scripts (for example tests/guard_mcli.py) call this tool.
How it fails safely: the CLI gets no account variable and no real key (see harness/mockcli.py child_env); the
runs folder lives next to this tool (tests/harness/runs, git-ignored). A timeout stops only the child it started.
Python 3.9 syntax, standard library only.

  python run_case.py --name c1 --cwd PROJECT --prompt "hi" [--scenario FILE.json | --scenario-json '[{"text":"x"}]']
         [--cli "--permission-mode default --allowedTools Write"] [--env KEY=VAL ...] [--max-turns 6] [--timeout 120]
         [--user-config-dir DIR] [--no-stream-json]
Scenario entries answer the requests that offer tools, in order: {"text": "...", "tool_uses": [{"name": "Read", "input": {...}}]}.
Placeholders inside a scenario: {CWD} = project path with forward slashes, {CWDW} = project path with escaped backslashes.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import sys
from typing import List, Optional

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
HARNESS = os.path.dirname(HERE)
sys.path.insert(0, HARNESS)

import mockcli as m  # noqa: E402

RUNS = os.path.join(HARNESS, "runs")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Run one headless claude -p case against the mock API.")
    ap.add_argument("--name", required=True)
    ap.add_argument("--cwd", required=True)
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--scenario")
    ap.add_argument("--scenario-json")
    ap.add_argument("--cli", default="")
    ap.add_argument("--env", action="append", default=[])
    ap.add_argument("--max-turns", type=int, default=6)
    ap.add_argument("--timeout", type=int, default=120)
    ap.add_argument("--user-config-dir")
    ap.add_argument("--no-stream-json", action="store_true")
    a = ap.parse_args(argv)
    exe = m.claude_exe()
    if not exe:
        sys.stdout.write("SKIP: claude is not on PATH\n")
        return 0
    mt = re.match(r"^/([a-zA-Z])/(.*)$", a.cwd)          # MSYS style /c/... paths
    if mt:
        a.cwd = mt.group(1).upper() + ":/" + mt.group(2)
    cwd = os.path.abspath(a.cwd)
    raw: Optional[str] = a.scenario_json
    if raw is None and a.scenario:
        with open(a.scenario, encoding="utf-8-sig") as f:
            raw = f.read()
    scenario = None
    if raw is not None:
        raw = raw.replace("{BS}", chr(92) * 2).replace("{CWDW}", cwd.replace("\\", "\\\\")).replace("{CWD}", cwd.replace("\\", "/"))
        scenario = json.loads(raw)
    out = os.path.join(RUNS, a.name)
    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    cfg = a.user_config_dir or os.path.join(out, "_cfg")
    os.makedirs(cfg, exist_ok=True)
    server = m.start_mock_server(out, scenario, req_files=True)
    try:
        extra = dict(e.split("=", 1) for e in a.env)
        env = m.child_env(server.url, cfg, extra=extra)
        cmd = [exe, "-p", a.prompt, "--max-turns", str(a.max_turns)]
        if not a.no_stream_json:
            cmd += ["--output-format", "stream-json", "--verbose", "--include-hook-events"]
        user_args = shlex.split(a.cli, posix=True)
        if "--setting-sources" not in user_args:
            cmd += ["--setting-sources", "project,local"]
        cmd += user_args
        code, so, se, secs = m._execute(cwd, cmd, b"", env, float(a.timeout), cwd)
    finally:
        server.stop()
    for name, text in (("stdout.txt", so), ("stderr.txt", se), ("cmd.txt", json.dumps(cmd) + "\ncwd=" + cwd + "\n")):
        with open(os.path.join(out, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    reqs = [x for x in os.listdir(out) if x.startswith("req-")]
    used = server.scenario_index if scenario is not None else 0
    sys.stdout.write("case=%s rc=%s secs=%.1f requests=%d scenario_used=%d/%d\n" % (a.name, code, secs, len(reqs), used, len(scenario or [])))
    shown = False
    for line in reversed(so.splitlines()):
        try:
            j = json.loads(line)
        except ValueError:
            continue
        if isinstance(j, dict) and j.get("type") == "result":
            keys = ("is_error", "subtype", "result", "num_turns", "permission_denials", "terminal_reason")
            sys.stdout.buffer.write(("result: " + json.dumps({k: j.get(k) for k in keys}, ensure_ascii=False)[:1500] + "\n").encode("utf-8", "replace"))
            shown = True
            break
    if not shown:
        sys.stdout.buffer.write(("stdout head: " + so[:600] + "\n").encode("utf-8", "replace"))
    if se.strip():
        sys.stdout.buffer.write(("stderr head: " + se[:600] + "\n").encode("utf-8", "replace"))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
