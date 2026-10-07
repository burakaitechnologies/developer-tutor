"""sim_session.py - play a tutor session against the REAL hooks, one step per command, and print what the model would see.

What: a command line wrapper around the real hook scripts. Each command runs a hook through the exact launcher
of tools/hooks.json (via tools/testkit.py), in a scratch project that holds a copy of the product, a folder name
with a space and a Turkish letter, and decoy random.py / json.py files. It prints the text or decision the model
would get. State between commands (session id, prompt counter, fake clock) lives next to the project, in DIR.sim/state.json and DIR.sim/env,
so separate calls behave like one session.
Why: layer 4 of the tests (SPEC 15) lets a tutor agent and a novice agent talk to each other while the hooks are
the real ones, and a person can follow the same conversation without a model.
How it fails safely: it only writes inside the project folder it was given and its sibling DIR.sim folder (never in the product); init refuses a
folder that is not an earlier sim project; no network; standard library only; output is written as UTF-8 bytes.

Usage:  python sim_session.py --project DIR <command> [args]      (init may omit --project)
  init [--name NAME] [--product DIR] [--clean]   create the scratch project, print its path (--clean: no decoy files)
  start [--source startup|resume|clear|compact]   SessionStart text, exactly as the model sees it
  turn-start "<learner message>" | --file FILE [--mode default]  UserPromptSubmit text for that message
  turn-end FILE                        Stop hook for the tutor answer in FILE; prints the exit status, then a ledger row
  post-write FILE-OR-REL [--content-from FILE] [--update]   PostToolUse for a Write; prints the additionalContext text
  post-bash "<command>" [--tool PowerShell]   PostToolUse for a shell command
  pre-bash "<command>" [--tool PowerShell]    PreToolUse guard: DENY / ASK / WARN / NONE and the reason
  pre-write FILE-OR-REL [--content-from FILE]  PreToolUse guard for a Write
  inbox-write "<line(s)>"              write a NEW inbox file like the model, then PostToolUse; prints Saved / Refused
  state                                state.json, the last 5 ledger rows, progress.jsonl row count
  show FILE                            print a file of the tutor data (path relative to agent-memory/tutor-data)
  fake-now "<ISO time>" [--tick N]     freeze the hook clock (TUTOR_FAKE_NOW); --tick N adds N minutes after each hook
  surface terminal|desktop|vscode|headless   pretend to be that surface (CLAUDE_CODE_ENTRYPOINT); default terminal
  reset                                remove the learner data and the saved session, keep the product copy
  subagent [type]                      SubagentStart text for a helper agent
  tail <ledger|progress|activity|recent|errors|state> [N]
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import sys
import tempfile
import uuid
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_NAME = "proj ş1"          # a space and a Turkish letter on purpose
DATA_REL = (".claude", "agent-memory", "tutor-data")


def out(text: str = "") -> None:
    try:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
        sys.stdout.flush()
    except (OSError, ValueError):
        pass


def err(text: str) -> None:
    try:
        sys.stderr.buffer.write((text + "\n").encode("utf-8", errors="replace"))
        sys.stderr.flush()
    except (OSError, ValueError):
        pass


def find_product(given: Optional[str] = None) -> str:
    candidates = [given, os.environ.get("TUTOR_PRODUCT"), os.path.join(HERE, "..", ".claude"), os.path.join(HERE, "..", "..", ".claude")]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "hooks", "dispatch.py")):
            return os.path.abspath(c)
    raise SystemExit("cannot find the product folder (a .claude folder with hooks/dispatch.py); use --product DIR")


def load_testkit(product: str) -> Any:
    sys.path.insert(0, os.path.join(product, "tools"))
    import testkit  # type: ignore
    return testkit


def split_args(argv: List[str]) -> Tuple[Dict[str, Any], List[str]]:
    """Options with a value and flags may appear anywhere; everything else is positional."""
    valued = ("--project", "--product", "--name", "--source", "--mode", "--content-from", "--tool", "--tick", "--file")
    flags = ("--update", "--framed", "--clean")
    opts: Dict[str, Any] = {}
    rest: List[str] = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a in valued and i + 1 < len(argv):
            opts[a[2:]] = argv[i + 1]
            i += 2
            continue
        if a in flags:
            opts[a[2:]] = True
            i += 1
            continue
        rest.append(a)
        i += 1
    return opts, rest


class Sim(object):
    """The scratch project and the small state files next to it."""

    def __init__(self, project: str, product: str) -> None:
        self.project, self.product = os.path.abspath(project), product
        self.tk = load_testkit(product)
        # The bookkeeping lives NEXT TO the project (name + ".sim"), so a tutor agent never sees it in the tree.
        self.sim_dir = self.project + ".sim"
        self.state_file = os.path.join(self.sim_dir, "state.json")
        self.env_file = os.path.join(self.sim_dir, "env")
        self.cfg: Dict[str, Any] = {"sid": str(uuid.uuid4()), "n": 0, "inbox": 0, "tick": 0}
        try:
            with open(self.state_file, encoding="utf-8") as f:
                self.cfg.update(json.load(f))
        except (OSError, ValueError):
            pass

    # ---- state
    def save(self) -> None:
        os.makedirs(self.sim_dir, exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8", newline="\n") as f:
            json.dump(self.cfg, f)

    def env(self) -> Dict[str, str]:
        """Variables for the hooks: the saved ones (DIR.sim/env) over the default surface (a plain terminal)."""
        values: Dict[str, str] = {"CLAUDE_CODE_ENTRYPOINT": "cli"}
        try:
            with open(self.env_file, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    if "=" in line and not line.startswith("#"):
                        key, value = line.split("=", 1)
                        values[key.strip()] = value.strip()
        except OSError:
            pass
        return values

    def set_env(self, key: str, value: str) -> None:
        saved: Dict[str, str] = {}
        try:
            with open(self.env_file, encoding="utf-8") as f:
                for line in f.read().splitlines():
                    if "=" in line and not line.startswith("#"):
                        k, v = line.split("=", 1)
                        saved[k.strip()] = v.strip()
        except OSError:
            pass
        saved[key] = value
        os.makedirs(self.sim_dir, exist_ok=True)
        with open(self.env_file, "w", encoding="utf-8", newline="\n") as f:
            for k in sorted(saved):
                f.write("%s=%s\n" % (k, saved[k]))

    def set_now(self, iso: str) -> None:
        self.set_env("TUTOR_FAKE_NOW", iso)

    def tick(self) -> None:
        minutes = int(self.cfg.get("tick") or 0)
        now = self.env().get("TUTOR_FAKE_NOW")
        if minutes and now:
            moment = datetime.datetime.fromisoformat(now) + datetime.timedelta(minutes=minutes)
            self.set_now(moment.replace(microsecond=0).isoformat())

    # ---- running hooks
    def prompt_id(self) -> str:
        return "p%03d" % int(self.cfg["n"])

    def run(self, mode: str, data: Dict[str, Any]) -> Any:
        data = dict(data)
        data.setdefault("session_id", self.cfg["sid"])
        data.setdefault("cwd", self.project)
        result = self.tk.launch(self.project, mode, data, env=self.env(), product=self.product)
        self.tick()
        self.save()
        if result.err.strip() or result.rc not in (0, 2):
            err("[hook %s exit %d] %s" % (mode, result.rc, " ".join(result.err.split())[:400]))
        return result

    def data_path(self, *parts: str) -> str:
        return os.path.join(self.project, *(DATA_REL + parts))

    def abs_path(self, target: str) -> str:
        if os.path.isabs(target):
            return target
        return os.path.join(self.project, *target.replace("\\", "/").split("/"))

    def native(self, path: str) -> str:
        """The path the way Claude Code reports it to hooks on this system (backslashes on Windows)."""
        return path.replace("/", "\\") if os.name == "nt" else path


def context_of(result: Any) -> str:
    return result.context() if result.out.lstrip().startswith("{") else result.out


def emit_context(result: Any, framed: str = "") -> None:
    text = context_of(result).rstrip("\n")
    if not text.strip():
        err("(no text for the model)")
        return
    out((framed + text) if framed else text)


def decision_of(result: Any) -> Tuple[str, str]:
    """(DENY|ASK|WARN|NONE, text) from a PreToolUse run, the way Claude Code would act on it."""
    text = result.out.strip()
    if not text:
        return ("DENY", "hook exit 2 without text") if result.rc == 2 else ("NONE", "")
    try:
        obj = json.loads(text)
    except ValueError:
        return "NONE", "(output was not JSON and is ignored by Claude Code: %s)" % text[:120]
    special = obj.get("hookSpecificOutput") or {}
    decision = special.get("permissionDecision")
    if decision == "deny":
        return "DENY", str(special.get("permissionDecisionReason") or "")
    if decision == "ask":
        return "ASK", str(special.get("permissionDecisionReason") or "")
    if decision == "allow":
        return "NONE", "WARNING: the hook printed permissionDecision allow, which auto-approves the call"
    if special.get("additionalContext"):
        return "WARN", str(special["additionalContext"])
    return "NONE", ""


def last_ledger_row(sim: Sim) -> str:
    rows = sim.tk.read_jsonl(sim.project, "state", "ledger.jsonl")
    if not rows:
        return json.dumps({"ledger": "no row written"})
    row = rows[-1]
    keys = ("prompt_id", "words", "result_words", "work_size", "check_marker", "fishing", "offer_line", "glossed", "unexplained", "banned_hits", "level_cap")
    return json.dumps({k: row.get(k) for k in keys if k in row}, ensure_ascii=False)


def write_file(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def read_content(opts: Dict[str, Any]) -> Optional[str]:
    if opts.get("content-from"):
        with open(opts["content-from"], encoding="utf-8-sig") as f:
            return f.read()
    return None


def cmd_init(opts: Dict[str, Any], rest: List[str]) -> int:
    product = find_product(opts.get("product"))
    tk = load_testkit(product)
    if opts.get("project"):
        project = os.path.abspath(opts["project"])
        base, name = os.path.dirname(project), os.path.basename(project)
        if os.path.exists(project):
            if os.path.isfile(os.path.join(project + ".sim", "state.json")):
                tk.remove_tree(project)
                tk.remove_tree(project + ".sim")          # counters and clock start fresh too
            elif os.listdir(project):
                err("refusing: %s exists and is not an earlier sim project (no state next to it)" % project)
                return 1
    else:
        base, name = tempfile.mkdtemp(prefix="tutor-sim-"), opts.get("name") or DEFAULT_NAME
    os.makedirs(base, exist_ok=True)
    project = tk.make_project(base, name=opts.get("name") or name, product=product, decoys=not opts.get("clean"))
    sim = Sim(project, os.path.join(project, ".claude"))
    sim.save()
    out(project)
    return 0


def main(argv: List[str]) -> int:
    opts, rest = split_args(argv)
    if not rest:
        out(__doc__ or "")
        return 0
    cmd, args = rest[0], rest[1:]
    if cmd == "init":
        return cmd_init(opts, args)
    project = opts.get("project") or os.environ.get("TUTOR_SIM_PROJECT")
    if not project:
        err("missing --project DIR (run 'init' first; it prints the path)")
        return 1
    if not os.path.isfile(os.path.join(project, ".claude", "hooks", "dispatch.py")):
        err("no sim project at %s (run 'init')" % project)
        return 1
    sim = Sim(project, os.path.join(os.path.abspath(project), ".claude"))
    tk = sim.tk

    if cmd == "start":
        source = opts.get("source") or (args[0] if args else "startup")
        if source in ("startup", "clear"):
            sim.cfg["sid"] = str(uuid.uuid4())
        r = sim.run("session-start", {"hook_event_name": "SessionStart", "source": source})
        emit_context(r)
        return 1 if r.rc == 1 else 0
    if cmd == "turn-start":
        sim.cfg["n"] = int(sim.cfg["n"]) + 1
        message = args[0] if args else ""
        if opts.get("file"):
            with open(opts["file"], encoding="utf-8-sig") as f:
                message = f.read().strip()
        r = sim.run("user-prompt", {"hook_event_name": "UserPromptSubmit", "prompt": message,
                                    "prompt_id": sim.prompt_id(), "permission_mode": opts.get("mode") or "default"})
        emit_context(r)
        return 1 if r.rc == 1 else 0
    if cmd == "turn-end":
        if not args:
            err("turn-end needs FILE with the tutor's answer")
            return 1
        with open(args[0], encoding="utf-8-sig") as f:
            answer = f.read()
        r = sim.run("stop", {"hook_event_name": "Stop", "prompt_id": sim.prompt_id(), "last_assistant_message": answer,
                             "stop_hook_active": False})
        out("exit %d" % r.rc)
        if r.out.strip():
            out("[unexpected stdout from Stop] " + r.out.strip()[:300])
        out(last_ledger_row(sim))
        return 1 if r.rc == 1 else 0
    if cmd in ("post-write", "pre-write"):
        if not args:
            err("%s needs a file" % cmd)
            return 1
        full = sim.abs_path(args[0])
        content = read_content(opts)
        if cmd == "post-write":
            if content is not None:
                write_file(full, content)
            elif os.path.isfile(full):
                with open(full, encoding="utf-8-sig") as f:
                    content = f.read()
            else:
                err("no such file and no --content-from: %s" % full)
                return 1
            path = sim.native(full)
            r = sim.run("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "Write", "prompt_id": sim.prompt_id(),
                                      "tool_input": {"file_path": path, "content": content},
                                      "tool_response": {"type": "update" if opts.get("update") else "create", "filePath": path}})
            emit_context(r)
            return 1 if r.rc == 1 else 0
        r = sim.run("pre-tool", {"hook_event_name": "PreToolUse", "tool_name": "Write", "prompt_id": sim.prompt_id(),
                                 "permission_mode": opts.get("mode") or "default",
                                 "tool_input": {"file_path": sim.native(full), "content": content if content is not None else ""}})
        kind, text = decision_of(r)
        out(kind)
        if text:
            out(("PreToolUse:Write hook error: " + text) if kind == "DENY" else text)
        return 1 if r.rc == 1 else 0
    if cmd in ("post-bash", "pre-bash"):
        tool = opts.get("tool") or "Bash"
        command = args[0] if args else ""
        if cmd == "post-bash":
            r = sim.run("post-tool", {"hook_event_name": "PostToolUse", "tool_name": tool, "prompt_id": sim.prompt_id(),
                                      "tool_input": {"command": command}, "tool_response": {"stdout": "", "stderr": ""}})
            emit_context(r)
            return 1 if r.rc == 1 else 0
        r = sim.run("pre-tool", {"hook_event_name": "PreToolUse", "tool_name": tool, "prompt_id": sim.prompt_id(),
                                 "permission_mode": opts.get("mode") or "default", "tool_input": {"command": command}})
        kind, text = decision_of(r)
        out(kind)
        if text:
            out(("PreToolUse:%s hook error: %s" % (tool, text)) if kind == "DENY" else text)
        return 1 if r.rc == 1 else 0
    if cmd == "inbox-write":
        text = (args[0] if args else "").replace("\\n", "\n")
        if not text.endswith("\n"):
            text += "\n"
        sim.cfg["inbox"] = int(sim.cfg["inbox"]) + 1
        full = sim.data_path("inbox", "sim-%03d.md" % sim.cfg["inbox"])
        path = sim.native(full)
        pre = sim.run("pre-tool", {"hook_event_name": "PreToolUse", "tool_name": "Write", "prompt_id": sim.prompt_id(),
                                   "permission_mode": opts.get("mode") or "default", "tool_input": {"file_path": path, "content": text}})
        kind, reason = decision_of(pre)
        if kind in ("DENY", "ASK"):
            out(kind)
            out(reason)
            return 0
        write_file(full, text)
        r = sim.run("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "Write", "prompt_id": sim.prompt_id(),
                                  "tool_input": {"file_path": path, "content": text},
                                  "tool_response": {"type": "create", "filePath": path}})
        answer = context_of(r).strip()
        out(answer if answer else "(no answer from the hook)")
        return 1 if r.rc == 1 else 0
    if cmd == "subagent":
        r = sim.run("subagent-start", {"hook_event_name": "SubagentStart", "agent_type": args[0] if args else "general-purpose", "agent_id": "a1"})
        emit_context(r)
        return 1 if r.rc == 1 else 0
    if cmd == "state":
        try:
            state = json.loads(tk.read_data(project, "state", "state.json") or "{}")
        except ValueError:
            state = {}
        out("session %s, %d prompts, clock %s" % (sim.cfg["sid"], int(sim.cfg["n"]), sim.env().get("TUTOR_FAKE_NOW", "real time")))
        out("state.json: " + json.dumps(state, ensure_ascii=False, sort_keys=True))
        ledger = tk.read_jsonl(project, "state", "ledger.jsonl")
        out("ledger rows: %d (last 5 below)" % len(ledger))
        for row in ledger[-5:]:
            out("  " + json.dumps(row, ensure_ascii=False))
        out("progress.jsonl rows: %d" % len(tk.read_jsonl(project, "learner", "progress.jsonl")))
        out("activity.jsonl rows: %d" % len(tk.read_jsonl(project, "state", "activity.jsonl")))
        return 0
    if cmd == "show":
        if not args:
            err("show needs FILE")
            return 1
        target = os.path.abspath(args[0]) if os.path.isabs(args[0]) else sim.data_path(*args[0].replace("\\", "/").split("/"))
        if not os.path.isfile(target):
            err("no such file: %s" % target)
            return 1
        with open(target, encoding="utf-8-sig", errors="replace") as f:
            sys.stdout.buffer.write(f.read().encode("utf-8", errors="replace"))
        sys.stdout.buffer.flush()
        return 0
    if cmd == "fake-now":
        if not args:
            err('fake-now needs an ISO time such as "2026-10-07T19:42:00"')
            return 1
        try:
            moment = datetime.datetime.fromisoformat(args[0])
        except ValueError:
            err("not an ISO time: %s" % args[0])
            return 1
        sim.set_now(moment.replace(microsecond=0).isoformat())
        sim.cfg["tick"] = int(opts.get("tick") or 0)
        sim.save()
        out("clock frozen at %s%s" % (moment.isoformat(), (", +%d min after each hook" % sim.cfg["tick"]) if sim.cfg["tick"] else ""))
        return 0
    if cmd == "surface":
        entry = {"terminal": "cli", "desktop": "claude-desktop", "vscode": "claude-vscode", "headless": "sdk-cli"}.get(args[0] if args else "")
        if not entry:
            err("surface needs one of: terminal, desktop, vscode, headless")
            return 1
        sim.set_env("CLAUDE_CODE_ENTRYPOINT", entry)
        out("surface is now %s (CLAUDE_CODE_ENTRYPOINT=%s)" % (args[0], entry))
        return 0
    if cmd == "reset":
        data = os.path.join(sim.project, *DATA_REL)
        if os.path.isdir(data):
            tk.remove_tree(data)
        if os.path.isfile(sim.env_file):
            os.remove(sim.env_file)
        sim.cfg = {"sid": str(uuid.uuid4()), "n": 0, "inbox": 0, "tick": 0}      # DIR.sim/state.json stays: it marks a sim project
        sim.save()
        out("reset: learner data removed, new session id, clock and surface back to the defaults")
        return 0
    if cmd == "tail":
        which = args[0] if args else "ledger"
        count = int(args[1]) if len(args) > 1 else 5
        files = {"ledger": ("state", "ledger.jsonl"), "progress": ("learner", "progress.jsonl"), "activity": ("state", "activity.jsonl"),
                 "recent": ("state", "recent-user.json"), "errors": ("state", "hook-errors.log"), "state": ("state", "state.json")}
        if which not in files:
            err("unknown file; choose one of: " + ", ".join(sorted(files)))
            return 1
        for line in [x for x in tk.read_data(project, *files[which]).split("\n") if x.strip()][-count:]:
            out(line)
        return 0
    err("unknown command %r (run without arguments for the list)" % cmd)
    return 1


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except SystemExit as stop:
        if isinstance(stop.code, str):
            err(stop.code)
            code = 1
        else:
            code = stop.code or 0
    sys.exit(code)
