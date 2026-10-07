"""ledger.py - measure each final answer of the model and turn the last rows into short notices.

What: analyse_answer(text, glossary, profile, activity) -> row (SPEC 6.5) and notices(rows, profile,
last_prompt_id) -> list of fact lines; outcomes(rows, profile) for the doctor.
Why: a teaching rule written once fades; a measured fact re-stated at the next message does not.
The row says how many words the result had, whether a real check was asked, which jargon terms
were explained, how long the sentences were and which banned words appeared. Everything is
computed by simple, language-neutral rules; the model judges what to do with a notice.
How it fails safely: analyse_answer never raises (an unreadable answer gives a row of zeros) and
never stores the answer text, only counts, term names and one clipped check line.
Who calls it: the Stop hook (analyse_answer) and the UserPromptSubmit hook (notices).
"""
from __future__ import annotations

import re
import sys
import unicodedata
from typing import Any, Dict, Iterable, List, Optional

from . import activity as activity_mod
from . import clock, config, text as textlib, untrusted

sys.dont_write_bytecode = True

_SENT = re.compile(r"[^\n]+?(?:[.!?…。]+(?=\s|$)|$)")
_STRIP_MD = re.compile(r"^[\s>\-*+#•]*(?:\d{1,3}[.)]\s+)?[*_`]*")
# A gloss: a bracket or dash, "=", "means", "stands for", "refers to" or a copula that starts a definition,
# within 160 characters after the term; a colon only close to it (within 30).
_GLOSS_PATTERN = re.compile(
    r"\(|\u2014|\u2013| - | = | means | stands for | refers to |\b(?:is|are) (?:a|an|the|one|when|what|where|how|used|short)\b",
    re.IGNORECASE)
_GLOSS_COLON = re.compile(r":")
# A term that the same sentence defines (see _defined_here).
_DEF_AFTER = re.compile(r"[\s`'\"*_)]*(?:(?:stores?|holds?|keeps?|means?|represents?|lets?|saves?|tracks?|returns?|marks?|gives?)\b"
                        r"|for (?:a|an|the|one|each|every)\b|,\s*(?:the|a|an)\b)", re.IGNORECASE)
_DEF_BEFORE = re.compile(r"\b(?:is|are|was|were)\s+(?:a|an|the|one)\s+(?:[\w\-]+\s+){0,3}$", re.IGNORECASE)
_DEF_TAIL = re.compile(r"[\s`'\"*_)]*(?:[.!?;:,]|$|(?:that|which|who|used|for|to|with|where|when|of|in|on)\b)", re.IGNORECASE)
# The Turkish verb git (go) is the Git term only as a command: git status, a line that starts with it.
_GIT_SUB = re.compile(r"\s*(?:status|add|commit|push|pull|init|clone|log|diff|branch|checkout|switch|merge|rebase|"
                      r"reset|restore|stash|remote|config|show|tag|fetch)\b")
_EN_STOP = frozenset("the and is to of a in you that it for with this on are be as at your we can an if so or not".split())
_REVIEW_FIELDS = ("words", "result_words", "work_size", "check_marker", "fishing", "offer_line", "glossed",
                  "unexplained", "avg_sentence_words", "max_sentence_words", "banned_hits", "level_cap")


# --------------------------------------------------------------------------- small helpers

def _fold(s: str) -> str:
    return textlib.fold(s)


def _label_table() -> Dict[str, List[str]]:
    """Folded labels without spaces, per kind, over all languages."""
    out: Dict[str, List[str]] = {"check": [], "offer": [], "card": []}
    for lang in config.LANGS:
        entry = config.LABELS.get(lang, {})
        for lab in entry.get("check", []):
            out["check"].append(re.sub(r"\s+", "", _fold(lab)))
        out["offer"].append(re.sub(r"\s+", "", _fold(entry.get("offer", ""))))
        for lab in entry.get("card", []):
            out["card"].append(re.sub(r"\s+", "", _fold(lab)))
    return {k: [v for v in vals if v] for k, vals in out.items()}


_LABELS_CACHE: Dict[str, List[str]] = {}


def label_kind(line: str) -> str:
    """'check' | 'offer' | 'card' | '' for a line that starts with a known label (any language)."""
    if not _LABELS_CACHE:
        _LABELS_CACHE.update(_label_table())
    head = re.sub(r"\s+", "", _fold(_STRIP_MD.sub("", line.strip(), count=1)))[:60]
    head = head.lstrip("*_`")
    for kind in ("check", "offer", "card"):
        for lab in _LABELS_CACHE[kind]:
            if head.startswith(lab):
                return kind
    return ""


def _is_english(text: str, profile: Optional[Dict[str, Any]]) -> bool:
    lang = str((profile or {}).get("language") or "").strip()
    if lang:
        return config.language_code(lang) == "en"
    words = re.findall(r"[a-zA-Z']+", text.lower())
    total = len(re.findall(r"\w+", text))
    if total < 8:
        return True
    return sum(1 for w in words if w in _EN_STOP) / float(total) >= 0.12


def _fishing(text: str) -> bool:
    folded = _fold(text)
    for lang in config.LANGS:
        for src in config.FISHING.get(lang, []):
            try:
                if re.search(src, folded):
                    return True
            except re.error:
                continue
    return False


def _word_re(phrase: str) -> "re.Pattern[str]":
    return re.compile(r"(?<![^\W_])" + re.escape(phrase) + r"(?![^\W_])")


_BANNED_CACHE: List[Any] = []


def banned_in(text: str) -> List[str]:
    """Banned words found in the text (distinct, in order of first use)."""
    if not _BANNED_CACHE:
        for phrase in config.all_of(config.BANNED):
            folded = _fold(phrase)
            if folded:
                _BANNED_CACHE.append((phrase, _word_re(folded)))
    folded_text = _fold(text)
    found: List[tuple] = []
    for phrase, rx in _BANNED_CACHE:
        m = rx.search(folded_text)
        if m:
            found.append((m.start(), phrase))
    found.sort()
    out: List[str] = []
    for _, phrase in found:
        if phrase not in out:
            out.append(phrase)
    return out[:10]


def banned_count(text: str) -> int:
    if not _BANNED_CACHE:
        banned_in("")
    folded_text = _fold(text)
    return sum(len(rx.findall(folded_text)) for _, rx in _BANNED_CACHE)


def _decision(sentence: str) -> bool:
    folded = _fold(sentence)
    for phrase in config.all_of(config.DECISION):
        if _fold(phrase) in folded:
            return True
    return False


# --------------------------------------------------------------------------- the row

def _terms(prose: str, glossary: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Jargon entries for the prose. A term whose first match sits inside a file name (index.html) is
    searched again after that place, because find_terms reports each term once."""
    if glossary is not None:
        return [g for g in glossary if isinstance(g, dict) and "start" in g and "end" in g]
    try:
        from . import knowledge
        found = knowledge.find_terms(prose)
        out: List[Dict[str, Any]] = []
        for entry in found:
            cur, offset = entry, 0
            for _ in range(4):
                if not _in_file_name(prose, int(cur["start"]) + offset, int(cur["end"]) + offset):
                    break
                tail_start = int(cur["end"]) + offset
                key = cur.get("id") or cur.get("term")
                nxt = [x for x in knowledge.find_terms(prose[tail_start:]) if (x.get("id") or x.get("term")) == key]
                if not nxt:
                    cur = None
                    break
                offset = tail_start
                cur = nxt[0]
            if cur is not None:
                shifted = dict(cur)
                shifted["start"], shifted["end"] = int(cur["start"]) + offset, int(cur["end"]) + offset
                out.append(shifted)
        return sorted(out, key=lambda e: e["start"])
    except Exception:
        return []


def _in_file_name(prose: str, start: int, end: int) -> bool:
    """True when the matched word is one part of a file name (index.html) or of a path (docs/decisions)."""
    if re.match(r"\.[A-Za-z0-9]", prose[end:end + 2]):
        return True
    if start >= 2 and prose[start - 1] in "./\\" and prose[start - 2].isalnum():
        return True
    return (end < len(prose) and prose[end] in "/\\") or (start > 0 and prose[start - 1] in "/\\")


def _defined_here(prose: str, start: int, end: int, lo: int, hi: int) -> bool:
    """True when the same sentence (prose[lo:hi]) defines the term: 'X stores ...', 'X for a whole number',
    'X, the ...' (the term is the subject), or 'X is a TERM that ...' / 'A save point is a Git TERM.' (the
    term is the thing named)."""
    following = prose[end:hi]
    if _DEF_AFTER.match(following):
        return True
    return bool(_DEF_BEFORE.search(prose[lo:start]) and _DEF_TAIL.match(following))


def _tr_verb_git(prose: str, start: int, end: int, tr_learner: bool) -> bool:
    """True for the Turkish verb 'git' (go) in Turkish text: a lower-case word that is not a command and is
    not followed by a Turkish suffix after an apostrophe. Written Git or GitHub, or a command, still counts."""
    if not tr_learner or prose[start:end] != "git":
        return False
    before = prose[:start].rstrip(" ")
    if before == "" or before[-1] in "`$>\n" or _GIT_SUB.match(prose, end):
        return False
    return prose[end:end + 1] != "'"


def _level_of(state: Any, cid: str) -> int:
    try:
        cs = state.get(cid) if state else None
        if cs is None:
            return 0
        return int(cs.get("level", 0) if isinstance(cs, dict) else getattr(cs, "level", 0))
    except Exception:
        return 0


def analyse_answer(text: str, glossary: Optional[List[Dict[str, Any]]] = None, profile: Optional[Dict[str, Any]] = None,
                   activity: Optional[List[Dict[str, Any]]] = None, state: Any = None,
                   skip_terms: Optional[Iterable[str]] = None, session: str = "", prompt_id: str = "") -> Dict[str, Any]:
    """The ledger row for one final answer. glossary: jargon entries as returned by
    knowledge.find_terms (looked up when None). state: learner.fold() result (a term whose concept is
    Understood needs no gloss). skip_terms: term keys already glossed this session."""
    profile = profile or {}
    limits = config.level_limits(profile.get("level"), profile.get("answer_words"))
    row: Dict[str, Any] = {
        "ts": clock.stamp(), "session": str(session)[:40], "prompt_id": str(prompt_id)[:60],
        "words": 0, "result_words": 0, "work_size": "none", "check_marker": False, "check_count": 0, "check_text": "",
        "fishing": False, "offer_line": False, "ends_q": False, "glossed": [], "glossed_ids": [], "glossed_keys": [], "unexplained": [],
        "avg_sentence_words": 0.0, "max_sentence_words": 0, "banned_hits": 0, "banned": [],
        "level_cap": limits["result_words"], "sentence_cap": limits["sentence_words"],
    }
    try:
        row["work_size"] = activity_mod.work_size(activity)
        if not isinstance(text, str) or not text.strip():
            return row
        prose = unicodedata.normalize("NFC", textlib.strip_code(text))
        lines = prose.split("\n")
        starts: List[int] = []
        pos = 0
        for ln in lines:
            starts.append(pos)
            pos += len(ln) + 1
        kinds = [label_kind(ln) for ln in lines]

        # label lines
        checks = [i for i, k in enumerate(kinds) if k == "check"]
        row["check_marker"] = bool(checks)
        row["check_count"] = len(checks)
        if checks:
            row["check_text"] = textlib.clip(" ".join(lines[checks[0]].split()), 200)
        row["offer_line"] = "offer" in kinds
        tail_lines = [ln for ln in lines if ln.strip()]
        row["ends_q"] = bool(tail_lines) and tail_lines[-1].rstrip().endswith(("?", "？"))

        # fishing: the marked check line, or a closing question of the answer
        if checks:
            row["fishing"] = _fishing(lines[checks[0]])
        else:
            tail = [ln for ln in lines if ln.strip()][-2:]
            tail_text = " ".join(tail)
            row["fishing"] = bool(tail) and tail_text.rstrip().endswith(("?", "？")) and _fishing(tail_text)

        # sentence spans (never across a line end), tagged by line kind
        spans: List[List[Any]] = []
        for i, ln in enumerate(lines):
            for m in _SENT.finditer(ln):
                if m.group().strip():
                    spans.append([starts[i] + m.start(), starts[i] + m.end(), i, ""])

        def span_of(offset: int) -> Optional[List[Any]]:
            for sp in spans:
                if sp[0] <= offset < sp[1]:
                    return sp
            return None

        # jargon: explained or not
        english = _is_english(prose, profile)
        lang = str(profile.get("language") or "").strip()
        tr_learner = config.language_code(lang) == "tr" if lang else not english
        skip = set(skip_terms or [])
        for entry in _terms(prose, glossary):
            cid = entry.get("id") or ""
            key = cid or ("g:" + str(entry.get("term", "")).lower())
            if key in skip or (cid and _level_of(state, cid) >= 2):
                continue
            start, end = int(entry["start"]), int(entry["end"])
            sp = span_of(start)
            if _in_file_name(prose, start, end) or (sp is not None and kinds[sp[2]] in ("offer", "card")):
                continue   # 'index' in index.html, or a topic named in the offer line, is not a first use
            if _tr_verb_git(prose, start, end, tr_learner):
                continue   # the Turkish verb git (go) is not the Git term
            explained = False
            if english:
                following = prose[end:end + 160].split("\n\n")[0]
                explained = bool(_GLOSS_PATTERN.search(following) or _GLOSS_COLON.search(following[:30]))
                if not explained:
                    lo, hi = (sp[0], sp[1]) if sp is not None else (max(0, start - 200), min(len(prose), end + 200))
                    explained = _defined_here(prose, start, end, lo, hi)
            elif sp is not None:
                sentence = prose[sp[0]:sp[1]]
                explained = textlib.word_count(sentence) >= 6 and textlib.word_count(sentence) - textlib.word_count(str(entry.get("matched", ""))) >= 5
            name = str(entry.get("term", ""))[:40]
            if explained:
                row["glossed"].append(name)
                row["glossed_keys"].append(key)
                if cid:
                    row["glossed_ids"].append(cid)
                if sp is not None and kinds[sp[2]] == "":
                    sp[3] = "gloss"
            else:
                row["unexplained"].append(str(entry.get("matched") or name)[:40])
        row["glossed"] = row["glossed"][:10]
        row["glossed_ids"] = row["glossed_ids"][:10]
        row["glossed_keys"] = row["glossed_keys"][:10]
        row["unexplained"] = row["unexplained"][:8]

        # words
        result = 0
        for sp in spans:
            sentence = prose[sp[0]:sp[1]]
            if kinds[sp[2]] in ("check", "offer", "card"):
                continue
            if sp[3] == "gloss" or _decision(sentence):
                continue
            result += textlib.word_count(sentence)
        row["words"] = textlib.word_count(prose)
        row["result_words"] = result

        body = "\n".join(ln for ln, k in zip(lines, kinds) if k != "card")
        avg, longest, _ = textlib.sentence_stats(body)
        row["avg_sentence_words"], row["max_sentence_words"] = avg, longest
        row["banned"] = banned_in(body)
        row["banned_hits"] = banned_count(body)
        return row
    except Exception:
        return row


# --------------------------------------------------------------------------- notices

def _work(r: Dict[str, Any]) -> bool:
    return r.get("work_size") in ("small", "medium", "large")


def _medium(r: Dict[str, Any]) -> bool:
    return r.get("work_size") in ("medium", "large")


def offer_ready(r: Any) -> bool:
    """True when the answer may carry the 'Next I can teach:' line: a finished piece of work (medium or large)
    or a lesson (no work, with a check or a gloss). Small work and plain chat do not."""
    if not isinstance(r, dict):
        return False
    if _medium(r):
        return True
    return r.get("work_size") in (None, "none") and bool(r.get("check_marker") or r.get("glossed"))


def notices(rows: List[Dict[str, Any]], profile: Optional[Dict[str, Any]] = None, last_prompt_id: str = "") -> List[str]:
    """At most 2 fact lines from the newest ledger rows. Empty when the newest row was already
    announced (its prompt_id equals last_prompt_id) or when nothing is off."""
    try:
        profile = profile or {}
        rows = [r for r in rows if isinstance(r, dict)]
        if not rows:
            return []
        latest = rows[-1]
        if last_prompt_id and str(latest.get("prompt_id", "")) == str(last_prompt_id):
            return []
        limits = config.level_limits(profile.get("level"), profile.get("answer_words"))
        cap, sent_cap = limits["result_words"], limits["sentence_words"]
        last3 = rows[-3:]
        out: List[str] = []

        no_check = len(last3) == 3 and all(_medium(r) and not r.get("check_marker") for r in last3)
        fishy = _medium(latest) and bool(latest.get("fishing"))
        if no_check or fishy:
            out.append("Your last medium work answers had no real check question.")
        elif len(last3) == 3 and all(_work(r) and int(r.get("result_words") or 0) > cap for r in last3):
            out.append("The result part of your last 3 answers was over %d words. Keep the result short and put "
                       "detail in a file. Checks and glosses stay." % cap)
        elif _work(latest) and int(latest.get("result_words") or 0) > cap:
            out.append("Your last answer had %d result words; the limit is %d. Keep the next result shorter."
                       % (int(latest.get("result_words") or 0), cap))
        names = [untrusted.neutralize(n, 30) for n in (latest.get("unexplained") or [])[:3] if isinstance(n, str)]
        if names:
            out.append("Terms used without a one-sentence explanation: %s. Explain them at your next first use or "
                       "now if still relevant." % ", ".join(names))
        last10 = rows[-10:]
        hits = sum(int(r.get("banned_hits") or 0) for r in last10)
        if hits >= 2:
            words: List[str] = []
            for r in last10:
                for w in r.get("banned") or []:
                    if isinstance(w, str) and w not in words:
                        words.append(w)
            if words:
                out.append("Words the style avoids appeared %d times in your last answers: %s."
                           % (hits, ", ".join(untrusted.neutralize(w, 20) for w in words[:5])))
        last2 = rows[-2:]
        if len(last2) == 2 and all(float(r.get("avg_sentence_words") or 0) > sent_cap for r in last2):
            out.append("Your last 2 answers averaged %.0f words per sentence; the limit is %d."
                       % (float(last2[-1].get("avg_sentence_words") or 0), sent_cap))
        return out[:2]
    except Exception:
        return []


# --------------------------------------------------------------------------- outcome bands (doctor, progress)

def outcomes(rows: List[Dict[str, Any]], profile: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Measured values for the target bands of SPEC 6.5 (None when there is too little data)."""
    rows = [r for r in rows if isinstance(r, dict)]
    limits = config.level_limits((profile or {}).get("level"), (profile or {}).get("answer_words"))
    med = [r for r in rows if _medium(r)]
    out: Dict[str, Any] = {"answers": len(rows), "medium_answers": len(med), "check_rate": None,
                           "unexplained_rate": None, "median_result_words": None, "avg_sentence_words": None,
                           "result_cap": limits["result_words"], "sentence_cap": limits["sentence_words"]}
    if med:
        out["check_rate"] = round(sum(1 for r in med if r.get("check_marker") and not r.get("fishing")) / float(len(med)), 2)
    terms = sum(len(r.get("glossed") or []) + len(r.get("unexplained") or []) for r in rows)
    if terms:
        out["unexplained_rate"] = round(sum(len(r.get("unexplained") or []) for r in rows) / float(terms), 2)
    words = sorted(int(r.get("result_words") or 0) for r in rows if _work(r))
    if words:
        out["median_result_words"] = words[len(words) // 2]
    avgs = [float(r.get("avg_sentence_words") or 0) for r in rows if r.get("avg_sentence_words")]
    if avgs:
        out["avg_sentence_words"] = round(sum(avgs) / len(avgs), 1)
    return out
