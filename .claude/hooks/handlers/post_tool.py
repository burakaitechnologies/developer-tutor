"""post_tool.py - PostToolUse hook: inbox answers, activity log, delegation counters, tripwires (SPEC 8.4).

What: after a Write, Edit, NotebookEdit, Bash or PowerShell call it (a) when the model wrote a file in
tutor-data/inbox/, lets learner.process_inbox() check the lines and answers `Saved:` or `Refused:`;
(b) records an activity row and updates last-signal dates and the "Claude ran this" counters;
(c) shows at most one tripwire (a nudge about a new dependency, a risky code pattern and so on).
Output: ONE JSON object with additionalContext, and only when there is something to say.
Why: only a hook can verify the learner's own words and count what the model did for the learner.
Claude-run commands never earn the learner credit; they only raise the delegated counter.
How it fails safely: the tool-supplied path is used only to decide whether to look at the inbox; the
hook lists the folder itself. Any failure of an optional part is skipped and logged (type and line only).
Who calls it: dispatch.py (post-tool). Writes activity.jsonl and state.json.
"""
from __future__ import annotations

import os
import re
import sys

from lib import activity, clock, fsio, hookio, paths
from handlers import _common

sys.dont_write_bytecode = True

INBOX_REL = ".claude/agent-memory/tutor-data/inbox/"
WRITE_TOOLS = ("write", "edit", "notebookedit")          # MultiEdit is not a tool of Claude Code: Edit covers it
SHELL_TOOLS = ("bash", "powershell")
_EARNED = re.compile(r"^Saved: .*\((?:learned|did|alone|reviewed)\)", re.M)
_COMMIT = re.compile(r"\bgit\b[^;&|\n]{0,60}\bcommit\b")


def _tool_path(tin):
    return str(tin.get("file_path") or tin.get("notebook_path") or "")


def handle(data):
    tool = str(data.get("tool_name") or "")
    low = tool.lower()
    if low not in WRITE_TOOLS and low not in SHELL_TOOLS:
        return
    tin = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
    st = _common.load_state()
    status, _ = _common.folder_status(st)
    ready = _common.data_ready(status)
    before = _common.copy_state(st)
    out = []
    sid = str(data.get("session_id") or st.get("session_id") or "")

    # (a) the inbox
    if low in WRITE_TOOLS:
        rel = paths.rel(_tool_path(tin)) if _tool_path(tin) else ""
        if rel.startswith(INBOX_REL) and rel.endswith(".md") and ready:
            learner = _common.engine("learner", "post-tool", st)
            if learner is None:
                out.append("The learner engine is not available, so nothing was recorded; tell the user.")
            else:
                lines = learner.process_inbox()
                out.extend(lines)
                if any(_EARNED.search(x) for x in lines):
                    st["delegation_streak"] = 0

    if ready:
        row = activity.tool_row(data)
        knowledge = _common.engine("knowledge", "post-tool", st)
        if row is not None:
            try:
                row["sess"] = sid[:12]
                activity.record(row)
            except Exception as exc:  # noqa: BLE001
                hookio.log_error("post-tool", exc)
            if knowledge is not None:
                _signals(st, knowledge, row, data, low)
        # (c) tripwires
        try:
            note = _tripwire(st, data, low, tin, sid, row)
            if note:
                out.append(note)
        except Exception as exc:  # noqa: BLE001
            hookio.log_error("post-tool", exc)
        _common.commit(before, st)
    if out:
        hookio.emit_json("PostToolUse", "\n".join(out))


def _signals(st, knowledge, row, data, low):
    """last_signal dates for every concept this call touches; the delegated counter for shell commands."""
    try:
        today = clock.session_day()
        tin = data.get("tool_input") if isinstance(data.get("tool_input"), dict) else {}
        text = str(tin.get("command") or "") if low in SHELL_TOOLS else str(row.get("path") or "")
        ids = knowledge.signals_for(text[:4000])
        if not ids:
            return
        last = st.get("last_signal") if isinstance(st.get("last_signal"), dict) else {}
        deleg = st.get("delegated") if isinstance(st.get("delegated"), dict) else {}
        concepts = knowledge.load_concepts()
        for cid in ids:
            last[cid] = today
            if low in SHELL_TOOLS and _is_skill(concepts.get(cid)):
                entry = deleg.get(cid) if isinstance(deleg.get(cid), dict) else {}
                dates = [d for d in entry.get("dates", []) if isinstance(d, str)]
                if today not in dates:
                    dates.append(today)
                deleg[cid] = {"dates": dates[-30:], "count": len(dates)}
        st["last_signal"] = last
        st["delegated"] = deleg
    except Exception as exc:  # noqa: BLE001
        hookio.log_error("post-tool", exc)


def _is_skill(row):
    """A concept the learner can DO (a command or an action) as opposed to an idea to understand."""
    if not isinstance(row, dict):
        return False
    return row.get("kind") == "skill" or row.get("check_type") in ("do", "debug")


def _greenfield(st, sid):
    cached = st.get("greenfield") if isinstance(st.get("greenfield"), dict) else {}
    if cached.get("session") == sid:
        return bool(cached.get("value"))
    value = int(st.get("session_count") or 1) <= 1
    if not value:
        count = 0
        root = paths.project_root()
        skip = {".git", "node_modules", ".claude", "__pycache__", ".venv", "venv"}
        for base, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in skip]
            count += len(files)
            if count >= 10:
                break
        value = count < 10
    st["greenfield"] = {"session": sid, "value": value}
    return value


_CMD_WORDS = ("install", " add", "mkdir", "md ", "docker", "compose", "pip", "npm", "yarn", "pnpm", "cargo", "go get", "gem ",
              "composer", "uv ", "poetry", "bun ", "commit", "dotnet")
_QUIET_EXT = (".md", ".txt", ".csv", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".pdf", ".log")


def _worth_checking(low, tin):
    """A cheap test before the (larger) archrules module is loaded."""
    if low in SHELL_TOOLS:
        command = str(tin.get("command") or "").lower()
        return any(w in command for w in _CMD_WORDS)
    rel = paths.rel(_tool_path(tin)) if _tool_path(tin) else ""
    return bool(rel) and not rel.startswith(".claude/") and not rel.endswith(_QUIET_EXT)


def _queue(st):
    return [q for q in (st.get("tripwire_queue") or []) if isinstance(q, dict)]


def _take_earlier(queue, turn, arch):
    """H5: the facts queued in an earlier turn, worded for the next message, and the rest of the queue. They
    are shown at the first tool call of a later turn, so a project without a save point still gets them."""
    earlier = [q for q in queue if int(q.get("turn", turn) or 0) < turn]
    if not earlier or arch is None:
        return "", queue
    summary = arch.summarise_queued(earlier, at_save_point=False)
    return summary, [q for q in queue if q not in earlier]


def _tripwire(st, data, low, tin, sid, row):
    turn = int(st.get("prompt_n") or 0)
    if not _worth_checking(low, tin):
        queue = _queue(st)
        if not any(int(q.get("turn", turn) or 0) < turn for q in queue):
            return ""
        summary, queue = _take_earlier(queue, turn, _common.engine("archrules", "post-tool", st))
        st["tripwire_queue"] = queue
        return summary
    arch = _common.engine("archrules", "post-tool", st)
    if arch is None:
        return ""
    greenfield = _greenfield(st, sid)
    found = []
    command = ""
    if low in WRITE_TOOLS:
        raw = _tool_path(tin)
        if not raw:
            return ""
        rel = paths.shown(raw)                  # display spelling (platform-7): the tripwire text keeps the file's case
        resp = data.get("tool_response") if isinstance(data.get("tool_response"), dict) else {}
        content = tin.get("content") if low == "write" else None
        if content is None:
            content = fsio.read_text(raw, None, 210000)
        previous = resp.get("originalFile") if isinstance(resp.get("originalFile"), str) else None
        created = (resp.get("type") == "create") if resp.get("type") else None
        found = arch.check_file(raw, content, rel, previous, greenfield, created)
    else:
        command = str(tin.get("command") or "")
        found = arch.check_command(command, greenfield)
    seen = st.get("tripwire_seen") if isinstance(st.get("tripwire_seen"), dict) else {}
    keys = list(seen.get("keys", [])) if seen.get("session") == sid else []
    queue = _queue(st)
    for tw in found:
        if tw.get("queued") and len(queue) < 20:
            item = {k: tw.get(k) for k in ("rule_id", "kind", "name", "rel", "line", "items", "once_key") if k in tw}
            item["turn"] = turn                 # the turn that queued it (H5)
            queue.append(item)
    for tw in arch.log_only(found):
        activity.record({"kind": "tripwire", "rule_id": tw.get("rule_id"), "path": tw.get("rel", ""), "prompt_id": str(data.get("prompt_id") or "")})
    text = ""
    pick = arch.select_visible(found, keys)
    if pick is not None and st.get("tripwire_prompt_n") != turn:
        keys.append(pick["once_key"])
        st["tripwire_prompt_n"] = turn
        text = str(pick.get("text") or "")
    if low in SHELL_TOOLS and queue and _COMMIT.search(command):
        summary = arch.summarise_queued(queue)          # the first save point: the one-line summary
        if summary:
            text = (text + "\n" + summary).strip()
            queue = []
    else:
        summary, queue = _take_earlier(queue, turn, arch)
        if summary:
            text = (text + "\n" + summary).strip()
    st["tripwire_seen"] = {"session": sid, "keys": keys[-100:]}
    st["tripwire_queue"] = queue
    return text
