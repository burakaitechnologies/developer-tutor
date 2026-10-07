"""gitq.py - read-only questions to Git, asked the safe way.

What: is_repo, branch, uncommitted_count, days_since_push, ignored_top_level (alias ignored_paths),
staged_diff, default_branch, has_remote, secrets_ignored, add_dry_run, outgoing_diff, outgoing_paths,
ls_files, staged_files.
Why: hooks need facts about the repository (state capsule, commit and push scanner). A repository
can carry hostile settings, so every call is hardened (SPEC 4.3): no pager, no optional locks, no
file-system monitor, no external diff or text conversion, no prompts, 5 second timeout, and only
sub-commands from a short allow-list. Git is never asked to fetch, pull, push or clone, and never to contact a
remote: `git remote` is allowed only to read the remote names (has_remote) and the URL of a name (get-url).
How it fails safely: each function returns None (or an empty value) when Git is missing, the folder is
not a repository, the call fails or times out. Text results are GitText (a str with .truncated).
Who calls it: session_start, the guard's commit/push scanner, tree, doctor.
"""
from __future__ import annotations

import os
import re
import sys
import time
from typing import List, Optional, Sequence, Set

sys.dont_write_bytecode = True

TIMEOUT = 5.0
ALLOWED = ("status", "diff", "log", "rev-parse", "branch", "remote", "config", "check-ignore", "ls-files",
           "add", "for-each-ref", "symbolic-ref", "show-ref")
_BASE = ["git", "--no-pager", "--no-optional-locks", "-c", "core.fsmonitor=false", "-c", "core.quotepath=false"]
_DROP_ENV = ("GIT_EXTERNAL_DIFF", "GIT_PAGER", "PAGER", "GIT_ASKPASS", "GIT_SSH_COMMAND", "GIT_DIR",
             "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM")
_NEVER_ADD_FLAGS = ("-i", "--interactive", "-p", "--patch", "-e", "--edit")


class GitText(str):
    """Output of a Git call. .truncated is True when it was cut at the byte cap."""
    truncated = False


def _env() -> dict:
    env = dict(os.environ)
    for key in _DROP_ENV:
        env.pop(key, None)
    env.update(GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never", GIT_OPTIONAL_LOCKS="0", LC_ALL="C", LANG="C")
    return env


def _check(argv: Sequence[str]) -> bool:
    """Only allow-listed sub-commands; `add` only with --dry-run; `config` only to read."""
    if not argv or argv[0] not in ALLOWED:
        return False
    if argv[0] == "add":
        return ("--dry-run" in argv or "-n" in argv) and not any(a in _NEVER_ADD_FLAGS for a in argv)
    if argv[0] == "config":
        return any(a in ("--get", "--get-all", "--list", "-l", "--get-regexp") for a in argv)
    if argv[0] == "branch":
        return not any(a in ("-d", "-D", "-m", "-M", "-c", "-C", "--delete", "--move", "--copy", "-f", "--force") for a in argv)
    if argv[0] == "remote":
        return len(argv) == 1 or argv[1] in ("-v", "get-url")       # `remote show` contacts the remote: refused
    return True


def run_git(cwd: str, argv: Sequence[str], timeout: float = TIMEOUT, max_bytes: int = 4 * 1024 * 1024) -> Optional[GitText]:
    """Run `git <argv>` in cwd. Returns the output (GitText), or None on any failure
    (missing git, not a repository, non-zero exit, timeout, refused sub-command)."""
    res = _run(cwd, argv, timeout, max_bytes)
    if res is None or res[0] != 0:
        return None
    return res[1]


def _run(cwd: str, argv: Sequence[str], timeout: float, max_bytes: int):
    """(exit code, GitText, stderr text) or None when git could not be started."""
    argv = list(argv)
    if not _check(argv):
        return None
    if not cwd or not os.path.isdir(cwd):
        return None
    if argv[0] in ("diff", "log"):
        argv = [argv[0], "--no-ext-diff", "--no-textconv"] + argv[1:]
    try:
        import subprocess
        import threading
        flags = 0x08000000 if os.name == "nt" else 0   # CREATE_NO_WINDOW
        proc = subprocess.Popen(_BASE + argv, cwd=cwd, env=_env(), stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=flags)
    except (OSError, ValueError, ImportError):
        return None
    timer = threading.Timer(timeout, _kill, [proc])
    timer.daemon = True
    timer.start()
    truncated = False
    err_box: List[bytes] = []
    # stderr has its own reader: a child that fills the stderr pipe first would block there while we wait for stdout
    err_reader = threading.Thread(target=_drain, args=(proc.stderr, err_box, 2000)) if proc.stderr else None
    if err_reader is not None:
        err_reader.daemon = True
        err_reader.start()
    try:
        data = proc.stdout.read(max_bytes + 1)
        if len(data) > max_bytes:
            data = data[:max_bytes]
            truncated = True
            _kill(proc)
        proc.wait(timeout=1.0)
        if err_reader is not None:
            err_reader.join(1.0)
    except Exception:
        _kill(proc)
        data = b""
        timer.cancel()
        return None
    finally:
        timer.cancel()
        for stream in (proc.stdout, proc.stderr):
            if stream is proc.stderr and err_reader is not None and err_reader.is_alive():
                continue           # still read by its thread: closing it now would wait for that read
            try:
                if stream:
                    stream.close()
            except OSError:
                pass
    if getattr(proc, "returncode", None) is None:
        _kill(proc)
        return None
    text = GitText(data.decode("utf-8", errors="replace"))
    text.truncated = truncated
    code = proc.returncode
    if truncated:
        code = 0   # we killed it on purpose after reading enough
    err = err_box[0] if err_box else b""
    return code, text, err.decode("utf-8", errors="replace")


def _drain(stream, box: List[bytes], keep: int) -> None:
    """Read a pipe to its end. The first `keep` bytes go to box[0]; the rest is read and dropped."""
    kept = b""
    try:
        reader = getattr(stream, "read1", None) or stream.read
        while True:
            chunk = reader(4096)
            if not chunk:
                break
            if len(kept) < keep:
                kept += chunk[:keep - len(kept)]
    except (OSError, ValueError):
        pass
    box.append(kept)


def _kill(proc) -> None:
    try:
        proc.kill()
    except OSError:
        pass


# --------------------------------------------------------------------------- questions

def is_repo(cwd: str) -> bool:
    """True when a .git entry exists in cwd or a parent (no process is started)."""
    try:
        cur = os.path.abspath(cwd)
        for _ in range(30):
            if os.path.exists(os.path.join(cur, ".git")):
                return True
            parent = os.path.dirname(cur)
            if parent == cur:
                return False
            cur = parent
    except (OSError, ValueError):
        pass
    return False


def branch(cwd: str) -> Optional[str]:
    """Current branch name; '(detached)' when HEAD is detached; None when not a repository."""
    if not is_repo(cwd):
        return None
    out = run_git(cwd, ["symbolic-ref", "--short", "-q", "HEAD"])
    if out is not None and out.strip():
        return out.strip()
    ok = run_git(cwd, ["rev-parse", "--git-dir"])
    return "(detached)" if ok is not None else None


def uncommitted_count(cwd: str) -> Optional[int]:
    """Number of changed or untracked paths (git status --porcelain lines); None when unknown."""
    if not is_repo(cwd):
        return None
    out = run_git(cwd, ["status", "--porcelain", "--untracked-files=normal"], max_bytes=2 * 1024 * 1024)
    if out is None:
        return None
    return len([ln for ln in out.split("\n") if ln.strip()])


def has_remote(cwd: str) -> bool:
    out = run_git(cwd, ["remote"]) if is_repo(cwd) else None
    return bool(out and out.strip())


def upstream(cwd: str) -> Optional[str]:
    out = run_git(cwd, ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"]) if is_repo(cwd) else None
    return out.strip() if out and out.strip() else None


def days_since_push(cwd: str) -> Optional[int]:
    """Whole days since the newest commit that the upstream branch holds (the last push, as far as
    this computer knows). None when there is no upstream (never pushed) or Git cannot answer."""
    if not is_repo(cwd):
        return None
    out = run_git(cwd, ["log", "-1", "--format=%ct", "@{u}"])
    if out is None or not out.strip().isdigit():
        return None
    return max(int((time.time() - int(out.strip())) // 86400), 0)


def ignored_top_level(cwd: str) -> Optional[Set[str]]:
    """Paths Git ignores (folders collapsed by --directory), relative, with '/' and no trailing '/'.
    None when Git cannot answer."""
    if not is_repo(cwd):
        return None
    out = run_git(cwd, ["ls-files", "-z", "--others", "--ignored", "--exclude-standard", "--directory"],
                  max_bytes=2 * 1024 * 1024)
    if out is None:
        return None
    return set(n.rstrip("/") for n in out.split("\0") if n)


ignored_paths = ignored_top_level


def staged_diff(cwd: str, max_bytes: int = 2 * 1024 * 1024) -> Optional[GitText]:
    """`git diff --cached -U0`: what the next commit would contain. None = could not check;
    .truncated True = cut at max_bytes."""
    if not is_repo(cwd):
        return None
    return run_git(cwd, ["diff", "--cached", "-U0"], max_bytes=max_bytes)


def head_diff(cwd: str, max_bytes: int = 2 * 1024 * 1024) -> Optional[GitText]:
    """`git diff HEAD -U0` (tracked changes, staged or not). Falls back to the staged diff when HEAD does not exist yet."""
    if not is_repo(cwd):
        return None
    out = run_git(cwd, ["diff", "HEAD", "-U0"], max_bytes=max_bytes)
    return out if out is not None else staged_diff(cwd, max_bytes)


def staged_files(cwd: str) -> Optional[List[str]]:
    out = run_git(cwd, ["diff", "--cached", "--name-only", "-z"]) if is_repo(cwd) else None
    return None if out is None else [n for n in out.split("\0") if n]


def ls_files(cwd: str, *pathspecs: str) -> Optional[List[str]]:
    out = run_git(cwd, ["ls-files", "-z", "--"] + list(pathspecs)) if is_repo(cwd) else None
    return None if out is None else [n for n in out.split("\0") if n]


def default_branch(cwd: str) -> str:
    """The remote's default branch name when known, else main or master if one exists, else 'main'."""
    if is_repo(cwd):
        out = run_git(cwd, ["symbolic-ref", "--short", "-q", "refs/remotes/origin/HEAD"])
        if out and "/" in out.strip():
            return out.strip().split("/", 1)[1]
        for name in ("main", "master"):
            if run_git(cwd, ["show-ref", "--verify", "--quiet", "refs/heads/" + name]) is not None:
                return name
        conf = run_git(cwd, ["config", "--get", "init.defaultBranch"])
        if conf and conf.strip():
            return conf.strip()
    return "main"


def add_dry_run(cwd: str, args: Sequence[str]) -> Optional[List[str]]:
    """Paths `git add <args>` WOULD stage (nothing is staged). None = could not check.
    Interactive flags are refused."""
    if not is_repo(cwd):
        return None
    argv = ["add", "--dry-run"] + [a for a in args if a != "--dry-run"]
    res = _run(cwd, argv, TIMEOUT, 2 * 1024 * 1024)
    if res is None:
        return None
    code, out, err = res
    if code != 0:
        # Git refuses an ignored path and lists nothing for it: nothing would be staged.
        return [] if "ignored by one of your .gitignore" in err else None
    found: List[str] = []
    for line in out.split("\n"):
        m = re.match(r"^(?:add|remove) '(.*)'$", line.strip())
        if m:
            found.append(m.group(1).replace("\\\\", "\\"))
    return found


def outgoing_diff(cwd: str, max_bytes: int = 2 * 1024 * 1024) -> Optional[GitText]:
    """Patch text of the commits a push would send: up to 200 commits since the upstream, or all
    commits not on any remote when there is no upstream."""
    if not is_repo(cwd):
        return None
    base = ["log", "-p", "-U0", "--max-count=200", "--format=commit %H"]
    up = upstream(cwd)
    if up:
        argv = base + [up + "..HEAD"]
    else:
        argv = base + ["HEAD", "--not", "--remotes"]
    return run_git(cwd, argv, max_bytes=max_bytes)


def outgoing_paths(cwd: str) -> Optional[List[str]]:
    """File paths touched by the commits a push would send."""
    if not is_repo(cwd):
        return None
    base = ["log", "--max-count=200", "--name-only", "-z", "--format="]
    up = upstream(cwd)
    argv = base + ([up + "..HEAD"] if up else ["HEAD", "--not", "--remotes"])
    out = run_git(cwd, argv)
    if out is None:
        return None
    names = []
    for part in out.split("\0"):
        part = part.strip("\n")
        if part and part not in names:
            names.append(part)
    return names


def gitignore_problem(cwd: str) -> str:
    """'' when the root .gitignore is readable by Git; else a plain sentence (UTF-16 or NUL bytes)."""
    try:
        with open(os.path.join(cwd, ".gitignore"), "rb") as f:
            head = f.read(4096)
    except OSError:
        return ""
    if head.startswith(b"\xff\xfe") or head.startswith(b"\xfe\xff") or b"\x00" in head:
        return ".gitignore is saved as UTF-16; Git cannot read it"
    return ""


def secrets_ignored(cwd: str) -> List[str]:
    """Problems with the ignore rules that protect secrets and tutor notes; [] when all is fine or
    when the folder is not a repository. One Git call asks about all four paths."""
    if not is_repo(cwd):
        return []
    problems: List[str] = []
    bad = gitignore_problem(cwd)
    if bad:
        problems.append(bad)
    wanted = [
        (".env", ".env is not ignored by Git", os.path.exists(os.path.join(cwd, ".env")) or has_remote(cwd)),
        (".env.local", ".env.local is not ignored by Git", os.path.exists(os.path.join(cwd, ".env.local"))),
        (".claude/agent-memory/tutor-data/chat/x.md", "tutor notes are not ignored by Git", True),
        (".claude/settings.local.json", "settings.local.json is not ignored by Git", True),
    ]
    wanted = [w for w in wanted if w[2]]
    if not wanted:
        return problems
    res = _run(cwd, ["check-ignore", "--"] + [w[0] for w in wanted], TIMEOUT, 10000)
    if res is None or res[0] not in (0, 1):
        return problems
    ignored = set(ln.strip() for ln in res[1].split("\n") if ln.strip())
    for path, message, _ in wanted:
        if path not in ignored:
            problems.append(message)
    return problems


def _check_ignore(cwd: str, path: str) -> Optional[bool]:
    """True = ignored, False = not ignored, None = could not ask."""
    res = _run(cwd, ["check-ignore", "-q", "--", path], TIMEOUT, 1000)
    if res is None:
        return None
    if res[0] == 0:
        return True
    if res[0] == 1:
        return False
    return None


def status_summary(cwd: str) -> Optional[dict]:
    """One `git status --porcelain -b` call: branch, number of changed or untracked paths, upstream name
    (or ''), commits ahead and behind. None when Git cannot answer."""
    if not is_repo(cwd):
        return None
    out = run_git(cwd, ["status", "--porcelain=v1", "-b", "--untracked-files=normal"], max_bytes=2 * 1024 * 1024)
    if out is None:
        return None
    lines = out.split("\n")
    head = lines[0] if lines and lines[0].startswith("## ") else ""
    changed = len([ln for ln in lines[1:] if ln.strip()])
    branch_name, up, ahead, behind = "", "", 0, 0
    if head:
        body = head[3:]
        m = re.match(r"^(.*?)(?:\.\.\.(\S+))?(?: \[(.*)\])?$", body)
        if m:
            branch_name = m.group(1) or ""
            up = m.group(2) or ""
            info = m.group(3) or ""
            ma, mb = re.search(r"ahead (\d+)", info), re.search(r"behind (\d+)", info)
            ahead = int(ma.group(1)) if ma else 0
            behind = int(mb.group(1)) if mb else 0
        if branch_name.startswith("No commits yet on "):
            branch_name = branch_name[len("No commits yet on "):]
        elif branch_name.startswith("HEAD (no branch)"):
            branch_name = "(detached)"
    return {"branch": branch_name, "changed": changed, "upstream": up, "ahead": ahead, "behind": behind}


def parallel(jobs: dict) -> dict:
    """Run several zero-argument callables at the same time (each starts a Git process) and return
    {name: result}. A job that raises gives None. Used by the session capsule to stay fast."""
    results: dict = {}
    try:
        import threading
    except ImportError:
        return {name: _safe_call(fn) for name, fn in jobs.items()}

    def work(name, fn):
        results[name] = _safe_call(fn)

    threads = [threading.Thread(target=work, args=(name, fn)) for name, fn in jobs.items()]
    for t in threads:
        t.daemon = True
        t.start()
    deadline = time.time() + TIMEOUT + 2
    for t in threads:
        t.join(max(deadline - time.time(), 0.05))
    for name in jobs:
        results.setdefault(name, None)
    return results


def _safe_call(fn):
    try:
        return fn()
    except Exception:
        return None
