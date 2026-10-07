"""_common.py - helpers shared by the handlers (not a hook itself).

What: the state.json layout and its session reset, the optional learner and knowledge engines (imported
lazily, a missing one is skipped with one note in the hook log), the profile reader, the WIDE-folder
rule for writing data, and assemble() which builds a size-limited text from prioritised lines.
Why: user_prompt, stop, post_tool and session_start must agree on one state file and one budget rule.
How it fails safely: every helper catches its own errors; engines that are missing return None.

state/state.json keys (hook-only; one coarse lock; unknown keys of other modules are kept):
  session_id session_count last_session_date prev_session_date folder_check prompt_n last_prompt_id
  last_answer_words open_check{text,prompt_id,shown} notified_prompt_id quiet_session task_skip_left
  yourturn_block_until yourturn_last_n yourturn_count error_paste_streak delegation_streak
  offers_shown offers_pending offers_ignored offers_off offers_printed offers_taken
  sessions_zero_taken asked_fewer reviews_offered reviews_off review_pending work_answers
  checks_session check_ns glossed_session{session,terms} last_signal{id:date} delegated{id:{dates,count}}
  tripwire_seen{session,keys} tripwire_prompt_n tripwire_queue greenfield{session,value}
  learner_note synced_warned (inbox_turn is written by learner.py, guard counters by the guard).
"""
from __future__ import annotations

import copy
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from lib import config, fsio, hookio, paths, untrusted

sys.dont_write_bytecode = True

SESSION_KEYS = ("prompt_n", "quiet_session", "task_skip_left", "yourturn_block_until", "yourturn_last_n",
                "yourturn_count", "error_paste_streak", "delegation_streak", "offers_pending", "offers_ignored",
                "offers_off", "offers_printed", "offers_taken", "reviews_offered", "reviews_off", "review_pending",
                "work_answers", "checks_session", "check_ns", "glossed_session", "tripwire_seen",
                "tripwire_prompt_n", "greenfield", "open_check", "last_answer_words",
                "err_episode", "guide_qs", "guide_row", "offers_carrier")


def state_path() -> str:
    return paths.sub("state", "state.json")


def load_state() -> Dict[str, Any]:
    st = fsio.read_json(state_path(), {})
    return st if isinstance(st, dict) else {}


def update_state(deltas: Dict[str, Any], removes: Tuple[str, ...] = (), nested: Optional[Dict[str, Dict[str, Any]]] = None) -> None:
    """Set keys (deltas), delete keys (removes) and merge into dict keys (nested) under the lock."""
    def mutate(st: Any) -> Any:
        if not isinstance(st, dict):
            st = {}
        st.update(deltas)
        for key in removes:
            st.pop(key, None)
        for key, sub in (nested or {}).items():
            cur = st.get(key) if isinstance(st.get(key), dict) else {}
            cur.update(sub)
            st[key] = cur
        return st
    fsio.update_json(state_path(), mutate, {})


# --------------------------------------------------------------------------- engines

def engine(name: str, mode: str, st: Optional[Dict[str, Any]] = None) -> Any:
    """Import lib.<name> lazily. None when it is missing or broken; one note per kind of problem in the log."""
    try:
        if name == "learner":
            from lib import learner as mod
        elif name == "knowledge":
            from lib import knowledge as mod
        elif name == "secrets":
            from lib import secrets as mod
        elif name == "archrules":
            from lib import archrules as mod
        else:
            return None
        return mod
    except Exception as exc:  # noqa: BLE001 - degrade, never crash
        if st is None or not st.get("learner_note"):
            hookio.log_note(mode, "%s engine missing (%s)" % (name, type(exc).__name__))
            if st is not None:
                st["learner_note"] = True
        return None


# --------------------------------------------------------------------------- profile and folder

def read_profile() -> Tuple[Dict[str, str], List[str]]:
    text = fsio.read_text(paths.sub("learner", "profile.md"), "", 20000)
    return config.parse_profile(text)


def folder_status(st: Dict[str, Any]) -> Tuple[str, str]:
    """('ok'|'WIDE'|'SYNCED', detail): the cached SessionStart result, else computed now."""
    cached = st.get("folder_check")
    if isinstance(cached, dict) and cached.get("status") in ("ok", "WIDE", "SYNCED") and cached.get("root") == paths.project_root():
        return cached["status"], str(cached.get("detail", ""))
    from lib import tree   # loaded only when the cached answer is missing
    status, detail = tree.folder_check(paths.project_root())
    return status, detail


def data_ready(status: str) -> bool:
    """May hooks write tutor data? In a WIDE folder nothing is created until the data folder exists
    (the learner agreed: the tutor-setup skill creates it). Refuses link folders."""
    try:
        if paths.data_exists():
            return paths.ensure_data()
        if status == "WIDE":
            return False
        return paths.ensure_data()
    except Exception:
        return False


def data_problem(status: str, ready: bool) -> str:
    """'' when the data folder works, else one plain sentence for the health line."""
    try:
        if paths.data_exists() and paths.has_link_in_chain(paths.data_dir(), paths.project_root()):
            return "the tutor data folder is a link (symlink or junction), so notes and progress are not saved"
        if not ready:
            return "" if status == "WIDE" else "the tutor data folder could not be created, so notes and progress are not saved"
        probe = paths.sub("state", ".probe")
        if not fsio.write_text(probe, "ok"):
            return "the tutor data folder is not writable, so notes and progress are not saved"
        try:
            os.remove(probe)
        except OSError:
            pass
    except Exception:
        return ""
    return ""


def shown_title(cid: str, title: str, knowledge: Any = None, limit: int = 40) -> str:
    """A concept name for a hook line. Names of shipped concept cards are plain; any other name (a custom
    thing the model recorded) is neutralized and fenced (SPEC 7.4)."""
    clean = untrusted.neutralize(title, limit)
    try:
        if knowledge is not None and cid and knowledge.concept(cid):
            return clean
    except Exception:
        pass
    return untrusted.fence("name", clean)


def shown_names(titles: List[str], knowledge: Any = None, limit: int = 30) -> str:
    """Comma list of names (no ids known): shipped card titles stay plain, others are fenced."""
    known = set()
    try:
        if knowledge is not None:
            known = {str(r.get("title")) for r in knowledge.load_concepts().values()}
    except Exception:
        known = set()
    return ", ".join(untrusted.neutralize(t, limit) if t in known else untrusted.fence("name", untrusted.neutralize(t, limit))
                     for t in titles)


def new_session_reset(st: Dict[str, Any], session_id: str, today: str) -> None:
    """Start a new learning session in the state dict (in place)."""
    if st.get("offers_printed") and not st.get("offers_taken"):
        st["sessions_zero_taken"] = int(st.get("sessions_zero_taken") or 0) + 1
    elif st.get("offers_taken"):
        st["sessions_zero_taken"] = 0
    for key in SESSION_KEYS:
        st.pop(key, None)
    st["prompt_n"] = 0
    st["session_id"] = session_id
    st["session_count"] = int(st.get("session_count") or 0) + 1
    st["prev_session_date"] = st.get("last_session_date") or ""
    st["last_session_date"] = today


# --------------------------------------------------------------------------- budgeted text

def assemble(items: List[Dict[str, Any]], normal: int, hard: int) -> Tuple[str, List[str]]:
    """Join prioritised lines. item = {"p": 0|1|2, "t": text, "tag": name}. Priority 2 lines are dropped
    first (from the end), then priority 1, until the text fits `normal`. Priority 0 lines may use up to
    `hard`; beyond that the longest line is clipped. Returns (text, tags of the lines kept)."""
    keep = [dict(i) for i in items if i.get("t")]

    def size(lst: List[Dict[str, Any]]) -> int:
        return sum(len(i["t"]) + 1 for i in lst)

    for level in (2, 1):
        while size(keep) > normal:
            idx = [n for n, i in enumerate(keep) if i["p"] == level]
            if not idx:
                break
            del keep[idx[-1]]
    while size(keep) > hard and keep:
        longest = max(range(len(keep)), key=lambda n: len(keep[n]["t"]))
        over = size(keep) - hard
        cut = max(len(keep[longest]["t"]) - over - 3, 20)
        keep[longest]["t"] = keep[longest]["t"][:cut].rstrip() + "..."
        if cut <= 20:
            break
    return "\n".join(i["t"] for i in keep), [i.get("tag", "") for i in keep if i.get("tag")]


def copy_state(st: Dict[str, Any]) -> Dict[str, Any]:
    """A deep copy to compare against later (see commit)."""
    return copy.deepcopy(st)


def commit(before: Dict[str, Any], after: Dict[str, Any]) -> None:
    """Write only the keys that differ between the two copies, so a stale copy never overwrites keys
    that another hook or module (learner, guard) changed in the meantime."""
    deltas = {k: v for k, v in after.items() if k not in before or before[k] != v}
    removes = tuple(k for k in before if k not in after)
    if deltas or removes:
        update_state(deltas, removes)
