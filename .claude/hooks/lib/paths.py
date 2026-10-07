"""paths.py - where things are: project folder, tutor data folder, product folders.

What: one place that knows the folder layout (SPEC section 5) and compares paths safely.
Why: every hook must agree on the layout, and Windows paths need care (backslashes, upper and
lower case, junctions, spaces and non-ASCII letters in the project folder).
How it fails safely: no function raises into a handler; ensure_data() returns False instead of
creating anything when a data folder is a link (symlink or junction) or cannot be created.
Who calls it: every other module of the hooks.
"""
from __future__ import annotations

import os
import sys

sys.dont_write_bytecode = True

DATA_REL = ".claude/agent-memory/tutor-data"   # relative to the project folder, written with "/"
DATA_DIRS = ("state", "learner", "journal", "inbox", "chat")

# Files the model may write (Markdown only). Everything else under tutor-data is written by hooks.
MODEL_FILES = ("now.md", "learner/profile.md", "learner/notes.md")
MODEL_DIRS = ("journal", "inbox")

_MOUNT_POINT = 0xA0000003   # Windows junction
_SYMLINK = 0xA000000C       # Windows symbolic link


def _hooks_dir() -> str:
    # lib/paths.py -> lib -> hooks
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def product_dir() -> str:
    """The .claude folder this code is running from (where knowledge/ and templates/ are)."""
    return os.path.dirname(_hooks_dir())


def project_root() -> str:
    """CLAUDE_PROJECT_DIR when set, else two levels above dispatch.py (hooks -> .claude -> project).
    Never the current directory and never the cwd from stdin (it follows `cd`)."""
    env = os.environ.get("CLAUDE_PROJECT_DIR", "")
    if env.strip():
        return os.path.abspath(env)
    return os.path.dirname(product_dir())


def claude_dir() -> str:
    return os.path.join(project_root(), ".claude")


def data_dir() -> str:
    return os.path.join(claude_dir(), "agent-memory", "tutor-data")


def sub(*parts: str) -> str:
    """A path inside the tutor data folder, e.g. sub("state", "state.json")."""
    return os.path.join(data_dir(), *parts)


def knowledge_dir() -> str:
    return os.path.join(product_dir(), "knowledge")


def templates_dir() -> str:
    return os.path.join(product_dir(), "templates")


def is_link(path: str) -> bool:
    """True for a symlink or a Windows junction (not for OneDrive placeholders or other reparse points)."""
    try:
        if os.path.islink(path):
            return True
        st = os.lstat(path)
        return getattr(st, "st_reparse_tag", 0) in (_MOUNT_POINT, _SYMLINK)
    except (OSError, ValueError):
        return False


def rel(path: str) -> str:
    """The path relative to the project folder, with "/" separators and normcase (lower case on
    Windows) so two spellings of one path compare equal. Outside the project: "../..." or, on
    another drive, the absolute path with "/" separators."""
    try:
        root = os.path.normcase(os.path.realpath(project_root()))
        target = os.path.normcase(os.path.realpath(path))
        try:
            out = os.path.relpath(target, root)
        except ValueError:
            out = target
        return out.replace("\\", "/")
    except (OSError, ValueError, TypeError):
        return str(path).replace("\\", "/")


def shown(path: str) -> str:
    """The path relative to the project folder for DISPLAY: "/" separators and the spelling the file system
    gives (no lower-casing). Use rel() to compare two paths and shown() for any text the learner or model reads."""
    try:
        root = os.path.realpath(project_root())
        target = os.path.realpath(path)
        try:
            out = os.path.relpath(target, root)     # on Windows this compares ignoring case but keeps the case of target
        except ValueError:
            out = target
        return out.replace("\\", "/")
    except (OSError, ValueError, TypeError):
        return str(path).replace("\\", "/")


def short_path(path: str, keep: int = 2) -> str:
    """The last `keep` segments of a path for a guard message: 'src/app/a.js' (or '.../app/a.js' when cut).
    Cut by whole segments only, so a file name is never shown in pieces."""
    segs = [s for s in str(path).replace("\\", "/").split("/") if s]
    if len(segs) <= keep:
        return "/".join(segs)
    return ".../" + "/".join(segs[-keep:])


def is_inside(path: str, folder: str) -> bool:
    """True when path is folder itself or below it (realpath + normcase; no filesystem access needed)."""
    try:
        a = os.path.normcase(os.path.realpath(path))
        b = os.path.normcase(os.path.realpath(folder))
        if a == b:
            return True
        return a.startswith(b.rstrip("\\/") + os.sep)
    except (OSError, ValueError, TypeError):
        return False


def has_link_in_chain(path: str, stop: str) -> bool:
    """True when `path` or any parent up to (not including) `stop` exists and is a link."""
    try:
        cur = os.path.abspath(path)
        stop_n = os.path.normcase(os.path.abspath(stop))
        for _ in range(40):
            if os.path.normcase(cur) == stop_n:
                return False
            if os.path.lexists(cur) and is_link(cur):
                return True
            parent = os.path.dirname(cur)
            if parent == cur:
                return False
            cur = parent
    except (OSError, ValueError):
        return True
    return False


def data_exists() -> bool:
    return os.path.isdir(data_dir())


def ensure_data(create: bool = True) -> bool:
    """Create the data folder and its sub-folders. Returns True when the folder is usable.
    Refuses (False) when the data folder or any parent below the project is a link, or when
    creating fails (read-only disk). create=False only checks."""
    try:
        base = data_dir()
        root = project_root()
        if has_link_in_chain(base, root):
            return False
        if not create:
            return os.path.isdir(base)
        for name in DATA_DIRS:
            folder = os.path.join(base, name)
            if os.path.lexists(folder) and is_link(folder):
                return False
            os.makedirs(folder, exist_ok=True)
        return os.path.isdir(base)
    except (OSError, ValueError):
        return False
