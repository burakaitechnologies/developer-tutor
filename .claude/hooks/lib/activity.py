"""activity.py - a short log of what the model did with tools (state/activity.jsonl, last 300 rows).

What: record(row), recent(n), since_last_prompt(), work_size(), work_happened(), plus helpers that
turn a PostToolUse input into a row (tool_row) and classify files and commands.
Why: the ledger needs to know how big the work behind an answer was (small, medium, large) to decide
whether a check was expected; offers and tripwires use the recent rows; nothing stores file content.
A row holds: ts, kind (prompt | tool | tripwire), tool, path (project-relative), ext, new, lines,
cmd (command head, 80 characters, redacted), dep, prompt_id, session.
How it fails safely: every function swallows IO errors; no row ever contains text of a file or of a
prompt; command heads pass through the secrets engine first (or a built-in fallback).
Who calls it: post_tool (record), user_prompt (prompt marker), stop and ledger (work_size), knowledge.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, Dict, List, Optional

from . import clock, config, fsio, paths

sys.dont_write_bytecode = True

DOC_EXT = (".md", ".txt", ".rst", ".json", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".conf", ".env.example", ".csv",
           ".gitignore", ".editorconfig", ".lock")
WRITE_TOOLS = ("write", "edit", "notebookedit")          # MultiEdit is not a tool of Claude Code: Edit covers it
SHELL_TOOLS = ("bash", "powershell")
_DEP_CMD = re.compile(
    r"(?:^|[\s;&|(])(?:(?:npm|pnpm|yarn|bun)\s+(?:install|add|i)\b|pip3?\s+install\b|python3?\s+-m\s+pip\s+install\b|"
    r"uv\s+(?:add|pip\s+install)\b|poetry\s+add\b|cargo\s+add\b|go\s+get\b|gem\s+install\b|composer\s+require\b|"
    r"dotnet\s+add\s+package\b)", re.IGNORECASE)
_DEP_FILES = ("package.json", "requirements.txt", "pyproject.toml", "cargo.toml", "go.mod", "gemfile", "composer.json",
              "pipfile", "setup.py", "setup.cfg")
_MAX_BYTES = 120 * 1024


def _path() -> str:
    return paths.sub("state", "activity.jsonl")


def redact(text: str) -> str:
    """Redact through the secrets engine; a built-in minimal fallback when it is missing."""
    try:
        from . import chatlog
        return chatlog.redact(text)
    except Exception:
        return "[hidden: redaction unavailable]"


def record(row: Dict[str, Any]) -> bool:
    """Append one row (ts is added); trims the file to the newest rows."""
    try:
        if not isinstance(row, dict):
            return False
        row = dict(row)
        row.setdefault("ts", clock.stamp())
        ok = fsio.jsonl_append(_path(), row)
        try:
            if os.path.getsize(_path()) > _MAX_BYTES:
                fsio.trim_jsonl(_path(), int(config.cfg("activity_keep")))
        except OSError:
            pass
        return ok
    except Exception:
        return False


def recent(n: int = 12) -> List[Dict[str, Any]]:
    return fsio.jsonl_read(_path(), n)


def since_last_prompt(rows: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    """Rows after the newest prompt marker (all rows when there is no marker)."""
    rows = rows if rows is not None else fsio.jsonl_read(_path(), int(config.cfg("activity_keep")))
    last = -1
    for i, r in enumerate(rows):
        if r.get("kind") == "prompt":
            last = i
    return rows[last + 1:]


def is_doc_path(path: str) -> bool:
    low = (path or "").lower()
    return low.endswith(DOC_EXT)


def _is_dep_file(path: str) -> bool:
    return os.path.basename((path or "").lower()) in _DEP_FILES


def work_size(rows: Optional[List[Dict[str, Any]]] = None) -> str:
    """'none' | 'small' | 'medium' | 'large' for the work since the last prompt (SPEC 6.5).
    small: one file of at most 10 lines, or documents and settings only. medium: 2+ files, more than
    10 lines, a new file or a new dependency. large: 5+ files."""
    try:
        rows = since_last_prompt(rows)
        files: Dict[str, int] = {}
        new_file = dep = False
        for r in rows:
            if r.get("kind") != "tool":
                continue
            tool = str(r.get("tool", "")).lower()
            if tool in WRITE_TOOLS and r.get("path") and not str(r["path"]).startswith(".claude/"):
                p = str(r["path"])   # tutor notes and settings under .claude/ are not the learner's project work
                files[p] = files.get(p, 0) + int(r.get("lines") or 0)
                new_file = new_file or bool(r.get("new"))
                dep = dep or bool(r.get("dep"))
            elif tool in SHELL_TOOLS and r.get("dep"):
                dep = True
        if not files and not dep:
            return "none"
        count, lines = len(files), sum(files.values())
        if count >= 5:
            return "large"
        if dep:
            return "medium"
        if files and all(is_doc_path(p) for p in files):
            return "small"
        if count >= 2 or lines > 10 or new_file:
            return "medium"
        return "small"
    except Exception:
        return "none"


def work_happened(rows: Optional[List[Dict[str, Any]]] = None) -> bool:
    return work_size(rows) != "none"


def counts(rows: Optional[List[Dict[str, Any]]] = None) -> Dict[str, int]:
    """files, lines, new files and dependency flag for the work since the last prompt (for the change card facts)."""
    rows = since_last_prompt() if rows is None else rows
    files: Dict[str, int] = {}
    new = 0
    dep = 0
    for r in rows:
        if (r.get("kind") == "tool" and str(r.get("tool", "")).lower() in WRITE_TOOLS and r.get("path")
                and not str(r["path"]).startswith(".claude/")):
            files[str(r["path"])] = files.get(str(r["path"]), 0) + int(r.get("lines") or 0)
            new += 1 if r.get("new") else 0
        if r.get("kind") == "tool" and r.get("dep"):
            dep += 1
    return {"files": len(files), "lines": sum(files.values()), "new": new, "dep": dep}


# --------------------------------------------------------------------------- rows from tool input

def _line_count(value: Any) -> int:
    if not isinstance(value, str) or not value:
        return 0
    return value.count("\n") + (0 if value.endswith("\n") else 1)


def tool_row(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """A row for a PostToolUse input, or None for tools we do not record."""
    try:
        tool = str(data.get("tool_name") or "")
        low = tool.lower()
        tin = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        resp = data.get("tool_response") if isinstance(data.get("tool_response"), dict) else {}
        row: Dict[str, Any] = {"kind": "tool", "tool": tool, "prompt_id": str(data.get("prompt_id") or ""),
                               "session": str(data.get("session_id") or "")[:40]}
        if low in WRITE_TOOLS:
            raw = str(tin.get("file_path") or tin.get("notebook_path") or resp.get("filePath") or "")
            rel = paths.rel(raw) if raw else ""
            row["path"] = rel[:200]
            row["ext"] = os.path.splitext(rel)[1].lower()[:12]
            if low == "write":
                row["lines"] = _line_count(tin.get("content"))
            elif low == "notebookedit":
                row["lines"] = _line_count(tin.get("new_source"))
            else:
                row["lines"] = max(_line_count(tin.get("new_string")), _line_count(tin.get("old_string")))
            kind = str(resp.get("type") or "")
            row["new"] = kind == "create" or (kind == "" and resp.get("originalFile") is None and low == "write")
            row["dep"] = _is_dep_file(rel)
            return row
        if low in SHELL_TOOLS:
            command = str(tin.get("command") or "")
            row["cmd"] = redact(command[:400])[:80]
            row["dep"] = bool(_DEP_CMD.search(command[:2000]))
            return row
        return None
    except Exception:
        return None
