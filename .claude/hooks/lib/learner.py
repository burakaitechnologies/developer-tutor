"""learner.py - the learner model: events in, honest levels out (SPEC 6.1, 6.2, 6.3, 6.9).

What: reads learner/progress.jsonl (one JSON object per line: ts, date, id, event, quote, src) and
derives the levels Seen, Understood, Practiced, Independent with fold(); plans reviews (steps 1, 3,
7, 14, 30 days); checks the learner's quotes; turns the small files that the model drops into
inbox/ into progress rows (process_inbox); imports text-only notes (import_notes); builds the
compact snapshot dict that the session-start capsule prints.
Why: levels are derived by a script, never written by the model, and a row needs proof: words the
learner really typed in one of their last 3 messages. A claim ("I know git") never raises a level
above Seen; Claude-run commands never earn credit; same-day evidence stops at Practiced.
How it fails safely: every public function catches errors and returns an empty value (process_inbox
returns one plain line saying nothing was recorded). The inbox code never reads or deletes a path
that a tool supplied: it lists the inbox folder itself, refuses links, reads at most 8 KB per file
and never echoes the text of a refused line (a file could be a link to a secret).
Who calls it: post_tool (process_inbox), stop (record_event), session_start and user_prompt
(snapshot, due_items, counts), doctor (import_notes, progress). Python 3.9, standard library only.

Public functions (all return safe defaults; none raises):
  load_events() -> rows            fold(events) -> {id: ConceptState}      counts(state, today)
  due(state, today, limit) -> ids  due_items(...) -> dicts                 warmup_items(...) -> ids
  review_cap(days_since_first, away_days)   rusty(cs, today)   effective_level(cs, today, away, warmup_passed)
  effective_levels(state, today, away, warmup_passed) -> {id: level}
  verify_soon(state, signal_ids)   away_days(today)            snapshot(profile, today) -> dict for the capsule
  verify_quote(quote, event, open_check_recent, prompts=None) -> (ok, reason)
  process_inbox() -> lines for the model    import_notes() -> counts   record_event(id, event, ...) -> bool
state.json keys read: last_signal, delegated, last_session_date, session_count, open_check;
written: inbox_turn (the refusal and row counters of the current learner message).
"""
from __future__ import annotations

import datetime
import os
import re
import stat
import time
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from . import clock, fsio, paths
except ImportError:  # loaded as a flat module (tests, scripts)
    import clock  # type: ignore
    import fsio  # type: ignore
    import paths  # type: ignore

EVENTS = ("met", "claimed", "learned", "did", "alone", "reviewed", "missed", "declined", "forget")
INBOX_EVENTS = ("learned", "did", "alone", "reviewed", "claimed", "missed", "declined", "forget")
NEEDS_QUOTE = ("learned", "did", "alone", "reviewed", "claimed")
LEVEL_NAMES = {0: "New", 1: "Seen", 2: "Understood", 3: "Practiced", 4: "Independent"}

STEPS = (1, 3, 7, 14, 30)      # review gaps in days; tier 1 gets one more step of 60
TIER1_LAST_STEP = 60
RELEVANCE_DAYS = 21            # a review is eligible only if the project used the concept this recently
CLAIM_SHOW_ME_DAYS = 7         # a claim becomes a show-me review item after this many days
AWAY_DAYS = 14                 # welcome-back protocol starts here

MAX_FILE_BYTES = 8192
MAX_LINES = 6
MAX_FILES_PER_CALL = 8
ROWS_PER_MESSAGE = 2
ROWS_FIRST_SESSION = 6
STOP_AFTER_REFUSALS = 2
MAX_PROMPT_CHARS = 1200
MIN_CHARS, MIN_WORDS, MIN_CHARS_SPACELESS = 12, 3, 8
UNPROMPTED_CHARS, UNPROMPTED_WORDS, UNPROMPTED_CHARS_SPACELESS = 20, 5, 14
MAX_QUOTE_STORED = 300
MAX_NOTES_BYTES = 262144

STOP_MESSAGE = "Refused. Do not write another inbox file this turn. Tell the user which lines were saved and which were not recorded."
RETRY_TEXT = "The file was deleted; write a new file with corrected lines."

_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_WORD_RE = re.compile(r"[^\W_]+")
# Words that ask for a removal, in the folded form that _tokens returns (accents and case removed):
# English, Turkish, German, Spanish and French. The Turkish stem sil is matched as a whole word only (silicon).
_FORGET_RE = re.compile(
    r"^(?:forget|remove|delete|unlearn|unut|vergiss|entfern|olvid|oubli|supprim)\w*$"
    r"|^(?:borra\w*|sil(?:in|mek|dim|ebil\w*|sene|meli|er|ip)?)$")
_RESERVED = frozenset(["con", "prn", "aux", "nul"] + ["com%d" % i for i in range(1, 10)]
                      + ["lpt%d" % i for i in range(1, 10)])
_BUILTIN_QUESTION_WORDS = (
    "what why how when where which who whom whose "
    "neden nasil niye hangi kim nerede nedir "
    "como cual cuando donde quien "
    "warum wann welche "
    "pourquoi comment quand quel quelle").split()

_CACHE: Dict[str, Any] = {}


# --------------------------------------------------------------------------- small helpers

def _log(exc: BaseException) -> None:
    """One line in hook-errors.log: error type, module, line number - never text from the learner."""
    try:
        try:
            from . import hookio  # type: ignore
        except ImportError:
            import hookio  # type: ignore
        hookio.log_error("learner", exc)
        return
    except Exception:
        pass
    try:
        tb = exc.__traceback__
        while tb is not None and tb.tb_next is not None:
            tb = tb.tb_next
        line = tb.tb_lineno if tb is not None else 0
        fsio.log_line("learner: %s at line %d" % (type(exc).__name__, line))
    except Exception:
        pass


def _date(s: Any) -> Optional[datetime.date]:
    try:
        s = str(s)
        return datetime.date(int(s[0:4]), int(s[5:7]), int(s[8:10]))
    except Exception:
        return None


def _add_days(s: str, n: int) -> str:
    d = _date(s)
    return (d + datetime.timedelta(days=n)).isoformat() if d else s


def _days(a: Any, b: Any) -> int:
    da, db = _date(a), _date(b)
    return (db - da).days if da and db else 0


def _today() -> str:
    try:
        v = clock.session_day()
        if isinstance(v, str) and _DATE_RE.match(v[:10]):
            return v[:10]
    except Exception:
        pass
    return datetime.date.today().isoformat()


def _stamp() -> str:
    try:
        v = clock.stamp()
        if isinstance(v, str) and v:
            return v
    except Exception:
        pass
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _afold(text: str) -> str:
    """Case- and accent-insensitive form for comparing words (not length preserving)."""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.replace("\u0131", "i").casefold()


def _tokens(text: str) -> List[str]:
    return _WORD_RE.findall(_afold(text))


def _flatten(value: Any, out: List[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for v in value.values():
            _flatten(v, out)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for v in value:
            _flatten(v, out)


def _config_list(name: str) -> List[str]:
    try:
        try:
            from . import config  # type: ignore
        except ImportError:
            import config  # type: ignore
        out: List[str] = []
        _flatten(getattr(config, name, None), out)
        return out
    except Exception:
        return []


def _filler_phrases() -> frozenset:
    """Folded token tuples of every filler (built-in list plus config.FILLERS in any language)."""
    got = _CACHE.get("fillers")
    if got is None:
        phrases = set()
        for item in _builtin_filler_items() + _config_list("FILLERS"):
            toks = tuple(_tokens(item))
            if toks:
                phrases.add(toks)
        got = frozenset(phrases)
        _CACHE["fillers"] = got
    return got


def _builtin_filler_items() -> List[str]:
    return [
        "ok", "okay", "k", "kk", "yes", "yeah", "yep", "yup", "sure", "fine", "good", "cool", "nice",
        "great", "alright", "all right", "thanks", "thank you", "thx", "ty", "got it", "i see",
        "i get it", "understood", "understand", "i understand", "makes sense", "that makes sense",
        "no problem", "please", "go on", "continue", "next", "lol", "haha", "hmm", "hm", "mhm",
        "right", "correct", "exactly", "agreed", "sounds good", "perfect", "awesome", "done",
        "no thanks", "yes please", "now", "so", "and", "then",
        "tamam", "tamamdir", "anladim", "anladik", "anliyorum", "anlasildi", "evet", "tesekkurler",
        "tesekkur ederim", "sagol", "sag ol", "eyvallah", "olur", "peki", "iyi", "guzel", "harika",
        "super", "mukemmel", "oldu", "simdi", "tamam anladim",
        "vale", "si", "gracias", "muchas gracias", "entendido", "entiendo", "de acuerdo", "claro",
        "listo", "bien", "perfecto", "genial",
        "ja", "danke", "verstanden", "verstehe", "alles klar", "gut", "klar", "genau", "in ordnung",
        "vielen dank",
        "oui", "merci", "compris", "d'accord", "parfait", "entendu", "c'est bon", "tres bien",
        "je vois", "j'ai compris",
    ]


def _question_starts() -> frozenset:
    """Folded token tuples that open a question ("what", "ne demek", "pourquoi"): built-in words plus
    config.QUESTION_WORDS in every language."""
    got = _CACHE.get("qstarts")
    if got is None:
        starts = set()
        for item in sorted(_BUILTIN_QUESTION_WORDS) + _config_list("QUESTION_WORDS"):
            toks = tuple(_tokens(item))
            if toks:
                starts.add(toks)
        got = frozenset(starts)
        _CACHE["qstarts"] = got
    return got


def reset_cache() -> None:
    _CACHE.clear()


def _knowledge():
    try:
        try:
            from . import knowledge  # type: ignore
        except ImportError:
            import knowledge  # type: ignore
        return knowledge
    except Exception:
        return None


def _concepts() -> Dict[str, Any]:
    k = _knowledge()
    try:
        return k.load_concepts() if k else {}
    except Exception:
        return {}


def _state_path() -> str:
    return paths.sub("state", "state.json")


def _state_json() -> Dict[str, Any]:
    try:
        data = fsio.read_json(_state_path(), {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


class _NoLock(object):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _lock(name: str = "learner"):
    try:
        return fsio.Lock(name)
    except Exception:
        return _NoLock()


# --------------------------------------------------------------------------- the concept state

class ConceptState(object):
    """What the events say about one concept. Built by fold(); treat as read-only."""

    __slots__ = ("id", "level", "kind", "tier", "first_date", "last_date", "claimed_date", "claim_open",
                 "real", "verified", "learned_date", "did_date", "alone_date", "declined", "missed",
                 "last_missed", "sure_wrong", "misc", "step", "next_review", "retired", "last_review",
                 "review_passes", "indep_passes", "lapsed")

    def __init__(self, cid: str, kind: str = "skill", tier: int = 2) -> None:
        self.id = cid
        self.level = 0
        self.kind = kind
        self.tier = tier
        self.first_date: Optional[str] = None
        self.last_date: Optional[str] = None
        self.claimed_date: Optional[str] = None
        self.claim_open = False        # claimed and not yet shown by real evidence
        self.real = False              # any learned/did/alone/reviewed seen
        self.verified = False          # ... from a hook-checked source (not text-only notes)
        self.learned_date: Optional[str] = None
        self.did_date: Optional[str] = None
        self.alone_date: Optional[str] = None
        self.declined = 0
        self.missed = 0
        self.last_missed: Optional[str] = None
        self.sure_wrong = 0
        self.misc: List[str] = []
        self.step = 0                  # index into the review ladder
        self.next_review: Optional[str] = None
        self.retired = False
        self.last_review: Optional[str] = None
        self.review_passes = 0
        self.indep_passes = 0          # review passes while at Independent
        self.lapsed = False            # missed and not yet passed again

    @property
    def told_me(self) -> bool:
        """Claimed, never shown by real evidence: displayed as 'told me', never above Seen."""
        return self.claimed_date is not None and not self.real and self.level <= 1

    @property
    def unverified(self) -> bool:
        """Level 2 or higher that rests only on text-only notes (src notes)."""
        return self.level >= 2 and not self.verified

    @property
    def label(self) -> str:
        if self.told_me:
            return "told me"
        if self.level >= 4 and self.indep_passes == 0:
            return "alone once"
        return LEVEL_NAMES.get(self.level, "New")

    def as_dict(self) -> Dict[str, Any]:
        d = {name: getattr(self, name) for name in self.__slots__}
        d["told_me"] = self.told_me
        d["label"] = self.label
        return d


def ladder(tier: int) -> Tuple[int, ...]:
    """Review gaps for a concept tier: tier 1 keeps one more step (60 days) before it retires."""
    return STEPS + (TIER1_LAST_STEP,) if tier == 1 else STEPS


# --------------------------------------------------------------------------- loading and folding

def progress_path() -> str:
    return paths.sub("learner", "progress.jsonl")


def _clean_row(row: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(row, dict):
        return None
    cid, event = row.get("id"), row.get("event")
    if not isinstance(cid, str) or not isinstance(event, str):
        return None
    cid, event = cid.strip()[:60], event.strip().lower()
    if not cid or event not in EVENTS:
        return None
    date = row.get("date")
    if not (isinstance(date, str) and _DATE_RE.match(date[:10])):
        ts = row.get("ts")
        date = ts[:10] if isinstance(ts, str) and _DATE_RE.match(ts[:10]) else None
    if date is None:
        return None
    out = dict(row)
    out.update(id=cid, event=event, date=date[:10])
    return out


def load_events(limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """All valid progress rows in file order. Damaged lines and unknown events are skipped."""
    try:
        rows = fsio.jsonl_read(progress_path(), None) or []
    except Exception:
        return []
    out = [r for r in (_clean_row(x) for x in rows) if r is not None]
    return out[-limit:] if limit else out


def _raise_level(cs: ConceptState, new: int, d: str) -> None:
    old = cs.level
    cs.level = max(old, new)
    if old < 2 <= cs.level and not cs.retired:
        steps = ladder(cs.tier)
        if cs.step >= len(steps):
            cs.retired, cs.next_review = True, None
        else:
            cs.next_review = _add_days(d, steps[cs.step])


def _credit(cs: ConceptState, d: str, explicit: bool = False) -> None:
    """A review passed (explicit) or the learner used the concept themselves (did/alone) on day d.

    A review that is due or overdue advances the step; after the last step the concept retires.
    A pass that comes early, or a use of the concept on a day when no review is due, only pushes the
    next date out, so daily use keeps a concept from coming up for review without moving it along.
    An explicit `reviewed` always counts as a pass (it is what confirms an Independent level); a use
    counts as a pass only when a review was due.
    """
    if cs.level < 2:
        return
    scheduled = cs.next_review is not None and not cs.retired
    is_due = scheduled and d >= cs.next_review  # type: ignore[operator]
    if explicit or is_due:
        cs.review_passes += 1
        if cs.level >= 4:
            cs.indep_passes += 1
        cs.last_review = d
        cs.lapsed = False
    if not scheduled:
        return
    steps = ladder(cs.tier)
    if is_due:
        cs.step += 1
        if cs.step >= len(steps):
            cs.retired, cs.next_review = True, None
        else:
            cs.next_review = _add_days(d, steps[cs.step])
    else:
        later = _add_days(d, steps[min(cs.step, len(steps) - 1)])
        if later > cs.next_review:  # type: ignore[operator]
            cs.next_review = later


def _apply(cs: ConceptState, kind: str, d: str, ev: Dict[str, Any]) -> None:
    notes = ev.get("src") == "notes"
    if kind != "declined":
        if cs.first_date is None:
            cs.first_date = d
        cs.last_date = d
    if kind == "met":
        cs.level = max(cs.level, 1)
    elif kind == "claimed":
        cs.claimed_date = d
        cs.level = max(cs.level, 1)
        if not cs.real:
            cs.claim_open = True
    elif kind == "declined":
        cs.declined += 1
    elif kind == "missed":
        cs.missed += 1
        cs.lapsed = True
        cs.last_missed = d
        cs.claim_open = False
        cs.retired = False
        if ev.get("sure"):
            cs.sure_wrong += 1
        misc = ev.get("misc")
        if isinstance(misc, str) and misc and misc not in cs.misc and len(cs.misc) < 8:
            cs.misc.append(misc[:40])
        if cs.level >= 4:
            cs.indep_passes = 0
        cs.level = max(1, cs.level - 1)
        first_day = cs.first_date == d
        cs.step = 1 if first_day else 0          # ladder[1] = 3 days, ladder[0] = 1 day
        cs.next_review = _add_days(d, 3 if first_day else 1)
    elif kind in ("learned", "did", "alone", "reviewed"):
        cs.real = True
        cs.claim_open = False
        if not notes:
            cs.verified = True
        if notes:                                  # unverified text-only notes stop at Understood
            if kind == "reviewed":
                _credit(cs, d, True)
            cs.learned_date = d if kind != "reviewed" else cs.learned_date
            _raise_level(cs, 2, d)
        elif kind == "learned":
            cs.learned_date = d
            _raise_level(cs, 2, d)
        elif kind == "reviewed":
            _credit(cs, d, True)
            _raise_level(cs, 2, d)
        elif kind == "did":
            _credit(cs, d)
            cs.did_date = d
            _raise_level(cs, 3, d)
        else:  # alone
            _credit(cs, d)
            prior = max([x for x in (cs.did_date, cs.learned_date) if x] or [""])
            cs.alone_date = d
            if cs.kind != "idea" and prior and d > prior:
                _raise_level(cs, 4, d)
            else:
                _raise_level(cs, 3, d)


def fold(events: Iterable[Dict[str, Any]], concepts: Optional[Dict[str, Any]] = None) -> Dict[str, ConceptState]:
    """Derive {concept id: ConceptState} from progress rows. Pure; sorts by date, keeps file order.

    Levels: Seen (met, or a claim shown as 'told me'), Understood (learned), Practiced (did),
    Independent (alone on a LATER day than the last did/learned, kind skill only). Same-day evidence
    stops at Practiced. missed lowers one level (floor Seen) and schedules a review. forget removes
    the concept. declined only counts.
    """
    try:
        if concepts is None:
            concepts = _concepts()
        rows = []
        for i, raw in enumerate(events or []):
            row = _clean_row(raw)
            if row is not None:
                rows.append((row["date"], i, row))
        rows.sort(key=lambda r: (r[0], r[1]))
        state: Dict[str, ConceptState] = {}
        for d, _, ev in rows:
            cid, kind = ev["id"], ev["event"]
            if kind == "forget":
                state.pop(cid, None)
                continue
            cs = state.get(cid)
            if cs is None:
                meta = concepts.get(cid) if isinstance(concepts, dict) else None
                ckind = (meta.get("kind") if isinstance(meta, dict) else "") or "skill"
                try:
                    tier = int(meta.get("tier", 2)) if isinstance(meta, dict) else 2
                except (TypeError, ValueError):
                    tier = 2
                cs = ConceptState(cid, "idea" if ckind == "idea" else "skill", tier)
                state[cid] = cs
            _apply(cs, kind, d, ev)
        return state
    except Exception as exc:
        _log(exc)
        return {}


# --------------------------------------------------------------------------- views of the state

def rusty(cs: ConceptState, today: str) -> bool:
    """Overdue by more than max(14, 2 x its review gap) days: shown as 'rusty', one level lower."""
    if cs.next_review is None or cs.retired or cs.level < 2:
        return False
    steps = ladder(cs.tier)
    gap = steps[min(cs.step, len(steps) - 1)]
    return _days(cs.next_review, today) > max(14, 2 * gap)


def effective_level(cs: ConceptState, today: str, away_days: int = 0, warmup_passed: bool = False) -> int:
    """Level used for fading decisions: one lower when rusty, or when the learner was away 14+ days
    and the warm-up has not passed yet (SPEC 6.3). Never below Seen for a concept that was seen."""
    level = cs.level
    if level >= 2 and (rusty(cs, today) or (away_days >= AWAY_DAYS and not warmup_passed)):
        level -= 1
    return level


def effective_levels(state: Dict[str, ConceptState], today: str, away: int = 0, warmup_passed: bool = False) -> Dict[str, int]:
    """{concept id: level used for fading} for the whole state (see effective_level)."""
    try:
        return {cid: effective_level(cs, today, away, warmup_passed) for cid, cs in (state or {}).items()}
    except Exception as exc:
        _log(exc)
        return {}


def counts(state: Dict[str, ConceptState], today: Optional[str] = None) -> Dict[str, int]:
    """Numbers per level. independent = level 4 with one review passed; alone_once = level 4 without."""
    out = {"total": 0, "seen": 0, "understood": 0, "practiced": 0, "independent": 0, "alone_once": 0,
           "told_me": 0, "declined": 0, "rusty": 0}
    try:
        for cs in (state or {}).values():
            out["total"] += 1
            if cs.declined:
                out["declined"] += 1
            if cs.told_me:
                out["told_me"] += 1
            elif cs.level == 1:
                out["seen"] += 1
            elif cs.level == 2:
                out["understood"] += 1
            elif cs.level == 3:
                out["practiced"] += 1
            elif cs.level >= 4:
                out["independent" if cs.indep_passes > 0 else "alone_once"] += 1
            if today and rusty(cs, today):
                out["rusty"] += 1
    except Exception as exc:
        _log(exc)
    return out


def review_cap(days_since_first: int, away_days: int = 0) -> int:
    """Most reviews offered in one session: 3 after a break of more than 14 days, 1 in the first
    14 days of learning, otherwise 2 (SPEC 6.3)."""
    if away_days > AWAY_DAYS:
        return 3
    return 1 if days_since_first < 14 else 2


def _signals(last_signal: Optional[Dict[str, Any]]) -> Dict[str, str]:
    if last_signal is None:
        last_signal = _state_json().get("last_signal")
    out: Dict[str, str] = {}
    if isinstance(last_signal, dict):
        for k, v in last_signal.items():
            if isinstance(k, str) and isinstance(v, str) and _DATE_RE.match(v[:10]):
                out[k] = v[:10]
    return out


def due_items(state: Dict[str, ConceptState], today: str, limit: Optional[int] = None,
              last_signal: Optional[Dict[str, Any]] = None, plan_ids: Optional[Iterable[str]] = None,
              order: str = "normal") -> List[Dict[str, Any]]:
    """Reviews that may be offered today, best first.

    A review needs: Understood or higher, next_review reached, not retired, AND the project used the
    concept in the last 21 days (state.json last_signal). Other items are parked; nothing is said
    about them. A claim older than 7 days with no real evidence is a 'show-me' item under the same
    rule. order 'normal': lapsed first, then today's plan (plan_ids), then oldest due.
    order 'welcome': today's plan first, then lapsed, then oldest due.
    """
    out: List[Dict[str, Any]] = []
    try:
        sig = _signals(last_signal)
        plan = set(plan_ids or [])
        for cid, cs in (state or {}).items():
            kind, due_date = None, None
            if cs.level >= 2 and not cs.retired and cs.next_review and cs.next_review <= today:
                kind, due_date = "review", cs.next_review
            elif cs.claim_open and cs.claimed_date and _days(cs.claimed_date, today) >= CLAIM_SHOW_ME_DAYS:
                kind, due_date = "show-me", _add_days(cs.claimed_date, CLAIM_SHOW_ME_DAYS)
            if kind is None:
                continue
            seen = sig.get(cid)
            age = max(0, _days(seen, today)) if seen else 10 ** 6
            if age > RELEVANCE_DAYS:
                continue
            out.append({"id": cid, "kind": kind, "due": due_date, "lapsed": cs.lapsed,
                        "rusty": rusty(cs, today), "in_plan": cid in plan, "signal_age": age,
                        "overdue_days": max(0, _days(due_date, today))})
        if order == "welcome":
            out.sort(key=lambda r: (0 if r["in_plan"] else 1, 0 if r["lapsed"] else 1, r["signal_age"], r["due"], r["id"]))
        else:
            out.sort(key=lambda r: (0 if r["lapsed"] else 1, 0 if r["in_plan"] else 1, r["signal_age"], r["due"], r["id"]))
        return out[:limit] if limit is not None else out
    except Exception as exc:
        _log(exc)
        return []


def due(state: Dict[str, ConceptState], today: str, limit: Optional[int] = None, **kw: Any) -> List[str]:
    """Ids of the reviews that may be offered today (see due_items)."""
    return [r["id"] for r in due_items(state, today, limit, **kw)]


def warmup_items(state: Dict[str, ConceptState], today: str, away_days: int, plan_ids: Optional[Iterable[str]] = None,
                 limit: int = 3) -> List[str]:
    """Welcome-back warm-up (SPEC 6.3): at most 3 concepts at Understood or higher (or lapsed ones that a
    miss dropped to Seen), today's plan first, then lapsed, then the ones not seen for the longest time. The 21-day project rule does not apply
    (after a long break nothing was used recently)."""
    if away_days < AWAY_DAYS:
        return []
    try:
        plan = set(plan_ids or [])
        cands = [cs for cs in (state or {}).values()
                 if not cs.retired and (cs.level >= 2 or (cs.lapsed and cs.level >= 1))]
        cands.sort(key=lambda cs: (0 if cs.id in plan else 1, 0 if cs.lapsed else 1, cs.last_date or "", cs.id))
        return [cs.id for cs in cands[:limit]]
    except Exception as exc:
        _log(exc)
        return []


def verify_soon(state: Dict[str, ConceptState], signal_ids: Iterable[str]) -> List[str]:
    """Claimed concepts (not yet shown by real evidence) whose signal appears in the current work."""
    sig = set(signal_ids or [])
    return sorted(cid for cid, cs in (state or {}).items() if cs.claim_open and cid in sig)


def away_days(today: Optional[str] = None, last_session: Optional[str] = None) -> int:
    """Days since the last session. last_session defaults to state.json last_session_date, else the
    newest progress date. 0 when nothing is known."""
    try:
        today = today or _today()
        ls = last_session or _state_json().get("last_session_date")
        if not (isinstance(ls, str) and _DATE_RE.match(ls[:10])):
            dates = [e["date"] for e in load_events()]
            ls = max(dates) if dates else None
        return max(0, _days(ls, today)) if ls else 0
    except Exception:
        return 0


def _delegated_count(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, int):
        return value
    if isinstance(value, (list, tuple)):
        return len(set(str(x) for x in value))
    if isinstance(value, dict):
        for key in ("count", "n"):
            if isinstance(value.get(key), int):
                return value[key]
        dates = value.get("dates")
        if isinstance(dates, (list, tuple)):
            return len(set(str(x) for x in dates))
    return 0


def _title(cid: str, concepts: Dict[str, Any], cap: int = 40) -> str:
    row = concepts.get(cid) if isinstance(concepts, dict) else None
    if isinstance(row, dict) and row.get("title"):
        return str(row["title"])[:cap]
    try:
        try:
            from . import untrusted  # type: ignore
        except ImportError:
            import untrusted  # type: ignore
        return untrusted.neutralize(cid.replace("-", " "), cap)
    except Exception:
        return re.sub(r"[<>`\x00-\x1f]", " ", cid.replace("-", " "))[:cap]


def snapshot(profile: Any = None, today: Optional[str] = None, events: Optional[List[Dict[str, Any]]] = None,
             state: Optional[Dict[str, ConceptState]] = None, last_signal: Optional[Dict[str, Any]] = None,
             plan_ids: Optional[Iterable[str]] = None) -> Dict[str, Any]:
    """Compact dict for the session-start capsule. Titles, not ids, are for display; ids stay too.

    Fields: counts, practicing (Understood/Practiced, newest first, max 6), told_me (max 5), declined
    (declined twice or more, max 8 titles), declined_once, verify_soon (claimed concepts with a
    recent project signal), delegated (Claude ran it 2+ times, level up to Understood), rusty, due
    (eligible reviews, or the warm-up when away 14+ days), backlog (how many reviews are eligible in
    all; a number for the caller, never for the learner), away_days, last_session, welcome_back,
    review_cap, first_date, days_since_first, events.
    """
    empty = {"counts": counts({}), "practicing": [], "told_me": [], "declined": [], "declined_once": [],
             "verify_soon": [], "delegated": [], "rusty": [], "due": [], "away_days": 0, "last_session": None,
             "welcome_back": False, "review_cap": 1, "first_date": None, "days_since_first": 0, "events": 0,
             "backlog": 0}
    try:
        today = today or _today()
        concepts = _concepts()
        if events is None:
            events = load_events()
        if state is None:
            state = fold(events, concepts)
        sj = _state_json()
        sig = _signals(last_signal if last_signal is not None else sj.get("last_signal"))
        ls = sj.get("last_session_date") if isinstance(sj.get("last_session_date"), str) else None
        away = away_days(today, ls)
        first = min([e["date"] for e in events] or [today]) if events else None
        since = max(0, _days(first, today)) if first else 0
        teaching = ""
        if isinstance(profile, dict):
            teaching = str(profile.get("teaching") or "").strip().lower()

        def title(cid: str) -> str:
            return _title(cid, concepts)

        out = dict(empty)
        out["counts"] = counts(state, today)
        out["events"] = len(events)
        out["away_days"] = away
        out["last_session"] = ls[:10] if ls else None
        out["welcome_back"] = away >= AWAY_DAYS
        out["first_date"] = first
        out["days_since_first"] = since
        out["review_cap"] = review_cap(since, away)
        mid = [cs for cs in state.values() if cs.level in (2, 3)]
        mid.sort(key=lambda cs: (cs.last_date or "", cs.id), reverse=True)
        out["practicing"] = [{"id": cs.id, "title": title(cs.id), "level": cs.level, "label": cs.label}
                             for cs in mid[:6]]
        told = sorted((cs for cs in state.values() if cs.claim_open), key=lambda cs: (cs.claimed_date or "", cs.id), reverse=True)
        out["told_me"] = [{"id": cs.id, "title": title(cs.id)} for cs in told[:5]]
        out["declined"] = [title(cs.id) for cs in sorted(state.values(), key=lambda c: c.id) if cs.declined >= 2][:8]
        out["declined_once"] = [title(cs.id) for cs in sorted(state.values(), key=lambda c: c.id) if cs.declined == 1][:8]
        out["verify_soon"] = sorted(cid for cid, cs in state.items()
                                    if cs.claim_open and cid in sig and _days(sig[cid], today) <= RELEVANCE_DAYS)
        out["rusty"] = sorted(cs.id for cs in state.values() if rusty(cs, today))[:8]
        deleg = sj.get("delegated")
        if isinstance(deleg, dict):
            items = []
            for cid, v in deleg.items():
                n = _delegated_count(v)
                cs = state.get(cid)
                if n >= 2 and cs is not None and 1 <= cs.level <= 2:
                    items.append((n, cid, cs.level))
            items.sort(key=lambda t: (-t[0], t[1]))
            out["delegated"] = [{"id": cid, "title": title(cid), "count": n, "level": lvl} for n, cid, lvl in items[:6]]
        if teaching in ("off", "light"):
            out["due"] = []
        elif out["welcome_back"]:
            ids = warmup_items(state, today, away, plan_ids)
            out["due"] = [{"id": cid, "title": title(cid), "kind": "warm-up"} for cid in ids]
        else:
            every = due_items(state, today, None, sig, plan_ids)
            out["backlog"] = len(every)
            items = every[:out["review_cap"]]
            out["due"] = [{"id": r["id"], "title": title(r["id"]), "kind": r["kind"], "rusty": r["rusty"]} for r in items]
        return out
    except Exception as exc:
        _log(exc)
        return empty


# --------------------------------------------------------------------------- quotes

_QUOTE_MAP = {ord(c): "'" for c in "\u2018\u2019\u201a\u201b\u2032\u00b4\u0060"}
_QUOTE_MAP.update({ord(c): '"' for c in "\u201c\u201d\u201e\u201f\u2033\u00ab\u00bb"})
_QUOTE_MAP.update({ord(c): "-" for c in "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"})
_QUOTE_MAP[ord("\u2026")] = "..."
_QUESTION_ENDS = ("?", "\uff1f", "\u061f", "\u2047", "\u2048")
_SPACELESS_RANGES = ((0x3040, 0x30FF), (0x3400, 0x4DBF), (0x4E00, 0x9FFF), (0xF900, 0xFAFF),
                     (0x20000, 0x2FA1F), (0x0E00, 0x0EFF), (0x1780, 0x17FF), (0x1000, 0x109F), (0x0F00, 0x0FFF))


def _norm(text: Any) -> str:
    """Comparison form for "is this the learner's own sentence": NFKD with the Latin/Greek/Cyrillic
    accent marks removed (models often drop them when they copy Turkish or French text), no invisible
    format characters, case-folded, dotless i = i, straight quotes and dashes, one space between words.
    Only used to compare two texts that are both normalised this way."""
    t = unicodedata.normalize("NFKD", str(text))
    t = "".join(c for c in t if not ("̀" <= c <= "ͯ") and unicodedata.category(c) != "Cf")
    t = t.casefold().translate(_QUOTE_MAP).replace("ı", "i")
    return " ".join(t.split())


def _edge(ch: str) -> bool:
    return ch.isspace() or unicodedata.category(ch)[0] in "PS"


def _core(text: Any) -> str:
    """Normalised text without punctuation or quote marks at the two ends."""
    t = _norm(text)
    i, j = 0, len(t)
    while i < j and _edge(t[i]):
        i += 1
    while j > i and _edge(t[j - 1]):
        j -= 1
    return t[i:j]


def _spaceless(core: str) -> bool:
    letters = [c for c in core if c.isalnum()]
    if not letters:
        return False
    hits = sum(1 for c in letters if any(lo <= ord(c) <= hi for lo, hi in _SPACELESS_RANGES))
    return hits * 2 >= len(letters)


def _word_count(core: str) -> int:
    return sum(1 for w in core.split() if any(c.isalnum() for c in w))


def _is_filler(core: str) -> bool:
    toks = _tokens(core)
    if not toks:
        return True
    phrases = _filler_phrases()
    longest = max(len(p) for p in phrases) if phrases else 1
    ok = [False] * (len(toks) + 1)
    ok[len(toks)] = True
    for i in range(len(toks) - 1, -1, -1):
        for n in range(1, min(longest, len(toks) - i) + 1):
            if ok[i + n] and tuple(toks[i:i + n]) in phrases:
                ok[i] = True
                break
    return ok[0]


def _is_question(quote: str) -> bool:
    q = quote.rstrip()
    while q and q[-1] in "\"'\u201d\u2019\u00bb)]}*_` \t":
        q = q[:-1]
    return q.endswith(_QUESTION_ENDS)


def _prefixes() -> List[str]:
    got = _CACHE.get("sysprefix")
    if got is None:
        raw = _config_list("SYSTEM_PREFIXES")
        got = [p.lower() for p in raw] or ["<task-notification", "<scheduled-task", "<system-reminder",
                                           "<command-name", "<agent-message", "[subagent hand-back]"]
        _CACHE["sysprefix"] = got
    return got


def has_system_prefix(text: Any) -> bool:
    """True when text starts with a known machine prefix (<task-notification, [Subagent hand-back], ...)."""
    low = str(text).lstrip().lower()
    return any(low.startswith(p) for p in _prefixes())


def looks_like_system_text(text: Any) -> bool:
    """True for a whole message made by a machine: a known prefix, a tag such as <div or </x, a
    bracketed report, or a slash command. Used to filter saved messages; a quote taken from the
    middle of a real message is checked with has_system_prefix only."""
    try:
        try:
            from . import chatlog  # type: ignore
        except ImportError:
            import chatlog  # type: ignore
        if chatlog.is_system_text(str(text)):
            return True
    except Exception:
        pass
    t = str(text).lstrip()
    if has_system_prefix(t):
        return True
    if len(t) > 1 and t[0] == "<" and (t[1].isalpha() or t[1] == "/"):
        return True
    if len(t) > 1 and t[0] == "[" and t[1].isupper():
        return True
    return t.startswith("/")


def recent_prompts(n: int = 3) -> List[Dict[str, str]]:
    """The last n REAL learner messages, newest last: [{prompt_id, text}]. Source: state/recent-user.json."""
    out: List[Dict[str, str]] = []
    try:
        data = fsio.read_json(paths.sub("state", "recent-user.json"), None)
        if isinstance(data, dict):
            data = data.get("prompts")
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    pid = item.get("prompt_id")
                    out.append({"prompt_id": str(pid) if pid is not None else "", "text": item["text"]})
                elif isinstance(item, str):
                    out.append({"prompt_id": "", "text": item})
        elif data is None:
            try:
                try:
                    from . import chatlog  # type: ignore
                except ImportError:
                    import chatlog  # type: ignore
                out = [{"prompt_id": "", "text": t} for t in chatlog.recent_user(n) if isinstance(t, str)]
            except Exception:
                out = []
    except Exception:
        out = []
    real = [p for p in out if p["text"].strip() and not looks_like_system_text(p["text"])]
    return real[-n:]


def verify_quote(quote: Any, event: str, open_check_recent: bool = True,
                 prompts: Optional[List[str]] = None) -> Tuple[bool, str]:
    """Is this quote usable as proof for this event? Returns (ok, reason); reason is "" when ok.

    Rules (SPEC 6.2): normalised substring of one of the last 3 real learner messages (each at most
    1,200 characters); at least 12 characters and 3 words (8 characters for scripts written without
    spaces); not only a filler such as "ok" or "tamam anladim"; not a question; no '[hidden:' marker;
    not system text. A `learned` quote with no open check shown in the last 3 messages needs 20
    characters and 5 words and must not start with a question word. For missed and declined only the
    authenticity rules apply (the words are optional). Pass prompts to test; otherwise the saved
    messages are read.
    """
    try:
        if not isinstance(quote, str) or not quote.strip():
            return False, "no words from the learner were given"
        quote = quote.strip()
        if "[hidden:" in quote.lower():
            return False, "the words contain a hidden-secret marker, so they cannot be proof"
        if has_system_prefix(quote):
            return False, "the words look like system text, not the learner's own words"
        relaxed = event in ("missed", "declined")
        core = _core(quote)
        if not core:
            return False, "the words are empty after removing punctuation"
        if not relaxed:
            if _is_question(quote):
                return False, "the words are a question; a question is not proof of understanding"
            spaceless = _spaceless(core)
            need_c, need_w = (MIN_CHARS_SPACELESS, 0) if spaceless else (MIN_CHARS, MIN_WORDS)
            if event == "learned" and not open_check_recent:
                need_c, need_w = ((UNPROMPTED_CHARS_SPACELESS, 0) if spaceless
                                  else (UNPROMPTED_CHARS, UNPROMPTED_WORDS))
            if len(unicodedata.normalize("NFC", core)) < need_c or (need_w and _word_count(core) < need_w):
                if spaceless:
                    return False, "the words are too short (need at least %d characters)" % need_c
                return False, "the words are too short (need at least %d characters and %d words)" % (need_c, need_w)
            if _is_filler(core):
                return False, "the words are only a filler such as 'ok' or 'thanks'"
            if event == "learned" and not open_check_recent:
                toks = _tokens(core)
                if any(tuple(toks[:len(q)]) == q for q in _question_starts()):
                    return False, "the words start like a question and no check was open; ask a check first"
        if prompts is None:
            prompts = [p["text"] for p in recent_prompts(3)]
        prompts = [p for p in prompts if isinstance(p, str) and not looks_like_system_text(p)][-3:]
        if not prompts:
            return False, "no saved learner message to compare with"
        found_long = False
        for p in prompts:
            if core in _norm(p):
                if len(p) <= MAX_PROMPT_CHARS:
                    return True, ""
                found_long = True
        if found_long:
            return False, "the words come from a message longer than %d characters; ask for a short answer in the learner's own words" % MAX_PROMPT_CHARS
        return False, "the words are not in the learner's last 3 messages"
    except Exception as exc:
        _log(exc)
        return False, "the words could not be checked"


def _open_check_recent(prompts: List[Dict[str, str]]) -> bool:
    """Was a marked check shown in an answer given to one of the last 3 learner messages (the answer
    to the newest message does not exist yet)? Reads the ledger rows (check_marker, prompt_id) and the
    open_check slot in state.json; true if either says so. `prompts` holds the newest 4 messages."""
    try:
        st = _state_json()
        if st.get("open_check"):
            return True
        rows = fsio.jsonl_read(paths.sub("state", "ledger.jsonl"), 6) or []
        ids = [p["prompt_id"] for p in prompts[-4:-1] if p["prompt_id"]]
        recent = rows[-3:]
        for r in rows:
            if isinstance(r, dict) and r.get("check_marker") and not r.get("fishing"):
                pid = r.get("prompt_id")
                if (pid and str(pid) in ids) or (not pid and r in recent):
                    return True
    except Exception:
        pass
    return False


# --------------------------------------------------------------------------- names (things)

def _slug(text: str) -> str:
    t = re.sub(r"[\W_]+", "-", _afold(text), flags=re.UNICODE).strip("-")
    return t[:40].strip("-")


def resolve_thing(text: str) -> Tuple[Optional[str], str, bool, str]:
    """What did the model mean? Returns (id, title, is_custom, problem).

    A concept id, title or term resolves to that concept. Anything else becomes a custom slug
    (at most 3 words, 40 characters). Windows reserved names are rejected (problem is set).
    """
    text = " ".join(str(text or "").split())
    if not text:
        return None, "", False, "the line names no concept"
    k = _knowledge()
    try:
        cid = k.resolve(text) if k else None
    except Exception:
        cid = None
    if cid:
        return cid, k.title_of(cid), False, ""
    if len(text.split()) > 3:
        return None, "", True, "a thing must be a concept id or at most 3 words"
    slug = _slug(text)
    if not slug:
        return None, "", True, "the name has no usable letters"
    if slug in _RESERVED or text.lower().split(".")[0] in _RESERVED:
        return None, "", True, "the name '%s' is reserved by Windows; use another word" % slug
    return slug, _safe(text), True, ""     # the stored title is neutralised (no brackets, no instructions)


# --------------------------------------------------------------------------- writing rows

def _append_row(row: Dict[str, Any]) -> bool:
    """Append one row to progress.jsonl (caller holds the lock). U+2028/2029/0085 never split a row."""
    try:
        clean = {k: (v.replace("\u2028", " ").replace("\u2029", " ").replace("\u0085", " ") if isinstance(v, str) else v)
                 for k, v in row.items()}
        return fsio.jsonl_append(progress_path(), clean) is not False
    except Exception as exc:
        _log(exc)
        return False


def make_row(cid: str, event: str, quote: str = "", src: str = "inbox", date: Optional[str] = None,
             ts: Optional[str] = None, **extra: Any) -> Dict[str, Any]:
    row: Dict[str, Any] = {"ts": ts or _stamp(), "date": date or _today(), "id": cid, "event": event,
                           "quote": (quote or "")[:MAX_QUOTE_STORED], "src": src}
    for k, v in extra.items():
        if v not in (None, "", False):
            row[k] = v
    return row


def record_event(cid: str, event: str, quote: str = "", src: str = "hook", once: bool = False, **extra: Any) -> bool:
    """Hook-written events (the Stop hook records `met`). once=True skips a concept that already has
    any event. Returns True if a row was appended. Never raises."""
    try:
        cid = str(cid or "").strip()[:60]
        if event not in EVENTS or not cid:
            return False
        with _lock("learner"):
            if once:
                if any(e["id"] == cid and e["event"] != "forget" for e in load_events()):
                    return False
            return _append_row(make_row(cid, event, quote, src, **extra))
    except Exception as exc:
        _log(exc)
        return False


# --------------------------------------------------------------------------- reading the inbox

def _decode(raw: bytes) -> Optional[str]:
    """utf-8-sig, then UTF-16 with a BOM, then cp1252 (replacing). None for text with NUL bytes."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
            text = raw.decode("utf-16", "replace")
        else:
            text = raw.decode("cp1252", "replace")
    if "\x00" in text:
        return None
    return text


def _strip_comments(text: str) -> str:
    """Remove <!-- ... --> blocks. An unclosed comment hides the rest of the file. Linear time."""
    out = []
    i = 0
    while True:
        j = text.find("<!--", i)
        if j < 0:
            out.append(text[i:])
            break
        out.append(text[i:j])
        k = text.find("-->", j + 4)
        if k < 0:
            break
        i = k + 3
    return "".join(out)


def _split_lines(text: str) -> List[str]:
    out = []
    for line in re.split(r"\r\n|\r|\n|\u2028|\u2029|\u0085", text):
        line = line.strip()
        line = re.sub(r"^(?:[-*+>]\s+|\d+[.)]\s+)", "", line)
        if line and not line.startswith("#"):
            out.append(line)
    return out


def _parse_line(line: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """'<event> <thing> | <words> [| sure] [| misc:<id>]' -> dict, or (None, reason)."""
    head, sep, tail = line.partition("|")
    toks = head.strip().split(None, 1)
    if not toks:
        return None, "the line is empty"
    event = toks[0].lower().rstrip(":")
    if event == "met":
        return None, "the event 'met' is written by hooks only"
    if event not in INBOX_EVENTS:
        return None, "unknown event '%s' (use learned, did, alone, reviewed, claimed, missed, declined or forget)" % event[:20]
    thing = toks[1].strip() if len(toks) > 1 else ""
    if not thing:
        return None, "the line has no concept name"
    quote, sure, misc = "", False, ""
    if sep:
        parts = [p.strip() for p in tail.split("|")]
        if event == "missed":     # optional trailing fields: | sure   | misc:<id>
            while parts and (parts[-1].lower() == "sure" or parts[-1].lower().startswith("misc:")):
                last = parts.pop().lower()
                if last == "sure":
                    sure = True
                else:
                    misc = _slug(last[5:])
        quote = "|".join(parts).strip()
    elif event in NEEDS_QUOTE:
        return None, "the line needs '| <the learner's exact words>'"
    return {"event": event, "thing": thing, "quote": quote, "sure": sure, "misc": misc}, ""


def _inside(path: str, folder: str) -> bool:
    a, b = os.path.normcase(os.path.realpath(path)), os.path.normcase(os.path.realpath(folder))
    return a != b and a.startswith(b.rstrip("\\/") + os.sep)


def _read_inbox_file(entry: "os.DirEntry", inbox_real: str) -> Tuple[Optional[str], str]:
    """Read one inbox file safely. Returns (text, "") or (None, problem)."""
    path = entry.path
    try:
        if entry.is_symlink() or not entry.is_file(follow_symlinks=False):
            return None, "not a plain file"
        if not _inside(path, inbox_real):
            return None, "the file is not inside the inbox folder"
        lst = os.lstat(path)
        if not stat.S_ISREG(lst.st_mode) or lst.st_nlink > 1:
            return None, "not a plain file"
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        try:
            fst = os.fstat(fd)
            if not stat.S_ISREG(fst.st_mode) or fst.st_nlink > 1:
                return None, "not a plain file"
            raw = os.read(fd, MAX_FILE_BYTES + 1)
        finally:
            os.close(fd)
    except OSError:
        return None, "the file could not be read"
    if len(raw) > MAX_FILE_BYTES:
        return None, "the file is longer than %d KB; write one to six short lines" % (MAX_FILE_BYTES // 1024)
    text = _decode(raw)
    if text is None:
        return None, "the file is not UTF-8 text (save it as UTF-8)"
    return text, ""


def _remove(path: str) -> None:
    """Delete a consumed inbox file; retry briefly (a virus scanner may hold it). Never raises."""
    for _ in range(3):
        try:
            os.unlink(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            time.sleep(0.05)


def _first_session(st: Dict[str, Any], events: List[Dict[str, Any]], today: str) -> bool:
    n = st.get("session_count")
    if isinstance(n, int) and not isinstance(n, bool):
        return n <= 1
    return not any(e["date"] < today for e in events)


def _prompt_key(prompts: List[Dict[str, str]]) -> str:
    if not prompts:
        return "none"
    last = prompts[-1]
    return last["prompt_id"] or ("t:%d:%s" % (len(last["text"]), _norm(last["text"])[:40]))


def _forget_ok(message: Any, names: Iterable[Any]) -> bool:
    """A forget line needs the learner's own words: a removal word in the learner's last message, or the
    name of the thing in that message. Text in a file that asks for a removal does not count. Fails closed."""
    try:
        toks = _tokens(str(message or ""))
        if any(_FORGET_RE.match(t) for t in toks):
            return True
        padded = " %s " % " ".join(toks)
        for name in names:
            words = _tokens(str(name or ""))
            if words and (" %s " % " ".join(words)) in padded:
                return True
    except Exception as exc:  # noqa: BLE001 - a check that fails must refuse, not accept
        _log(exc)
    return False


def process_inbox(prompts: Optional[List[str]] = None, open_check_recent: Optional[bool] = None,
                  first_session: Optional[bool] = None, today: Optional[str] = None) -> List[str]:
    """Turn the files in inbox/ into progress rows. Returns the lines for the model (PostToolUse
    additionalContext): `Saved: <title> (<event>)` and `Refused: <reason>. The file was deleted; ...`.

    The tool-supplied path is never used: this lists inbox/*.md itself. Parameters exist for tests.
    """
    try:
        return _process_inbox(prompts, open_check_recent, first_session, today)
    except Exception as exc:
        _log(exc)
        return ["Inbox not processed because of an internal error. Nothing was recorded; tell the user."]


def _process_inbox(prompts_in: Optional[List[str]], open_check: Optional[bool],
                   first_session: Optional[bool], today: Optional[str]) -> List[str]:
    inbox, data = paths.sub("inbox"), paths.data_dir()
    if not os.path.lexists(inbox):
        return []
    wanted = os.path.normcase(os.path.join(os.path.realpath(data), "inbox"))
    if (paths.has_link_in_chain(inbox, paths.project_root()) or not os.path.isdir(inbox)
            or os.path.normcase(os.path.realpath(inbox)) != wanted):
        return ["Inbox not read: the inbox folder is a link or is not a normal folder. Nothing was recorded; tell the user."]
    inbox_real = os.path.realpath(inbox)
    try:
        entries = sorted((e for e in os.scandir(inbox)
                          if e.name.lower().endswith(".md") and (e.is_symlink() or not e.is_dir(follow_symlinks=False))),
                         key=lambda e: e.name)
    except OSError:
        return []
    if not entries:
        return []
    today = today or _today()
    messages: List[str] = []
    with _lock("learner"):
        st = _state_json()
        events = load_events()
        state = fold(events)
        if prompts_in is None:
            plist4 = recent_prompts(4)      # the 4th newest only helps to see a check asked before the 3rd
        else:
            plist4 = [{"prompt_id": "", "text": t} for t in prompts_in]
        plist = plist4[-3:]
        texts = [p["text"] for p in plist]
        if open_check is None:
            open_check = _open_check_recent(plist4)
        first = _first_session(st, events, today) if first_session is None else first_session
        row_cap = ROWS_FIRST_SESSION if first else ROWS_PER_MESSAGE
        key = _prompt_key(plist)
        turn = st.get("inbox_turn") if isinstance(st.get("inbox_turn"), dict) else {}
        if turn.get("key") != key:
            turn = {"key": key, "rows": 0, "refused": 0}
        recent_rows = {(e["id"], e["event"], _core(e.get("quote") or ""), e["date"]) for e in events[-200:]}
        day_done = {(e["id"], e["event"]) for e in events[-200:] if e.get("date") == today}
        changed = False
        for entry in entries[:MAX_FILES_PER_CALL]:
            path = entry.path
            if turn["refused"] >= STOP_AFTER_REFUSALS:
                messages.append(STOP_MESSAGE)
                if entry.is_symlink():
                    _remove(path)
                elif entry.is_file(follow_symlinks=False):
                    _remove(path)
                continue
            text, problem = _read_inbox_file(entry, inbox_real)
            if text is None:
                if problem == "the file could not be read":     # a scanner may hold it; keep it for the next call
                    messages.append("An inbox file could not be read yet. Nothing was recorded for it; write it again if it does not clear.")
                    continue
                turn["refused"] += 1
                changed = True
                messages.append("Refused: %s. %s" % (problem, RETRY_TEXT))
                _remove(path)
                continue
            lines = _split_lines(_strip_comments(text))
            reasons: List[str] = []
            if not lines:
                reasons.append("the file has no entry lines")
            elif len(lines) > MAX_LINES:
                reasons.append("the file has more than %d lines" % MAX_LINES)
                lines = []
            for n, line in enumerate(lines, 1):
                parsed, why = _parse_line(line)
                if parsed is None:
                    reasons.append("line %d: %s" % (n, why))
                    continue
                event = parsed["event"]
                cid, title, custom, problem = resolve_thing(parsed["thing"])
                if cid is None:
                    reasons.append("line %d: %s" % (n, problem))
                    continue
                if turn["rows"] >= row_cap:
                    reasons.append("line %d: at most %d entries per learner message (%d in the first session)"
                                   % (n, ROWS_PER_MESSAGE, ROWS_FIRST_SESSION))
                    continue
                quote = parsed["quote"]
                if event == "forget":
                    if cid not in state:
                        messages.append("Nothing to remove: %s is not on the list." % _safe(title))
                        continue
                    if not _forget_ok(texts[-1] if texts else "", (parsed["thing"], title, cid.replace("-", " "))):
                        reasons.append("line %d: a forget line needs the learner's own words in the last message "
                                       "(a word such as forget, or the name of the thing)" % n)
                        continue
                    quote = ""
                elif quote or event in NEEDS_QUOTE:
                    ok, why = verify_quote(quote, event, bool(open_check), texts)
                    if not ok:
                        reasons.append("line %d: %s" % (n, why))
                        continue
                    quote = _unwrap(quote)
                    if event in ("missed", "declined") and len(_core(quote)) < 4:
                        quote = ""          # a one-letter "quote" proves nothing; keep the event without words
                sig = (cid, event, _core(quote), today)
                if sig in recent_rows:
                    messages.append("Already on the list: %s (%s)." % (_safe(title), event))
                    continue
                extra: Dict[str, Any] = {}
                if event == "missed":
                    extra["sure"] = parsed["sure"] or None
                    extra["misc"] = parsed["misc"] or None
                if custom:
                    extra["title"] = title
                if event in ("did", "alone") and (cid, event) in day_done:
                    extra["repeat"] = True      # kept, but one practice counts per day
                if _append_row(make_row(cid, event, quote, "inbox", date=today, **extra)):
                    recent_rows.add(sig)
                    day_done.add((cid, event))
                    turn["rows"] += 1
                    changed = True
                    messages.append("Saved: %s (%s)" % (_safe(title), event))
                    state = fold(load_events())     # later lines of this file see this row
                else:
                    reasons.append("line %d: the row could not be written" % n)
            if reasons:
                turn["refused"] += 1
                changed = True
                messages.append("Refused: %s. %s" % ("; ".join(reasons), RETRY_TEXT))
            _remove(path)
        if changed or st.get("inbox_turn") != turn:
            def put(data: Any) -> Any:      # only our own key: other hooks keep theirs
                if not isinstance(data, dict):
                    data = {}
                data["inbox_turn"] = turn
                return data
            try:
                fsio.update_json(_state_path(), put, {})
            except Exception as exc:
                _log(exc)
    return messages


def _unwrap(quote: str) -> str:
    q = quote.strip()
    pairs = {'"': '"', "'": "'", "\u201c": "\u201d", "\u2018": "\u2019", "\u00ab": "\u00bb"}
    if len(q) > 2 and q[0] in pairs and q[-1] == pairs[q[0]]:
        q = q[1:-1].strip()
    return q


def _safe(title: str) -> str:
    try:
        try:
            from . import untrusted  # type: ignore
        except ImportError:
            import untrusted  # type: ignore
        return untrusted.neutralize(title, 40)
    except Exception:
        return re.sub(r"[<>`\x00-\x1f]", " ", str(title))[:40]


# --------------------------------------------------------------------------- text-only notes

_NOTE_EVENTS = INBOX_EVENTS + ("met",)


def import_notes() -> Dict[str, int]:
    """Text-only mode (SPEC 6.9): move learner/notes.md lines into progress.jsonl with src 'notes'
    (unverified; such rows stop at Understood), then rename notes.md to notes.imported.md.

    Line format: `YYYY-MM-DD | event | concept id or title | "exact words"`. The words are kept only when
    verify_quote accepts them against the saved learner messages; otherwise the event is kept without words.
    A forget line needs a removal word or the thing's name in the learner's last saved message.
    Safe to run twice: a second run finds no notes.md, and rows already imported are not added again.
    Returns {"imported": n, "skipped": n, "renamed": 0 or 1}.
    """
    result = {"imported": 0, "skipped": 0, "renamed": 0}
    try:
        src = paths.sub("learner", "notes.md")
        if not os.path.isfile(src) or paths.is_link(src):
            return result
        try:
            with open(src, "rb") as fh:
                raw = fh.read(MAX_NOTES_BYTES + 1)
        except OSError:
            return result
        text = _decode(raw[:MAX_NOTES_BYTES])
        if text is None:
            result["skipped"] += 1
            return result
        today = _today()
        saved = recent_prompts(3)
        last_words = saved[-1]["text"] if saved else ""     # the learner's last message, for a forget line
        with _lock("learner"):
            existing = {(e["id"], e["event"], e["date"], _core(e.get("quote") or ""))
                        for e in load_events() if e.get("src") == "notes"}
            for line in _split_lines(_strip_comments(text)):
                parts = [p.strip() for p in line.split("|", 3)]
                if len(parts) < 3 or not _DATE_RE.match(parts[0]):
                    result["skipped"] += 1
                    continue
                date, event = parts[0], parts[1].lower().rstrip(":")
                d = _date(date)
                if event not in _NOTE_EVENTS or d is None or _days(today, date) > 1:
                    result["skipped"] += 1
                    continue
                cid, title, custom, problem = resolve_thing(parts[2])
                if cid is None:
                    result["skipped"] += 1
                    continue
                if event == "forget" and not _forget_ok(last_words, (parts[2], title, cid.replace("-", " "))):
                    result["skipped"] += 1
                    continue
                quote = _unwrap(parts[3]) if len(parts) > 3 else ""
                if quote:
                    quote = _redact(quote)
                # A quote is kept only when it is the learner's own words in a saved message (verify_quote).
                # Otherwise the event stays and the words go: a notes file can be written by the model.
                if event == "forget" or (quote and not verify_quote(quote, event, False)[0]):
                    quote = ""
                sig = (cid, event, date, _core(quote))
                if sig in existing:
                    continue
                extra = {"title": title} if custom else {}
                if _append_row(make_row(cid, event, quote, "notes", date=date, ts=date + "T00:00:00", **extra)):
                    existing.add(sig)
                    result["imported"] += 1
                else:
                    result["skipped"] += 1
            result["renamed"] = _retire_notes(src)
    except Exception as exc:
        _log(exc)
    return result


def _redact(text: str) -> str:
    try:
        try:
            from . import secrets as _secrets  # type: ignore
        except ImportError:
            import secrets as _secrets  # type: ignore
        return _secrets.redact(text)
    except Exception:
        return text


def _retire_notes(src: str) -> int:
    """Rename notes.md to notes.imported.md; if that exists already, append and remove notes.md."""
    dst = paths.sub("learner", "notes.imported.md")
    try:
        if os.path.lexists(dst) and paths.is_link(dst):
            return 0
        if not os.path.exists(dst):
            os.replace(src, dst)
            return 1
        old = fsio.read_text(src, "")
        fsio.append_text(dst, "\n" + old)
        os.unlink(src)
        return 1
    except Exception as exc:
        _log(exc)
        return 0
