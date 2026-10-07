"""mockcli.py - run the REAL Claude Code CLI against the mock API and look at everything it did.

What: start_mock(), make_project(), run_claude(), run_claude_stream() and the Run object that holds the parsed
stream-json events, the tool calls and results, the permission denials, the hook events and the requests the
mock received (= exactly what the model would have seen).
Why: the login of a build machine may be expired, and the interesting questions are about Claude Code itself:
what it loads, which hooks it runs, what it blocks. Recipes: SPEC 15 layer 3.
How it fails safely: the child process gets a private config folder (nothing from the real ~/.claude), a
placeholder API key made up at run time and a base URL on 127.0.0.1; every variable that could point it to
a real account is removed from ITS environment only. Temp folders are removed by cleanup_project() and at exit.
A timed-out child is stopped by its own process id (taskkill /T on Windows), never by name.
Python 3.9 syntax, standard library only. Output goes through say() as UTF-8 bytes (safe on a cp1252 console).
Who calls it: tests/test_mock_cli.py, harness/scenario.py, people.
"""
from __future__ import annotations

import atexit
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import mock_api  # noqa: E402

DEFAULT_NAME = "proj ş1"          # a space and a Turkish letter on purpose
# Files that would shadow the standard library (or the hooks' own lib/ package) if sys.path were not isolated.
DECOYS = ("random.py", "json.py", "secrets.py", "re.py", "subprocess.py", "pathlib.py", "os.py", "hashlib.py")
_KEEP_ENV = ("CLAUDE_CODE_GIT_BASH_PATH",)
_COPY_IGNORE = shutil.ignore_patterns("__pycache__", "agent-memory", "*.pyc", "*.tutor-backup", "settings.local.json")
_BASES: List[str] = []
_CONFIG_DIRS: Dict[str, str] = {}
_LIVE_MOCKS: List[Any] = []


class HarnessError(Exception):
    """The harness itself could not do its job (no claude, the mock was not reached, ...)."""


def say(text: str = "") -> None:
    """Print one line as UTF-8 bytes; never raises on a cp1252 console."""
    try:
        sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
        sys.stdout.flush()
    except (OSError, ValueError, AttributeError):
        pass


# --------------------------------------------------------------------------- where things are

def claude_exe() -> Optional[str]:
    return shutil.which("claude")


def have_claude() -> bool:
    return claude_exe() is not None


def claude_version() -> str:
    exe = claude_exe()
    if not exe:
        return ""
    try:
        proc = subprocess.run([exe, "--version"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        return proc.stdout.decode("utf-8", "replace").strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


def find_product(given: Optional[str] = None) -> str:
    """The .claude folder under test: --product, env TUTOR_PRODUCT, ../.claude or ../../.claude next to tests/."""
    tests_dir = os.path.dirname(HERE)
    candidates = [given, os.environ.get("TUTOR_PRODUCT"), os.path.join(tests_dir, "..", ".claude"),
                  os.path.join(tests_dir, "..", "..", ".claude")]
    for c in candidates:
        if c and os.path.isfile(os.path.join(c, "hooks", "dispatch.py")):
            return os.path.abspath(c)
    raise HarnessError("cannot find the product folder (a .claude folder with hooks/dispatch.py); use --product DIR")


# --------------------------------------------------------------------------- the mock

def start_mock_server(logdir: Optional[str] = None, scenario: Optional[List[Dict[str, Any]]] = None,
                      req_files: bool = False) -> "mock_api.MockServer":
    server = mock_api.serve(logdir, 0, scenario, req_files)
    _LIVE_MOCKS.append(server)
    return server


def release_mock(server: Optional[Any]) -> None:
    """Stop a mock this module started for one call (its requests are already copied into the Run)."""
    if server is None:
        return
    server.stop()
    if server in _LIVE_MOCKS:
        _LIVE_MOCKS.remove(server)


def start_mock(logdir: str) -> Tuple[str, Callable[[], None]]:
    """Start the mock on a free port. Returns (base_url, stop). The key for the child is made up per run."""
    server = start_mock_server(logdir)
    return server.url, server.stop


@atexit.register
def _stop_live_mocks() -> None:
    for server in _LIVE_MOCKS:
        try:
            server.stop()
        except Exception:  # noqa: BLE001
            pass


def placeholder_key() -> str:
    """A throwaway value that is not a credential; made up at run time so no key-shaped literal is stored."""
    return "mock-" + uuid.uuid4().hex


# --------------------------------------------------------------------------- environment of the child

def path_without(names: Sequence[str] = ("python", "python3", "py"), path: Optional[str] = None) -> str:
    """PATH with every folder removed that holds one of the named programs (python, python3, py, ...)."""
    exts = ("", ".exe", ".cmd", ".bat", ".com") if os.name == "nt" else ("",)
    kept = []
    for entry in (path if path is not None else os.environ.get("PATH", "")).split(os.pathsep):
        if not entry:
            continue
        hit = False
        for name in names:
            for ext in exts:
                try:
                    if os.path.isfile(os.path.join(entry, name + ext)):
                        hit = True
                except OSError:
                    pass
        if not hit:
            kept.append(entry)
    return os.pathsep.join(kept)


def child_env(url: str, cfgdir: str, path_env: Optional[str] = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    """Environment for the claude child ONLY: no account variables, mock URL, throwaway key, private config folder."""
    env: Dict[str, str] = {}
    for key, value in os.environ.items():
        upper = key.upper()
        if key in _KEEP_ENV:
            env[key] = value
        elif upper.startswith("CLAUDE") or upper.startswith("ANTHROPIC") or upper in ("AI_AGENT", "CLAUDECODE"):
            continue                      # includes CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH, which must stay unset
        else:
            env[key] = value
    env["CLAUDE_CONFIG_DIR"] = cfgdir
    env["ANTHROPIC_BASE_URL"] = url
    env["ANTHROPIC_API_KEY"] = placeholder_key()
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["DISABLE_TELEMETRY"] = "1"
    env["DISABLE_AUTOUPDATER"] = "1"
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["no_proxy"] = "127.0.0.1,localhost"
    if path_env is not None:
        env["PATH"] = path_env
        if os.name == "nt":
            env.pop("Path", None)
    env.update(extra or {})
    return env


def config_dir_for(project: str) -> str:
    """One private CLAUDE_CONFIG_DIR per project (so --resume finds the session of the earlier call)."""
    key = os.path.abspath(project)
    if key not in _CONFIG_DIRS:
        base = getattr(project, "base", None)
        if base and os.path.isdir(base):
            cfg = os.path.join(base, "_cfg")
            os.makedirs(cfg, exist_ok=True)
        else:
            cfg = tempfile.mkdtemp(prefix="tutor-cfg-")
            _BASES.append(cfg)
        _CONFIG_DIRS[key] = cfg
    return _CONFIG_DIRS[key]


def trust_project(project: str) -> None:
    """Pretend the learner accepted the trust dialog (project permissions.allow only applies after that)."""
    cfg = config_dir_for(project)
    path = os.path.join(cfg, ".claude.json")
    data: Dict[str, Any] = {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    projects = data.setdefault("projects", {})
    projects[os.path.abspath(project).replace("\\", "/")] = {"hasTrustDialogAccepted": True}
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f)


# --------------------------------------------------------------------------- projects

class ProjectPath(str):
    """A project folder path (a str) that also remembers its scratch base, where its settings came from and notes."""
    base: str
    settings_source: str
    notes: List[str]


def read_json(path: str, default: Any = None) -> Any:
    try:
        with open(path, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path: str, obj: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def merge_hooks(settings: Dict[str, Any], hooks_doc: Dict[str, Any]) -> Dict[str, Any]:
    """Return a copy of settings with the "hooks" of hooks_doc added (arrays per event are concatenated)."""
    out = copy.deepcopy(settings)
    incoming = hooks_doc.get("hooks", hooks_doc)
    hooks = out.setdefault("hooks", {})
    for event, groups in incoming.items():
        hooks[event] = list(hooks.get(event, [])) + copy.deepcopy(groups)
    return out


def merge_settings(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    """Shallow merge for test overrides: lists under permissions are united, other keys are replaced."""
    out = copy.deepcopy(base)
    for key, value in extra.items():
        if key == "permissions" and isinstance(value, dict):
            perms = out.setdefault("permissions", {})
            for pkey, pvalue in value.items():
                if isinstance(pvalue, list):
                    perms[pkey] = list(perms.get(pkey, [])) + [x for x in pvalue if x not in perms.get(pkey, [])]
                else:
                    perms[pkey] = pvalue
        else:
            out[key] = copy.deepcopy(value)
    return out


def reference_settings() -> Dict[str, Any]:
    """A small stand-in floor (SPEC 4.2 shapes) used ONLY by experiments when the product has no settings.json."""
    pushes = ["git push --force *", "git push -f *", "git push * --force", "git push * --force *",
              "git push * -f", "git push * -f *", "git push +*", "git push * +*"]
    deny = ["Read(./.env)", "Read(./.env.*)", "Read(./**/*.pem)", "Read(**/id_rsa)", "Read(~/.ssh/**)"]
    deny += ["Bash(%s)" % p for p in pushes] + ["PowerShell(%s)" % p for p in pushes]
    return {"outputStyle": "tutor", "permissions": {"defaultMode": "acceptEdits", "deny": deny,
                                                    "ask": ["Bash(git push *)", "PowerShell(git push *)"]}}


def make_project(product: str, name: str = DEFAULT_NAME, hooks: bool = False, settings_from_product: Any = True,
                 git: bool = False, base: Optional[str] = None, extra_settings: Optional[Dict[str, Any]] = None,
                 local_settings: Optional[Dict[str, Any]] = None, decoys: bool = True) -> ProjectPath:
    """A temp project folder holding a copy of the product in .claude/.

    hooks=True merges tools/hooks.json into the COPY of settings.json (the product is never changed).
    settings_from_product: True = use the product's settings.json (if the product has none, a minimal
    settings.json with outputStyle tutor is written and the path's .notes says so); False = no settings.json;
    "reference" = the small stand-in floor from reference_settings().
    """
    base_dir = base or tempfile.mkdtemp(prefix="tutor-mock-")
    if base is None:
        _BASES.append(base_dir)
    proj = ProjectPath(os.path.join(base_dir, name))
    proj.base, proj.notes, proj.settings_source = base_dir, [], "none"
    os.makedirs(proj, exist_ok=True)
    dst = os.path.join(proj, ".claude")
    shutil.copytree(product, dst, ignore=_COPY_IGNORE)
    settings_path = os.path.join(dst, "settings.json")
    has_product_settings = os.path.isfile(settings_path)
    if settings_from_product == "reference":
        write_json(settings_path, reference_settings())
        proj.settings_source = "reference"
        proj.notes.append("settings.json is the harness reference floor")
    elif settings_from_product and has_product_settings:
        proj.settings_source = "product"
    elif settings_from_product:
        write_json(settings_path, {"outputStyle": "tutor"})
        proj.settings_source = "fallback"
        proj.notes.append("product has no settings.json: wrote a minimal one with outputStyle tutor")
    elif has_product_settings:
        os.remove(settings_path)
    settings = read_json(settings_path, None) if os.path.isfile(settings_path) else None
    if extra_settings:
        settings = merge_settings(settings or {}, extra_settings)
    if hooks:
        hooks_doc = read_json(os.path.join(product, "tools", "hooks.json"), None)
        if not isinstance(hooks_doc, dict):
            raise HarnessError("tools/hooks.json is missing or not valid JSON")
        settings = merge_hooks(settings or {}, hooks_doc)
    if settings is not None and (extra_settings or hooks):
        write_json(settings_path, settings)
    if local_settings is not None:
        write_json(os.path.join(dst, "settings.local.json"), local_settings)
    if decoys:
        for decoy in DECOYS:
            with open(os.path.join(proj, decoy), "w", encoding="utf-8", newline="\n") as f:
                f.write("raise SystemExit('DECOY %s WAS IMPORTED')\n" % decoy)
        os.makedirs(os.path.join(proj, "lib"), exist_ok=True)
        with open(os.path.join(proj, "lib", "__init__.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write("raise SystemExit('DECOY lib WAS IMPORTED')\n")
    if git:
        try:
            subprocess.run(["git", "init", "-q"], cwd=proj, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        except (OSError, subprocess.TimeoutExpired):
            proj.notes.append("git init failed")
    return proj


def remove_tree(path: str) -> None:
    def onerror(func: Callable[..., Any], p: str, exc: Any) -> None:
        try:
            os.chmod(p, 0o700)
            func(p)
        except OSError:
            pass
    shutil.rmtree(path, onerror=onerror)


def cleanup_project(project: str) -> None:
    """Remove the scratch folder a make_project() call created (and the private config folder)."""
    base = getattr(project, "base", None)
    key = os.path.abspath(project)
    cfg = _CONFIG_DIRS.pop(key, None)
    for path in (base, cfg):
        if path and os.path.isdir(path):
            remove_tree(path)
            if path in _BASES:
                _BASES.remove(path)


@atexit.register
def cleanup_all() -> None:
    for path in list(_BASES):
        if os.path.isdir(path):
            remove_tree(path)
    _BASES[:] = []


# --------------------------------------------------------------------------- the Run object

def _parse_events(text: str) -> List[Dict[str, Any]]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                events.append(obj)
    return events


class Run(object):
    """Everything one claude call did. Attributes are read-only data; helpers are small and boring."""

    def __init__(self, project: str, argv: List[str], returncode: int, stdout: str, stderr: str, seconds: float,
                 requests: List[Dict[str, Any]], owned_mock: Optional[Any] = None) -> None:
        self.project, self.argv, self.returncode = project, argv, returncode
        self.stdout, self.stderr, self.seconds = stdout, stderr, seconds
        self.events = _parse_events(stdout)
        self.request_records = requests
        self.requests = [r["body"] for r in requests]
        self._owned_mock = owned_mock
        self.init: Optional[Dict[str, Any]] = next((e for e in self.events if e.get("type") == "system" and e.get("subtype") == "init"), None)
        results = [e for e in self.events if e.get("type") == "result"]
        self.result: Optional[Dict[str, Any]] = results[-1] if results else None
        self.hook_events = [e for e in self.events if e.get("type") == "system" and e.get("subtype") in ("hook_started", "hook_response")]
        self.tool_uses: List[Dict[str, Any]] = []
        self.tool_results: List[Dict[str, Any]] = []
        names: Dict[str, str] = {}
        for e in self.events:
            message = e.get("message") if isinstance(e.get("message"), dict) else {}
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if e.get("type") == "assistant" and block.get("type") == "tool_use":
                    names[str(block.get("id"))] = str(block.get("name"))
                    self.tool_uses.append({"id": block.get("id"), "name": block.get("name"), "input": block.get("input") or {}})
                elif e.get("type") == "user" and block.get("type") == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, list):
                        inner = "\n".join(str(b.get("text", "")) for b in inner if isinstance(b, dict))
                    self.tool_results.append({"tool_use_id": block.get("tool_use_id"), "name": names.get(str(block.get("tool_use_id")), ""),
                                              "is_error": bool(block.get("is_error")), "text": str(inner or "")})

    # ---- results
    @property
    def denials(self) -> List[Dict[str, Any]]:
        value = (self.result or {}).get("permission_denials")
        return value if isinstance(value, list) else []

    @property
    def session_id(self) -> str:
        return str((self.init or self.result or {}).get("session_id") or "")

    @property
    def api_error(self) -> bool:
        return bool(self.result and self.result.get("terminal_reason") == "api_error")

    def final_text(self) -> str:
        """The text of the last assistant text block."""
        for e in reversed(self.events):
            if e.get("type") == "assistant":
                for block in reversed((e.get("message") or {}).get("content") or []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        return str(block.get("text", ""))
        return ""

    # ---- hooks
    def hook_responses(self, prefix: str = "") -> List[Dict[str, Any]]:
        return [e for e in self.hook_events if e.get("subtype") == "hook_response" and str(e.get("hook_name", "")).startswith(prefix)]

    def hook_summary(self) -> List[str]:
        return ["%s exit=%s outcome=%s" % (e.get("hook_name"), e.get("exit_code"), e.get("outcome")) for e in self.hook_responses()]

    # ---- what the model saw
    @property
    def model_requests(self) -> List[Dict[str, Any]]:
        """Requests of the main conversation that offered tools (no side queries, no helper agents)."""
        out = []
        for body in self.requests:
            if body.get("tools") and "cc_is_subagent=true" not in mock_api.system_text(body):
                out.append(body)
        return out

    def system_texts(self, index: int = 0) -> List[str]:
        """Every text the model gets besides the learner's own words, for request number index (model requests only):
        the top-level system prompt, system-role messages (newer models) and system-reminder blocks of user
        messages (older models put the environment, output style, agent list and skill list there)."""
        body = self.model_requests[index]
        texts = [mock_api.system_text(body)]
        for message in body.get("messages") or []:
            if not isinstance(message, dict):
                continue
            content = message.get("content")
            if message.get("role") == "system":
                texts.append(mock_api.flatten_text(content))
            elif message.get("role") == "user" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "text" and str(block.get("text", "")).lstrip().startswith("<system-reminder>"):
                        texts.append(str(block.get("text", "")))
        return texts

    def find_text(self, needle: str, index: int = 0) -> str:
        """The first system text of request index that contains needle ('' when none does)."""
        for text in self.system_texts(index):
            if needle in text:
                return text
        return ""

    @property
    def context_window(self) -> int:
        """Context window (tokens) Claude Code reports for the model of this run (0 when unknown)."""
        usage = (self.result or {}).get("modelUsage")
        if isinstance(usage, dict):
            for value in usage.values():
                if isinstance(value, dict) and value.get("contextWindow"):
                    return int(value["contextWindow"])
        return 0

    def first_user_text(self, index: int = 0) -> str:
        """All text blocks of the first user message of request index (CLAUDE.md and rules arrive here)."""
        body = self.model_requests[index]
        for message in body.get("messages") or []:
            if isinstance(message, dict) and message.get("role") == "user":
                return mock_api.flatten_text(message.get("content"))
        return ""

    def request_text(self, index: int = 0) -> str:
        """Everything in request number index as one string (system prompt and all messages)."""
        body = self.model_requests[index]
        return "\n".join(self.system_texts(index) + [mock_api.flatten_text(m.get("content")) for m in body.get("messages") or []
                                                      if isinstance(m, dict) and m.get("role") != "system"])

    def all_request_text(self) -> str:
        return "\n".join(json.dumps(b, ensure_ascii=False) for b in self.requests)

    def cleanup(self) -> None:
        if self._owned_mock is not None:
            self._owned_mock.stop()
            self._owned_mock = None


# --------------------------------------------------------------------------- running claude

def _stop_tree(proc: "subprocess.Popen[bytes]") -> None:
    """Stop the child we started (and its children) by process id. Never by image name."""
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        else:
            proc.kill()
    except (OSError, subprocess.TimeoutExpired):
        pass


def _execute(project: str, argv: List[str], stdin_bytes: bytes, env: Dict[str, str], timeout: float, cwd: Optional[str]) -> Tuple[int, str, str, float]:
    started = time.time()
    proc = subprocess.Popen(argv, cwd=cwd or project, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        out, err = proc.communicate(input=stdin_bytes, timeout=timeout)
        code = proc.returncode
    except subprocess.TimeoutExpired:
        _stop_tree(proc)
        try:
            out, err = proc.communicate(timeout=20)
        except (subprocess.TimeoutExpired, ValueError):
            out, err = b"", b""
        code = -999
        err = err + b"\nHARNESS: timeout"
    return code, out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace"), time.time() - started


def run_claude(project: str, prompt: str, permission_mode: Optional[str] = "default", allowed_tools: Optional[Sequence[str]] = None,
               resume: Optional[str] = None, session_id: Optional[str] = None, max_turns: int = 6,
               extra_args: Sequence[str] = (), path_env: Optional[str] = None, timeout: float = 120.0,
               mock: Optional[Any] = None, env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None,
               trusted: bool = True, model: Optional[str] = None, scenario: Optional[List[Dict[str, Any]]] = None) -> Run:
    """One `claude -p` call against the mock. The prompt travels on stdin (UTF-8, no quoting problems).

    permission_mode None leaves the choice to the project settings (defaultMode). allowed_tools becomes
    --allowedTools. trusted=True records the trust-dialog answer in the private config (project allow rules
    only apply after that). mock: pass a MockServer to share one log between calls; the Run keeps only the
    requests that arrived during this call.
    """
    exe = claude_exe()
    if not exe:
        raise HarnessError("claude is not on PATH")
    owned = None
    if mock is None:
        logdir = os.path.join(getattr(project, "base", None) or tempfile.gettempdir(), "_mock_%s" % uuid.uuid4().hex[:6])
        mock = owned = start_mock_server(logdir, scenario)
    first = len(mock.requests)
    cfg = config_dir_for(project)
    if trusted:
        trust_project(project)
    argv = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--setting-sources", "project,local", "--max-turns", str(max_turns)]
    if permission_mode:
        argv += ["--permission-mode", permission_mode]
    if model:
        argv += ["--model", model]
    if session_id:
        argv += ["--session-id", session_id]
    if resume:
        argv += ["--resume", resume]
    argv += list(extra_args)
    if allowed_tools:
        argv += ["--allowedTools"] + list(allowed_tools)
    code, out, err, secs = _execute(project, argv, prompt.encode("utf-8"), child_env(mock.url, cfg, path_env, env), timeout, cwd)
    run = Run(project, argv, code, out, err, secs, list(mock.requests[first:]), owned)
    release_mock(owned)
    return run


def run_claude_stream(project: str, prompts: Sequence[str], permission_mode: Optional[str] = "default",
                      allowed_tools: Optional[Sequence[str]] = None, max_turns: int = 6, extra_args: Sequence[str] = (),
                      path_env: Optional[str] = None, timeout: float = 180.0, mock: Optional[Any] = None,
                      env: Optional[Dict[str, str]] = None, cwd: Optional[str] = None, trusted: bool = True,
                      model: Optional[str] = None) -> Run:
    """Several user messages in ONE claude process (--input-format stream-json); "/compact" works as a message."""
    exe = claude_exe()
    if not exe:
        raise HarnessError("claude is not on PATH")
    owned = None
    if mock is None:
        logdir = os.path.join(getattr(project, "base", None) or tempfile.gettempdir(), "_mock_%s" % uuid.uuid4().hex[:6])
        mock = owned = start_mock_server(logdir)
    first = len(mock.requests)
    cfg = config_dir_for(project)
    if trusted:
        trust_project(project)
    argv = [exe, "-p", "--input-format", "stream-json", "--output-format", "stream-json", "--verbose", "--include-hook-events",
            "--setting-sources", "project,local", "--max-turns", str(max_turns)]
    if permission_mode:
        argv += ["--permission-mode", permission_mode]
    if model:
        argv += ["--model", model]
    argv += list(extra_args)
    if allowed_tools:
        argv += ["--allowedTools"] + list(allowed_tools)
    lines = [json.dumps({"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": p}]}}, ensure_ascii=False)
             for p in prompts]
    code, out, err, secs = _execute(project, argv, ("\n".join(lines) + "\n").encode("utf-8"), child_env(mock.url, cfg, path_env, env),
                                    timeout, cwd)
    run = Run(project, argv, code, out, err, secs, list(mock.requests[first:]), owned)
    release_mock(owned)
    return run


def run_command(project: str, args: Sequence[str], timeout: float = 90.0, path_env: Optional[str] = None,
                env: Optional[Dict[str, str]] = None, trusted: bool = True) -> Tuple[int, str, str]:
    """Run a non-session claude command (for example `claude doctor`) in the same isolated environment."""
    exe = claude_exe()
    if not exe:
        raise HarnessError("claude is not on PATH")
    server = start_mock_server(None)
    try:
        cfg = config_dir_for(project)
        if trusted:
            trust_project(project)
        code, out, err, _ = _execute(project, [exe] + list(args), b"", child_env(server.url, cfg, path_env, env), timeout, None)
        return code, out, err
    finally:
        server.stop()


# --------------------------------------------------------------------------- reading skill and agent files

def folded_value(text: str, key: str) -> str:
    """Value of a top-level frontmatter key; understands plain, quoted and `>-` folded block values."""
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return ""
    body = []
    for line in lines[1:]:
        if line.strip() == "---":
            break
        body.append(line)
    for i, line in enumerate(body):
        if line.startswith(key + ":"):
            rest = line[len(key) + 1:].strip()
            if rest in (">-", ">", "|-", "|"):
                parts = []
                for nxt in body[i + 1:]:
                    if nxt.startswith((" ", "\t")) or not nxt.strip():
                        parts.append(nxt.strip())
                    else:
                        break
                return " ".join(p for p in parts if p)
            if len(rest) >= 2 and rest[0] == rest[-1] and rest[0] in "\"'":
                rest = rest[1:-1]
            return rest
    return ""


def product_skills(product: str) -> List[Tuple[str, str]]:
    """[(name, description)] for every skill folder of the product, in folder order."""
    out = []
    root = os.path.join(product, "skills")
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        path = os.path.join(root, name, "SKILL.md")
        if os.path.isfile(path):
            with open(path, encoding="utf-8-sig") as f:
                text = f.read()
            out.append((folded_value(text, "name") or name, folded_value(text, "description")))
    return out


def product_agents(product: str) -> List[Tuple[str, str]]:
    out = []
    root = os.path.join(product, "agents")
    for name in sorted(os.listdir(root)) if os.path.isdir(root) else []:
        if name.endswith(".md"):
            with open(os.path.join(root, name), encoding="utf-8-sig") as f:
                text = f.read()
            out.append((folded_value(text, "name") or name[:-3], folded_value(text, "description")))
    return out
