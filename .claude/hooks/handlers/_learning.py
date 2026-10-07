"""_learning.py - the learning facts of the per-message block (not a hook itself).

What: offer candidates (and whether earlier offers were taken or ignored), a due review, verify-soon, a
your-turn candidate. Why: keeps user_prompt.py short. All of it is optional: it needs the learner and
knowledge engines and is skipped when they are missing.
Rules (SPEC 6.3): offers only after a finished work turn and only when the set changed; at most one
review a turn, capped per session; your-turn at most once per 3 work answers and 3 (5 after week 1) a
session. Nothing is printed here; the caller assembles the lines and applies the state changes.
How it fails safely: any error is logged (type and line) and the feature is skipped.
Who calls it: user_prompt.
"""
from __future__ import annotations

import sys

from lib import activity, config, hookio, ledger, untrusted
from handlers import _common

sys.dont_write_bytecode = True

LEVEL_NAMES = {0: "New", 1: "Seen", 2: "Understood", 3: "Practiced", 4: "Independent"}


def _item(p, text, tag=""):
    return {"p": p, "t": text, "tag": tag}


def learning_facts(st, items, learner, knowledge, profile, prompt, flags, rows, extras_ok, teaching, today):
    try:
        # the previous offers: taken or ignored? Only offers whose line the answer really printed count.
        pending = st.get("offers_pending")
        if pending:
            _settle_offers(st, knowledge, prompt, pending, rows)
        if st.get("review_pending") and flags.get("not_now"):
            st["reviews_off"] = True
        st["review_pending"] = False
        events = learner.load_events()
        folded = learner.fold(events)
        sig = knowledge.signals_for(prompt[:4000])
        last = st.get("last_signal") if isinstance(st.get("last_signal"), dict) else {}
        for cid in sig:
            last[cid] = today
        st["last_signal"] = last
        if teaching == "off" or not extras_ok:
            return
        snap = learner.snapshot(profile, today, events=events, state=folded)
        recent = activity.since_last_prompt()
        soon = learner.verify_soon(folded, set(sig) | knowledge.signals_for(" ".join(str(r.get("path") or r.get("cmd") or "") for r in recent)))
        if soon and teaching == "normal":
            items.append(_item(2, "Verify-soon: %s (the user said they know it; check with one small step when the work needs it)."
                               % ", ".join(_common.shown_title(s, s, knowledge) for s in soon[:2])))
        if teaching != "normal":
            return
        _your_turn(st, items, knowledge, snap)
        cap = int(snap.get("review_cap") or 1)
        due = snap.get("due") or []
        if (due and int(st.get("prompt_n") or 0) >= 2 and not st.get("reviews_off")
                and int(st.get("reviews_offered") or 0) < cap):
            d = due[0]
            items.append(_item(2, "Review due: %s (%s). After answering the request, offer it as a quick one with no score; "
                                  "drop it if the user says not now." % (_common.shown_title(d.get("id", ""), d.get("title", ""), knowledge), d.get("kind", "review")), "review"))
            st["review_new"] = True
        _offers(st, items, learner, knowledge, profile, prompt, rows, folded)
    except Exception as exc:  # noqa: BLE001 - facts are optional
        hookio.log_error("user-prompt", exc)


def _settle_offers(st, knowledge, prompt, pending, rows):
    """The candidates printed before this message count (taken or ignored) only if the answer that should carry
    the 'Next I can teach:' line has it (ledger offer_line). Candidates printed at session start are carried by
    the first answer of the session, so they wait one message. Anything else is dropped unseen and not counted."""
    carrier = str(st.get("offers_carrier") or "")
    if carrier == "session":
        st["offers_carrier"] = str(st.get("last_prompt_id") or "")
        return
    st["offers_pending"], st["offers_carrier"] = [], ""
    row = next((r for r in reversed(rows or []) if carrier and str(r.get("prompt_id", "")) == carrier), None)
    if row is None or not row.get("offer_line"):
        return
    st["offers_printed"] = True
    taken = knowledge.offer_taken(prompt, pending)
    st["offers_ignored"] = knowledge.update_ignored(int(st.get("offers_ignored") or 0), taken)
    if taken:
        st["offers_taken"] = True
    if knowledge.offers_policy(st["offers_ignored"], 0)["off"]:
        st["offers_off"] = True


def _your_turn(st, items, knowledge, snap):
    n = int(st.get("prompt_n") or 0)
    works = int(st.get("work_answers") or 0)
    cap = 3 if int(snap.get("days_since_first") or 0) < 7 else 5
    if n < int(st.get("yourturn_block_until") or 0) or int(st.get("yourturn_count") or 0) >= cap:
        return
    if works - int(st.get("yourturn_last_n") or -3) < 3:
        return
    for d in snap.get("delegated") or []:
        row = knowledge.concept(d.get("id"))
        if int(d.get("level") or 0) >= 1 and row and row.get("try"):
            items.append(_item(2, "Your-turn candidate: %s (%s; Claude ran it %d times)." % (
                _common.shown_title(d.get("id", ""), d.get("title", ""), knowledge), LEVEL_NAMES.get(int(d["level"]), "Seen"), int(d.get("count") or 0)),
                "yourturn"))
            st["yourturn_new"] = works   # counted only if the line is really printed (see user_prompt)
            return


def _offers(st, items, learner, knowledge, profile, prompt, rows, folded):
    if profile["onboarded"] != "yes" or st.get("offers_off"):
        return
    if int(st.get("sessions_zero_taken") or 0) >= 3 and not st.get("asked_fewer"):
        items.append(_item(1, 'Ask once whether the learner wants fewer lessons ("light").'))
        st["asked_fewer"] = True
    if not rows or not ledger.offer_ready(rows[-1]) or rows[-1].get("prompt_id") == st.get("offers_row_id"):
        return
    st["offers_row_id"] = rows[-1].get("prompt_id", "")
    picks = knowledge.pick_offers(folded, activity.recent(12), profile, 3, prompt, st.get("offers_shown"))
    ids = [p["id"] for p in picks]
    if ids and knowledge.offers_changed(st.get("offers_shown"), ids):
        items.append(_item(2, "Offer candidates for the \"%s\" line: %s." % (
            config.labels_for(profile["language"])["offer"], ", ".join(_common.shown_title(p["id"], p["title"], knowledge) for p in picks)), "offers"))
        st["offers_new"] = ids
