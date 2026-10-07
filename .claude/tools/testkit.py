"""testkit.py - helpers shared by the selftests and by tests/sim_session.py (not a test itself).

What: builds a scratch project (a copy of the product plus decoy files), runs a hook through the EXACT
launcher from tools/hooks.json with CLAUDE_PROJECT_DIR set, and offers a small Session class that plays a
conversation (start, prompt, answer, tool calls) against the real hooks.
Why: every claim about a hook must be tested the way Claude Code runs it: a project path with a space and a
Turkish letter, decoy random.py / json.py / secrets.py in the project root, stdin as UTF-8 JSON.
How it fails safely: it only writes inside the scratch folders it creates (under the system temp folder or the
folder it is given); never in the product folder. No network. Standard library only.
Who calls it: selftest_*.py modules and repo/tests/sim_session.py.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

sys.dont_write_bytecode = True

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PRODUCT_DIR = os.path.dirname(TOOLS_DIR)                 # the .claude folder this file belongs to
DECOYS = ("random.py", "json.py", "secrets.py", "re.py", "subprocess.py", "pathlib.py", "os.py", "hashlib.py")
DEFAULT_NAME = "proj ş1"                             # a space and a Turkish letter on purpose


class Result(object):
    def __init__(self, rc: int, out: str, err: str, ms: float) -> None:
        self.rc, self.out, self.err, self.ms = rc, out, err, ms

    def json(self) -> Any:
        try:
            return json.loads(self.out)
        except ValueError:
            return None

    def context(self) -> str:
        """The text the model would see: plain stdout, or additionalContext of the JSON object."""
        obj = self.json()
        if isinstance(obj, dict):
            return str((obj.get("hookSpecificOutput") or {}).get("additionalContext") or "")
        return self.out

    def __repr__(self) -> str:
        return "Result(rc=%d, out=%r, err=%r, %.0f ms)" % (self.rc, self.out[:200], self.err[:200], self.ms)


def quick() -> bool:
    return os.environ.get("TUTOR_SELFTEST_QUICK") == "1"


def temp_base(prefix: str = "tutor-test-") -> str:
    return tempfile.mkdtemp(prefix=prefix)


def remove_tree(path: str) -> None:
    """Delete a scratch folder we created (tests only)."""
    def onerror(func, p, exc):
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)


def make_project(base: str, name: str = DEFAULT_NAME, product: Optional[str] = None, decoys: bool = True,
                 copy_product: bool = True) -> str:
    """A scratch project folder with a copy of the product in .claude/ (without tutor data and caches)."""
    proj = os.path.join(base, name)
    os.makedirs(proj, exist_ok=True)
    if copy_product:
        src = product or PRODUCT_DIR
        dst = os.path.join(proj, ".claude")
        if os.path.exists(dst):
            remove_tree(dst)
        shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "agent-memory", "*.pyc", "*.tutor-backup"))
    if decoys:
        for decoy in DECOYS:
            with open(os.path.join(proj, decoy), "w", encoding="utf-8", newline="\n") as f:
                f.write("raise SystemExit('DECOY %s WAS IMPORTED')\n" % decoy)
        os.makedirs(os.path.join(proj, "lib"), exist_ok=True)
        with open(os.path.join(proj, "lib", "__init__.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("raise SystemExit('DECOY lib WAS IMPORTED')\n")
    return proj


def hook_entry(mode: str, product: Optional[str] = None) -> Dict[str, Any]:
    spec = json.load(open(os.path.join(product or PRODUCT_DIR, "tools", "hooks.json"), encoding="utf-8"))["hooks"]
    for groups in spec.values():
        for group in groups:
            for handler in group["hooks"]:
                if handler["args"][-1] == mode:
                    return handler
    raise KeyError(mode)


def python_command(entry: Dict[str, Any]) -> str:
    """The interpreter named in hooks.json if it is on PATH, else the interpreter running the tests.
    The environment variable TUTOR_TEST_PYTHON (a full path) forces another interpreter, e.g. to try 3.9."""
    forced = os.environ.get("TUTOR_TEST_PYTHON", "")
    if forced and os.path.isfile(forced):
        return forced
    name = entry["command"]
    found = shutil.which(name)
    if found and not _is_store_stub(found):
        return found
    return sys.executable


def _is_store_stub(path: str) -> bool:
    low = path.lower().replace("\\", "/")
    return "/microsoft/windowsapps/" in low and os.path.getsize(path) == 0


def launch(project: str, mode: str, data: Optional[Dict[str, Any]] = None, env: Optional[Dict[str, str]] = None,
           raw: Optional[bytes] = None, timeout: float = 60.0, cwd: Optional[str] = None,
           product: Optional[str] = None) -> Result:
    """Run one hook through the exact launcher command of tools/hooks.json."""
    entry = hook_entry(mode, product)
    argv = [python_command(entry)] + list(entry["args"])
    environ = dict(os.environ)
    environ["CLAUDE_PROJECT_DIR"] = project
    environ.pop("PYTHONUTF8", None)
    environ.pop("PYTHONIOENCODING", None)
    environ.pop("TUTOR_FAKE_NOW", None)
    environ.update(env or {})
    stdin = raw if raw is not None else json.dumps(data if data is not None else {}).encode("utf-8")
    start = time.perf_counter()
    try:
        proc = subprocess.run(argv, input=stdin, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environ,
                              cwd=cwd or project, timeout=timeout)
        rc, out, err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        rc, out, err = 124, b"", b"timeout"
    ms = (time.perf_counter() - start) * 1000.0
    return Result(rc, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace"), ms)


def data_dir(project: str) -> str:
    return os.path.join(project, ".claude", "agent-memory", "tutor-data")


def read_data(project: str, *parts: str) -> str:
    try:
        with open(os.path.join(data_dir(project), *parts), encoding="utf-8") as f:
            return f.read()
    except OSError:
        return ""


def read_jsonl(project: str, *parts: str) -> List[Dict[str, Any]]:
    rows = []
    for line in read_data(project, *parts).split("\n"):
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except ValueError:
                pass
    return rows


def write_model_file(project: str, rel: str, text: str) -> str:
    """Write a file the way the model's Write tool would (UTF-8, LF) and return its absolute path."""
    path = os.path.join(project, *rel.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


class Session(object):
    """A scripted conversation against the real hooks (what the harness does for the model)."""

    def __init__(self, project: str, sid: str = "00000000-aaaa-bbbb-cccc-000000000001", product: Optional[str] = None,
                 env: Optional[Dict[str, str]] = None) -> None:
        self.project, self.sid, self.product = project, sid, product
        self.env = dict(env or {})
        self.n = 0
        self.last: Optional[Result] = None

    def run(self, mode: str, data: Dict[str, Any], **kw: Any) -> Result:
        data = dict(data)
        data.setdefault("session_id", self.sid)
        data.setdefault("cwd", self.project)
        self.last = launch(self.project, mode, data, env=self.env, product=self.product, **kw)
        return self.last

    def start(self, source: str = "startup") -> Result:
        return self.run("session-start", {"hook_event_name": "SessionStart", "source": source})

    def prompt(self, text: str, mode: str = "default") -> Result:
        self.n += 1
        return self.run("user-prompt", {"hook_event_name": "UserPromptSubmit", "prompt": text,
                                        "prompt_id": "p%03d" % self.n, "permission_mode": mode})

    def stop(self, answer: str) -> Result:
        return self.run("stop", {"hook_event_name": "Stop", "prompt_id": "p%03d" % self.n,
                                 "last_assistant_message": answer, "stop_hook_active": False})

    def write(self, rel: str, content: str = "x\n", created: bool = True) -> Result:
        path = write_model_file(self.project, rel, content)
        return self.run("post-tool", {"hook_event_name": "PostToolUse", "tool_name": "Write", "prompt_id": "p%03d" % self.n,
                                      "tool_input": {"file_path": path.replace("/", "\\") if os.name == "nt" else path,
                                                     "content": content},
                                      "tool_response": {"type": "create" if created else "update", "filePath": path}})

    def bash(self, command: str, tool: str = "Bash") -> Result:
        return self.run("post-tool", {"hook_event_name": "PostToolUse", "tool_name": tool, "prompt_id": "p%03d" % self.n,
                                      "tool_input": {"command": command}, "tool_response": {"stdout": "", "stderr": ""}})

    def state(self) -> Dict[str, Any]:
        try:
            return json.loads(read_data(self.project, "state", "state.json") or "{}")
        except ValueError:
            return {}


def loaded_modules(project: str, mode: str, data: Optional[Dict[str, Any]] = None) -> List[str]:
    """Names of lib.* and handlers.* modules loaded when a hook runs (the lazy-import check)."""
    hooks = os.path.join(project, ".claude", "hooks")
    code = (
        "import json,sys,os,runpy\n"
        "p=sys.argv[1]; sys.argv=[p,sys.argv[2]]\n"
        "try:\n"
        "    runpy.run_path(p,run_name='__main__')\n"
        "except SystemExit:\n"
        "    pass\n"
        "sys.stderr.write('LOADED '+json.dumps(sorted(m for m in sys.modules if m.startswith(('lib.','handlers.')))))\n"
    )
    environ = dict(os.environ)
    environ["CLAUDE_PROJECT_DIR"] = project
    proc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c", code, os.path.join(hooks, "dispatch.py"), mode],
                          input=json.dumps(data or {}).encode("utf-8"), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          env=environ, cwd=project, timeout=60)
    err = proc.stderr.decode("utf-8", "replace")
    marker = err.rfind("LOADED ")
    if marker < 0:
        return []
    try:
        return json.loads(err[marker + 7:].strip())
    except ValueError:
        return []
