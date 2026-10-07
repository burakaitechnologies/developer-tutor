"""knowledge.py - reads the concept cards and the glossary, finds terms and signals, picks offers.

What: lazy, cached loaders for knowledge/concepts/*.jsonl (schema v2) and knowledge/glossary.jsonl;
concept(id); find_terms(text) for the jargon detector; signals_for(text) for "what is the learner
working on"; pick_offers() for the "Next I can teach:" candidates (SPEC 6.3); small helpers for the
printed-offer memory that the caller keeps in state.json.
Why: hooks supply FACTS (which words were jargon, which topics fit the work); the model words them.
How it fails safely: every function swallows IO and parse errors and returns an empty value. A
malformed line, a missing key or an unknown key never raises. Nothing heavy runs at import time;
files are read on first use and cached for the life of the process (reset_cache() for tests).
Who calls it: user_prompt (offers, verify-soon), post_tool (signals), stop/ledger (find_terms),
learner (concept rows for kind, tier, titles). It never imports learner.
Python 3.9, standard library only.

Public functions: load_concepts() -> {id: row}   load_glossary() -> [row]   concept(id)   resolve(name)
  find_terms(text) -> [entry with start/end]   signals_for(text) -> {ids}
  pick_offers(state, activity, profile, k=3, last_message="", shown=None) -> [{id, title, ...}]
  record_shown(shown, ids)   offers_changed(shown, ids)   offer_taken(message, ids)
  offers_policy(ignored_in_a_row, sessions_without_taken)   update_ignored(n, taken)   reset_cache()
"""
from __future__ import annotations

import json
import os
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Set

try:
    from . import fsio, paths
except ImportError:  # loaded as a flat module (tests, scripts)
    import fsio  # type: ignore
    import paths  # type: ignore

MAX_LINE = 20000          # a concept row longer than this is skipped
MAX_SCAN_CHARS = 50000    # find_terms and signals_for look at this much text
MIN_SIGNAL = 4            # signals shorter than this are ignored (SPEC 12.1)

_CACHE: Dict[str, Any] = {"dir": None, "concepts": None, "glossary": None,
                          "terms": None, "signals": None, "names": None, "report": None}
_FOLD_CHARS: Dict[str, str] = {}
_WORD_RE = re.compile(r"[^\W_]+")


def reset_cache() -> None:
    """Forget everything that was loaded (used by tests and after a knowledge edit)."""
    for key in _CACHE:
        _CACHE[key] = None


# --------------------------------------------------------------------------- folding

def _fold_char(ch: str) -> str:
    if ch == "ı":  # dotless i
        return "i"
    decomposed = unicodedata.normalize("NFKD", ch)
    base = "".join(c for c in decomposed if not unicodedata.combining(c))
    if len(base) == 1:
        low = base.lower()
        return low if len(low) == 1 else base
    low = ch.lower()
    return low if len(low) == 1 else ch


def fold(text: Any) -> str:
    """Lower-case and remove accents, keeping the SAME LENGTH as the input so that
    positions found in the folded text are valid in the original (NFC) text."""
    if not text:
        return ""
    text = str(text)
    if text.isascii():
        return text.lower()
    out = []
    cache = _FOLD_CHARS
    for ch in text:
        f = cache.get(ch)
        if f is None:
            f = _fold_char(ch)
            cache[ch] = f
        out.append(f)
    return "".join(out)


def _nfc(text: str) -> str:
    try:
        return unicodedata.normalize("NFC", text)
    except Exception:
        return text


def _wordch(ch: str) -> bool:
    return ch.isalnum() or ch == "_" or bool(unicodedata.combining(ch))


def _path_norm(folded: str) -> str:
    return re.sub(r"[\\/]+", "/", folded)


# --------------------------------------------------------------------------- loading

def _kdir() -> str:
    try:
        return os.path.join(paths.knowledge_dir())
    except Exception:
        return ""


def _str_list(value: Any, lower: bool = False) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    out = []
    for item in value:
        if isinstance(item, str) and item.strip():
            s = item.strip()
            out.append(s.lower() if lower else s)
    return out


def _norm_concept(row: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    cid = row.get("id")
    if not isinstance(cid, str):
        return None
    cid = cid.strip()
    if not cid or len(cid) > 60 or re.search(r"\s", cid):
        return None
    out = dict(row)
    out["id"] = cid
    title = row.get("title")
    out["title"] = title.strip() if isinstance(title, str) and title.strip() else cid
    dom = row.get("domain")
    out["domain"] = dom.strip().lower() if isinstance(dom, str) and dom.strip() else cid.split("-")[0]
    try:
        tier = int(row.get("tier", 2))
    except (TypeError, ValueError):
        tier = 2
    out["tier"] = min(max(tier, 1), 3)
    out["needs"] = [n for n in _str_list(row.get("needs")) if n != cid]
    out["terms"] = _str_list(row.get("terms"))
    out["signals"] = _str_list(row.get("signals"), lower=True)
    for key in ("plain", "check", "pitfall", "try", "check_type"):
        if not isinstance(row.get(key), str):
            out[key] = ""
    out["rubric"] = _str_list(row.get("rubric"))
    kind = row.get("kind")
    out["kind"] = kind.strip().lower() if isinstance(kind, str) and kind.strip() else ""
    return out


def _read_jsonl_rows(path: str, report: Dict[str, int]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    text = fsio.read_text(path, "")
    if not text:
        return rows
    for line in text.lstrip("﻿").split("\n"):
        line = line.strip()
        if not line:
            continue
        if len(line) > MAX_LINE:
            report["bad"] += 1
            continue
        try:
            obj = json.loads(line)
        except Exception:
            report["bad"] += 1
            continue
        if isinstance(obj, dict):
            rows.append(obj)
        else:
            report["bad"] += 1
    return rows


def _ensure_dir_cache() -> None:
    key = _kdir()
    if _CACHE["dir"] != key:
        reset_cache()
        _CACHE["dir"] = key


def load_concepts() -> Dict[str, Dict[str, Any]]:
    """{concept id: row}. Order is file name, then line. A duplicate id keeps the first row."""
    _ensure_dir_cache()
    if _CACHE["concepts"] is not None:
        return _CACHE["concepts"]
    out: Dict[str, Dict[str, Any]] = {}
    report = {"bad": 0, "dup": 0, "rows": 0}
    try:
        base = os.path.join(_kdir(), "concepts")
        names = sorted(n for n in os.listdir(base) if n.lower().endswith(".jsonl"))
    except Exception:
        base, names = "", []
    for name in names:
        try:
            for raw in _read_jsonl_rows(os.path.join(base, name), report):
                row = _norm_concept(raw)
                if row is None:
                    report["bad"] += 1
                elif row["id"] in out:
                    report["dup"] += 1
                else:
                    out[row["id"]] = row
                    report["rows"] += 1
        except Exception:
            report["bad"] += 1
    _CACHE["concepts"] = out
    _CACHE["report"] = report
    return out


def load_glossary() -> List[Dict[str, Any]]:
    """Glossary rows (jargon terms without a concept). Rows without a term are dropped."""
    _ensure_dir_cache()
    if _CACHE["glossary"] is not None:
        return _CACHE["glossary"]
    rows: List[Dict[str, Any]] = []
    report = {"bad": 0, "dup": 0, "rows": 0}
    try:
        for raw in _read_jsonl_rows(os.path.join(_kdir(), "glossary.jsonl"), report):
            term = raw.get("term")
            if not isinstance(term, str) or not term.strip():
                continue
            row = dict(raw)
            row["term"] = term.strip()
            row["aliases"] = _str_list(raw.get("aliases"))
            row["plain"] = raw.get("plain") if isinstance(raw.get("plain"), str) else ""
            row["domain"] = raw.get("domain") if isinstance(raw.get("domain"), str) else ""
            rows.append(row)
    except Exception:
        pass
    _CACHE["glossary"] = rows
    return rows


def load_report() -> Dict[str, int]:
    """Counts from the last concept load: rows, bad lines, duplicate ids (for doctor)."""
    load_concepts()
    return dict(_CACHE.get("report") or {"bad": 0, "dup": 0, "rows": 0})


def concept(cid: Any) -> Optional[Dict[str, Any]]:
    """One concept row by id (exact, then lower-case), or None."""
    if not isinstance(cid, str):
        return None
    rows = load_concepts()
    return rows.get(cid) or rows.get(cid.strip().lower())


def title_of(cid: str) -> str:
    row = concept(cid)
    return row["title"] if row else cid


def _names_index() -> Dict[str, str]:
    """folded id / title / term -> concept id (first wins). Used to resolve what the model wrote."""
    if _CACHE["names"] is not None and _CACHE["dir"] == _kdir():
        return _CACHE["names"]
    idx: Dict[str, str] = {}
    for cid, row in load_concepts().items():
        for name in [cid, cid.replace("-", " "), row["title"]] + list(row["terms"]):
            key = " ".join(fold(name).split())
            if key and key not in idx:
                idx[key] = cid
    _CACHE["names"] = idx
    return idx


def resolve(text: Any) -> Optional[str]:
    """The concept id that a short name points at (id, title or term, accents and case ignored)."""
    if not isinstance(text, str):
        return None
    key = " ".join(fold(text).replace("_", " ").split())
    if not key:
        return None
    idx = _names_index()
    return idx.get(key) or idx.get(key.replace("-", " ")) or idx.get(key.replace(" ", "-"))


# --------------------------------------------------------------------------- terms

class _Term(object):
    __slots__ = ("term", "alias", "match", "offset", "id", "source", "plain", "domain", "rx", "flex")

    def __init__(self, term, alias, match, offset, cid, source, plain, domain):
        self.term = term
        self.alias = alias
        self.match = match
        self.offset = offset
        self.id = cid
        self.source = source
        self.plain = plain
        self.domain = domain
        self.rx = None
        self.flex = (" " in match) or ("-" in match)


def _term_index() -> Dict[str, List[_Term]]:
    if _CACHE["terms"] is not None and _CACHE["dir"] == _kdir():
        return _CACHE["terms"]
    index: Dict[str, List[_Term]] = {}
    seen: Set[str] = set()

    def add(main: str, alias: str, cid: str, source: str, plain: str, domain: str) -> None:
        match = " ".join(fold(alias).split())
        m = _WORD_RE.search(match)
        if not m or len(match) < 2 or match in seen:
            return
        seen.add(match)
        index.setdefault(m.group(), []).append(
            _Term(main, alias, match, m.start(), cid, source, plain, domain))

    for cid, row in load_concepts().items():
        terms = row["terms"]
        for alias in terms:
            add(terms[0], alias, cid, "concept", row["plain"], row["domain"])
    for row in load_glossary():
        if row.get("jargon") is False:
            continue
        for alias in [row["term"]] + row["aliases"]:
            add(row["term"], alias, "", "glossary", row["plain"], row["domain"])
    for lst in index.values():
        lst.sort(key=lambda t: -len(t.match))
    _CACHE["terms"] = index
    return index


def _flex_match(t: _Term, folded: str, start: int) -> int:
    """Length of a match of a multi-word term where a space may also be a hyphen or several spaces."""
    if t.rx is None:
        pieces = [re.escape(p) for p in re.split(r"[\s\-]+", t.match) if p]
        t.rx = re.compile(r"[\s\-]+".join(pieces))
    m = t.rx.match(folded, start)
    return m.end() - start if m else -1


def find_terms(text: Any, limit: int = 60) -> List[Dict[str, Any]]:
    """Jargon terms found in text: concept `terms` and glossary `term`/`aliases`.

    Word-boundary, case-insensitive, accent-folded. One entry per term (first position), in text
    order. Each entry: term (main form), alias (the form that matched), matched (text slice), id
    (concept id or ""), source ("concept"|"glossary"), plain, domain, start, end. Positions refer
    to the NFC form of the text (identical for normal text). Turkish suffixes after an apostrophe
    (git'i) match; suffixes glued to the word (reponun) do not - safe, not smart.
    """
    try:
        if not isinstance(text, str) or not text:
            return []
        text = _nfc(text[:MAX_SCAN_CHARS])
        folded = fold(text)
        index = _term_index()
        if not index:
            return []
        found: Dict[str, Dict[str, Any]] = {}
        n = len(folded)
        for m in _WORD_RE.finditer(folded):
            cands = index.get(m.group())
            if not cands:
                continue
            for t in cands:
                start = m.start() - t.offset
                if start < 0:
                    continue
                if folded.startswith(t.match, start):
                    length = len(t.match)
                elif t.flex:
                    length = _flex_match(t, folded, start)
                    if length < 0:
                        continue
                else:
                    continue
                end = start + length
                if start > 0 and _wordch(folded[start - 1]):
                    continue
                if end < n and _wordch(folded[end]):
                    continue
                key = t.id or ("g:" + t.term.lower())
                if key in found:
                    break
                found[key] = {"term": t.term, "alias": t.alias, "matched": text[start:end],
                              "id": t.id, "source": t.source, "plain": t.plain,
                              "domain": t.domain, "start": start, "end": end}
                break
            if len(found) >= limit:
                break
        return sorted(found.values(), key=lambda e: e["start"])
    except Exception:
        return []


# --------------------------------------------------------------------------- signals

_PLAIN_SIGNAL = re.compile(r"^[a-z0-9 ]+$")   # words and spaces only: matched as whole words (json, docs folder)


def _signal_pairs() -> List[Any]:
    """(signal, concept id, whole-word regex or None). Signals with punctuation (a call name and a bracket, logs/, .git/) stay
    plain substrings; a plain word such as json does not match inside jsonl or myjson."""
    if _CACHE["signals"] is not None and _CACHE["dir"] == _kdir():
        return _CACHE["signals"]
    pairs = []
    seen = set()
    for cid, row in load_concepts().items():
        for sig in row["signals"]:
            s = _path_norm(fold(sig)).strip()
            if len(s) < MIN_SIGNAL or (s, cid) in seen:
                continue
            seen.add((s, cid))
            rx = re.compile(r"(?<![^\W_])" + re.escape(s) + r"(?![^\W_])") if _PLAIN_SIGNAL.match(s) else None
            pairs.append((s, cid, rx))
    _CACHE["signals"] = pairs
    return pairs


def signals_for(text: Any) -> Set[str]:
    """Concept ids whose `signals` occur in text (commands, file names, the learner's message).

    Plain substring match on lower-cased, accent-folded text; backslashes and doubled slashes are
    treated as one slash, so a Windows path matches a signal written with a slash.
    """
    try:
        if not isinstance(text, str) or not text:
            return set()
        hay = _path_norm(fold(text[:MAX_SCAN_CHARS]))
        return {cid for sig, cid, rx in _signal_pairs() if (rx.search(hay) if rx is not None else sig in hay)}
    except Exception:
        return set()


# --------------------------------------------------------------------------- offers

def _get(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _level(cs: Any) -> int:
    try:
        return int(_get(cs, "level", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _state_json() -> Dict[str, Any]:
    try:
        data = fsio.read_json(paths.sub("state", "state.json"), {})
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _blob(items: Iterable[Any]) -> str:
    """Join every string found in activity rows into one text for signal matching."""
    parts: List[str] = []

    def walk(value: Any, depth: int) -> None:
        if depth > 3:
            return
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            for k, v in value.items():
                if k not in ("ts", "date", "session", "session_id", "prompt_id"):
                    walk(v, depth + 1)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v, depth + 1)

    for item in items or []:
        walk(item, 0)
    return "\n".join(parts)


def _learn_first(profile: Any) -> Set[str]:
    raw = _get(profile, "learn_first", "")
    if isinstance(raw, (list, tuple)):
        raw = ",".join(str(x) for x in raw)
    if not isinstance(raw, str):
        return set()
    return {w for w in re.split(r"[\s,;]+", fold(raw)) if w}


def _id_list(ids: Any) -> List[str]:
    if isinstance(ids, str):
        return [ids]
    try:
        return [str(i) for i in ids]
    except TypeError:
        return []


def shown_ids(shown: Any, last: int = 5) -> Set[str]:
    """Ids in the last `last` printed offer sets (shown = list of lists, oldest first)."""
    out: Set[str] = set()
    if isinstance(shown, (list, tuple)):
        for group in list(shown)[-last:]:
            if isinstance(group, (list, tuple)):
                out.update(str(x) for x in group)
    return out


def record_shown(shown: Any, ids: Iterable[str], keep: int = 5) -> List[List[str]]:
    """Return the new offers_shown list after `ids` were PRINTED. Pure: the caller stores it."""
    groups = [list(g) for g in shown if isinstance(g, (list, tuple))] if isinstance(shown, (list, tuple)) else []
    new = _id_list(ids)
    if new:
        groups.append(new)
    return groups[-keep:]


def offers_changed(shown: Any, ids: Iterable[str]) -> bool:
    """True when `ids` differ (as a set) from the set printed last time. An empty set never counts."""
    new = set(_id_list(ids))
    if not new:
        return False
    if isinstance(shown, (list, tuple)) and shown and isinstance(shown[-1], (list, tuple)):
        return new != {str(i) for i in shown[-1]}
    return True


def pick_offers(state: Any, activity: Any, profile: Any, k: int = 3,
                last_message: str = "", shown: Any = None) -> List[Dict[str, Any]]:
    """Up to k concepts worth offering now (SPEC 6.3). Never invents a topic; may return fewer.

    state: learner.fold() result (objects or dicts with level, told_me, declined). activity: the last
    activity rows (the caller passes at most 12). profile: parsed profile dict (learn_first).
    shown: offers_shown from state.json (list of printed id lists); read from state.json if None.
    Candidates are at level 0 or 1 (a claim alone does not count), all hard `needs` at Understood or
    above, declined less than twice, not in the last 5 printed sets. Sort key: signal hit in recent
    work or the learner's last message first, then learn_first domains, then tier, then id.
    """
    try:
        concepts = load_concepts()
        if not concepts or k <= 0:
            return []
        state = state or {}
        if shown is None:
            shown = _state_json().get("offers_shown")
        skip = shown_ids(shown)
        hit = signals_for(_blob(list(activity or [])[-12:]) + "\n" + str(last_message or ""))
        first = _learn_first(profile)
        ranked = []
        for cid, row in concepts.items():
            if cid in skip:
                continue
            cs = state.get(cid)
            lvl = _level(cs)
            if lvl >= 2:
                continue
            if lvl == 1 and _get(cs, "told_me", False):
                continue
            try:
                if int(_get(cs, "declined", 0) or 0) >= 2:
                    continue
            except (TypeError, ValueError):
                pass
            if any(n in concepts and _level(state.get(n)) < 2 for n in row["needs"]):
                continue
            sig = cid in hit
            lf = row["domain"] in first
            ranked.append(((0 if sig else 1, 0 if lf else 1, row["tier"], cid), row, sig, lf))
        ranked.sort(key=lambda item: item[0])
        return [{"id": row["id"], "title": row["title"], "domain": row["domain"], "tier": row["tier"],
                 "signal": sig, "learn_first": lf} for _, row, sig, lf in ranked[:k]]
    except Exception:
        return []


def offer_taken(message: Any, ids: Iterable[str]) -> bool:
    """True when the learner's next message names (or asks about) one of the offered concepts."""
    try:
        if not isinstance(message, str) or not message.strip():
            return False
        hay = " " + " ".join(fold(_nfc(message[:MAX_SCAN_CHARS])).split()) + " "
        for cid in ids:
            row = concept(cid)
            names = [cid.replace("-", " ")] + ([row["title"]] + row["terms"] if row else [])
            for name in names:
                needle = " ".join(fold(name).split())
                if len(needle) < 3:
                    continue
                at = hay.find(needle)
                while at >= 0:
                    before = hay[at - 1]
                    after = hay[at + len(needle)] if at + len(needle) < len(hay) else " "
                    if not _wordch(before) and not _wordch(after):
                        return True
                    at = hay.find(needle, at + 1)
        return False
    except Exception:
        return False


def offers_policy(ignored_in_a_row: int, sessions_without_taken: int = 0) -> Dict[str, bool]:
    """Fatigue rules of SPEC 6.3. off: 2 offers ignored in a row (print `Offers off for this session`).
    ask_fewer: 3 sessions with no offer taken (print the fact once; the model asks about "light")."""
    try:
        return {"off": int(ignored_in_a_row) >= 2, "ask_fewer": int(sessions_without_taken) >= 3}
    except (TypeError, ValueError):
        return {"off": False, "ask_fewer": False}


def update_ignored(ignored_in_a_row: int, taken: bool) -> int:
    """New value of the ignored-in-a-row counter after the learner's next message."""
    try:
        return 0 if taken else int(ignored_in_a_row) + 1
    except (TypeError, ValueError):
        return 0
