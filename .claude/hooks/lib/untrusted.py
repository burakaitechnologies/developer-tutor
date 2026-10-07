"""untrusted.py - make text from files, git, notes or the web safe to put in front of the model.

What: neutralize(text, max_len) and fence(label, text).
Why: a file name or a note can say "ignore all previous instructions". Hook output is read by the
model as trusted context, so everything copied from outside goes through here first (SPEC 7.4).
neutralize drops control, format, surrogate, private-use, unassigned and line-separator characters
(this removes right-to-left overrides, zero-width characters and tag characters), turns angle
brackets and backticks into harmless look-alikes, collapses whitespace, cuts the text and replaces
anything that looks like an instruction with a marker. fence wraps the result in a labelled block.
How it fails safely: any error returns the marker text, never the raw input.
Who calls it: session_start (tree names, now.md, ADR titles, branch, profile text), user_prompt, post_tool.
"""
from __future__ import annotations

import re
import sys
import unicodedata

sys.dont_write_bytecode = True

HIDDEN = "[text hidden: looks like instructions]"
_DROP = {"Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"}
_SPACE_LIKE = {"\t": " ", "\n": " ", "\r": " ", "\x0b": " ", "\x0c": " ", "\x85": " ", " ": " ", " ": " "}
_REPLACE = {"<": "‹", ">": "›", "`": "'"}
_INJECTION = re.compile(
    r"(?:\b(?:ignore|disregard|forget|override)\b[^.\n]{0,40}\b(?:previous|prior|above|earlier|all|any|every)\b"
    r"[^.\n]{0,30}\b(?:instructions?|prompts?|rules?|messages?|context)\b)"
    r"|(?:\bignore\s+(?:all|previous|prior|any)\b)"
    r"|(?:system[\s_-]{0,3}reminder)"
    r"|(?:\byou\s+are\s+now\b)"
    r"|(?:\bdisregard\b)"
    r"|(?:\bnew\s+instructions?\b)"
    r"|(?:\bnote\s+to\s+(?:the\s+)?(?:ai|assistant|model|claude)\b)"
    r"|(?:\[/?inst\])|(?:<\|[a-z_]{2,20}\|>)"
    # Turkish, German, Spanish and French: override, system prompt, reveal a secret, run a command.
    # Each phrase needs an override verb with a qualified noun, or an addressee (asistan, modele, Claude),
    # so that ordinary sentences in these languages (install commands, the password field) stay visible.
    r"|(?:\b(?:önceki|onceki|yukarıdaki|yukaridaki|tüm|tum|bütün|butun)\s+(?:talimat|kural|yönerge|yonerge|komut)\w*"
    r"[^.\n]{0,30}\b(?:yok\s+say|görmezden\s+gel|gormezden\s+gel|unut)\w*)"
    r"|(?:\bsistem\s+istemi\w*)"
    r"|(?:\bgizli\s+anahtar\w*\b[^.\n]{0,12}\b(?:göster|goster|ver|yaz|paylaş|paylas|söyle|soyle)\w*)"
    r"|(?:\b(?:şifre|sifre|parola)\w*\s+(?:bana|bize)\s+(?:göster|goster|ver|yaz|söyle|soyle)\w*)"
    r"|(?:\b(?:asistan\w*|yapay\s+zeka\w*|modele|claude)\b[^.\n]{0,30}\b[çc]al[ıi][şs]t[ıi]r\w*)"
    r"|(?:\b(?:ignorier\w*|missachte\w*)\s+(?:alle\w*|s[äa]mtliche\w*|deine\w*)\s+"
    r"(?:(?:vorherig|bisherig|obig|vorig)\w*\s+)?(?:anweisung|instruktion|regel)\w*)"
    r"|(?:\b(?:ignorier\w*|missachte\w*)\s+(?:die|diese)\s+(?:vorherig|bisherig|obig|vorig)\w*\s+"
    r"(?:anweisung|instruktion|regel)\w*)"
    r"|(?:\bvergiss\s+(?:alle|deine)\s+(?:vorherig\w*|bisherig\w*|obig\w*)\b)"
    r"|(?:\bsystem[- ]?prompt\w*|\bsystemanweisung\w*)"
    r"|(?:\b(?:zeig\w*|gib\w*|verrat\w*|nenn\w*)\s+(?:mir|uns)\s+(?:bitte\s+)?(?:den\s+|das\s+|dein\w*\s+|die\s+)?"
    r"(?:geheim\w*|kennwort\w*|passwort\w*|schl[üu]ssel\w*|token\w*))"
    r"|(?:\b(?:claude|assistent\w*|ki)\b[^.\n]{0,30}\b(?:f[üu]hr\w*|starte\w*)\s+(?:bitte\s+)?"
    r"(?:(?:diesen|den|folgenden|dem|diesem)\s+){1,2}(?:befehl|kommando)\w*)"
    r"|(?:\b(?:ignora\w*|olvida\w*|olvide\w*|desestima\w*)\b[^.\n]{0,25}\b(?:instrucciones|indicaciones|reglas)\s+"
    r"(?:anteriores|previas|precedentes)\b)"
    r"|(?:\bprompt\s+del\s+sistema\b)"
    r"|(?:\b(?:dime|dame|mu[ée]strame|revelame|revela)\s+(?:la\s+|el\s+|tu\s+|tus\s+)?(?:contrase[nñ]a|clave|secreto|token|llave)\w*)"
    r"|(?:\b(?:claude|asistente\w*|ia)\b[^.\n]{0,30}\b(?:ejecut\w*|corr[ae]\w*)\s+(?:este\s+|ese\s+|el\s+)?(?:comando|orden)\w*)"
    r"|(?:\b(?:ignor\w*|oubli\w*)\b[^.\n]{0,25}\b(?:instructions?|consignes?)\s+"
    r"(?:pr[ée]c[ée]dentes?|ant[ée]rieures?|ci[-\s]dessus|au[-\s]dessus)\b)"
    r"|(?:\bprompt\s+syst[èe]me\b|\binvite\s+syst[èe]me\b)"
    r"|(?:\b(?:montre\w*|donne\w*|dis|dites|r[ée]v[èe]le\w*)\s*-?\s*(?:moi|nous)\s+(?:le\s+|la\s+|ton\s+|ta\s+|votre\s+)?"
    r"(?:mot\s+de\s+passe|cl[ée]\s+secr[èe]te|jeton|secret)\w*)"
    r"|(?:\b(?:claude|assistant\w*|mod[èe]le|ia)\b[^.\n]{0,30}\b(?:ex[ée]cut\w*|lanc\w*)\s+(?:cette\s+|ce\s+|la\s+|le\s+)?"
    r"(?:commande|instruction)\w*)",
    re.IGNORECASE)


def neutralize(text: object, max_len: int = 200) -> str:
    """Safe, single-line, length-limited text. Never raises."""
    try:
        if not isinstance(text, str):
            text = "" if text is None else str(text)
        # regexes below run on a bounded slice: a hostile 1 MB name cannot make this slow
        text = text[:min(max(max_len * 3, 300), 20000)] if max_len is not None else text[:20000]
        out = []
        for ch in text:
            sp = _SPACE_LIKE.get(ch)
            if sp is not None:
                out.append(sp)
                continue
            if unicodedata.category(ch) in _DROP:
                continue
            out.append(_REPLACE.get(ch, ch))
        cleaned = " ".join("".join(out).split())
        cleaned = _INJECTION.sub(HIDDEN, cleaned)
        # a marker next to a marker is one marker
        cleaned = re.sub(r"(?:\[text hidden: looks like instructions\]\s*){2,}", HIDDEN + " ", cleaned).strip()
        if max_len is not None and max_len >= 0 and len(cleaned) > max_len:
            cleaned = cleaned[:max(max_len - 3, 0)].rstrip() + "..."
        return cleaned
    except Exception:
        return HIDDEN




def fence(label: str, text: str) -> str:
    """<<untrusted label="...">> text <</untrusted>>. One line for a short single-line text, else
    the text sits between two lines. The text is NOT neutralized here: callers run neutralize on
    each piece first. The label is neutralized and limited to 40 characters."""
    safe_label = re.sub(r"[^A-Za-z0-9 ._-]", "", neutralize(label, 40))
    body = text if isinstance(text, str) else ""
    body = body.replace("<</untrusted>>", "\u2039\u2039/untrusted\u203a\u203a").strip("\n")
    if "\n" not in body and len(body) <= 200:
        return '<<untrusted label="%s">> %s <</untrusted>>' % (safe_label, body)
    return '<<untrusted label="%s">>\n%s\n<</untrusted>>' % (safe_label, body)
