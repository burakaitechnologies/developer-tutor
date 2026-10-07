"""tree.py - the folder check (is this a good project folder?) and the small project tree.

What: folder_check(root) -> ("ok" | "WIDE" | "SYNCED", detail); draw(root, budget_chars, budget) -> text;
tree_hash(root, budget) -> short hash of the top two levels.
Why: a learner who opens Claude Code in Documents or on the Desktop gives the tutor a whole life's
files to look at; the check says so (SPEC 6.8). The tree gives the model a map of the project at
session start. It follows the prototype's drawing rules: folders first, at most 20 entries per
folder, every Git-ignored item as ONE line and never opened, no .git, no tutor notes.
Safety: every name goes through untrusted.neutralize (60 characters); the caller fences the result.
How it fails safely: a scan budget (300 ms or 20,000 entries) returns a "tree skipped" note; any error
returns an empty string. folder_check never reads file contents.
Who calls it: session_start, user_prompt (cached result), doctor.
"""
from __future__ import annotations

import hashlib
import os
import sys
import time
from typing import Any, List, Optional, Set, Tuple

from . import config, gitq, untrusted

sys.dont_write_bytecode = True

PROJECT_MARKERS = ("package.json", "pyproject.toml", "requirements.txt", "index.html", "Cargo.toml", "go.mod", ".git")
NEVER_SHOWN = {".git"}
FALLBACK_STORAGE = {"__pycache__", "node_modules", ".venv", "venv", ".next", "dist", "build", ".cache", "coverage", "target"}
LOCAL_NOTE = "  (local only, not in Git)"
FALLBACK_NOTE = "  (storage folder, not opened)"
TUTOR_NOTE = "  (tutor files)"
SYNC_NAMES = ("onedrive", "icloud", "dropbox", "google drive", "googledrive", "mobile documents")
KNOWN_FOLDERS = {"desktop", "documents", "downloads",
                 "masaüstü", "masaustu", "belgeler", "i̇ndirilenler", "indirilenler", "i̇ndirmeler",
                 "escritorio", "documentos", "descargas", "schreibtisch", "dokumente", "bureau", "téléchargements",
                 "telechargements"}
WIDE_ENTRY_LIMIT = 150


def _norm(p: str) -> str:
    return os.path.normcase(os.path.abspath(p)).rstrip("\\/") or os.path.normcase(os.path.abspath(p))


def folder_check(root: str, budget: Any = None) -> Tuple[str, str]:
    """('WIDE', reason) | ('SYNCED', service name) | ('ok', ''). Pure path logic plus one early-exit
    scandir (stops at 151 entries)."""
    try:
        root_abs = os.path.abspath(root)
        r = _norm(root_abs)
        home = _norm(os.path.expanduser("~"))
        parent = os.path.dirname(root_abs)
        if os.path.dirname(root_abs) == root_abs:
            return "WIDE", "a drive root"
        if r in ("/", "/users", "/home", "c:\\users"):
            return "WIDE", "the folder that holds all user folders"
        if r == home:
            return "WIDE", "your home folder"
        if r == _norm(os.path.dirname(home)):
            return "WIDE", "the folder that holds your home folder"
        name = os.path.basename(root_abs).lower()
        parent_n = _norm(parent)
        parent_name = os.path.basename(parent).lower()
        under_home = parent_n == home
        sync_parent = any(s in parent_name for s in SYNC_NAMES) and _norm(os.path.dirname(parent)) in (home, _norm(os.path.dirname(home)))
        if any(s in name for s in SYNC_NAMES) and parent_n == home:
            return "WIDE", "your cloud-synced home folder (%s)" % _sync_name(root_abs)
        if (under_home or sync_parent or any(s in parent_name for s in SYNC_NAMES)) and name in KNOWN_FOLDERS:
            return "WIDE", "your %s folder" % name.capitalize()
        if "com~apple~clouddocs" in name and "mobile documents" in parent_name:
            return "WIDE", "your iCloud Drive"
        # a folder with many entries and no project file
        count, marker = 0, False
        try:
            with os.scandir(root_abs) as it:
                for entry in it:
                    count += 1
                    if entry.name in PROJECT_MARKERS:
                        marker = True
                    if count > 5000:
                        break
        except OSError:
            pass
        if count > WIDE_ENTRY_LIMIT and not marker:
            return "WIDE", "more than %d items and no project file" % WIDE_ENTRY_LIMIT
        sync = _sync_name(root_abs)
        if sync:
            return "SYNCED", sync
        return "ok", ""
    except (OSError, ValueError):
        return "ok", ""


def _sync_name(path: str) -> str:
    low = path.lower().replace("\\", "/")
    for key, label in (("onedrive", "OneDrive"), ("icloud", "iCloud"), ("mobile documents", "iCloud"),
                       ("dropbox", "Dropbox"), ("google drive", "Google Drive"), ("googledrive", "Google Drive")):
        if key in low:
            return label
    return ""


# --------------------------------------------------------------------------- drawing

class _Scan(object):
    def __init__(self, root: str, ignored: Optional[Set[str]], budget: Any) -> None:
        self.root = root
        self.ignored = ignored
        self.budget = budget
        self.entries = 0
        self.deadline = time.monotonic() + int(config.cfg("tree_budget_ms")) / 1000.0
        self.limit = int(config.cfg("tree_max_entries"))
        self.per_folder = int(config.cfg("tree_max_per_folder"))
        self.cache: dict = {}
        self.skipped = False

    def out_of_budget(self) -> bool:
        if self.entries > self.limit or time.monotonic() > self.deadline:
            self.skipped = True
            return True
        if self.budget is not None:
            try:
                if self.budget.left() < 0.2:
                    self.skipped = True
                    return True
            except Exception:
                pass
        return False

    def listing(self, folder: str, rel: str) -> Tuple[List[Tuple[str, bool, str]], int]:
        """([(name, is_folder, note)], hidden count) for one folder."""
        if folder in self.cache:
            return self.cache[folder]
        folders: List[str] = []
        files: List[str] = []
        try:
            with os.scandir(folder) as it:
                for entry in it:
                    self.entries += 1
                    if self.entries % 500 == 0 and self.out_of_budget():
                        break
                    try:
                        is_dir = entry.is_dir(follow_symlinks=False)
                    except OSError:
                        is_dir = False
                    if is_dir and entry.name in NEVER_SHOWN:
                        continue
                    if rel == ".claude" and entry.name == "agent-memory":
                        continue
                    (folders if is_dir else files).append(entry.name)
        except OSError:
            self.cache[folder] = ([], 0)
            return self.cache[folder]
        key = lambda n: (n.lower(), n)
        ordered = [(n, True) for n in sorted(folders, key=key)] + [(n, False) for n in sorted(files, key=key)]
        shown: List[Tuple[str, bool, str]] = []
        hidden = 0
        for name, is_dir in ordered:
            if len(shown) >= self.per_folder:
                hidden += 1
                continue
            child = (rel + "/" + name) if rel else name
            note = ""
            if self.ignored is not None:
                if child in self.ignored:
                    note = LOCAL_NOTE
            elif is_dir and name in FALLBACK_STORAGE:
                note = FALLBACK_NOTE
            if not note and is_dir and child == ".claude":
                note = TUTOR_NOTE
            shown.append((name, is_dir, note))
        self.cache[folder] = (shown, hidden)
        return self.cache[folder]

    def lines(self, max_depth: int) -> List[str]:
        out: List[str] = [untrusted.neutralize(os.path.basename(os.path.abspath(self.root)) or self.root, 60) + "/"]

        def walk(folder: str, rel: str, prefix: str, depth: int) -> None:
            shown, hidden = self.listing(folder, rel)
            for i, (name, is_dir, note) in enumerate(shown):
                last = i == len(shown) - 1 and not hidden
                label = untrusted.neutralize(name, 60) + ("/" if is_dir else "")
                out.append(prefix + ("\u2514\u2500\u2500 " if last else "\u251c\u2500\u2500 ") + label + note)
                if note or not is_dir or depth >= max_depth or self.out_of_budget():
                    continue
                child_rel = (rel + "/" + name) if rel else name
                walk(os.path.join(folder, name), child_rel, prefix + ("    " if last else "\u2502   "), depth + 1)
            if hidden:
                out.append(prefix + "\u2514\u2500\u2500 ... %d more" % hidden)

        walk(self.root, "", "", 1)
        return out


def _ignored(root: str) -> Optional[Set[str]]:
    try:
        return gitq.ignored_top_level(root) if gitq.is_repo(root) else None
    except Exception:
        return None


def draw(root: str, budget_chars: int = 1200, budget: Any = None, ignored: Optional[Set[str]] = None,
         use_git: bool = True) -> str:
    """The tree text (top two levels), at most budget_chars. '' on error; a one-line note when the
    folder is too big to scan in the time budget."""
    try:
        if not os.path.isdir(root):
            return ""
        if ignored is None and use_git:
            ignored = _ignored(root)
        scan = _Scan(root, ignored, budget)
        best: List[str] = []
        for depth in (1, 2):
            lines = scan.lines(depth)
            if scan.skipped:
                return "(tree skipped: folder too big)"
            text = "\n".join(lines)
            if len(text) <= budget_chars:
                best = lines
            else:
                if not best:
                    best = _truncate(lines, budget_chars)
                break
        return "\n".join(best)
    except Exception:
        return ""


def _truncate(lines: List[str], budget_chars: int) -> List[str]:
    out: List[str] = []
    size = 0
    for line in lines:
        if size + len(line) + 1 > budget_chars - 20:
            out.append("... (tree cut to fit)")
            break
        out.append(line)
        size += len(line) + 1
    return out


def tree_hash(root: str, budget: Any = None) -> str:
    """12 hex characters that change when the top two levels change."""
    try:
        scan = _Scan(root, None, budget)
        text = "\n".join(scan.lines(2))
        return hashlib.sha1(text.encode("utf-8", "replace")).hexdigest()[:12]
    except Exception:
        return ""
