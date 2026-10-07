"""_facts.py - what the learner's message says about the learner (not a hook itself).

What: detect(prompt) returns plain flags: quiet/skip/"my turn"/"you do it"/"not now" phrases (whole message
or first clause of at most 6 words), confusion and frustration, an error paste with or without a guess,
and an inquiry (the learner asks why/what/how).
Why: the user-prompt hook turns these into short FACTS for the model; the model decides what to do.
Everything is data-driven from lib/config.py (five languages; accents and case are folded).
How it fails safely: only the first 4,000 characters are examined (a 2 MB paste costs the same as a
small one); an error in one detector gives False for that flag.
Who calls it: user_prompt.
"""
from __future__ import annotations

import re
import sys
from typing import Any, Dict, List

from lib import config, text as textlib

sys.dont_write_bytecode = True

_CLAUSE_END = re.compile(r"[.,;:!?\n—–]")
_CACHE: Dict[str, Any] = {}


def _phrase_rx(table: Dict[str, List[str]]) -> "re.Pattern[str]":
    """Regex over the multi-word phrases of a table (single words are handled by _matches)."""
    key = "rx" + str(id(table))
    rx = _CACHE.get(key)
    if rx is None:
        phrases = sorted({textlib.fold(p) for p in config.all_of(table) if p and " " in p.strip()}, key=len, reverse=True)
        rx = (re.compile(r"(?<![^\W_])(?:" + "|".join(re.escape(p) for p in phrases) + r")(?![^\W_])")
              if phrases else re.compile(r"(?!x)x"))
        _CACHE[key] = rx
    return rx


def _singles(table: Dict[str, List[str]]) -> set:
    key = "one" + str(id(table))
    got = _CACHE.get(key)
    if got is None:
        got = {textlib.fold(p) for p in config.all_of(table) if p and " " not in p.strip()}
        _CACHE[key] = got
    return got


def _matches(table: Dict[str, List[str]], cands: List[str]) -> bool:
    """A multi-word phrase may sit anywhere in a short message; a single word must BE the message."""
    rx, ones = _phrase_rx(table), _singles(table)
    for c in cands:
        if rx.search(c) or re.sub(r"[^\w]+", "", c) in ones:
            return True
    return False


# A negation right before a phrase ("do not teach me", "nicht erklar mir"): the phrase then asks for no lesson.
_NEG_BEFORE = re.compile(r"(?<![^\W_])(?:do not|don't|dont|not|never|no|nicht|kein|ne|pas|jamais|nunca|asla|degil)\s*$")


def _matches_unnegated(table: Dict[str, List[str]], cands: List[str]) -> bool:
    """Like _matches, but a multi-word phrase that a negation word precedes does not count."""
    rx, ones = _phrase_rx(table), _singles(table)
    for c in cands:
        for m in rx.finditer(c):
            if not _NEG_BEFORE.search(c[:m.start()]):
                return True
        if re.sub(r"[^\w]+", "", c) in ones:
            return True
    return False


def _candidates(folded: str) -> List[str]:
    """The texts a short command phrase may sit in: the whole message, or its first clause, when <= 6 words."""
    out: List[str] = []
    whole = folded.strip()
    if whole and len(whole.split()) <= 6:
        out.append(whole)
    first = _CLAUSE_END.split(whole, 1)[0].strip()
    if first and len(first.split()) <= 6 and first not in out:
        out.append(first)
    return out


def _any_rx(sources: List[str], text: str) -> bool:
    for src in sources:
        try:
            if re.search(src, text):
                return True
        except re.error:
            continue
    return False


def detect(prompt: str) -> Dict[str, bool]:
    flags = {k: False for k in ("quiet_on", "quiet_off", "skip", "my_turn", "you_do", "not_now", "confusion",
                                "frustration", "error_paste", "guess", "inquiry")}
    try:
        head = prompt[:4000]
        folded = textlib.fold(head)
        cands = _candidates(folded)
        for flag, table in (("quiet_on", config.QUIET_PHRASES),
                            ("skip", config.SKIP_PHRASES), ("my_turn", config.MY_TURN_PHRASES),
                            ("you_do", config.YOU_DO_PHRASES), ("not_now", config.NOT_NOW_PHRASES)):
            flags[flag] = _matches(table, cands)
        flags["quiet_off"] = _matches_unnegated(config.QUIET_OFF_PHRASES, cands)
        if flags["quiet_off"]:
            flags["quiet_on"] = False
        flags["confusion"] = _any_rx(config.all_of(config.CONFUSION), folded[:1500])
        flags["frustration"] = _any_rx(config.all_of(config.FRUSTRATION), folded[:800])
        scan = prompt[:20000]
        pasted = _any_rx(config.all_of(config.ERROR_PATTERNS), scan) and (scan.count("\n") >= 1 or len(scan) >= 80)
        flags["guess"] = any(textlib.fold(w) in folded[:1500] for w in config.all_of(config.GUESS_WORDS))
        flags["error_paste"] = bool(pasted)
        words = folded.split()
        first_two = " ".join(words[:2])
        question_words = [textlib.fold(w) for w in config.all_of(config.QUESTION_WORDS)]
        starts_q = bool(words) and (words[0] in question_words or first_two in question_words)
        flags["inquiry"] = (starts_q or head.rstrip().endswith(("?", "？"))) and not pasted and len(words) <= 60
    except Exception:
        pass
    return flags
