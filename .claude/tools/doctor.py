"""doctor.py - health check, progress picture and settings helper for the tutor (run: python3 .claude/tools/doctor.py <command>).

What: one script with these commands: check, progress, enable-hooks, disable-hooks, envcheck, audit,
share-notes, wipe, verify. Run it with no command to see the list in plain words.
Why: a beginner needs one safe place to ask "is it working?", "what have I learned?" and "turn the
helper scripts on or off". Every change to a settings file is made by this script, after the learner
agreed, with a backup first, and never by the model editing the file.
How it fails safely: it needs no helper scripts (hooks) and no running Claude Code. Every command that
changes a file writes a backup first, writes the new file in one step and reads it back. A bad command
line prints a short usage text and exits 1, never 2. Internal errors print one plain line and exit 1.
Nothing in this file opens a network connection itself or runs a file it scans; programs it starts are python
(a probe), claude --version, git and gh, each with a time limit and without a shell. The one command that can
cause network traffic is share-notes on: it asks GitHub through the learner's own gh program.
Who calls it: the learner, the skills tutor, progress, before-push and fix-it (exact command forms are in
their allowed-tools lines), tools/install.py (it loads this file with runpy and calls audit_scan,
merge_hooks, remove_our_hooks, repair_gitignore and the manifest helpers), tools/selftest_tools.py.
Python 3.9, standard library only. The functions near the top are pure helpers that other tools reuse.
"""
from __future__ import annotations

import argparse
import copy
import fnmatch
import hashlib
import json
import os
import re
import runpy
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
CLAUDE_DIR = os.path.dirname(TOOLS_DIR)
ROOT = os.path.dirname(CLAUDE_DIR)
DATA = os.path.join(CLAUDE_DIR, "agent-memory", "tutor-data")

MIN_CLAUDE = (2, 1, 288)
MIN_PYTHON = (3, 9)
PROBE_TOKEN = "tutor-probe-ok"
MAX_READ = 256 * 1024
ATT, OKAY, INFO = "Needs attention", "OK", "Info"
# The pages and notes the kit links to. A copy without one is broken even when MANIFEST.txt does not name it.
KIT_PAGE_FILES = ("README.md", "CHANGELOG.md", "settings.json.explained.md", "docs/commands.md", "docs/customize.md",
                  "docs/faq.md", "docs/getting-started.md", "docs/how-it-works.md", "docs/troubleshooting.md")

SKILL_NAMES = ("tutor", "tutor-setup", "learn", "progress", "explain", "think-first", "new-project", "fix-it",
               "save-point", "before-push", "git-rescue")
FORCE_PUSH_RULES = ("Bash(git push --force *)", "Bash(git push -f *)", "Bash(git push * --force)",
                    "Bash(git push * --force *)", "Bash(git push * -f)", "Bash(git push * -f *)",
                    "Bash(git push +*)", "Bash(git push * +*)")
GITIGNORE_LINES = ("agent-memory/tutor-data/", "settings.local.json", "*.tutor-backup", "__pycache__/", "*.pyc")
SHARE_BEGIN = "# >>> share-notes"
SHARE_END = "# <<< share-notes"
KIT_SETTINGS_KEYS = ("$schema", "outputStyle", "permissions", "hooks")
RISKY_SETTINGS_KEYS = ("apiKeyHelper", "statusLine", "env", "enableAllProjectMcpServers", "skipDangerousModePermissionPrompt",
                       "enabledPlugins", "extraKnownMarketplaces")
HOOK_MODES = ("session-start", "user-prompt", "pre-tool", "post-tool", "stop", "subagent-start")
DOMAIN_NAMES = {"term": "Terminal", "files": "Files", "git": "Git", "gh": "GitHub", "cc": "Claude Code",
                "prog": "Programming", "web": "Web", "data": "Data", "test": "Testing", "sec": "Security",
                "arch": "Design choices", "proj": "Projects", "ai": "AI"}
KNOWLEDGE_CHECKS = ("knowledge_checks", "run_knowledge_checks", "validate_knowledge")

STATE: Dict[str, Any] = {"capture": None, "libs": True}   # tests set capture to [] to collect output; libs False = never import hooks/lib
_LIBS: Dict[str, Any] = {}


class UsageError(Exception):
    """A bad command line. Never turned into exit code 2."""


# --------------------------------------------------------------------------- output and small helpers

def out(text: str = "") -> None:
    """Print one line as UTF-8 bytes, so a Windows console with a legacy code page cannot crash us."""
    cap = STATE["capture"]
    if cap is not None:
        cap.append(text)
        return
    data = (text + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except (AttributeError, OSError, ValueError):
        try:
            sys.stdout.write(text + "\n")
        except Exception:
            pass


def words(text: str) -> int:
    return len(re.findall(r"\S+", text or ""))


def decode_bytes(raw: bytes) -> str:
    """Text of a user-editable file: UTF-8 (with or without BOM), UTF-16 with BOM, else cp1252. LF line ends."""
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8", errors="replace")
    elif raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        text = raw.decode("utf-16", errors="replace")
    else:
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("cp1252", errors="replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_bytes(path: str, limit: int = MAX_READ) -> Optional[bytes]:
    try:
        with open(path, "rb") as handle:
            return handle.read(limit + 1)[:limit + 1]
    except OSError:
        return None


def read_text(path: str, limit: int = MAX_READ) -> Optional[str]:
    raw = read_bytes(path, limit)
    return None if raw is None else decode_bytes(raw[:limit])


def write_file_atomic(path: str, data: bytes) -> bool:
    """Write bytes next to the target, then rename over it. True when the file now holds the bytes."""
    tmp = "%s.tmp%d" % (path, os.getpid())
    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(tmp, "wb") as handle:
            handle.write(data)
        for _ in range(3):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                time.sleep(0.05)
        else:
            return False
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def write_text_file(path: str, text: str) -> bool:
    """UTF-8 without BOM, LF line ends."""
    return write_file_atomic(path, text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8"))


def sha256_file(path: str) -> Optional[str]:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(65536), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def is_link(path: str) -> bool:
    """True for a symbolic link or a Windows junction (other reparse points such as OneDrive files are not links)."""
    try:
        if os.path.islink(path):
            return True
        info = os.lstat(path)
        return getattr(info, "st_reparse_tag", 0) in (0xA0000003, 0xA000000C)
    except (OSError, ValueError):
        return False


def norm(path: str) -> str:
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(path))


def is_inside(path: str, folder: str, allow_equal: bool = True) -> bool:
    a, b = norm(path), norm(folder)
    if a == b:
        return allow_equal
    return a.startswith(b.rstrip("\\/") + os.sep)


def has_link_between(path: str, stop: str) -> bool:
    """True when path, or a parent below stop, is a link."""
    cur = os.path.abspath(path)
    stop_n = os.path.normcase(os.path.abspath(stop))
    for _ in range(60):
        if os.path.normcase(cur) == stop_n:
            return False
        if os.path.lexists(cur) and is_link(cur):
            return True
        parent = os.path.dirname(cur)
        if parent == cur:
            return False
        cur = parent
    return True


def find_on_path(name: str, path: Optional[str] = None) -> str:
    """Like shutil.which, but it never returns a program from the current folder or from inside the project folder
    (a program planted in a downloaded project must not be started by this script). Returns "" when not found."""
    exts = [""]
    if os.name == "nt":
        pathext = [e.lower() for e in os.environ.get("PATHEXT", ".EXE;.CMD;.BAT").split(";") if e]
        exts = [""] if os.path.splitext(name)[1].lower() in pathext else pathext
    for entry in (os.environ.get("PATH", "") if path is None else path).split(os.pathsep):
        entry = entry.strip().strip('"')
        if not entry or entry == os.curdir or not os.path.isabs(entry) or is_inside(entry, ROOT):
            continue
        for ext in exts:
            candidate = os.path.join(entry, name + ext)
            if os.path.isfile(candidate) and (os.name == "nt" or os.access(candidate, os.X_OK)):
                return candidate
    return ""


def _prepare_lib_path() -> None:
    os.environ["CLAUDE_PROJECT_DIR"] = ROOT
    hooks = os.path.join(CLAUDE_DIR, "hooks")
    if hooks not in sys.path:
        sys.path.insert(0, hooks)
    sys.dont_write_bytecode = True


def lib(name: str) -> Any:
    """A module of hooks/lib (shipped with this kit), or None when it cannot be loaded."""
    if not STATE["libs"]:
        return None
    if name in _LIBS:
        return _LIBS[name]
    mod = None
    try:
        _prepare_lib_path()
        if name == "paths":
            from lib import paths as mod
        elif name == "fsio":
            from lib import fsio as mod
        elif name == "gitq":
            from lib import gitq as mod
        elif name == "config":
            from lib import config as mod
        elif name == "knowledge":
            from lib import knowledge as mod
        elif name == "learner":
            from lib import learner as mod
        elif name == "ledger":
            from lib import ledger as mod
        elif name == "activity":
            from lib import activity as mod
        elif name == "untrusted":
            from lib import untrusted as mod
        elif name == "secrets":
            from lib import secrets as mod
        elif name == "clock":
            from lib import clock as mod
    except Exception:
        mod = None
    _LIBS[name] = mod
    return mod


def safe_text(text: Any, limit: int = 100) -> str:
    """Single-line text with control characters, angle brackets and instruction-like phrases neutralised."""
    mod = lib("untrusted")
    if mod is not None:
        try:
            return str(mod.neutralize(text, limit))
        except Exception:
            pass
    kept = []
    for ch in str(text):
        if unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"):
            kept.append(" ")
        elif ch in "<>`":
            kept.append("'")
        else:
            kept.append(ch)
    clean = " ".join("".join(kept).split())
    return clean[:max(limit - 3, 0)] + "..." if len(clean) > limit else clean


def _spawn(argv: List[str], timeout: float, cwd: Optional[str] = None, env: Optional[Dict[str, str]] = None,
           data: Optional[bytes] = None) -> Tuple[Optional[int], str, str]:
    """Run a program without a shell. Returns (exit code, stdout, stderr); the code is None on a start failure or timeout.
    data, when given, is sent to the program's standard input."""
    try:
        flags = 0x08000000 if os.name == "nt" else 0
        if data is None:
            proc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=timeout, cwd=cwd, env=env, creationflags=flags)
        else:
            proc = subprocess.run(argv, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  timeout=timeout, cwd=cwd, env=env, creationflags=flags)
        return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, "", "timeout"
    except (OSError, ValueError) as exc:
        return None, "", type(exc).__name__


def _git(args: List[str], cwd: str, timeout: float = 10.0) -> Tuple[Optional[int], str, str]:
    env = dict(os.environ)
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_OPTIONAL_LOCKS="0")
    return _spawn(["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false"] + list(args), timeout, cwd, env)


def git_ignore_map(cwd: str, paths: List[str]) -> Optional[Dict[str, Tuple[bool, str]]]:
    """Ask Git, in one call, whether each path is ignored. Returns {path: (ignored, rule)} or None when Git cannot answer.
    The rules are judged without looking at what is tracked (--no-index); a path matched by a ! rule is not ignored."""
    env = dict(os.environ)
    env.update(GIT_TERMINAL_PROMPT="0", GIT_OPTIONAL_LOCKS="0")
    data = "".join(p + "\0" for p in paths).encode("utf-8")
    code, text, _ = _spawn(["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.quotepath=false",
                            "check-ignore", "-z", "--stdin", "--no-index", "-v", "-n"], 15.0, cwd, env, data)
    if code not in (0, 1):
        return None
    parts = text.split("\0")
    result: Dict[str, Tuple[bool, str]] = {}
    for i in range(0, len(parts) - 3, 4):
        source, line, pattern, path = parts[i:i + 4]
        result[path] = (bool(pattern) and not pattern.startswith("!"), "%s:%s:%s" % (source, line, pattern) if pattern else "no rule")
    return result if len(result) == len(paths) else None


# --------------------------------------------------------------------------- settings files

def strip_json_comments(text: str) -> str:
    """Remove // and /* */ comments that are outside strings (to tell 'has comments' from 'broken')."""
    result: List[str] = []
    i, n, in_str = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            result.append(ch)
            if ch == "\\" and i + 1 < n:
                result.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            result.append(ch)
            i += 1
        elif ch == "/" and text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif ch == "/" and text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def load_settings(path: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """(settings dict, "") or (None, reason) with reason missing, unreadable, comments, invalid or notobject."""
    if not os.path.isfile(path):
        return None, "missing"
    raw = read_bytes(path, 4 * 1024 * 1024)
    if raw is None:
        return None, "unreadable"
    text = decode_bytes(raw).lstrip("\ufeff")
    try:
        data = json.loads(text)
    except ValueError:
        try:
            json.loads(strip_json_comments(text))
            return None, "comments"
        except ValueError:
            return None, "invalid"
    if not isinstance(data, dict):
        return None, "notobject"
    return data, ""


def dump_settings(data: Dict[str, Any]) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def merge_lists(base: Any, extra: Any) -> List[Any]:
    out_list = list(base) if isinstance(base, list) else []
    for item in (extra if isinstance(extra, list) else []):
        if item not in out_list:
            out_list.append(item)
    return out_list


def merged_settings(claude_dir: str) -> Tuple[Dict[str, Any], List[Tuple[str, str]]]:
    """The view Claude Code builds from settings.json plus settings.local.json (local wins for scalars,
    lists are joined, objects are merged). Returns (merged, [(file name, problem)])."""
    merged: Dict[str, Any] = {}
    problems: List[Tuple[str, str]] = []

    def blend(base: Dict[str, Any], extra: Dict[str, Any]) -> None:
        for key, value in extra.items():
            if isinstance(value, dict) and isinstance(base.get(key), dict):
                blend(base[key], value)
            elif isinstance(value, list) and isinstance(base.get(key), list):
                base[key] = merge_lists(base[key], value)
            else:
                base[key] = copy.deepcopy(value)

    for name in ("settings.json", "settings.local.json"):
        data, why = load_settings(os.path.join(claude_dir, name))
        if data is None:
            if why != "missing":
                problems.append((name, why))
            elif name == "settings.json":
                problems.append((name, "missing"))
            continue
        blend(merged, data)
    return merged, problems


# --------------------------------------------------------------------------- manifest

def read_manifest(path: str) -> Tuple[Optional[str], Dict[str, str], int]:
    """(version, {relative path: sha256}, number of bad lines). Version None when there is no file."""
    text = read_text(path, 8 * 1024 * 1024)
    if text is None:
        return None, {}, 0
    version, files, bad = "", {}, 0
    for line in text.split("\n"):
        if not line.strip():
            continue
        if line.startswith("#"):
            m = re.match(r"^#\s*version\s+(\S+)", line)
            if m:
                version = m.group(1)
            continue
        m = re.match(r"^([0-9a-fA-F]{64})  (.+)$", line)
        if not m:
            bad += 1
            continue
        files[m.group(2).strip().replace("\\", "/")] = m.group(1).lower()
    return version, files, bad


def is_excluded(rel: str) -> bool:
    """Files that are never part of the manifest: our own data, caches, backups and local settings."""
    parts = rel.replace("\\", "/").split("/")
    if parts[0] == "agent-memory" or "__pycache__" in parts:
        return True
    name = parts[-1]
    if rel == "MANIFEST.txt" or rel == "settings.local.json":
        return True
    return name.endswith((".pyc", ".tutor-backup", ".new")) or ".tutor-backup" in name


def list_shipped_files(claude_dir: str) -> List[str]:
    """Relative paths (forward slashes) of every file under claude_dir that the manifest would list.
    Links are not followed and not listed."""
    found: List[str] = []
    stack = [claude_dir]
    while stack:
        cur = stack.pop()
        try:
            entries = list(os.scandir(cur))
        except OSError:
            continue
        for entry in entries:
            if is_link(entry.path):
                continue
            rel = os.path.relpath(entry.path, claude_dir).replace("\\", "/")
            if entry.is_dir(follow_symlinks=False):
                if entry.name in ("agent-memory", "__pycache__"):
                    continue
                stack.append(entry.path)
            elif not is_excluded(rel):
                found.append(rel)
    return sorted(found)


def compare_manifest(claude_dir: str, files: Dict[str, str]) -> Dict[str, List[str]]:
    """modified (content differs), eol (differs only in line endings), missing, extra, merged (settings.json)."""
    result: Dict[str, List[str]] = {"modified": [], "eol": [], "missing": [], "extra": [], "merged": []}
    for rel, want in sorted(files.items()):
        path = os.path.join(claude_dir, *rel.split("/"))
        if not os.path.isfile(path):
            result["missing"].append(rel)
            continue
        got = sha256_file(path)
        if got == want:
            continue
        if rel == "settings.json":
            result["merged"].append(rel)
            continue
        raw = read_bytes(path, 64 * 1024 * 1024)
        if raw is not None and hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == want:
            result["eol"].append(rel)
        else:
            result["modified"].append(rel)
    known = set(files)
    for rel in list_shipped_files(claude_dir):
        if rel not in known:
            result["extra"].append(rel)
    return result


# --------------------------------------------------------------------------- interpreters

_NAME_RE = re.compile(r"^(python3?(\.\d+)?|py)(\.exe)?$", re.IGNORECASE)


def check_interpreter_name(name: str) -> Tuple[str, List[str], str]:
    """Validate an interpreter name. Returns (command, extra arguments, problem); problem is "" when fine.
    Accepted: python3, python, python3.12, py (or "py -3"), and an absolute path whose file name is one of these."""
    text = (name or "").strip()
    parts = text.split()
    if len(parts) == 2 and parts[0].lower() in ("py", "py.exe") and parts[1] == "-3":
        text = parts[0]
    base = os.path.basename(text.replace("\\", "/")) if os.path.isabs(text) or "/" in text or "\\" in text else text
    if not text or not _NAME_RE.match(base):
        return "", [], ("The interpreter name must be python3, python, py, or the full path of one of them. "
                        "Other names are refused on purpose.")
    if ("/" in text or "\\" in text) and not os.path.isabs(text):
        return "", [], "Use only a plain name or a full path, not a relative path."
    if os.path.isabs(text) and is_inside(text, ROOT):
        return "", [], "The interpreter must not be inside the project folder. Use python3, python or py instead."
    extra = ["-3"] if re.sub(r"\.exe$", "", base.lower()) == "py" else []
    return text, extra, ""


def is_store_stub(path: str, returncode: Optional[int] = None, output: str = "") -> bool:
    """The Microsoft Store shortcut that opens the Store instead of running Python."""
    if returncode == 9009 or "python was not found" in (output or "").lower():
        return True
    low = (path or "").replace("\\", "/").lower()
    if "/windowsapps/" in low:
        try:
            return os.path.getsize(path) == 0
        except OSError:
            return False
    return False


def probe_interpreter(command: str, extra: Optional[List[str]] = None, timeout: float = 5.0) -> Tuple[bool, str, str]:
    """Run the interpreter once. Returns (works, version text, plain problem)."""
    path = command if os.path.isabs(command) else find_on_path(command)
    if not path:
        return False, "", "'%s' was not found on this computer." % command
    # A zero-byte file in WindowsApps is also what a REAL launcher installed from the Store looks like (an app
    # execution alias), so the size alone proves nothing: run it, and only call it a stub when the run fails.
    code = "import sys; print('%s'); print(sys.version_info[0], sys.version_info[1], sys.version_info[2])" % PROBE_TOKEN
    rc, so, se = _spawn([path] + list(extra or []) + ["-I", "-c", code], timeout)
    if rc is None:
        if is_store_stub(path):
            return False, "", "'%s' is a Microsoft Store shortcut, not a real Python." % command
        return False, "", "'%s' could not be started (%s)." % (command, se)
    if (rc != 0 or PROBE_TOKEN not in so) and is_store_stub(path, rc, so + se):
        return False, "", "'%s' is a Microsoft Store shortcut, not a real Python." % command
    lines = [ln.strip() for ln in so.strip().split("\n")]
    if rc != 0 or not lines or lines[0] != PROBE_TOKEN:
        return False, "", "'%s' did not run Python correctly (exit code %s)." % (command, rc)
    ver = lines[1] if len(lines) > 1 else ""
    m = re.match(r"^(\d+) (\d+) (\d+)$", ver)
    if m and (int(m.group(1)), int(m.group(2))) < MIN_PYTHON:
        return False, ver.replace(" ", "."), "Python %s is too old. The tutor needs 3.9 or newer." % ver.replace(" ", ".")
    return True, ver.replace(" ", "."), ""


def find_working_interpreter() -> Tuple[str, List[str], str]:
    """The first of python3, python, py -3 that passes the probe: (command, extra args, version) or ("", [], "")."""
    for cmd, extra in (("python3", []), ("python", []), ("py", ["-3"])):
        ok, ver, _ = probe_interpreter(cmd, extra)
        if ok:
            return cmd, extra, ver
    return "", [], ""


def display_name(command: str, extra: List[str]) -> str:
    return "py -3" if extra else command


# --------------------------------------------------------------------------- hooks in settings.json

def read_hooks_spec(path: Optional[str] = None) -> Tuple[Optional[Dict[str, Any]], str]:
    """The hook entries of tools/hooks.json: ({event: [groups]}, "") or (None, plain problem)."""
    path = path or os.path.join(TOOLS_DIR, "hooks.json")
    data, why = load_settings(path)
    if data is None or not isinstance(data.get("hooks"), dict) or not data["hooks"]:
        return None, "tools/hooks.json is missing or damaged (%s). Copy it again from the kit." % (why or "no hooks")
    for groups in data["hooks"].values():
        if not isinstance(groups, list):
            return None, "tools/hooks.json is damaged. Copy it again from the kit."
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("hooks"), list):
                return None, "tools/hooks.json is damaged. Copy it again from the kit."
            for handler in group["hooks"]:
                if not isinstance(handler, dict) or not isinstance(handler.get("args"), list):
                    return None, "tools/hooks.json is damaged. Copy it again from the kit."
    return data["hooks"], ""


def is_our_handler(handler: Any) -> bool:
    """A hook entry of ours: one launcher argument (or the command text) contains dispatch.py."""
    if not isinstance(handler, dict):
        return False
    if any(isinstance(a, str) and "dispatch.py" in a for a in (handler.get("args") or [])):
        return True
    return isinstance(handler.get("command"), str) and "dispatch.py" in handler["command"]


def remove_our_hooks(hooks: Any) -> Tuple[Dict[str, Any], int]:
    """A copy of the hooks object without our entries; empty groups and empty events are dropped."""
    result: Dict[str, Any] = {}
    removed = 0
    for event, groups in (hooks.items() if isinstance(hooks, dict) else []):
        if not isinstance(groups, list):
            result[event] = copy.deepcopy(groups)
            continue
        kept_groups = []
        for group in groups:
            if isinstance(group, dict) and isinstance(group.get("hooks"), list):
                keep = [h for h in group["hooks"] if not is_our_handler(h)]
                removed += len(group["hooks"]) - len(keep)
                if keep:
                    new_group = copy.deepcopy(group)
                    new_group["hooks"] = copy.deepcopy(keep)
                    kept_groups.append(new_group)
            else:
                kept_groups.append(copy.deepcopy(group))
        if kept_groups:
            result[event] = kept_groups
    return result, removed


def merge_hooks(settings: Dict[str, Any], spec: Dict[str, Any], command: str, pre_args: List[str]) -> Dict[str, Any]:
    """A copy of settings with our hook entries (re)written. Other hook entries stay; running it twice gives the same result."""
    result = copy.deepcopy(settings)
    existing = result.get("hooks") if isinstance(result.get("hooks"), dict) else {}
    cleaned, _ = remove_our_hooks(existing)
    for event, groups in spec.items():
        target = cleaned.setdefault(event, [])
        for group in groups:
            new_group = copy.deepcopy(group)
            for handler in new_group["hooks"]:
                handler["command"] = command
                handler["args"] = list(pre_args) + list(handler["args"])
            target.append(new_group)
    result["hooks"] = cleaned
    return result


def our_handlers(hooks: Any) -> List[Tuple[str, Dict[str, Any]]]:
    found: List[Tuple[str, Dict[str, Any]]] = []
    for event, groups in (hooks.items() if isinstance(hooks, dict) else []):
        for group in (groups if isinstance(groups, list) else []):
            for handler in (group.get("hooks") if isinstance(group, dict) and isinstance(group.get("hooks"), list) else []):
                if is_our_handler(handler):
                    found.append((str(event), handler))
    return found


def settings_refusal(why: str) -> str:
    if why == "comments":
        return ("settings.json has comments in it. JSON does not allow comments, and this script would remove them. "
                "Nothing was changed. Remove the comments by hand, or ask the tutor for help.")
    if why in ("invalid", "notobject"):
        return ("settings.json is not valid JSON, so Claude Code ignores the whole file. Nothing was changed. "
                "Restore settings.json.tutor-backup or copy settings.json again from the kit.")
    return "settings.json could not be read (%s). Nothing was changed." % why


def backup_settings(path: str) -> bool:
    """Copy settings.json to settings.json.tutor-backup (exact bytes). True when no backup is needed or it was made."""
    if not os.path.isfile(path):
        return True
    try:
        shutil.copyfile(path, path + ".tutor-backup")
        return True
    except OSError:
        return False


# --------------------------------------------------------------------------- commands: enable and disable hooks

def cmd_enable_hooks(interpreter: Optional[str]) -> int:
    spec, problem = read_hooks_spec()
    if spec is None:
        out(problem)
        return 1
    if interpreter:
        command, extra, bad = check_interpreter_name(interpreter)
        if bad:
            out(bad)
            return 1
        ok, ver, why = probe_interpreter(command, extra)
        if not ok:
            out("Hooks stay off. " + why)
            out("Try another name, for example: python3, python or py. Nothing was changed.")
            return 1
    else:
        command, extra, ver = find_working_interpreter()
        if not command:
            out("I could not find a working Python (I tried python3, python and py -3). Hooks stay off.")
            out("The tutor still works from text. See docs/troubleshooting.md for how to install Python.")
            return 1
    path = os.path.join(CLAUDE_DIR, "settings.json")
    if os.path.lexists(path) and is_link(path):
        out("settings.json is a link. I do not change links. Nothing was changed.")
        return 1
    settings, why = load_settings(path)
    if settings is None and why != "missing":
        out(settings_refusal(why))
        return 1
    if settings is None:
        settings = {}
    if "hooks" in settings and not isinstance(settings["hooks"], dict):
        out("settings.json has a hooks entry of the wrong type. Claude Code ignores such a file. Nothing was changed.")
        return 1
    updated = merge_hooks(settings, spec, command, extra)
    if updated == settings and os.path.isfile(path):
        out("Hooks were already on with %s. Nothing changed." % display_name(command, extra))
    else:
        if not backup_settings(path):
            out("I could not write the backup file, so I changed nothing.")
            return 1
        if not write_text_file(path, dump_settings(updated)):
            out("I could not write settings.json. Nothing was changed.")
            return 1
        again, why2 = load_settings(path)
        if again != updated:
            restore_after_failed_write(path)
            out("The new settings.json did not read back correctly, so I put the old one back.")
            return 1
        out("Hooks are now on. Claude Code reloads settings by itself; if the next message shows no state block, restart the session.")
        out("Interpreter used: %s (Python %s)." % (display_name(command, extra), ver))
        out("To turn them off: %s .claude/tools/doctor.py disable-hooks" % (command if not extra else "py -3"))
        out("Emergency switch: save a file .claude/settings.local.json that contains {\"disableAllHooks\": true}.")
        out("A copy of the old file is in .claude/settings.json.tutor-backup.")
    local, _ = load_settings(os.path.join(CLAUDE_DIR, "settings.local.json"))
    if local and local.get("disableAllHooks") is True:
        out("Note: settings.local.json switches all hooks off. They stay off until you remove that line.")
    import_notes_step()
    return 0


def restore_after_failed_write(path: str) -> None:
    backup = path + ".tutor-backup"
    try:
        if os.path.isfile(backup):
            shutil.copyfile(backup, path)
        else:
            os.remove(path)
    except OSError:
        pass


def import_notes_step() -> None:
    """Move text-only notes (learner/notes.md) into the learner list, once. Safe to run again."""
    notes = os.path.join(DATA, "learner", "notes.md")
    if not os.path.isfile(notes):
        return
    learner = lib("learner")
    if learner is None or not hasattr(learner, "import_notes"):
        out("I could not load the learner module, so your notes stay in notes.md for now.")
        return
    try:
        result = learner.import_notes()
    except Exception:
        out("Importing your notes failed. They stay in notes.md.")
        return
    imported, skipped = int(result.get("imported", 0)), int(result.get("skipped", 0))
    out("Your earlier notes were added to your list: %d lines imported, %d skipped. "
        "They count as not checked yet until you show them again." % (imported, skipped))
    if result.get("renamed"):
        out("notes.md was renamed to notes.imported.md.")


def cmd_disable_hooks() -> int:
    path = os.path.join(CLAUDE_DIR, "settings.json")
    if os.path.lexists(path) and is_link(path):
        out("settings.json is a link. I do not change links. Nothing was changed.")
        return 1
    settings, why = load_settings(path)
    if settings is None:
        if why == "missing":
            out("There is no settings.json, so there is nothing to turn off.")
            return 0
        out(settings_refusal(why))
        return 1
    if not isinstance(settings.get("hooks"), dict):
        out("Hooks were not on (no hooks entry in settings.json). Nothing changed.")
        return 0
    cleaned, removed = remove_our_hooks(settings["hooks"])
    if removed == 0:
        out("None of the tutor's hooks are in settings.json. Nothing changed.")
        return 0
    updated = copy.deepcopy(settings)
    if cleaned:
        updated["hooks"] = cleaned
    else:
        del updated["hooks"]
    if not backup_settings(path):
        out("I could not write the backup file, so I changed nothing.")
        return 1
    if not write_text_file(path, dump_settings(updated)):
        out("I could not write settings.json. Nothing was changed.")
        return 1
    again, _ = load_settings(path)
    if again != updated:
        restore_after_failed_write(path)
        out("The new settings.json did not read back correctly, so I put the old one back.")
        return 1
    out("Hooks are now off (%d entries removed). Your own hook entries, if any, were kept." % removed)
    out("To turn them on again: python3 .claude/tools/doctor.py enable-hooks")
    out("Emergency switch without Python: save .claude/settings.local.json containing {\"disableAllHooks\": true}.")
    return 0


# --------------------------------------------------------------------------- check

def finding(status: str, section: str, title: str, detail: str = "", fix: str = "", topic: str = "") -> Dict[str, str]:
    return {"status": status, "section": section, "title": title, "detail": detail, "fix": fix, "topic": topic}


def parse_version(text: str) -> Optional[Tuple[int, int, int]]:
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def probe_claude(result: Dict[str, Any]) -> None:
    """Fill result with claude --version (5 second limit). TUTOR_DOCTOR_CLAUDE=none skips it; a path replaces the program."""
    override = os.environ.get("TUTOR_DOCTOR_CLAUDE", "")
    if override.lower() == "none":
        result.update(found=False, version=None, raw="")
        return
    path = override or find_on_path("claude")
    if not path:
        result.update(found=False, version=None, raw="")
        return
    rc, so, se = _spawn([path, "--version"], 5.0)
    text = (so or se).strip()
    result.update(found=rc is not None, version=parse_version(text), raw=text[:80], timeout=(rc is None and se == "timeout"))


def check_python(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    v = sys.version_info
    name = re.sub(r"\.exe$", "", os.path.basename(sys.executable or "python").lower())
    if (v[0], v[1]) < MIN_PYTHON:
        return [finding(ATT, "Python", "Python %d.%d.%d is too old for the helper scripts." % (v[0], v[1], v[2]),
                        "The tutor needs Python 3.9 or newer for its helper scripts.",
                        "The tutor still works from text. Install a newer Python if you want the helper scripts.", "Python found")]
    return [finding(OKAY, "Python", "Python %d.%d.%d (%s) runs this check." % (v[0], v[1], v[2], name))]


def check_launcher(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    handlers = our_handlers(ctx["merged"].get("hooks"))
    if not handlers:
        return []
    combos: List[Tuple[str, Tuple[str, ...]]] = []
    for _, handler in handlers:
        cmd = str(handler.get("command") or "")
        args = handler.get("args") or []
        extra = ("-3",) if args and args[0] == "-3" else ()
        if (cmd, extra) not in combos:
            combos.append((cmd, extra))
    results: List[Dict[str, str]] = []
    failed = False
    for cmd, extra in combos:
        label = display_name(cmd, list(extra))
        _, _, bad = check_interpreter_name(cmd)
        if not bad and os.path.isabs(cmd):
            # a full path comes from a file that anybody could have edited: look at it, but do not run it
            results.append(finding(INFO, "Hook launcher", "The hooks start Python from the full path '%s'." % safe_text(cmd, 100),
                                   "This check does not run a program named in a settings file. It %s." % ("exists" if os.path.isfile(cmd) else "was NOT found")))
            failed = failed or not os.path.isfile(cmd)
            continue
        ok, ver, why = (False, "", bad) if bad else probe_interpreter(cmd, list(extra))
        if ok:
            results.append(finding(OKAY, "Hook launcher", "The hooks start Python with '%s' and that works (Python %s)." % (label, ver)))
            continue
        failed = True
        fix = "Turn the hooks off, or fix the name. Ask the tutor, or run the commands below."
        results.append(finding(ATT, "Hook launcher", "The hooks use '%s' but it does not work." % label, why, fix,
                               "Helper scripts on but Python missing or wrong name"))
    if failed:
        wanted = ctx.get("fix_interpreter")
        if wanted:
            if wanted != "auto":
                command, extra2, bad = check_interpreter_name(wanted)
                ok, ver, why = (False, "", bad) if bad else probe_interpreter(command, extra2)
                if ok:
                    results.append(finding(INFO, "Hook launcher", "'%s' works." % wanted,
                                           fix="Run: %s .claude/tools/doctor.py enable-hooks --interpreter %s"
                                               % (_my_python(), wanted.split()[0])))
                else:
                    results.append(finding(INFO, "Hook launcher", "'%s' does not work either." % wanted, why))
            else:
                command, extra2, ver = find_working_interpreter()
                if command:
                    results.append(finding(INFO, "Hook launcher", "'%s' works (Python %s)." % (display_name(command, extra2), ver),
                                           fix="Run: %s .claude/tools/doctor.py enable-hooks --interpreter %s"
                                               % (display_name(command, extra2), command)))
                else:
                    results.append(finding(INFO, "Hook launcher", "I found no working Python name to suggest.",
                                           fix="Turn the hooks off: %s .claude/tools/doctor.py disable-hooks" % _my_python()))
    return results


def _my_python() -> str:
    """A name the learner can type to run this script again."""
    for cmd in ("python3", "python"):
        if find_on_path(cmd):
            return cmd
    return "py -3" if find_on_path("py") else "python"


def check_claude(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    info = ctx["claude"]
    if not info.get("found"):
        return [finding(INFO, "Claude Code", "I could not run 'claude --version' here.",
                        "This is fine if you use the Desktop app. The kit was tested on Claude Code %d.%d.%d." % MIN_CLAUDE)]
    ver = info.get("version")
    if ver is None:
        return [finding(INFO, "Claude Code", "I could not read the Claude Code version (%s)." % safe_text(info.get("raw", ""), 40))]
    text = "%d.%d.%d" % ver
    if ver < MIN_CLAUDE:
        return [finding(ATT, "Claude Code", "Claude Code %s is older than 2.1.288, the version this kit was tested with." % text,
                        fix="Update Claude Code the way you installed it. Look up the current steps; do not guess them.",
                        topic="Claude Code older than 2.1.288")]
    return [finding(OKAY, "Claude Code", "Claude Code %s is new enough (2.1.288 or newer)." % text)]


def check_settings(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    for name, why in ctx["settings_problems"]:
        if why == "missing":
            results.append(finding(ATT, "Settings", "settings.json is missing.",
                                   "Without it the tutor voice and the safety rules are off.",
                                   "Copy settings.json again from the kit.", "Safety rules missing from settings.json"))
        elif why == "comments":
            results.append(finding(ATT, "Settings", "%s has comments in it. Claude Code ignores the whole file." % name,
                                   fix="Remove the comments (JSON does not allow them) or copy the file again from the kit.",
                                   topic="settings.json invalid"))
        else:
            results.append(finding(ATT, "Settings", "%s is not valid JSON. Claude Code ignores the whole file." % name,
                                   "The safety rules in it are off while it is broken.",
                                   "Restore settings.json.tutor-backup or copy settings.json again from the kit.", "settings.json invalid"))
    merged = ctx["merged"]
    if any(w == "missing" or n == "settings.json" for n, w in ctx["settings_problems"]) and not merged:
        return results
    wrong: List[str] = []
    if "outputStyle" in merged and not isinstance(merged["outputStyle"], str):
        wrong.append("outputStyle")
    perms = merged.get("permissions")
    if "permissions" in merged and not isinstance(perms, dict):
        wrong.append("permissions")
    elif isinstance(perms, dict):
        for key in ("allow", "deny", "ask"):
            if key in perms and not (isinstance(perms[key], list) and all(isinstance(x, str) for x in perms[key])):
                wrong.append("permissions." + key)
        if "defaultMode" in perms and not isinstance(perms["defaultMode"], str):
            wrong.append("permissions.defaultMode")
    if "hooks" in merged and not isinstance(merged["hooks"], dict):
        wrong.append("hooks")
    if wrong:
        results.append(finding(ATT, "Settings", "A settings entry has the wrong type: %s." % ", ".join(wrong),
                               "Claude Code ignores the whole file when a known entry has the wrong type.",
                               "Restore settings.json.tutor-backup or copy settings.json again from the kit.", "settings.json invalid"))
    risky = [k for k in RISKY_SETTINGS_KEYS if k in merged]
    mode = perms.get("defaultMode") if isinstance(perms, dict) else None
    if mode == "bypassPermissions":
        risky.append("permissions.defaultMode=bypassPermissions")
    if risky:
        results.append(finding(ATT, "Settings", "Settings contain entries that can run programs or switch safety off: %s." % ", ".join(risky),
                               "The kit does not use them. Check that you added them on purpose.",
                               "Run 'doctor.py audit' to see each one in plain words."))
    unknown = [k for k in merged if k not in KIT_SETTINGS_KEYS and k not in RISKY_SETTINGS_KEYS and k != "disableAllHooks"]
    if unknown:
        results.append(finding(INFO, "Settings", "Settings hold entries the kit does not use: %s." % ", ".join(sorted(unknown)[:8]),
                               "That is fine if you added them on purpose."))
    if merged.get("disableAllHooks") is True:
        results.append(finding(INFO, "Settings", "The emergency switch disableAllHooks is on, so hooks do not run.",
                               fix="Remove that line from settings.local.json to turn hooks on again."))
    if not any(r["status"] == ATT for r in results):
        results.append(finding(OKAY, "Settings", "settings.json is valid and uses only entries Claude Code knows."))
    return results


def check_hooks(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    handlers = our_handlers(ctx["merged"].get("hooks"))
    if not handlers:
        return [finding(INFO, "Helper scripts", "The helper scripts (hooks) are off. This is normal at the start.",
                        "The tutor works from text. Hooks add measurements and the safety guard.",
                        "Ask the tutor to turn them on when you want them.", "Helper scripts off")]
    events = sorted(set(e for e, _ in handlers))
    missing = [e for e in ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart") if e not in events]
    if missing:
        return [finding(INFO, "Helper scripts", "Hooks are on for %d of 6 events. Missing: %s." % (6 - len(missing), ", ".join(missing)),
                        fix="Run doctor.py enable-hooks again to write all six.")]
    return [finding(OKAY, "Helper scripts", "The helper scripts (hooks) are on for all 6 events.", ", ".join(events))]


def frontmatter_value(text: str, key: str) -> str:
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return ""
    for ln in lines[1:80]:
        if ln.strip() == "---":
            break
        m = re.match(r"^%s\s*:\s*(.*)$" % re.escape(key), ln)
        if m:
            return m.group(1).strip().strip("'\"").strip()
    return ""


def check_output_style(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    wanted = ctx["merged"].get("outputStyle")
    if not isinstance(wanted, str) or not wanted:
        return [finding(ATT, "Output style", "No output style is chosen, so the tutor voice is off.",
                        fix="Set \"outputStyle\": \"tutor\" in settings.json, or copy the file again from the kit.", topic="Output style does not match")]
    folder = os.path.join(CLAUDE_DIR, "output-styles")
    try:
        names = sorted(n for n in os.listdir(folder) if n.lower().endswith(".md"))
    except OSError:
        names = []
    for name in names:
        text = read_text(os.path.join(folder, name), 20000) or ""
        if frontmatter_value(text, "name") == wanted:
            return [finding(OKAY, "Output style", "The output style '%s' is set and its file exists." % safe_text(wanted, 30))]
    return [finding(ATT, "Output style", "The output style '%s' has no matching file in output-styles." % safe_text(wanted, 30),
                    "The name in settings.json must be the name inside the style file (the kit uses 'tutor').",
                    "Fix the name in settings.json, or copy output-styles/tutor.md again.", "Output style does not match")]


def check_folder(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    cwd = norm(os.getcwd())
    if cwd == norm(ROOT):
        return [finding(OKAY, "Started in", "You are in the project folder that holds .claude.")]
    return [finding(INFO, "Started in", "The current folder is not the folder that holds .claude.",
                    "Claude Code reads the tutor settings only when you open the folder that holds .claude. In a sub-folder they are not read.",
                    "Close the session and open the project folder itself, then start again.", "Started in a sub-folder")]


def check_floor(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    perms = ctx["merged"].get("permissions")
    if not isinstance(perms, dict):
        return [finding(ATT, "Safety rules", "settings.json has no permissions block, so the permission rules are gone.",
                        fix="Copy settings.json again from the kit.", topic="Safety rules missing from settings.json")]

    def strings(key: str) -> List[str]:
        value = perms.get(key)
        return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []

    deny, ask = strings("deny"), strings("ask")
    if not deny and not ask:
        return [finding(ATT, "Safety rules", "The deny and ask lists are empty, so the permission rules are gone.",
                        fix="Copy settings.json again from the kit.", topic="Safety rules missing from settings.json")]
    results: List[Dict[str, str]] = []
    missing = [r for r in FORCE_PUSH_RULES if r not in deny]
    both = set(deny) | set(ask)
    no_twin = [r for r in both if r.startswith("Bash(") and r.endswith(")") and ("PowerShell(" + r[5:]) not in both]
    if missing:
        results.append(finding(ATT, "Safety rules", "%d of the 8 force-push rules %s missing from the deny list." % (len(missing), "is" if len(missing) == 1 else "are"),
                               "A force push can destroy work on GitHub.", "Copy settings.json again from the kit.",
                               "Safety rules missing from settings.json"))
    if no_twin:
        results.append(finding(ATT, "Safety rules", "%d Bash rules have no PowerShell twin." % len(no_twin),
                               "On Windows the PowerShell tool would then go around those rules.",
                               "Copy settings.json again from the kit.", "Safety rules missing from settings.json"))
    if not results:
        results.append(finding(OKAY, "Safety rules", "%d deny rules and %d ask rules are in place, with all 8 force-push shapes."
                               % (len(deny), len(ask))))
    return results


def gitignore_text_problem(path: str) -> str:
    raw = read_bytes(path, 4096)
    if raw is None:
        return ""
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") or b"\x00" in raw:
        return ".gitignore is saved as UTF-16; Git cannot read it"
    return ""


def check_gitignore(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    results: List[Dict[str, str]] = []
    path = os.path.join(CLAUDE_DIR, ".gitignore")
    if not os.path.isfile(path):
        results.append(finding(ATT, "Git ignore", ".claude/.gitignore is missing, so private notes are not protected.",
                               fix="Run install.py with --update, or copy .gitignore again from the kit.", topic=".env or the notes folder not ignored by Git"))
    else:
        bad = gitignore_text_problem(path)
        text = read_text(path) or ""
        lines = set(ln.strip() for ln in text.split("\n"))
        share = any(ln.startswith(SHARE_BEGIN) for ln in lines)
        lacking = [w for w in GITIGNORE_LINES if w not in lines and not (share and w == GITIGNORE_LINES[0])]
        if bad:
            results.append(finding(ATT, "Git ignore", ".claude/.gitignore is saved as UTF-16. Git cannot read it.",
                                   fix="Save it again as UTF-8, or run install.py with --update.", topic=".gitignore saved as UTF-16"))
        elif lacking:
            results.append(finding(ATT, "Git ignore", ".claude/.gitignore lacks %d protective line(s): %s." % (len(lacking), ", ".join(lacking)),
                                   fix="Run install.py with --update, or copy .gitignore again from the kit.",
                                   topic=".env or the notes folder not ignored by Git"))
    gitq = lib("gitq")
    if not find_on_path("git"):
        results.append(finding(INFO, "Git ignore", "Git is not installed (or not on PATH), so I could not test the ignore rules.",
                               "The first save point of the tutor sets Git up."))
        return results
    if gitq is None:
        results.append(finding(INFO, "Git ignore", "I could not load the Git helper, so I did not test the ignore rules.",
                               "The hook modules in .claude/hooks/lib are missing or need a newer Python."))
        return results
    if not gitq.is_repo(ROOT):
        results.append(finding(INFO, "Git ignore", "This folder is not a Git repository yet, so there is nothing to ignore.",
                               "The first save point sets it up."))
        return results
    problems = list(gitq.secrets_ignored(ROOT))
    for message in problems:
        topic = ".gitignore saved as UTF-16" if "UTF-16" in message else ".env or the notes folder not ignored by Git"
        results.append(finding(ATT, "Git ignore", message[0].upper() + message[1:] + ".",
                               fix="Add the line to .gitignore. The new-project skill writes the first .gitignore; other skills edit it only after a yes.", topic=topic))
    if not problems:
        results.append(finding(OKAY, "Git ignore", "Git ignores .env, the tutor notes and settings.local.json."))
    return results


def check_git_identity(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    if not find_on_path("git"):
        return []
    code1, name, _ = _git(["config", "--get", "user.name"], ROOT, 5.0)
    code2, mail, _ = _git(["config", "--get", "user.email"], ROOT, 5.0)
    if code1 == 0 and name.strip() and code2 == 0 and mail.strip():
        return [finding(OKAY, "Git name", "Git knows your name and e-mail for save points.")]
    return [finding(INFO, "Git name", "Git has no name or e-mail yet.", "The first save point will ask for them. Not urgent.",
                    topic="Git name and e-mail not set")]


def light_knowledge_check() -> Tuple[List[str], int, int]:
    """(problems, concept count, glossary count) from a plain read of knowledge/*.jsonl."""
    problems: List[str] = []
    ids: Dict[str, str] = {}
    base = os.path.join(CLAUDE_DIR, "knowledge")
    cdir = os.path.join(base, "concepts")
    try:
        files = sorted(n for n in os.listdir(cdir) if n.endswith(".jsonl"))
    except OSError:
        return ["knowledge/concepts is missing"], 0, 0
    count = 0
    for name in files:
        text = read_text(os.path.join(cdir, name), 8 * 1024 * 1024) or ""
        for number, line in enumerate(text.split("\n"), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                problems.append("%s line %d is not valid JSON" % (name, number))
                continue
            if not isinstance(row, dict) or not all(k in row for k in ("id", "title", "domain", "tier")):
                problems.append("%s line %d lacks id, title, domain or tier" % (name, number))
                continue
            if row["id"] in ids:
                problems.append("%s line %d repeats the id %s" % (name, number, safe_text(row["id"], 40)))
            ids[row["id"]] = name
            count += 1
    gloss = 0
    text = read_text(os.path.join(base, "glossary.jsonl"), 8 * 1024 * 1024) or ""
    for number, line in enumerate(text.split("\n"), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            if not isinstance(row, dict) or not row.get("term"):
                raise ValueError
            gloss += 1
        except ValueError:
            problems.append("glossary.jsonl line %d is damaged" % number)
    if count == 0:
        problems.append("no lesson cards were found")
    return problems, count, gloss


def run_validate_knowledge() -> Optional[List[str]]:
    """Call the knowledge check of tools/validate.py when it exists. None = not available (use the light check)."""
    path = os.path.join(TOOLS_DIR, "validate.py")
    if not os.path.isfile(path):
        return None
    box: Dict[str, Any] = {}

    def work() -> None:
        try:
            ns = runpy.run_path(path, run_name="validate_module")
            if all(callable(ns.get(n)) for n in ("Product", "Report", "Ctx", "check_knowledge")):
                # validate.py: build a report for this folder and run only its knowledge check
                report = ns["Report"]()
                ns["check_knowledge"](ns["Ctx"](ns["Product"](CLAUDE_DIR), report, True, False, False))
                box["problems"] = [re.sub(r"^ERROR ", "", str(p)) for p in report.errors]
                return
            for name in KNOWLEDGE_CHECKS:
                fn = ns.get(name)
                if callable(fn):
                    box["problems"] = [str(p) for p in (fn() or [])]
                    return
        except BaseException:
            box["error"] = True

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    thread.join(10.0)
    return box.get("problems")


def check_knowledge(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    problems = run_validate_knowledge()
    source = "the kit's validator"
    count = gloss = -1
    if problems is None:
        problems, count, gloss = light_knowledge_check()
        source = "a plain read"
    if problems:
        shown = "; ".join(problems[:3]) + ("; and %d more" % (len(problems) - 3) if len(problems) > 3 else "")
        return [finding(ATT, "Lessons", "Some lesson data is damaged (%d problems)." % len(problems), shown,
                        "Copy the knowledge folder again from the kit.", "Lesson data damaged")]
    extra = " (%d lesson cards, %d glossary terms)" % (count, gloss) if count >= 0 else ""
    return [finding(OKAY, "Lessons", "The lesson data loads without problems%s." % extra, "Checked with %s." % source)]


def check_error_log(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    text = read_text(os.path.join(DATA, "state", "hook-errors.log"), 220000)
    if not text:
        return [finding(OKAY, "Error log", "The helper scripts logged no errors.")]
    clock = lib("clock")
    today = clock.today() if clock is not None else time.strftime("%Y-%m-%d")
    cutoff = ""
    try:
        y, m, d = (int(x) for x in today.split("-"))
        import datetime
        cutoff = (datetime.date(y, m, d) - datetime.timedelta(days=7)).isoformat()
    except Exception:
        cutoff = ""
    lines = [ln for ln in text.split("\n") if len(ln) > 10 and ln[:4].isdigit()]
    recent = [ln for ln in lines if ln[:10] >= cutoff]
    if not recent:
        return [finding(OKAY, "Error log", "The helper scripts logged no errors in the last 7 days.")]
    tail = " | ".join(safe_text(ln, 160) for ln in recent[-3:])
    return [finding(INFO, "Error log", "The helper scripts logged %d error line(s) in the last 7 days." % len(recent),
                    "Newest: " + tail + ". The log holds names of files and error types, never your text.",
                    "One old error is harmless. The same error again and again is worth fixing.",
                    "Errors in the helper-script log")]


def check_manifest(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    version, files, bad = read_manifest(os.path.join(CLAUDE_DIR, "MANIFEST.txt"))
    results: List[Dict[str, str]] = []
    # cheap presence check that does not depend on MANIFEST.txt (a broken install can leave the pages out of it)
    absent = [rel for rel in KIT_PAGE_FILES if rel not in files and not os.path.isfile(os.path.join(CLAUDE_DIR, *rel.split("/")))]
    if absent:
        results.append(finding(ATT, "Kit files", "%d kit page(s) are missing: %s." % (len(absent), ", ".join(absent[:5])),
                               fix="Run install.py with --update, or copy the files again from the kit.", topic="Kit files changed by the learner"))
    if version is None:
        results.append(finding(INFO, "Kit files", "There is no MANIFEST.txt, so I cannot tell whether kit files were changed.",
                               "This is normal in a development copy."))
        return results
    result = compare_manifest(CLAUDE_DIR, files)
    if result["missing"]:
        results.append(finding(ATT, "Kit files", "%d kit file(s) are missing: %s." % (len(result["missing"]), ", ".join(result["missing"][:5])),
                               fix="Run install.py with --update, or copy the files again from the kit.", topic="Kit files changed by the learner"))
    if result["modified"]:
        results.append(finding(INFO, "Kit files", "%d kit file(s) differ from the released version: %s." % (len(result["modified"]), ", ".join(result["modified"][:5])),
                               "That is fine if you changed them on purpose. An update keeps them and saves the new version as <file>.new.",
                               topic="Kit files changed by the learner"))
    if result["eol"]:
        results.append(finding(INFO, "Kit files", "%d kit file(s) differ only in line endings." % len(result["eol"])))
    if result["merged"]:
        results.append(finding(INFO, "Kit files", "settings.json differs from the released copy because settings were merged. This is expected."))
    if bad:
        results.append(finding(INFO, "Kit files", "MANIFEST.txt has %d line(s) I could not read." % bad))
    if not results:
        results.append(finding(OKAY, "Kit files", "All %d kit files match the released version." % len(files)))
    return results


def outcome_measures(ctx: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    """Measures for the target bands of SPEC 6.5. Returns (list of {name, text, target, ok}, number of answers)."""
    fsio, ledger, config, learner = lib("fsio"), lib("ledger"), lib("config"), lib("learner")
    if fsio is None or ledger is None or config is None:
        return [], 0
    rows = fsio.jsonl_read(os.path.join(DATA, "state", "ledger.jsonl"), 200)
    profile_text = fsio.read_text(os.path.join(DATA, "learner", "profile.md"), "")
    profile = config.parse_profile(profile_text)[0] if profile_text else {}
    values = ledger.outcomes(rows, profile)
    measures: List[Dict[str, Any]] = []
    answers = int(values.get("answers") or 0)

    def add(name: str, value: Any, target: str, ok: Optional[bool], shown: str) -> None:
        measures.append({"name": name, "value": value, "target": target, "ok": ok, "shown": shown})

    cr = values.get("check_rate")
    add("A real check question after medium or large work", cr, "70% or more",
        None if cr is None else cr >= 0.70, "not enough medium work yet" if cr is None else "%d%% of %d medium or large answers" % (round(cr * 100), values.get("medium_answers", 0)))
    ur = values.get("unexplained_rate")
    add("New terms left unexplained at first use", ur, "10% or less",
        None if ur is None else ur <= 0.10, "no terms yet" if ur is None else "%d%%" % round(ur * 100))
    mw = values.get("median_result_words")
    cap = values.get("result_cap", 120)
    add("Typical length of the result part", mw, "%d words or fewer" % cap,
        None if mw is None else mw <= cap, "no work answers yet" if mw is None else "%d words" % mw)
    aw = values.get("avg_sentence_words")
    scap = values.get("sentence_cap", 15)
    add("Average sentence length", aw, "%d words or fewer" % scap,
        None if aw is None else aw <= scap, "no answers yet" if aw is None else "%.1f words" % aw)
    reviewed = missed = 0
    events: List[Dict[str, Any]] = []
    if learner is not None:
        try:
            events = learner.load_events()
        except Exception:
            events = []
    for ev in events:
        if ev.get("event") == "reviewed":
            reviewed += 1
        elif ev.get("event") == "missed":
            missed += 1
    if reviewed + missed >= 5:
        rate = reviewed / float(reviewed + missed)
        add("Review answers that were right", rate, "60% to 90%", 0.60 <= rate <= 0.90, "%d%% of %d reviews" % (round(rate * 100), reviewed + missed))
    else:
        add("Review answers that were right", None, "60% to 90%", None, "not enough reviews yet")
    if answers >= 5 and rows:
        first = str(rows[0].get("ts") or "")[:10]
        steps = [e for e in events if e.get("date", "") >= first and e.get("event") in ("learned", "did", "alone", "reviewed", "claimed")]
        add("Learner steps recorded per 10 answers", round(len(steps) * 10.0 / answers, 1), "no fixed target", None,
            "%.1f" % (len(steps) * 10.0 / answers))
    return measures, answers


def check_outcomes(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    measures, answers = outcome_measures(ctx)
    if not measures:
        return []
    if answers < 5:
        return [finding(INFO, "Teaching numbers", "Not enough answers yet (%d so far; 5 are needed)." % answers,
                        "The numbers appear after a few answers, once the helper scripts are on.")]
    lines = []
    for m in measures:
        flag = "" if m["ok"] in (None, True) else " - outside the target"
        lines.append("%s: %s (target: %s)%s" % (m["name"], m["shown"], m["target"], flag))
    out_count = sum(1 for m in measures if m["ok"] is False)
    title = "Teaching numbers over the last %d answers; %d outside their target." % (answers, out_count) if out_count else \
        "Teaching numbers over the last %d answers are inside their targets." % answers
    return [finding(INFO, "Teaching numbers", title, "\n".join(lines), topic="Teaching numbers out of range")]


def check_data_folder(ctx: Dict[str, Any]) -> List[Dict[str, str]]:
    if os.path.lexists(DATA) and has_link_between(DATA, ROOT):
        return [finding(ATT, "Notes folder", "The tutor data folder is a link, so the helper scripts refuse to use it.",
                        fix="Replace the link by a normal folder.")]
    return []


def run_checks(fix_interpreter: Optional[str] = None) -> List[Dict[str, str]]:
    claude_box: Dict[str, Any] = {}
    thread = threading.Thread(target=probe_claude, args=(claude_box,), daemon=True)
    thread.start()
    merged, problems = merged_settings(CLAUDE_DIR)
    ctx = {"merged": merged, "settings_problems": problems, "claude": claude_box, "fix_interpreter": fix_interpreter}
    findings: List[Dict[str, str]] = []
    steps = [check_python, check_launcher, None, check_settings, check_hooks, check_output_style, check_folder, check_floor,
             check_gitignore, check_git_identity, check_knowledge, check_error_log, check_manifest, check_outcomes, check_data_folder]
    for step in steps:
        if step is None:
            thread.join(6.0)
            findings.extend(check_claude(ctx))
            continue
        try:
            findings.extend(step(ctx))
        except Exception as exc:
            findings.append(finding(INFO, step.__name__.replace("check_", "").replace("_", " ").capitalize(),
                                    "This check could not run (%s)." % type(exc).__name__))
    return findings


def cmd_check(strict: bool, as_json: bool, fix_interpreter: Optional[str]) -> int:
    findings = run_checks(fix_interpreter)
    attention = [f for f in findings if f["status"] == ATT]
    if as_json:
        out(json.dumps(findings, indent=2, ensure_ascii=False))
        return 1 if (strict and attention) else 0
    version = (read_text(os.path.join(CLAUDE_DIR, "VERSION"), 100) or "").strip() or "unknown"
    out("Python: %d.%d.%d at %s" % (sys.version_info[0], sys.version_info[1], sys.version_info[2], sys.executable))
    out("Tutor health check. Kit version %s." % safe_text(version, 20))
    # the full folder path on its own line: a learner copies it, so it is never cut short
    out("Project folder:")
    out("  " + safe_text(ROOT, 2000))
    if not attention:
        out("Verdict: everything works.")
    elif len(attention) == 1:
        out("Verdict: one thing needs fixing first.")
    else:
        out("Verdict: it works, with %d things that need attention." % len(attention))
    out("")
    for f in findings:
        out("%-15s %s: %s" % (f["status"], f["section"], f["title"]))
        for line in f["detail"].split("\n") if f["detail"] else []:
            out("                %s" % line)
        if f["fix"]:
            out("                What to do: %s" % f["fix"])
        if f["status"] == ATT and f["topic"]:
            out("                Topic: %s" % f["topic"])
    return 1 if (strict and attention) else 0


# --------------------------------------------------------------------------- progress

LEVEL_ORDER = {"Independent": 4, "alone once": 4, "Practiced": 3, "Understood": 2, "Seen": 1, "told me": 1}
_NOTE_EVENTS = ("met", "claimed", "learned", "did", "alone", "reviewed", "missed", "declined", "forget")


def parse_notes_lines(text: str) -> List[Dict[str, Any]]:
    """Rows from text-only notes: `YYYY-MM-DD | event | concept | "words"`. Lines that do not parse are skipped."""
    rows: List[Dict[str, Any]] = []
    for line in (text or "").split("\n"):
        parts = [p.strip() for p in line.strip().lstrip("-*+ ").split("|", 3)]
        if len(parts) < 3 or not re.match(r"^\d{4}-\d{2}-\d{2}$", parts[0]):
            continue
        event = parts[1].lower().rstrip(":")
        if event not in _NOTE_EVENTS or not parts[2]:
            continue
        quote = parts[3].strip().strip('"').strip() if len(parts) > 3 else ""
        cid = re.sub(r"[^\w]+", "-", parts[2].lower(), flags=re.UNICODE).strip("-")[:40]
        rows.append({"date": parts[0], "ts": parts[0] + "T00:00:00", "id": cid, "event": event, "quote": quote,
                     "src": "notes", "title": parts[2][:40]})
    return rows


def clean_quote(quote: str, limit_words: int) -> str:
    """The learner's own words, made safe: secrets hidden first, then control characters and tags neutralised."""
    sec, unt = lib("secrets"), lib("untrusted")
    if sec is None or unt is None:
        return ""
    try:
        text = unt.neutralize(sec.redact(quote), 200)
    except Exception:
        return ""
    parts = text.split()
    if len(parts) > limit_words:
        text = " ".join(parts[:limit_words]) + "..."
    return text


def delegated_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return len(set(str(x) for x in value))
    if isinstance(value, dict):
        for key in ("count", "n"):
            if isinstance(value.get(key), int):
                return value[key]
        if isinstance(value.get("dates"), (list, tuple)):
            return len(set(str(x) for x in value["dates"]))
    return 0


def build_picture(data: Dict[str, Any], max_words: int = 200) -> str:
    """Render the progress picture and shrink it until it fits: shorter quotes, no quotes, fewer items."""
    plan = [(12, 5, True, True, 3), (6, 5, True, True, 3), (0, 5, True, True, 3), (0, 3, True, True, 3),
            (0, 3, False, True, 2), (0, 2, False, False, 2), (0, 1, False, False, 1)]
    text = ""
    for quote_words, n_items, show_rusty, show_indep, n_next in plan:
        text = render_picture(data, quote_words, n_items, show_rusty, show_indep, n_next)
        if words(text) <= max_words:
            return text
    return " ".join(text.split()[:max_words])


def render_picture(data: Dict[str, Any], quote_words: int, n_items: int, show_rusty: bool, show_indep: bool, n_next: int) -> str:
    lines: List[str] = []
    if data.get("from_notes"):
        lines.append("This comes from your notes file; no script has checked it yet.")
    items = data["strengths"][:n_items]
    if items:
        lines.append("What your list shows:")
        by_domain: Dict[str, List[Dict[str, Any]]] = {}
        for item in items:
            by_domain.setdefault(item["domain"], []).append(item)
        for domain, group in by_domain.items():
            for item in group:
                piece = "%s - %s: %s" % (domain, item["title"], item["label"])
                if quote_words and item.get("quote"):
                    quote = clean_quote(item["quote"], quote_words)
                    if quote:
                        piece += '. You said: "%s"' % quote
                lines.append("- " + piece)
    if data["told"]:
        lines.append("You told me you know: %s. The work has not shown it yet." % ", ".join(data["told"][:3]))
    for item in data["delegated"][:2]:
        lines.append("Claude did this for you %d times; you have not done it yet: %s. Want to type it? Say \"my turn\"."
                     % (item["count"], item["title"]))
    if show_indep and data["alone"]:
        lines.append("You did this on your own: %s." % ", ".join(data["alone"][:2]))
    if show_rusty and data["rusty"]:
        lines.append("A little rusty: %s." % ", ".join(data["rusty"][:2]))
    if data["next"]:
        names = []
        for entry in data["next"][:n_next]:
            names.append(entry["title"] + (" (your work uses it now)" if entry.get("signal") else ""))
        lines.append("Next options: %s." % "; ".join(names))
    elif data.get("next_note"):
        lines.append(data["next_note"])
    if data.get("out_of_range"):
        lines.append("Teaching measures outside their target: %s." % "; ".join(data["out_of_range"][:2]))
    return "\n".join(lines)


def collect_progress() -> Optional[Dict[str, Any]]:
    """Gather the data for the progress picture, or None when there is no data at all."""
    learner, knowledge, config, fsio = lib("learner"), lib("knowledge"), lib("config"), lib("fsio")
    events: List[Dict[str, Any]] = []
    from_notes = False
    progress_path = os.path.join(DATA, "learner", "progress.jsonl")
    if learner is not None:
        try:
            events = learner.load_events()
        except Exception:
            events = []
    else:
        text = read_text(progress_path, 4 * 1024 * 1024) or ""
        for line in text.split("\n"):
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if isinstance(row, dict) and isinstance(row.get("id"), str) and isinstance(row.get("event"), str):
                events.append(row)
    notes_path = os.path.join(DATA, "learner", "notes.md")
    if not events:
        notes_text = read_text(notes_path, 262144)
        if notes_text:
            events = parse_notes_lines(notes_text)
            from_notes = bool(events)
    if not events:
        return None
    concepts: Dict[str, Any] = {}
    if knowledge is not None:
        try:
            concepts = knowledge.load_concepts()
        except Exception:
            concepts = {}
    state: Dict[str, Any] = {}
    if learner is not None:
        try:
            state = learner.fold(events, concepts)
        except Exception:
            state = {}
    titles = {e["id"]: e.get("title") for e in events if e.get("title")}

    def title_of(cid: str) -> str:
        row = concepts.get(cid) if isinstance(concepts, dict) else None
        if isinstance(row, dict) and row.get("title"):
            return str(row["title"])[:40]
        return safe_text(titles.get(cid) or cid.replace("-", " "), 40)

    def domain_of(cid: str) -> str:
        row = concepts.get(cid) if isinstance(concepts, dict) else None
        dom = str(row.get("domain")) if isinstance(row, dict) and row.get("domain") else ""
        return DOMAIN_NAMES.get(dom, "Other")

    quote_for: Dict[str, str] = {}
    for ev in events:
        if ev.get("event") in ("learned", "did", "alone", "reviewed") and ev.get("quote"):
            quote_for[ev["id"]] = str(ev["quote"])
    strengths: List[Dict[str, Any]] = []
    told: List[str] = []
    alone: List[str] = []
    rusty_ids: List[str] = []
    today = time.strftime("%Y-%m-%d")
    clock = lib("clock")
    if clock is not None:
        try:
            today = clock.session_day()
        except Exception:
            pass
    if state:
        for cid, cs in state.items():
            label = cs.label
            if cs.told_me:
                told.append(title_of(cid))
                continue
            if cs.level >= 1:
                strengths.append({"id": cid, "title": title_of(cid), "domain": domain_of(cid), "label": label,
                                  "level": LEVEL_ORDER.get(label, cs.level), "date": cs.last_date or "",
                                  "quote": quote_for.get(cid, "")})
            if cs.level >= 4:
                alone.append(title_of(cid))
            try:
                if learner.rusty(cs, today):
                    rusty_ids.append(title_of(cid))
            except Exception:
                pass
    else:
        order = {"met": 1, "claimed": 1, "learned": 2, "did": 3, "alone": 3}
        best: Dict[str, int] = {}
        claimed: Dict[str, bool] = {}
        for ev in sorted(events, key=lambda e: str(e.get("date"))):
            cid = ev["id"]
            if ev["event"] == "forget":
                best.pop(cid, None)
                claimed.pop(cid, None)
                continue
            if ev["event"] == "claimed":
                claimed.setdefault(cid, True)
            if ev["event"] in order:
                best[cid] = max(best.get(cid, 0), order[ev["event"]])
                if order[ev["event"]] >= 2:
                    claimed[cid] = False
        names = {1: "Seen", 2: "Understood", 3: "Practiced"}
        for cid, lvl in best.items():
            if claimed.get(cid) and lvl <= 1:
                told.append(title_of(cid))
            else:
                strengths.append({"id": cid, "title": title_of(cid), "domain": domain_of(cid), "label": names[lvl],
                                  "level": lvl, "date": "", "quote": quote_for.get(cid, "")})
    strengths.sort(key=lambda s: s["date"], reverse=True)
    strengths.sort(key=lambda s: -s["level"])          # stable: highest level first, newest first inside a level
    delegated: List[Dict[str, Any]] = []
    sj = fsio.read_json(os.path.join(DATA, "state", "state.json"), {}) if fsio is not None else {}
    deleg = sj.get("delegated") if isinstance(sj, dict) else None
    if isinstance(deleg, dict):
        for cid, value in deleg.items():
            n = delegated_count(value)
            cs = state.get(cid) if state else None
            level = cs.level if cs is not None else 0
            if n >= 3 and level <= 2:
                delegated.append({"id": cid, "title": title_of(cid), "count": n})
        delegated.sort(key=lambda d: (-d["count"], d["title"]))
    nxt: List[Dict[str, Any]] = []
    note = ""
    if knowledge is not None and state is not None:
        try:
            profile_text = fsio.read_text(os.path.join(DATA, "learner", "profile.md"), "") if fsio is not None else ""
            profile = config.parse_profile(profile_text)[0] if (config is not None and profile_text) else {}
            act = lib("activity")
            recent = act.recent(12) if act is not None else []
            nxt = knowledge.pick_offers(state, recent, profile, k=3, shown=[])
        except Exception:
            nxt = []
    if not nxt:
        tail = (read_text(notes_path, 20000) or "").strip().split("\n")[-3:] if os.path.isfile(notes_path) else []
        if tail and any(t.strip() for t in tail):
            note = "No lesson options could be read; your newest notes are the place to continue."
    out_of_range: List[str] = []
    try:
        measures, answers = outcome_measures({})
        if answers >= 5:
            out_of_range = [m["name"].lower() for m in measures if m["ok"] is False]
    except Exception:
        out_of_range = []
    return {"strengths": strengths, "told": told, "alone": alone, "rusty": rusty_ids, "delegated": delegated, "next": nxt,
            "next_note": note, "from_notes": from_notes, "out_of_range": out_of_range}


def cmd_progress(show_numbers: bool) -> int:
    try:
        data = collect_progress()
    except Exception as exc:
        out("I could not read your list (%s). Nothing was changed." % type(exc).__name__)
        return 1
    if data is None:
        out("No learning data yet. Your list starts when you explain or do something with the tutor.")
    else:
        out(build_picture(data))
    if show_numbers:
        measures, answers = outcome_measures({})
        out("")
        out("Teaching numbers (last 200 answers; %d answers read):" % answers)
        if not measures:
            out("The measuring modules could not be loaded.")
        for m in measures:
            flag = "" if m["ok"] in (None, True) else " - outside the target"
            out("- %s: %s (target: %s)%s" % (m["name"], m["shown"], m["target"], flag))
    return 0


# --------------------------------------------------------------------------- envcheck

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
_PLACEHOLDER = re.compile(r"^(replace[-_ ]?me|change[-_ ]?me|your[-_a-z0-9 ]*(here|key|token|secret)|x{3,}|todo|placeholder|\.\.\.|<[^>]*>)$", re.IGNORECASE)


def parse_env_names(text: str) -> Tuple[List[Tuple[str, str]], int]:
    """([(NAME, 'set' | 'empty' | 'set (looks like a placeholder)')], number of lines that are not NAME=value).
    The values themselves are never returned."""
    found: List[Tuple[str, str]] = []
    other = 0
    for raw in text.lstrip("\ufeff").split("\n"):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        m = _ENV_LINE.match(line)
        if not m:
            other += 1
            continue
        rest = m.group(2).strip()
        value = ""
        if rest[:1] in ('"', "'"):
            quote = rest[0]
            end = rest.find(quote, 1)
            value = rest[1:end] if end > 0 else rest[1:]
        elif rest.startswith("#"):
            value = ""
        else:
            value = re.split(r"\s+#", rest, maxsplit=1)[0].strip()
        if not value.strip():
            state = "empty"
        elif _PLACEHOLDER.match(value.strip()):
            state = "set (looks like a placeholder)"
        else:
            state = "set"
        found.append((m.group(1), state))
    return found, other


def cmd_envcheck(file: Optional[str]) -> int:
    candidates: List[str] = []
    if file:
        path = file if os.path.isabs(file) else (os.path.join(os.getcwd(), file) if os.path.exists(os.path.join(os.getcwd(), file)) else os.path.join(ROOT, file))
        candidates = [path]
    else:
        for name in (".env", ".env.example"):
            if os.path.isfile(os.path.join(ROOT, name)):
                candidates.append(os.path.join(ROOT, name))
    if not candidates:
        out("There is no .env or .env.example file in this project folder. Nothing to check.")
        return 0
    seen: Dict[str, Dict[str, str]] = {}
    for path in candidates:
        base = os.path.basename(path)
        if not is_inside(path, ROOT):
            out("%s is outside the project folder. I only read settings files inside it." % safe_text(base, 40))
            return 1
        if "env" not in base.lower():
            out("%s does not look like a settings file (its name has no 'env'). I read only .env style files." % safe_text(base, 40))
            return 1
        if is_link(path) or not os.path.isfile(path):
            out("%s was not found (or is a link)." % safe_text(base, 40))
            return 1
        raw = read_bytes(path, MAX_READ)
        text = decode_bytes(raw[:MAX_READ] if raw else b"")
        if "PRIVATE KEY" in text:
            out("%s looks like a key file, not a settings file. I did not read it." % safe_text(base, 40))
            return 1
        names, other = parse_env_names(text)
        out("%s: %d variable name(s). Values are never shown." % (safe_text(base, 40), len(names)))
        counts: Dict[str, int] = {}
        for name, state in names:
            counts[name] = counts.get(name, 0) + 1
            out("  %s: %s" % (safe_text(name, 60), state))
        for name, n in counts.items():
            if n > 1:
                out("  Note: %s appears %d times; the last one usually wins." % (safe_text(name, 60), n))
        if other:
            out("  %d line(s) are not in NAME=value form (they are not listed)." % other)
        seen[base] = dict(names)
    if ".env" in seen and ".env.example" in seen:
        missing = [n for n in seen[".env.example"] if n not in seen[".env"]]
        extra = [n for n in seen[".env"] if n not in seen[".env.example"]]
        if missing:
            out("In .env.example but missing from .env: %s" % ", ".join(safe_text(n, 60) for n in missing[:15]))
        if extra:
            out("In .env but not in .env.example: %s" % ", ".join(safe_text(n, 60) for n in extra[:15]))
        if not missing and not extra:
            out(".env and .env.example have the same variable names.")
    return 0


# --------------------------------------------------------------------------- audit

def read_limited(path: str) -> Tuple[Optional[str], bool]:
    """(text, too_big): at most 256 KB, links refused."""
    if is_link(path):
        return None, False
    raw = read_bytes(path, MAX_READ)
    if raw is None:
        return None, False
    return decode_bytes(raw[:MAX_READ]), len(raw) > MAX_READ


def _frontmatter_block(text: str) -> Dict[str, str]:
    lines = text.split("\n")
    keys: Dict[str, str] = {}
    if not lines or lines[0].strip() != "---":
        return keys
    current = ""
    for ln in lines[1:300]:
        if ln.strip() == "---":
            break
        m = re.match(r"^([A-Za-z][\w-]*)\s*:\s*(.*)$", ln)
        if m and not ln.startswith((" ", "\t")):
            current = m.group(1)
            keys[current] = m.group(2)
        elif current and ln.startswith((" ", "\t")):
            keys[current] += " " + ln.strip()
    return keys


def kit_hook_launchers(kit_dir: str) -> Tuple[set, set]:
    """(launcher code strings, mode names) of the kit's own hooks.json, used to tell our entries from foreign ones."""
    spec, _ = read_hooks_spec(os.path.join(kit_dir, "tools", "hooks.json"))
    codes, modes = set(), set()
    for groups in (spec or {}).values():
        for group in groups:
            for handler in group.get("hooks", []):
                args = [a for a in handler.get("args", []) if isinstance(a, str)]
                for a in args:
                    if "dispatch.py" in a:
                        codes.add(a)
                if args:
                    modes.add(args[-1])
    return codes, modes


def audit_scan(folder: str, kit_dir: Optional[str] = None, extra_hashes: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """List everything in `folder` that can run code or change safety rules.

    Returns {"items": [{"path", "reason"}], "ours": number of kit files recognised by hash, "notes": [...]}.
    Files whose sha256 equals the folder's own .claude/MANIFEST.txt (or extra_hashes: the new kit's manifest)
    are ours and are not items. Nothing is executed; links are not followed; files are read up to 256 KB."""
    folder = os.path.abspath(folder)
    kit_dir = kit_dir or CLAUDE_DIR
    claude = os.path.join(folder, ".claude")
    items: List[Dict[str, str]] = []
    notes: List[str] = []
    ours = 0
    known: Dict[str, set] = {}
    _, own_files, _ = read_manifest(os.path.join(claude, "MANIFEST.txt"))
    for rel, sha in list(own_files.items()) + list((extra_hashes or {}).items()):
        known.setdefault(rel, set()).add(sha)
    kit_settings, _ = load_settings(os.path.join(kit_dir, "settings.json"))
    kit_allow = set(("Skill(%s)" % n) for n in SKILL_NAMES)
    if kit_settings and isinstance(kit_settings.get("permissions"), dict):
        kit_allow |= set(x for x in kit_settings["permissions"].get("allow", []) if isinstance(x, str))
    launcher_codes, launcher_modes = kit_hook_launchers(kit_dir)
    old_hooks_json = os.path.join(claude, "tools", "hooks.json")
    if os.path.isfile(old_hooks_json) and not is_link(old_hooks_json) and sha256_file(old_hooks_json) in known.get("tools/hooks.json", set()):
        # the project's own (older) hooks.json is ours by hash: the entries it produced are ours too, so an update does not stop
        more_codes, more_modes = kit_hook_launchers(claude)
        launcher_codes, launcher_modes = launcher_codes | more_codes, launcher_modes | more_modes

    def add(path: str, reason: str) -> None:
        items.append({"path": path.replace("\\", "/"), "reason": reason})

    def display(path: str) -> str:
        return os.path.relpath(path, folder).replace("\\", "/")

    def is_ours(rel: str, path: str) -> bool:
        wanted = known.get(rel)
        if not wanted:
            return False
        got = sha256_file(path)
        return got is not None and got in wanted

    def changed_note(rel: str) -> str:
        return " (this kit file was changed)" if rel in known else ""

    def walk_files(base: str) -> Iterable[Tuple[str, bool]]:
        stack = [base]
        count = 0
        while stack:
            cur = stack.pop()
            try:
                entries = sorted(os.scandir(cur), key=lambda e: e.name)
            except OSError:
                continue
            for entry in entries:
                count += 1
                if count > 20000:
                    notes.append("I stopped listing %s after 20000 entries." % display(base))
                    return
                if is_link(entry.path):
                    yield entry.path, True
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name != "__pycache__":          # caches made by running our own scripts
                        stack.append(entry.path)
                else:
                    yield entry.path, False

    # .claude/hooks and .claude/tools: programs
    for sub, reason in (("hooks", "a program that Claude Code can start by itself"), ("tools", "a script in the tools folder that you can run")):
        base = os.path.join(claude, sub)
        if not os.path.isdir(base):
            continue
        for path, linked in walk_files(base):
            rel = os.path.relpath(path, claude).replace("\\", "/")
            if linked:
                add(display(path), "a link (not followed): it could point anywhere")
            elif is_ours(rel, path):
                ours += 1
            elif sub == "tools" and path.endswith((".pyc",)):
                continue
            elif sub == "hooks" or path.endswith((".py", ".sh", ".bat", ".cmd", ".ps1", ".js")):
                add(display(path), reason + (changed_note(rel) or (" (not part of the kit)" if sub == "tools" else "")))

    # settings files
    for name in ("settings.json", "settings.local.json"):
        path = os.path.join(claude, name)
        if not os.path.lexists(path):
            continue
        shown = display(path)
        if is_link(path):
            add(shown, "a link (not followed): it could point anywhere")
            continue
        text, too_big = read_limited(path)
        if too_big:
            add(shown, "larger than 256 KB, so I did not read it all")
            continue
        data, why = load_settings(path)
        if data is None:
            notes.append("%s is not valid JSON (%s); Claude Code ignores it." % (shown, why))
            continue
        hooks = data.get("hooks")
        if isinstance(hooks, dict):
            for event, groups in hooks.items():
                for group in (groups if isinstance(groups, list) else []):
                    for handler in (group.get("hooks") if isinstance(group, dict) and isinstance(group.get("hooks"), list) else []):
                        args = [a for a in (handler.get("args") or []) if isinstance(a, str)] if isinstance(handler, dict) else []
                        if isinstance(handler, dict) and any(a in launcher_codes for a in args) and args and args[-1] in launcher_modes:
                            ours += 1
                        else:
                            command = " ".join([str(handler.get("command", ""))] + args[:2]) if isinstance(handler, dict) else str(handler)
                            add(shown, "a hook for %s runs this when Claude Code works: %s" % (safe_text(event, 30), safe_text(command, 80)))
        for key, reason in (("statusLine", "a status line runs a program every few seconds"),
                            ("apiKeyHelper", "apiKeyHelper runs a program to get your key"),
                            ("enableAllProjectMcpServers", "it starts every tool server (MCP) that the project lists"),
                            ("skipDangerousModePermissionPrompt", "it skips the warning before the no-questions mode"),
                            ("enabledPlugins", "plugins can bring hooks and programs"),
                            ("extraKnownMarketplaces", "it adds a place to download plugins from")):
            if key in data:
                add(shown, reason)
        if "env" in data:
            names = ", ".join(safe_text(k, 30) for k in list(data["env"])[:6]) if isinstance(data["env"], dict) else "?"
            add(shown, "env sets environment variables for every command: %s" % names)
        if data.get("disableAllHooks") is True:
            add(shown, "disableAllHooks switches all hooks off (a safety setting)")
        perms = data.get("permissions")
        if isinstance(perms, dict):
            allow = [x for x in perms.get("allow", []) if isinstance(x, str)] if isinstance(perms.get("allow"), list) else []
            for entry in allow:
                if entry in kit_allow:
                    ours += 1
                else:
                    add(shown, "permissions.allow lets this run without asking: %s" % safe_text(entry, 80))
            if perms.get("defaultMode") in ("bypassPermissions", "dontAsk", "auto"):
                add(shown, "the permission mode %s asks fewer questions than normal" % safe_text(perms["defaultMode"], 30))

    # skills, agents, commands
    for sub in ("skills", "commands", "agents"):
        base = os.path.join(claude, sub)
        if not os.path.isdir(base):
            continue
        for path, linked in walk_files(base):
            if linked:
                add(display(path), "a link (not followed): it could point anywhere")
                continue
            if not path.lower().endswith(".md"):
                continue
            rel = os.path.relpath(path, claude).replace("\\", "/")
            text, too_big = read_limited(path)
            if text is None:
                continue
            fm = _frontmatter_block(text)
            reasons: List[str] = []
            if re.search(r"\b(Bash|PowerShell)\b", fm.get("allowed-tools", "")) or re.search(r"\b(Bash|PowerShell)\b", fm.get("tools", "")) and sub == "commands":
                reasons.append("allows running commands without asking")
            if sub == "commands" and re.search(r"(^|\n)!`|(^|\n)!\s", text):
                reasons.append("runs a shell command when the command starts")
            if sub == "agents":
                for key in ("hooks", "mcpServers", "permissionMode"):
                    if key in fm:
                        reasons.append("the helper agent sets %s" % key)
            if not reasons:
                continue
            if is_ours(rel, path):
                ours += 1
            else:
                add(display(path), "; ".join(reasons) + changed_note(rel))

    # project root
    mcp = os.path.join(folder, ".mcp.json")
    if os.path.lexists(mcp):
        add(display(mcp), "it lists tool servers (MCP) that start programs")
    tasks = os.path.join(folder, ".vscode", "tasks.json")
    if os.path.isfile(tasks) and not is_link(tasks):
        text, _ = read_limited(tasks)
        if text and re.search(r"\"runOn\"\s*:\s*\"folderOpen\"", text):
            add(display(tasks), "a task with runOn starts when the folder is opened in VS Code")
    for name in (".devcontainer", ".devcontainer.json"):
        path = os.path.join(folder, name)
        if os.path.lexists(path):
            add(display(path), "a dev container runs setup commands when opened in a container")
    for name, reason in ((".envrc", "direnv runs this shell file when you enter the folder"),
                         (".husky", "git hooks installed by husky run when you commit"),
                         (".pre-commit-config.yaml", "pre-commit runs these programs when you commit")):
        path = os.path.join(folder, name)
        if os.path.lexists(path):
            add(display(path), reason)
    githooks = os.path.join(folder, ".git", "hooks")
    if os.path.isdir(githooks) and not is_link(githooks):
        try:
            for entry in sorted(os.scandir(githooks), key=lambda e: e.name):
                if entry.is_file(follow_symlinks=False) and not entry.name.endswith(".sample"):
                    add(display(entry.path), "a Git hook runs this when you use Git")
        except OSError:
            pass

    # package.json and *.pth: a bounded search below the project folder
    skip = {"node_modules", ".git", "__pycache__", ".venv", "venv", "dist", "build", "target", ".next", ".claude"}
    stack = [(folder, 0)]
    count = 0
    while stack:
        cur, depth = stack.pop()
        try:
            entries = sorted(os.scandir(cur), key=lambda e: e.name)
        except OSError:
            continue
        for entry in entries:
            count += 1
            if count > 20000:
                notes.append("I stopped searching for package.json and .pth files after 20000 entries.")
                stack = []
                break
            if is_link(entry.path):
                continue
            if entry.is_dir(follow_symlinks=False):
                if entry.name in skip and not (entry.name in ("venv", ".venv")):
                    continue
                if depth < 3:
                    stack.append((entry.path, depth + 1))
            elif entry.name == "package.json" and depth <= 2:
                text, _ = read_limited(entry.path)
                try:
                    scripts = json.loads(text or "{}").get("scripts", {})
                except (ValueError, AttributeError):
                    scripts = {}
                if isinstance(scripts, dict):
                    for key in ("preinstall", "install", "postinstall", "prepare"):
                        if key in scripts:
                            add(display(entry.path), "the script '%s' runs by itself when packages are installed" % key)
            elif entry.name.endswith(".pth"):
                add(display(entry.path), "a .pth file can run Python code when Python starts")
    return {"items": items, "ours": ours, "notes": notes}


def cmd_audit(folder: Optional[str]) -> int:
    target = os.path.abspath(folder) if folder else ROOT
    if not os.path.isdir(target):
        out("Folder not found: %s" % safe_text(target, 120))
        return 1
    result = audit_scan(target)
    items = result["items"]
    out("Audit of %s" % safe_text(target, 140))
    out("This lists everything that can run code or change safety rules. Nothing was run.")
    if result["ours"]:
        out("Ours (unchanged): %d kit entries match the kit's own manifest." % result["ours"])
    shown = 0
    for item in items:
        if shown >= 60:
            out("... and %d more." % (len(items) - shown))
            break
        out("- %s: %s" % (safe_text(item["path"], 100), item["reason"]))
        shown += 1
    for note in result["notes"]:
        out("Note: " + safe_text(note, 160))
    if not items:
        out("Nothing else was found.")
    out("AUDIT: %d items that can run code" % len(items))
    return 0


# --------------------------------------------------------------------------- share-notes

def _split_keep(data: bytes) -> List[bytes]:
    return data.split(b"\n")


def build_share_block(original: str, removed_root_line: str) -> List[str]:
    lines = [
        SHARE_BEGIN + " (added by: doctor.py share-notes on; undo with: doctor.py share-notes off)",
        "# original line: " + original,
    ]
    if removed_root_line:
        lines.append("# root line removed: " + removed_root_line)
    lines += [
        "# Shared with a private repository: now.md, journal/, learner/profile.md.",
        "# Never shared: chat/, state/, inbox/, learner/progress.jsonl, learner/notes.md.",
        "agent-memory/tutor-data/*",
        "!agent-memory/tutor-data/now.md",
        "!agent-memory/tutor-data/journal/",
        "!agent-memory/tutor-data/learner/",
        "agent-memory/tutor-data/learner/*",
        "!agent-memory/tutor-data/learner/profile.md",
        SHARE_END,
    ]
    return lines


def find_share_block(lines: List[str]) -> Tuple[int, int]:
    start = end = -1
    for i, ln in enumerate(lines):
        if ln.strip().startswith(SHARE_BEGIN) and start < 0:
            start = i
        elif ln.strip().startswith(SHARE_END) and start >= 0:
            end = i
            break
    return (start, end) if start >= 0 and end > start else (-1, -1)


SHARED_PATHS = ("now.md", "journal/2026-01-01.md", "learner/profile.md")
PRIVATE_PATHS = ("chat/2026-01-01.md", "state/state.json", "inbox/note.md", "learner/progress.jsonl", "learner/notes.md")


def in_repo(cwd: str) -> bool:
    gitq = lib("gitq")
    if gitq is not None:
        try:
            return bool(gitq.is_repo(cwd))
        except Exception:
            pass
    return os.path.exists(os.path.join(cwd, ".git"))


def verify_ignore_rules(gitignore_text: str, repo_cwd: Optional[str], sharing: bool) -> Tuple[bool, List[str]]:
    """Ask real Git about each notes path. Uses the project's repository when there is one, else a throw-away
    repository that holds only these rules. sharing=True expects now.md, journal and profile.md to be visible to Git;
    sharing=False expects every notes file to be hidden. Returns (all as intended, plain result lines)."""
    lines: List[str] = []
    ok = True
    scratch = None
    cwd = repo_cwd
    if cwd is None or not in_repo(cwd):
        import tempfile
        scratch = tempfile.mkdtemp(prefix="tutor-ignore-")
        cwd = scratch
        code, _, _ = _git(["init", "-q"], cwd, 20.0)
        if code != 0:
            shutil.rmtree(scratch, ignore_errors=True)
            return False, ["I could not start Git to test the rules."]
        write_text_file(os.path.join(cwd, ".claude", ".gitignore"), gitignore_text)
    try:
        base = ".claude/agent-memory/tutor-data/"
        wanted = [(p, not sharing) for p in SHARED_PATHS] + [(p, True) for p in PRIVATE_PATHS]
        answers = git_ignore_map(cwd, [base + rel for rel, _ in wanted])
        for rel, should_be_ignored in wanted:
            got = answers.get(base + rel) if answers else None
            if got is None:
                ok = False
                lines.append("%s: Git could not answer" % rel)
            elif got[0] == should_be_ignored:
                lines.append("%s: %s, as intended" % (rel, "private (hidden from Git)" if got[0] else "shared (visible to Git)"))
            else:
                ok = False
                lines.append("%s: %s but should be %s (rule: %s)" % (rel, "hidden" if got[0] else "visible",
                                                                    "hidden" if should_be_ignored else "visible", safe_text(got[1], 80)))
    finally:
        if scratch:
            shutil.rmtree(scratch, ignore_errors=True)
    return ok, lines


def repo_visibility() -> Tuple[str, str]:
    """('PRIVATE' | 'PUBLIC' | 'INTERNAL' | 'UNKNOWN', reason). Asks gh once, with a time limit."""
    gh = find_on_path("gh")
    if not gh:
        return "UNKNOWN", "The GitHub tool (gh) is not installed."
    rc, so, se = _spawn([gh, "repo", "view", "--json", "visibility", "--jq", ".visibility"], 20.0, cwd=ROOT)
    word = (so or "").strip().upper()
    if rc == 0 and word in ("PRIVATE", "PUBLIC", "INTERNAL"):
        return word, ""
    return "UNKNOWN", "gh could not tell me (is this folder connected to GitHub, and are you signed in?)."


def plain_gitignore_bytes(raw: Optional[bytes]) -> bool:
    return raw is not None and not (raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") or b"\x00" in raw[:4096])


def take_root_line(root_path: str) -> Tuple[str, Optional[bytes], Optional[bytes]]:
    """Remove the first root .gitignore line that is exactly .claude/agent-memory/ (or without the slash).
    Returns (removed line or "", original bytes, new bytes). Nothing is written here."""
    if not os.path.isfile(root_path) or is_link(root_path):
        return "", None, None
    raw = read_bytes(root_path, 4 * 1024 * 1024)
    if not plain_gitignore_bytes(raw):
        return "", raw, None
    removed, kept = "", []
    for row in raw.split(b"\n"):
        plain = row.rstrip(b"\r").strip()
        if not removed and plain in (b".claude/agent-memory/", b".claude/agent-memory"):
            removed = plain.decode("ascii")
            continue
        kept.append(row)
    return removed, raw, b"\n".join(kept)


def cmd_share_notes(mode: str, confirmed_private: bool) -> int:
    path = os.path.join(CLAUDE_DIR, ".gitignore")
    root_path = os.path.join(ROOT, ".gitignore")
    if is_link(path):
        out(".claude/.gitignore is a link. I did not touch it.")
        return 1
    status, repair_notes = repair_gitignore(path)
    if status == "failed":
        out("I could not write .claude/.gitignore. Nothing was changed.")
        return 1
    if status in ("created", "repaired"):
        out("First I repaired .claude/.gitignore (%s)." % "; ".join(repair_notes))
    text = read_text(path) or ""
    lines = text.split("\n")
    start, end = find_share_block(lines)
    repo_cwd = ROOT if in_repo(ROOT) else None
    if mode == "on":
        if start >= 0:
            ok, results = verify_ignore_rules(text, repo_cwd, True)
            out("Notes sharing is already on.")
            for ln in results:
                out("  " + ln)
            return 0 if ok else 1
        if not confirmed_private:
            visibility, why = repo_visibility()
            if visibility != "PRIVATE":
                if visibility == "UNKNOWN":
                    out("I cannot confirm that the repository is private. " + why)
                    out("Notes sharing stays off. If you checked on github.com that it is PRIVATE, run again with --i-checked-it-is-private.")
                else:
                    out("The repository is %s. Notes would be visible to others, so sharing stays off." % visibility)
                return 1
        old_gitignore = read_bytes(path, 1024 * 1024) or b""
        removed_root, root_before, root_after = take_root_line(root_path)
        index = next((i for i, ln in enumerate(lines) if ln.strip() == GITIGNORE_LINES[0]), -1)
        block = build_share_block(GITIGNORE_LINES[0], removed_root)
        if index >= 0:
            new_lines = lines[:index] + block + lines[index + 1:]
        else:
            new_lines = [ln for ln in lines if ln != ""] + [""] + block
        new_text = "\n".join(new_lines)
        if not new_text.endswith("\n"):
            new_text += "\n"
        if not write_text_file(path, new_text):
            out("I could not write .claude/.gitignore. Nothing was changed.")
            return 1
        if removed_root and root_after is not None and not write_file_atomic(root_path, root_after):
            write_file_atomic(path, old_gitignore)
            out("I could not write the root .gitignore. I put .claude/.gitignore back. Nothing was changed.")
            return 1
        ok, results = verify_ignore_rules(new_text, repo_cwd, True)
        if not ok:
            write_file_atomic(path, old_gitignore)
            if removed_root and root_before is not None:
                write_file_atomic(root_path, root_before)
            out("The rules did not work as planned, so I put everything back. Notes stay private.")
            for ln in results:
                out("  " + ln)
            return 1
        out("Notes sharing is now on for this private repository.")
        out("Shared: now.md, the journal folder and learner/profile.md.")
        out("Kept private: chat copies, state, inbox, your progress list (progress.jsonl) and notes.md.")
        for ln in results:
            out("  " + ln)
        if removed_root:
            out("I also removed the line '%s' from the root .gitignore, because it hid all notes." % removed_root)
        out("To undo: python3 .claude/tools/doctor.py share-notes off")
        return 0
    if start < 0:
        out("Notes sharing is already off. Nothing changed.")
        return 0
    original, root_line = GITIGNORE_LINES[0], ""
    for ln in lines[start:end]:
        if ln.startswith("# original line:"):
            original = ln.split(":", 1)[1].strip() or original
        elif ln.startswith("# root line removed:"):
            root_line = ln.split(":", 1)[1].strip()
    old_gitignore = read_bytes(path, 1024 * 1024) or b""
    new_text = "\n".join(lines[:start] + [original] + lines[end + 1:])
    if not write_text_file(path, new_text):
        out("I could not write .claude/.gitignore. Nothing was changed.")
        return 1
    ok, results = verify_ignore_rules(new_text, repo_cwd, False)
    if not ok:
        write_file_atomic(path, old_gitignore)
        out("Git did not hide every notes file after the change, so I put the sharing rules back.")
        for ln in results:
            out("  " + ln)
        return 1
    out("Notes sharing is now off. All notes stay on this computer again.")
    if root_line in (".claude/agent-memory/", ".claude/agent-memory") and os.path.isfile(root_path) and not is_link(root_path):
        raw = read_bytes(root_path, 4 * 1024 * 1024) or b""
        if plain_gitignore_bytes(raw) and root_line.encode("ascii") not in [r.rstrip(b"\r").strip() for r in raw.split(b"\n")]:
            sep = b"" if (not raw or raw.endswith(b"\n")) else b"\n"
            if write_file_atomic(root_path, raw + sep + root_line.encode("ascii") + b"\n"):
                out("I put the line '%s' back into the root .gitignore, as it was before." % root_line)
    if repo_cwd and find_on_path("git"):
        code, tracked, _ = _git(["ls-files", ".claude/agent-memory"], ROOT, 10.0)
        if code == 0 and tracked.strip():
            n = len([x for x in tracked.split("\n") if x.strip()])
            out("%d notes file(s) are already tracked by Git. To stop tracking them, run:" % n)
            out("  git rm --cached -r .claude/agent-memory/tutor-data")
            out("I did not run it. Files already pushed stay in the repository history.")
    return 0


def repair_gitignore(path: str, template: Optional[str] = None) -> Tuple[str, List[str]]:
    """Make sure .claude/.gitignore has the five protective lines (a share-notes block counts for the first).
    Writes UTF-8 with LF, never UTF-16. Returns (status, notes): created, repaired, ok or failed."""
    notes: List[str] = []
    raw = read_bytes(path, 1024 * 1024) if os.path.lexists(path) else None
    if raw is None:
        body = read_text(template, 100000) if template and os.path.isfile(template) else None
        if not body or not all(w in body for w in GITIGNORE_LINES):
            body = ("# Developer Tutor: files that must never be committed by accident.\n\n"
                    "# The tutor's private notes, learner list, chat copies and hook logs.\n%s\n\n"
                    "# Settings and backups for this computer only.\n%s\n%s\n\n# Python leftovers.\n%s\n%s\n" % GITIGNORE_LINES)
        if not write_text_file(path, body):
            return "failed", ["could not write " + path]
        return "created", ["the file was missing, so it was created"]
    utf16 = raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff") or b"\x00" in raw[:4096]
    text = decode_bytes(raw)
    present = set(ln.strip() for ln in text.split("\n"))
    share = any(ln.startswith(SHARE_BEGIN) for ln in present)
    missing = [w for w in GITIGNORE_LINES if w not in present and not (share and w == GITIGNORE_LINES[0])]
    if not missing and not utf16:
        return "ok", notes
    new_text = text if text.endswith("\n") or not text else text + "\n"
    if missing:
        new_text += "\n# Added by the tutor installer.\n" + "\n".join(missing) + "\n"
        notes.append("added line(s): " + ", ".join(missing))
    if utf16:
        notes.append("converted from UTF-16 to UTF-8")
    if not write_text_file(path, new_text):
        return "failed", ["could not write " + path]
    return "repaired", notes


# --------------------------------------------------------------------------- wipe

def safe_remove(path: str) -> int:
    """Delete a file, a link (the link only, never its target) or a folder tree. Returns the number of files removed."""
    removed = 0
    try:
        if is_link(path):
            try:
                os.unlink(path)
            except OSError:
                os.rmdir(path)
            return 1
        if os.path.isdir(path):
            for entry in list(os.scandir(path)):
                removed += safe_remove(entry.path)
            os.rmdir(path)
            return removed
        try:
            os.unlink(path)
        except PermissionError:
            os.chmod(path, 0o600)
            os.unlink(path)
        return 1
    except OSError:
        return removed


def count_tree(path: str) -> Tuple[int, int]:
    """(files, bytes) below path without following links."""
    files = size = 0
    if is_link(path):
        return 1, 0
    if os.path.isdir(path):
        try:
            for entry in os.scandir(path):
                f, s = count_tree(entry.path)
                files += f
                size += s
        except OSError:
            pass
        return files, size
    try:
        return 1, os.path.getsize(path)
    except OSError:
        return 1, 0


def cmd_wipe(what: str, yes: bool) -> int:
    if not os.path.lexists(DATA):
        out("There is no tutor data folder here, so there is nothing to delete.")
        return 0
    if has_link_between(DATA, ROOT) or not os.path.isdir(DATA) or not is_inside(DATA, ROOT, allow_equal=False):
        out("The tutor data folder is a link or points outside this project. I refuse to delete anything.")
        return 1
    if what == "all":
        victims = [e.path for e in os.scandir(DATA)]
    else:
        folder = os.path.join(DATA, what)
        if os.path.lexists(folder) and (is_link(folder) or not is_inside(folder, DATA, allow_equal=False)):
            out("The %s folder is a link. I refuse to delete anything." % what)
            return 1
        victims = [e.path for e in os.scandir(folder)] if os.path.isdir(folder) else []
    total_files = total_bytes = 0
    for victim in victims:
        f, s = count_tree(victim)
        total_files += f
        total_bytes += s
    label = {"chat": "chat copies", "state": "state files (logs and counters)", "all": "all tutor data, including your list and journal"}[what]
    if not victims:
        out("Nothing to delete in %s." % label)
        return 0
    out("This would delete %d file(s), %.1f KB, from %s." % (total_files, total_bytes / 1024.0, label))
    for victim in sorted(victims)[:12]:
        f, s = count_tree(victim)
        out("  %s (%d file(s))" % (safe_text(os.path.basename(victim), 60), f))
    out("Only files inside .claude/agent-memory/tutor-data are touched.")
    if not yes:
        interactive = False
        try:
            interactive = bool(sys.stdin and sys.stdin.isatty())
        except (AttributeError, ValueError):
            interactive = False
        if not interactive:
            out("Run again with --yes to delete.")
            return 1
        sys.stdout.write("Type DELETE to continue: ")
        sys.stdout.flush()
        answer = sys.stdin.readline().strip()
        if answer != "DELETE":
            out("Nothing was deleted.")
            return 1
    done = sum(safe_remove(v) for v in victims)
    out("Deleted %d file(s)." % done)
    return 0


# --------------------------------------------------------------------------- verify

def cmd_verify() -> int:
    problems = 0
    version, files, bad = read_manifest(os.path.join(CLAUDE_DIR, "MANIFEST.txt"))
    out("Kit check (MANIFEST, safety lint, lesson data)")
    absent = [rel for rel in KIT_PAGE_FILES if rel not in files and not os.path.isfile(os.path.join(CLAUDE_DIR, *rel.split("/")))]
    if absent:
        problems += len(absent)
        out("Needs attention: %d kit page(s) missing: %s" % (len(absent), ", ".join(absent[:8])))
    if version is None:
        out("Info: there is no MANIFEST.txt, so file hashes were not checked.")
    else:
        result = compare_manifest(CLAUDE_DIR, files)
        out("Manifest: version %s, %d files." % (safe_text(version, 20), len(files)))
        # a changed or missing kit file makes this copy not the release: the verdict fails and the exit code is 1
        for key, label in (("modified", "differ from the release"), ("missing", "missing")):
            if result[key]:
                problems += len(result[key])
                out("Needs attention: %d file(s) %s: %s" % (len(result[key]), label, ", ".join(result[key][:8])))
        if result["modified"]:
            out("  If you changed them on purpose, that is fine. The exit code only says this copy is not the released kit.")
        if result["eol"]:
            out("Info: %d file(s) differ only in line endings." % len(result["eol"]))
        if result["merged"]:
            out("Info: settings.json is merged with your own settings (expected).")
        extra_info = [r for r in result["extra"] if r.split("/")[0] in ("skills", "rules", "hooks")]
        extra_other = [r for r in result["extra"] if r not in extra_info]
        if extra_info:
            out("Info: %d extra file(s) in skills, rules or hooks: %s" % (len(extra_info), ", ".join(extra_info[:8])))
        if extra_other:
            out("Info: %d other extra file(s): %s" % (len(extra_other), ", ".join(extra_other[:8])))
        if bad:
            out("Info: %d MANIFEST line(s) could not be read." % bad)
    selftest = os.path.join(TOOLS_DIR, "selftest.py")
    sec_failures: Optional[List[str]] = None
    sec_module = os.path.join(TOOLS_DIR, "selftest_security.py")
    try:
        if os.path.isfile(sec_module):
            ns = runpy.run_path(sec_module, run_name="selftest_module")
            fn = ns.get("run_security") or ns.get("run")
            sec_failures = [str(x) for x in (fn() or [])] if callable(fn) else None
        elif os.path.isfile(selftest):
            ns = runpy.run_path(selftest, run_name="selftest_runner")
            discover, run_module = ns.get("discover"), ns.get("run_module")
            if callable(discover) and callable(run_module):
                sec_failures = []
                for name, path in discover():
                    failures, _, _ = run_module(path, True)
                    if failures:
                        sec_failures.extend("%s: %s" % (name, f) for f in failures)
    except BaseException as exc:
        sec_failures = ["the safety lint crashed (%s)" % type(exc).__name__]
    if sec_failures is None:
        out("Info: the safety lint (selftest --security) is not available here.")
    elif sec_failures:
        problems += len(sec_failures)
        out("Needs attention: the safety lint found %d problem(s):" % len(sec_failures))
        for ln in sec_failures[:8]:
            out("  - " + safe_text(ln, 160))
    else:
        out("OK: the safety lint found nothing (no network code, no shell tricks).")
    validate = os.path.join(TOOLS_DIR, "validate.py")
    if os.path.isfile(validate):
        rc, so, se = _spawn([sys.executable, "-B", validate, "--quick"], 120.0, cwd=ROOT)
        tail = (so.strip().split("\n") or [""])[-3:]
        if rc == 0:
            out("OK: validate.py --quick passed.")
        else:
            problems += 1
            out("Needs attention: validate.py --quick reported problems (exit code %s)." % rc)
        for ln in tail:
            if ln.strip():
                out("  " + safe_text(ln, 160))
    else:
        problems_k, count, gloss = light_knowledge_check()
        if problems_k:
            problems += len(problems_k)
            out("Needs attention: lesson data has %d problem(s): %s" % (len(problems_k), "; ".join(problems_k[:3])))
        else:
            out("OK: %d lesson cards and %d glossary terms load. (validate.py is not in this copy.)" % (count, gloss))
    out("Verdict: %s" % ("all checks passed." if problems == 0 else "%d thing(s) need attention." % problems))
    return 0 if problems == 0 else 1


# --------------------------------------------------------------------------- command line

USAGE = """doctor.py - checks and settings helper for the tutor.
Run it like this: python3 .claude/tools/doctor.py <command>   (or python, or py -3)
Commands:
  check [--strict] [--json] [--fix-interpreter [NAME]]   is everything working?
  progress [numbers]                                      what have I learned?
  enable-hooks [--interpreter NAME]                       turn the helper scripts (hooks) on
  disable-hooks                                           turn them off
  envcheck [FILE]                                         list names in .env (never the values)
  audit [FOLDER]                                          list everything in a folder that can run code
  share-notes on|off [--i-checked-it-is-private]          keep your notes in a private GitHub repository (asks GitHub through gh)
  wipe chat|state|all [--yes]                             delete tutor data on this computer
  verify                                                  compare the kit files with the release, safety lint, lessons;
                                                          exit 1 when a kit file differs or is missing
Emergency switch without Python: save .claude/settings.local.json containing {"disableAllHooks": true}"""


class Parser(argparse.ArgumentParser):
    """Argument parser that never exits with code 2: a bad command line raises UsageError."""

    def error(self, message: str) -> Any:  # type: ignore[override]
        raise UsageError(message)

    def exit(self, status: int = 0, message: Optional[str] = None) -> Any:  # type: ignore[override]
        raise UsageError(message or "")


def build_parser() -> Parser:
    parser = Parser(prog="doctor.py", add_help=False)
    sub = parser.add_subparsers(dest="cmd", parser_class=Parser)
    p = sub.add_parser("check", add_help=False)
    p.add_argument("--strict", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--fix-interpreter", nargs="?", const="auto", default=None)
    p = sub.add_parser("progress", add_help=False)
    p.add_argument("what", nargs="?", choices=["numbers"], default=None)
    p = sub.add_parser("enable-hooks", add_help=False)
    p.add_argument("--interpreter", default=None)
    p.add_argument("--yes-hot-reload-ok", action="store_true")
    sub.add_parser("disable-hooks", add_help=False)
    p = sub.add_parser("envcheck", add_help=False)
    p.add_argument("file", nargs="?", default=None)
    p = sub.add_parser("audit", add_help=False)
    p.add_argument("folder", nargs="?", default=None)
    p = sub.add_parser("share-notes", add_help=False)
    p.add_argument("mode", choices=["on", "off"])
    p.add_argument("--i-checked-it-is-private", action="store_true")
    p = sub.add_parser("wipe", add_help=False)
    p.add_argument("what", choices=["chat", "state", "all"])
    p.add_argument("--yes", action="store_true")
    sub.add_parser("verify", add_help=False)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args_list = list(sys.argv[1:] if argv is None else argv)
    if STATE["libs"]:
        os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"   # Windows: never start git.exe or python.exe found in the current folder
    if not args_list or args_list[0] == "help" or any(a in ("-h", "--help") for a in args_list[:2]):
        out(USAGE)
        return 0
    try:
        args = build_parser().parse_args(args_list)
        if not args.cmd:
            raise UsageError("no command")
    except UsageError:
        out("I did not understand that command line.")
        out(USAGE)
        return 1
    try:
        if args.cmd == "check":
            return cmd_check(args.strict, args.json, args.fix_interpreter)
        if args.cmd == "progress":
            return cmd_progress(args.what == "numbers")
        if args.cmd == "enable-hooks":
            return cmd_enable_hooks(args.interpreter)
        if args.cmd == "disable-hooks":
            return cmd_disable_hooks()
        if args.cmd == "envcheck":
            return cmd_envcheck(args.file)
        if args.cmd == "audit":
            return cmd_audit(args.folder)
        if args.cmd == "share-notes":
            return cmd_share_notes(args.mode, args.i_checked_it_is_private)
        if args.cmd == "wipe":
            return cmd_wipe(args.what, args.yes)
        if args.cmd == "verify":
            return cmd_verify()
    except KeyboardInterrupt:
        out("Stopped.")
        return 1
    except Exception as exc:
        tb = exc.__traceback__
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
        where = "%s line %d" % (os.path.basename(tb.tb_frame.f_code.co_filename), tb.tb_lineno) if tb else "unknown place"
        out("doctor.py stopped because of an internal error (%s in %s). If a settings file was being changed, "
            "the old copy is in the .tutor-backup file." % (type(exc).__name__, where))
        return 1
    return 1


if __name__ == "__main__":
    sys.exit(main())
