"""stop.py - Stop hook: measures the final answer and PRINTS NOTHING (SPEC 8.5).

What: appends one ledger row (words, result words, work size, check marker, fishing, offer line, glossed
and unexplained terms, sentence length, banned words), remembers the check line as the open check, and
records a `met` event for each concept the answer explained.
Why: output on Stop makes Claude take an extra turn (verified), so findings are stored and the next
UserPromptSubmit hook turns them into short facts (notices). The hook ignores stop_hook_active: it does
the same cheap work and prints nothing, so it can never cause a loop.
How it fails safely: an empty final message is skipped entirely; in a WIDE folder with no data folder
nothing is written; a missing learner or knowledge engine only skips the part that needs it.
Who calls it: dispatch.py (stop). Reads profile.md, activity.jsonl, state.json; writes ledger.jsonl,
state.json and (through learner.record_event) progress.jsonl.
"""
from __future__ import annotations

import sys

from lib import activity, chatlog, fsio, hookio, ledger, paths
from handlers import _common

sys.dont_write_bytecode = True


def handle(data):
    msg = data.get("last_assistant_message")
    if not isinstance(msg, str) or not msg.strip():
        return
    st = _common.load_state()
    status, _ = _common.folder_status(st)
    if not _common.data_ready(status):
        return
    before = _common.copy_state(st)
    profile, _warn = _common.read_profile()
    learner = _common.engine("learner", "stop", st)
    sid = str(data.get("session_id") or st.get("session_id") or "")
    pid = str(data.get("prompt_id") or st.get("last_prompt_id") or "")
    folded = None
    if learner:
        try:
            folded = learner.fold(learner.load_events())
        except Exception as exc:  # noqa: BLE001
            hookio.log_error("stop", exc)
    glossed = st.get("glossed_session") if isinstance(st.get("glossed_session"), dict) else {}
    skip = set(glossed.get("terms", [])) if glossed.get("session") == sid else set()
    msg = msg[:200000]
    row = ledger.analyse_answer(msg, None, profile, activity.since_last_prompt(), state=folded, skip_terms=skip,
                                session=sid, prompt_id=pid)
    path = paths.sub("state", "ledger.jsonl")
    fsio.jsonl_append(path, row)
    _trim(path)

    st["last_answer_words"] = row["words"]
    if row["work_size"] != "none":
        st["work_answers"] = int(st.get("work_answers") or 0) + 1
        st["delegation_streak"] = int(st.get("delegation_streak") or 0) + 1
    if row["check_marker"]:
        st["open_check"] = {"text": row["check_text"], "prompt_id": pid, "shown": False}
        st["checks_session"] = int(st.get("checks_session") or 0) + 1
        st["check_ns"] = (list(st.get("check_ns") or []) + [int(st.get("prompt_n") or 0)])[-12:]
    else:
        st.pop("open_check", None)
    if row["glossed_keys"]:
        terms = list(skip) + [k for k in row["glossed_keys"] if k not in skip]
        st["glossed_session"] = {"session": sid, "terms": terms[-200:]}
    _common.commit(before, st)
    if profile.get("chat_copy") == "on":
        chatlog.add_chat("assistant", msg[:20000], pid, sid, force=True)
    if learner:
        for cid in row["glossed_ids"]:
            try:
                learner.record_event(cid, "met", "", "hook", once=True)
            except Exception as exc:  # noqa: BLE001
                hookio.log_error("stop", exc)


def _trim(path):
    try:
        import os
        if os.path.getsize(path) > 160 * 1024:
            fsio.trim_jsonl(path, 200)
    except OSError:
        pass
