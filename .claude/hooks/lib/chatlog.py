"""chatlog.py - the learner's recent real messages (the quote source) and the optional chat copy.

What: add_recent_user / recent_user (state/recent-user.json: the last 5 REAL prompts, redacted, each at
most 4,000 characters), is_system_text / is_command (which prompts are machine-made), add_chat (an
OPT-IN readable copy in chat/YYYY-MM-DD.md, only when the profile says chat_copy: on), prune.
Why: a learned-event is accepted only with the learner's own words from one of the last 3 real prompts
(SPEC 6.2). The quote source must never hold a secret, a machine message or text the learner did not
type. Chat copies are off by default; when on, they are redacted the same way.
How it fails safely: redact() uses the secrets engine; if that module is missing a small built-in
pattern set hides the common key shapes, and the hook log gets one note. Nothing here raises.
Who calls it: user_prompt, stop (assistant copy), session_start (prune), learner (recent_user,
is_system_text), activity (redact).
"""
from __future__ import annotations

import os
import re
import sys
from typing import Any, List, Optional

from . import clock, config, fsio, paths, text as textlib

sys.dont_write_bytecode = True

_FALLBACK = [
    re.compile(r"-----" + r"BEGIN [A-Z ]{0,30}PRIVATE KEY" + r"-----.{0,4000}?(?:-----" + r"END [A-Z ]{0,30}PRIVATE KEY" + r"-----|\Z)", re.S),
    re.compile(r"\bsk-[A-Za-z0-9_\-]{20,200}"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,100}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,120}"),
    re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,60}"),
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,100}"),
    re.compile(r"(?i)\bbearer\s{1,3}[A-Za-z0-9._\-]{20,300}"),
    re.compile(r"(?im)^[ \t]{0,8}(?:export[ \t]{1,4})?[A-Z][A-Z0-9_]{0,40}(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIALS?)"
               r"[A-Z0-9_]{0,20}[ \t]{0,3}[:=][ \t]{0,3}['\"]?[^\s'\"]{6,200}"),
]
_noted = {"missing": False}


def redact(text: str) -> str:
    """Secrets replaced by [hidden: ...]. Never returns the input after an error in the engine."""
    if not isinstance(text, str):
        return ""
    try:
        from . import secrets
        return secrets.redact(text)
    except Exception:
        if not _noted["missing"]:
            _noted["missing"] = True
            try:
                from . import hookio
                hookio.log_note("chatlog", "secrets engine missing: using the built-in fallback")
            except Exception:
                pass
        out = text[:200000]
        for rx in _FALLBACK:
            out = rx.sub("[hidden: key or password]", out)
        return out


def secret_kinds(text: str) -> List[str]:
    """Kinds of secret found in text (for the 'do not repeat it' fact); [] when none or no engine."""
    try:
        from . import secrets
        kinds: List[str] = []
        for hit in secrets.find_secrets(text):
            if hit.kind not in kinds:
                kinds.append(hit.kind)
        return kinds[:3]
    except Exception:
        try:
            return ["key or password"] if any(rx.search(text[:200000]) for rx in _FALLBACK) else []
        except Exception:
            return []


# --------------------------------------------------------------------------- machine prompts

_TAG = re.compile(r"^<[A-Za-z/]")
_BRACKET = re.compile(r"^\[[A-Z]")


def is_system_text(text: str) -> bool:
    """True for a prompt made by a machine (SPEC 4.3): after leading whitespace it starts with '<'
    and a letter or '/', or '[' and a capital letter, or with a known system prefix. Slash commands
    are NOT system text (see is_command)."""
    if not isinstance(text, str):
        return False
    head = text.lstrip()
    if not head:
        return False
    if _TAG.match(head) or _BRACKET.match(head):
        return True
    return config.is_system_prefix(head)


def is_command(text: str) -> bool:
    return isinstance(text, str) and text.lstrip().startswith("/")


# --------------------------------------------------------------------------- recent real prompts

def _recent_path() -> str:
    return paths.sub("state", "recent-user.json")


def add_recent_user(prompt_id: str, text: str, ts: Optional[str] = None) -> bool:
    """Store one real prompt (redacted, clipped) as the newest of the last 5. Same prompt_id = replaced."""
    try:
        keep = int(config.cfg("recent_user_keep"))
        limit = int(config.cfg("recent_user_chars"))
        clean = redact(text)[:limit]
        if not clean.strip():
            return False
        item = {"prompt_id": str(prompt_id or ""), "ts": ts or clock.stamp(), "text": clean}

        def mutate(rows: Any) -> Any:
            rows = [r for r in rows if isinstance(r, dict)] if isinstance(rows, list) else []
            if item["prompt_id"]:
                rows = [r for r in rows if r.get("prompt_id") != item["prompt_id"]]
            rows.append(item)
            return rows[-keep:]

        return fsio.update_json(_recent_path(), mutate, []) is not None
    except Exception:
        return False


def recent_user(n: int = 3) -> List[str]:
    """Texts of the last n real prompts, oldest first."""
    try:
        rows = fsio.read_json(_recent_path(), [])
        if isinstance(rows, dict):
            rows = rows.get("prompts", [])
        texts = [r["text"] for r in rows if isinstance(r, dict) and isinstance(r.get("text"), str)]
        return texts[-n:] if n > 0 else []
    except Exception:
        return []


# --------------------------------------------------------------------------- chat copy (opt-in)

def chat_copy_on() -> bool:
    try:
        profile, _ = config.parse_profile(fsio.read_text(paths.sub("learner", "profile.md"), "", 20000))
        return profile.get("chat_copy") == "on"
    except Exception:
        return False


def add_chat(role: str, text: str, prompt_id: str = "", session_id: str = "", ts: Optional[str] = None,
             force: bool = False) -> bool:
    """Append a redacted block to today's chat copy. Does nothing unless chat_copy is on (or force)."""
    try:
        if not force and not chat_copy_on():
            return False
        role = role if role in ("user", "assistant", "system") else "system"
        body = redact(text).strip()[:20000]
        if not body:
            return False
        day = clock.session_day()
        path = paths.sub("chat", day + ".md")
        name = {"user": "User", "assistant": "Tutor", "system": "System"}[role]
        key = re.sub(r"[^A-Za-z0-9_.:-]", "", str(prompt_id or ""))[:60] or textlib.short_code(body)
        marker = "<!-- %s %s -->" % (role, key)
        with fsio.Lock("chat"):
            existing = fsio.read_text(path, "")
            if marker in existing:
                return False
            pieces = []
            if not existing:
                pieces.append("# Chat copy %s\n\nA redacted copy kept on this computer because chat_copy is on. "
                              "Delete the file to remove it.\n" % day)
            session_id = re.sub(r"[^A-Za-z0-9_.:-]", "", str(session_id or ""))[:60]
            sess_marker = "<!-- session %s -->" % session_id
            if session_id and sess_marker not in existing:
                pieces.append("\n%s\n" % sess_marker)
            hhmm = (ts or clock.stamp())[11:16]
            pieces.append("\n%s\n## %s %s\n\n%s\n" % (marker, hhmm, name, textlib.lower_headings(body)))
            return fsio.append_text(path, "".join(pieces))
    except Exception:
        return False


_CHAT_NAME = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")


def prune(days: Optional[int] = None) -> int:
    """Delete chat copies older than the retention (default 30 days). Returns how many were removed."""
    removed = 0
    try:
        days = int(config.cfg("chat_retention_days")) if days is None else int(days)
        folder = paths.sub("chat")
        if not os.path.isdir(folder) or paths.is_link(folder):
            return 0
        today = clock.session_day()
        for name in os.listdir(folder):
            m = _CHAT_NAME.match(name)
            if not m:
                continue
            age = clock.days_between(m.group(1), today)
            if age is not None and age > days:
                try:
                    os.remove(os.path.join(folder, name))
                    removed += 1
                except OSError:
                    pass
    except Exception:
        pass
    return removed
