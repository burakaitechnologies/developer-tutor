"""text.py - small text helpers: word counts, code stripping, sentences, comparing words.

What: word_count, strip_code, clip, normalise, fold, sentences, avg_sentence_words, sentence_stats,
short_code, lower_headings, units.
Why: the ledger measures answers (words outside code, sentence length) and the quote check compares
the learner's words with what the model wrote; both must agree on one definition.
How it fails safely: pure functions on str; a non-str input is treated as ''. Regexes have bounded
or linear shapes (no nested quantifiers).
Who calls it: ledger, learner, chatlog, handlers, hookio.
"""
from __future__ import annotations

import hashlib
import re
import sys
import unicodedata
from typing import List, Tuple

sys.dont_write_bytecode = True

_QUOTES = str.maketrans({"‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
                         "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"'})
_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_ABBREV = ("e.g.", "i.e.", "etc.", "vs.", "approx.", "no.", "fig.", "cf.")
_SPLIT = re.compile(r"(?<=[.!?…。])[\"')\]]*\s+")
_BULLET = re.compile(r"^\s*(?:[-*+•]|\d{1,3}[.)])\s+")
_HEADING = re.compile(r"^(#{1,4}) ", re.M)


def _s(value: object) -> str:
    return value if isinstance(value, str) else ""


def units(text: str) -> int:
    """Length as JavaScript counts it (UTF-16 units)."""
    text = _s(text)
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


def word_count(text: str) -> int:
    """Words = whitespace-separated tokens that hold at least one letter or digit."""
    return sum(1 for tok in _s(text).split() if any(ch.isalnum() for ch in tok))


def strip_code(text: str) -> str:
    """Remove fenced code blocks (``` or ~~~; an unclosed fence runs to the end)."""
    out: List[str] = []
    fence = ""
    for line in _s(text).split("\n"):
        m = _FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = ""
            continue
        if m:
            fence = m.group(1)
            continue
        out.append(line)
    return "\n".join(out)


def clip(text: str, n: int) -> str:
    """At most n characters; a cut text ends with '...'."""
    text = _s(text)
    if n <= 0:
        return ""
    if len(text) <= n:
        return text
    if n <= 3:
        return text[:n]
    return text[:n - 3].rstrip() + "..."


def normalise(text: str) -> str:
    """Form for comparing words: NFC, straight quotes, dotted and dotless i equal, lower case,
    whitespace runs become one space."""
    text = unicodedata.normalize("NFC", _s(text))
    text = text.replace("İ", "i").replace("ı", "i").translate(_QUOTES).lower()
    return re.sub(r"\s+", " ", text).strip()


def fold(text: str) -> str:
    """normalise() plus accents removed (for matching words across spellings)."""
    base = unicodedata.normalize("NFD", normalise(text))
    return "".join(ch for ch in base if not unicodedata.combining(ch))


def short_code(text: str) -> str:
    return hashlib.sha1(_s(text).encode("utf-8", errors="replace")).hexdigest()[:12]


def lower_headings(text: str) -> str:
    """Move '#'..'####' headings two levels down so pasted text cannot forge a heading."""
    return _HEADING.sub(lambda m: "#" * (len(m.group(1)) + 2) + " ", _s(text))


def sentences(text: str) -> List[str]:
    """Sentences outside code: split at . ! ? followed by space, and at line ends (list items too)."""
    out: List[str] = []
    for line in strip_code(text).split("\n"):
        line = _BULLET.sub("", line.strip())
        if not line or not any(ch.isalnum() for ch in line):
            continue
        pieces = _SPLIT.split(line)
        merged: List[str] = []
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                continue
            if merged and (merged[-1].lower().endswith(_ABBREV) or re.search(r"(?:^|\s)\w\.$", merged[-1])):
                merged[-1] = merged[-1] + " " + piece
            else:
                merged.append(piece)
        out.extend(merged)
    return out


def sentence_stats(text: str) -> Tuple[float, int, int]:
    """(average words per sentence, longest sentence in words, number of sentences)."""
    counts = [word_count(s) for s in sentences(text)]
    counts = [c for c in counts if c > 0]
    if not counts:
        return 0.0, 0, 0
    return round(sum(counts) / len(counts), 1), max(counts), len(counts)


def avg_sentence_words(text: str) -> float:
    return sentence_stats(text)[0]
