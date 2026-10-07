"""user_prompt.py - UserPromptSubmit hook: one short block of FACTS before the model reads the message (SPEC 8.2).

What: skips machine-made prompts (task notifications, reminders, hand-back reports, tags); stores the
learner's real words (redacted) as the quote source; prints, in a fixed order and within 450 characters
(900 at most): the time line, a pasted-secret fact, the open check, confusion or frustration, error-paste
and delegation streak facts, notices from the ledger, verify-soon, a your-turn candidate, a due review,
offer candidates, and session facts (quiet mode, skip, labels in another language).
Why: hooks supply facts the model cannot know; the model judges. Plain stdout is context for this event.
No profile line and no counter line are printed per message.
How it fails safely: every optional fact is built inside try; if the learner or knowledge engine is
missing the feature is skipped (one note in the hook log, 'engine missing'); a WIDE folder without a
data folder is never written to; the state file is updated with only the keys this hook changed.
Who calls it: dispatch.py (user-prompt). Reads profile.md, state.json, ledger.jsonl, progress.jsonl;
writes recent-user.json, activity.jsonl (prompt marker), state.json and, only if chat_copy is on, chat/.
"""
from __future__ import annotations

import re
import sys

from lib import activity, chatlog, clock, config, fsio, hookio, ledger, paths, untrusted
from handlers import _common, _facts, _learning

sys.dont_write_bytecode = True

ERROR_FACT = ("The user pasted an error for the %s time in a row without a guess. Read this one together: quote the "
              "one key line, ask which word they know and which file it names, then ask for a hypothesis.")
GUIDE_FACT = ("The user pasted an error and got guiding questions back twice in a row. Give the explanation and the fix "
              "now: say what the line does, make the change, and say where to look to check it.")


def _guide_streak(st, pasted, rows, command):
    """Count the answers in a row that end with a question during an error episode (the learner pasted an error
    and has not had the fix yet). An answer that gives a change or does not end with a question ends the episode.
    Each answer (ledger row) is counted once."""
    if command:
        return 0
    last = rows[-1] if rows else None
    if isinstance(last, dict) and str(last.get("prompt_id", "")) != str(st.get("guide_row") or ""):
        st["guide_row"] = str(last.get("prompt_id", ""))
        if last.get("work_size") in ("medium", "large") or not last.get("ends_q"):
            st["err_episode"], st["guide_qs"] = False, 0
        elif st.get("err_episode"):
            st["guide_qs"] = int(st.get("guide_qs") or 0) + 1
    if pasted:
        st["err_episode"] = True
    return int(st.get("guide_qs") or 0) if st.get("err_episode") else 0


def _ordinal(n):
    return "%d%s" % (n, "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th"))


def _item(p, text, tag=""):
    return {"p": p, "t": text, "tag": tag}


def handle(data):
    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip() or chatlog.is_system_text(prompt):
        return
    command = chatlog.is_command(prompt)
    st = _common.load_state()
    before = _common.copy_state(st)
    status, _detail = _common.folder_status(st)
    ready = _common.data_ready(status)
    profile, _warn = _common.read_profile()
    sid = str(data.get("session_id") or "")
    pid = str(data.get("prompt_id") or "")
    today = clock.session_day()
    teaching = profile["teaching"]
    if ready and sid and st.get("session_id") != sid:
        _common.new_session_reset(st, sid, today)
    if ready and not command:
        st["prompt_n"] = int(st.get("prompt_n") or 0) + 1
    st["last_prompt_id"] = pid or st.get("last_prompt_id", "")

    flags = _facts.detect(prompt) if not command else {}
    learner = _common.engine("learner", "user-prompt", st) if ready and not command else None
    knowledge = _common.engine("knowledge", "user-prompt", st) if learner else None
    items = []

    # session switches
    if flags.get("quiet_on"):
        st["quiet_session"] = True
    if flags.get("quiet_off"):
        st["quiet_session"] = False
    if flags.get("skip"):
        st["task_skip_left"] = 3
    skip_active = int(st.get("task_skip_left") or 0) > 0 and not command
    skip_turns = max(int(st.get("task_skip_left") or 0) - 1, 0)
    if skip_active:
        st["task_skip_left"] = skip_turns
    quiet = bool(st.get("quiet_session")) or teaching == "off"
    frustrated, confused = bool(flags.get("frustration")), bool(flags.get("confusion"))
    err_now = bool(flags.get("error_paste")) and not flags.get("guess")

    # streaks
    if not command:
        st["error_paste_streak"] = int(st.get("error_paste_streak") or 0) + 1 if err_now else 0
        if flags.get("inquiry"):
            st["delegation_streak"] = 0

    # the time line
    perm = re.sub(r"[^A-Za-z]", "", str(data.get("permission_mode") or ""))[:20]
    words = st.get("last_answer_words")
    line = clock.time_line()
    if perm:
        line += ". Permission mode: " + perm
    if isinstance(words, int):
        line += ". Last answer: %d words" % words
    items.append(_item(0, line))

    # secrets and the quote source
    if not command:
        kinds = chatlog.secret_kinds(prompt[:200000])
        if kinds:
            items.append(_item(0, "The user message contains something that looks like a secret (kind: %s; rules/safety.md, "
                                  "pasted secret). The value is exposed: do not repeat it. Say so, name the provider from "
                                  "that kind, and ask the user to revoke it there first, even if it came from another "
                                  "site; then they put a new value in .env themselves."
                               % untrusted.neutralize(kinds[0], 30)))
        if ready:
            chatlog.add_recent_user(pid, prompt[:8000])
            if profile["chat_copy"] == "on":
                chatlog.add_chat("user", prompt[:8000], pid, sid, force=True)
            activity.record({"kind": "prompt", "prompt_id": pid, "session": sid[:12]})

    # the open check (once)
    oc = st.get("open_check")
    if isinstance(oc, dict) and not oc.get("shown") and not command:
        items.append(_item(0, 'Open check (asked last turn): "%s". The user\'s message may be the answer: grade it against '
                              "the concept's rubric and record it per rules/keeping-memory.md; if it is a new request, "
                              "treat the check as skipped." % untrusted.neutralize(oc.get("text", ""), 150)))
        oc["shown"] = True
        st["open_check"] = oc
    if frustrated:
        items.append(_item(0, "User may be frustrated: no offers, checks or reviews this turn; fix first."))
    elif confused:
        items.append(_item(0, "User signals confusion: simplify, one step at a time, a different example."))
    streak = int(st.get("error_paste_streak") or 0)
    if err_now and streak >= 3 and streak % 3 == 0:
        items.append(_item(0, ERROR_FACT % _ordinal(streak)))

    extras_ok = not (quiet or skip_active or frustrated or err_now or command)
    rows = fsio.jsonl_read(paths.sub("state", "ledger.jsonl"), 10) if ready and not command else []
    if _guide_streak(st, bool(flags.get("error_paste")), rows, command) >= 2:
        items.append(_item(1, GUIDE_FACT))

    # delegation streak
    if extras_ok and int(st.get("delegation_streak") or 0) >= 6:
        items.append(_item(1, "Offer one step or a walk-through this turn, once."))
        st["delegation_streak"] = 0

    # notices from the ledger
    if rows and not command and teaching != "off" and not quiet and not skip_active and not frustrated:
        notes = ledger.notices(rows, profile, st.get("notified_prompt_id", ""))
        if teaching == "light":
            notes = [n for n in notes if n.startswith("Terms used without")]
        if rows[-1].get("prompt_id"):
            st["notified_prompt_id"] = rows[-1]["prompt_id"]
        for n in notes[:2]:
            items.append(_item(1, n))

    if learner and knowledge and hookio.budget().left() > 2.0:
        _learning.learning_facts(st, items, learner, knowledge, profile, prompt, flags, rows, extras_ok, teaching, today)

    # session facts
    if st.get("quiet_session"):
        items.append(_item(1, "Quiet mode is on for this session (the user asked): keep the quiet floor."))
    if skip_active:
        items.append(_item(1, "The user asked to skip the lesson part for this request and the next %d turns: keep the "
                              "quiet floor." % skip_turns))
    if flags.get("my_turn"):
        items.append(_item(1, 'The user said "my turn": let them type this step (start at rung R2).'))
    if flags.get("you_do"):
        items.append(_item(2, 'The user said "you do it": do it and narrate (R0). Claude-run use counts as delegated.'))
        st["yourturn_block_until"] = int(st.get("prompt_n") or 0) + 10
    if st.get("offers_off"):
        items.append(_item(2, "Offers off for this session"))
    if config.language_code(profile["language"]) != "en":
        labels = config.labels_for(profile["language"])
        items.append(_item(1, "Labels in the learner's language: check lines start with %s; offer line starts with %s"
                              % (" / ".join(labels["check"]), labels["offer"])))

    text, kept = _common.assemble(items, int(config.cfg("prompt_normal_chars")), int(config.cfg("prompt_hard_chars")))
    _finish_printed(st, kept)   # only what was printed counts as shown
    hookio.emit_plain(text)
    if ready:
        _common.commit(before, st)


def _finish_printed(st, kept):
    """Apply the state changes that depend on a fact really being printed."""
    new_offers = st.pop("offers_new", None)
    if new_offers and "offers" in kept:
        from lib import knowledge
        st["offers_shown"] = knowledge.record_shown(st.get("offers_shown"), new_offers)
        st["offers_pending"] = list(new_offers)
        st["offers_carrier"] = str(st.get("last_prompt_id") or "")   # the answer to this message carries the line
    works = st.pop("yourturn_new", None)
    if works is not None and "yourturn" in kept:
        st["yourturn_count"] = int(st.get("yourturn_count") or 0) + 1
        st["yourturn_last_n"] = works
    if st.pop("review_new", None) and "review" in kept:
        st["reviews_offered"] = int(st.get("reviews_offered") or 0) + 1
        st["review_pending"] = True
