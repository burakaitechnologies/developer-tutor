"""config.py - settings, limits and the word lists of every supported language (en, tr, es, de, fr).

What: DEFAULTS and cfg(key); parse_profile(text) -> (dict, warnings); level_limits(level); and the
data tables LABELS, FISHING, QUESTION_WORDS, FILLERS, BANNED, QUIET_PHRASES, SKIP_PHRASES,
MY_TURN_PHRASES, YOU_DO_PHRASES, QUIET_OFF_PHRASES, NOT_NOW_PHRASES, CONFUSION, FRUSTRATION, ERROR_PATTERNS, GUESS_WORDS, DECISION,
SYSTEM_PREFIXES, SURFACES.
Why: nothing language-specific or tunable is written into the logic. A detector folds case and
accents and accepts the words of ANY known language, so a learner who switches language is still
understood. To add a language, add one entry to each table.
Shapes: tables named above (except SYSTEM_PREFIXES and SURFACES) are {language code: [strings]};
use all_of(TABLE) for the flat list over all languages. Phrases are written in plain lower case;
compare with text.fold(). FISHING, CONFUSION, FRUSTRATION and ERROR_PATTERNS hold regular-expression
sources (bounded, no nested quantifiers) to be matched against folded text, except ERROR_PATTERNS
which is matched against the raw text.
LABELS[lang] = {"check": [3 labels], "offer": label, "gloss": [decision-sentence markers],
"card": [change-card labels]}.
How it fails safely: parse_profile never raises; an invalid value is dropped with one warning that
names the key, not the value (the value is untrusted text).
Who calls it: nearly every module.
"""
from __future__ import annotations

import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

# --------------------------------------------------------------------------- numbers and defaults

DEFAULTS: Dict[str, Any] = {
    # profile (SPEC 5.1)
    "onboarded": "no", "language": "", "level": "auto", "teaching": "normal", "comments": "teaching",
    "tree": "session", "learn_first": "", "answer_words": "", "chat_copy": "off", "call_me": "",
    # budgets (SPEC 3, 8)
    "capsule_max_chars": 3000, "compact_max_chars": 2000, "resume_max_chars": 600,
    "prompt_normal_chars": 450, "prompt_hard_chars": 900, "tree_max_chars": 1200,
    "tree_budget_ms": 300, "tree_max_entries": 20000, "tree_max_per_folder": 20,
    # time and retention
    "rollover_hour": 4, "chat_retention_days": 30, "recent_user_keep": 5, "recent_user_chars": 4000,
    "ledger_keep": 200, "activity_keep": 300, "error_log_max_bytes": 200 * 1024,
    # behaviour
    "away_days": 14, "inbox_max_bytes": 8192, "git_timeout": 5.0,
    "notice_over_cap_runs": 3, "fatigue_offers_ignored": 2,
}


def cfg(key: str, default: Any = None) -> Any:
    return DEFAULTS.get(key, default)


# --------------------------------------------------------------------------- levels

_LEVELS = {
    #        sentence, hard, result words, glosses, new concepts
    "A2": (10, 14, 90, 1, 1),
    "B1": (15, 20, 120, 2, 1),
    "B2": (20, 25, 140, 3, 2),
    "C1": (25, 30, 160, 3, 2),
}


def level_limits(level: Optional[str] = "auto", answer_words: Optional[Any] = None) -> Dict[str, int]:
    """Ceilings of the level table (SPEC 6.4). 'auto' or unknown = B1. answer_words overrides the result cap."""
    code = str(level or "auto").strip().upper()
    if code not in _LEVELS:
        code = "B1"
    sentence, hard, result, glosses, concepts = _LEVELS[code]
    try:
        if answer_words not in (None, ""):
            result = max(20, min(int(answer_words), 400))
    except (TypeError, ValueError):
        pass
    return {"level": code, "sentence_words": sentence, "sentence_hard": hard, "result_words": result,
            "glosses": glosses, "concepts": concepts}


# --------------------------------------------------------------------------- profile

PROFILE_ENUMS = {
    "onboarded": ("yes", "no"),
    "level": ("auto", "a2", "b1", "b2", "c1"),
    "teaching": ("normal", "light", "off"),
    "comments": ("teaching", "normal", "minimal"),
    "tree": ("session", "off"),
    "chat_copy": ("off", "on"),
}
PROFILE_KEYS = ("onboarded", "language", "level", "teaching", "comments", "tree", "learn_first",
                "answer_words", "chat_copy", "call_me")
_NAME_OK = re.compile(r"^[^\W\d_][^\W\d_ '\-]*(?:[ '\-][^\W\d_]+){0,3}$", re.UNICODE)
_DOMAIN_OK = re.compile(r"^[a-z][a-z0-9\-]{1,19}$")


def parse_profile(text: str) -> Tuple[Dict[str, str], List[str]]:
    """Read the `---` block at the top of learner/profile.md. Known keys only; values are clipped to
    40 characters (call_me to 30); a value outside its allowed set is dropped with a warning that
    names the key. Returns (profile dict with every key present, warnings)."""
    profile = {k: str(DEFAULTS[k]) for k in PROFILE_KEYS}
    warnings: List[str] = []
    try:
        body = (text or "")[:6000].lstrip(chr(0xFEFF) + " \t\r\n")
        body = re.sub(r"^(?:<!--.*?-->\s*)+", "", body, count=1, flags=re.S)   # a leading note from the template
        lines = body.lstrip(" \t\r\n").split("\n")
        if not lines or lines[0].strip() != "---":
            return profile, warnings
        for raw in lines[1:80]:
            line = raw.rstrip()
            if line.strip() == "---":
                break
            if ":" not in line or line.lstrip().startswith("#"):
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            if key not in PROFILE_KEYS:
                continue
            value = re.split(r"\s#", value, maxsplit=1)[0].strip().strip("'\"").strip()
            value = value[:40]
            if key == "call_me":
                value = value[:30]
                if value and not _NAME_OK.match(value):
                    warnings.append("profile: call_me is not a plain name and is ignored")
                    value = ""
            elif key in PROFILE_ENUMS:
                low = value.lower()
                if low and low not in PROFILE_ENUMS[key]:
                    warnings.append("profile: the value of %s is not valid and is ignored" % key)
                    continue
                value = low.upper() if key == "level" and low != "auto" else low
                if key == "level" and low == "auto":
                    value = "auto"
            elif key == "answer_words":
                if value:
                    try:
                        n = int(value)
                        if not 20 <= n <= 400:
                            raise ValueError
                        value = str(n)
                    except ValueError:
                        warnings.append("profile: answer_words must be a number from 20 to 400 and is ignored")
                        continue
            elif key == "language":
                if value and not re.match(r"^[^\W\d_][^\d_]{0,39}$", value, re.UNICODE):
                    warnings.append("profile: language is not a plain name and is ignored")
                    continue
            elif key == "learn_first":
                parts = [p.strip().lower() for p in re.split(r"[,; ]+", value) if p.strip()]
                good = [p for p in parts if _DOMAIN_OK.match(p)]
                if len(good) != len(parts):
                    warnings.append("profile: learn_first has an invalid entry that is ignored")
                value = ",".join(good)
            profile[key] = value
    except Exception:
        warnings.append("profile: could not be read")
    return profile, warnings


# --------------------------------------------------------------------------- languages

LANGUAGE_NAMES = {
    "en": ("english", "en", "ingilizce", "inglés", "ingles", "englisch", "anglais"),
    "tr": ("turkish", "türkçe", "turkce", "tr", "türkisch", "turc", "turco"),
    "es": ("spanish", "español", "espanol", "es", "spanisch", "espagnol", "ispanyolca"),
    "de": ("german", "deutsch", "de", "almanca", "alemán", "aleman", "allemand"),
    "fr": ("french", "français", "francais", "fr", "fransızca", "francés", "frances", "französisch"),
}
LANGS = tuple(LANGUAGE_NAMES.keys())


def language_code(name: Optional[str]) -> str:
    """'Turkish' / 'Türkçe' / 'tr' -> 'tr'. Empty or unknown -> 'en'."""
    low = (name or "").strip().lower()
    for code, names in LANGUAGE_NAMES.items():
        if low in names:
            return code
    return "en"


def all_of(table: Dict[str, Iterable[str]]) -> List[str]:
    """Flat list of a per-language table over all languages (order en, tr, es, de, fr)."""
    out: List[str] = []
    for lang in LANGS:
        for item in table.get(lang, ()):
            if item not in out:
                out.append(item)
    return out


def labels_for(language: Optional[str]) -> Dict[str, Any]:
    return LABELS.get(language_code(language), LABELS["en"])


LABELS: Dict[str, Dict[str, Any]] = {
    "en": {"check": ["Check:", "Predict:", "Your move:"], "offer": "Next I can teach:",
           "gloss": ["I chose", "I picked", "I decided", "I went with"], "card": ["Change card:"]},
    "tr": {"check": ["Kontrol:", "Tahmin:", "Sıra sende:"], "offer": "Sıradaki konular:",
           "gloss": ["seçtim", "tercih ettim", "karar verdim"], "card": ["Değişiklik kartı:", "Change card:"]},
    "es": {"check": ["Comprueba:", "Predice:", "Tu turno:"], "offer": "Siguientes temas:",
           "gloss": ["elegí", "escogí", "decidí", "opté por"], "card": ["Tarjeta de cambios:", "Change card:"]},
    "de": {"check": ["Prüfe:", "Vorhersage:", "Du bist dran:"], "offer": "Als Nächstes kann ich erklären:",
           "gloss": ["ich habe gewählt", "ich habe mich für", "ich habe entschieden"], "card": ["Änderungskarte:", "Change card:"]},
    "fr": {"check": ["Vérifie :", "Prédis :", "À toi :"], "offer": "Prochains sujets :",
           "gloss": ["j'ai choisi", "j'ai opté", "j'ai décidé"], "card": ["Fiche de changement :", "Change card:"]},
}

# Regular expressions on folded text (lower case, accents removed). Bounded shapes only.
FISHING: Dict[str, List[str]] = {
    "en": [r"does (?:that|this|it) make sense", r"any questions", r"ready to (?:continue|proceed|move on)",
           r"\bshall i\b", r"\bwant me to\b", r"\bwould you like me to\b", r"do you understand", r"is that clear",
           r"does (?:that|this) help", r"let me know if", r"should i (?:continue|proceed|go on)", r"(?:got|make) it\?",
           r"are you (?:ok|okay|with me|following)", r"how does that sound"],
    "tr": [r"mantikli mi", r"anlasildi mi", r"anladin mi", r"anlamis miydin", r"devam edeyim mi", r"soru(?:n| var)\b.{0,12}mi",
           r"sorun var mi", r"yardimci oldu mu", r"istersen", r"ister misin", r"hazir misin", r"net mi", r"tamam mi"],
    "es": [r"tiene sentido", r"alguna pregunta", r"lo entiendes", r"entendido\?", r"quieres que", r"listo para continuar",
           r"continuo\?", r"te parece bien", r"esta claro\?", r"quieres que siga"],
    "de": [r"ergibt das sinn", r"noch fragen", r"verstanden\?", r"soll ich", r"mochtest du, dass ich", r"bereit weiterzumachen",
           r"ist das klar", r"hast du fragen", r"alles klar\?", r"weiter\?"],
    "fr": [r"est-ce que (?:ca|cela) a du sens", r"des questions", r"c'est clair", r"veux-tu que", r"je continue\?",
           r"pret a continuer", r"tu comprends", r"ca te va", r"tout est clair"],
}

QUESTION_WORDS: Dict[str, List[str]] = {
    "en": ["why", "what", "how", "which", "when", "where", "who", "explain", "what's", "whats"],
    "tr": ["neden", "nicin", "niye", "nasil", "nedir", "hangi", "ne demek", "acikla", "ne ise yarar", "kim", "nerede", "ne zaman"],
    "es": ["por que", "que", "como", "cual", "donde", "cuando", "quien", "explica", "para que"],
    "de": ["warum", "was", "wie", "welche", "welcher", "wo", "wann", "wer", "erklare", "wozu"],
    "fr": ["pourquoi", "quoi", "comment", "quel", "quelle", "ou", "quand", "qui", "explique", "c'est quoi"],
}

FILLERS: Dict[str, List[str]] = {
    "en": ["ok", "okay", "yes", "yeah", "yep", "sure", "fine", "good", "cool", "thanks", "thank you", "got it", "i see",
           "alright", "all right", "nice", "great", "understood", "i understand", "no problem", "makes sense", "right"],
    "tr": ["tamam", "anladim", "anladım", "evet", "olur", "peki", "iyi", "harika", "tesekkurler", "teşekkürler", "sagol",
           "sağol", "eyvallah", "super", "süper", "anlasildi", "anlaşıldı", "mantikli", "mantıklı"],
    "es": ["vale", "si", "sí", "entendido", "claro", "bien", "perfecto", "gracias", "genial", "de acuerdo", "ok", "listo", "entiendo"],
    "de": ["ok", "okay", "ja", "verstanden", "gut", "klar", "danke", "super", "alles klar", "in ordnung", "ich verstehe", "passt"],
    "fr": ["ok", "oui", "d'accord", "compris", "bien", "super", "merci", "parfait", "genial", "génial", "c'est bon", "je comprends"],
}

BANNED: Dict[str, List[str]] = {
    "en": ["easy", "just", "simply", "obviously", "of course", "great question"],
    "tr": ["kolay", "basit", "sadece", "tabii ki", "elbette", "zaten", "guzel soru", "mukemmel", "acikca"],
    "es": ["facil", "simple", "simplemente", "solo", "obviamente", "trivial", "por supuesto", "buena pregunta", "excelente"],
    "de": ["einfach", "leicht", "nur", "offensichtlich", "trivial", "naturlich", "gute frage", "ausgezeichnet"],
    "fr": ["facile", "simple", "simplement", "juste", "evidemment", "trivial", "bien sur", "bonne question", "excellent"],
}

QUIET_PHRASES: Dict[str, List[str]] = {
    "en": ["quiet mode", "no lessons", "teaching off", "stop teaching", "no teaching", "turn teaching off", "be quiet"],
    "tr": ["sessiz mod", "ders yok", "ogretme", "ogretmeyi kapat", "ders verme", "sessiz modu ac", "sessiz ol"],
    "es": ["modo silencioso", "sin lecciones", "sin clases", "no ensenes", "silencio"],
    "de": ["stiller modus", "keine lektionen", "kein unterricht", "nicht erklaren", "leise modus"],
    "fr": ["mode silencieux", "pas de lecons", "sans lecons", "arrete d'enseigner", "mode calme"],
}

SKIP_PHRASES: Dict[str, List[str]] = {
    "en": ["just do it", "skip this", "skip the lesson", "no explanation", "don't explain", "dont explain", "no lesson now"],
    "tr": ["sadece yap", "hemen yap", "yap gitsin", "bunu atla", "aciklama yok", "aciklama yapma"],
    "es": ["solo hazlo", "hazlo ya", "saltalo", "salta esto", "sin explicaciones", "no expliques"],
    "de": ["mach es einfach", "einfach machen", "ohne erklarung", "nicht erklaren jetzt"],
    "fr": ["fais-le", "fais le simplement", "saute ca", "sans explication", "ne m'explique pas"],
}

MY_TURN_PHRASES: Dict[str, List[str]] = {
    "en": ["my turn", "let me try", "let me do it", "i'll do it", "i will do it", "i'll type it", "let me type"],
    "tr": ["sira bende", "ben yapayim", "ben deneyeyim", "ben yazayim"],
    "es": ["mi turno", "dejame probar", "yo lo hago", "dejame hacerlo"],
    "de": ["ich bin dran", "lass mich", "ich mache es", "ich probiere es"],
    "fr": ["a moi", "laisse-moi", "je le fais", "je vais essayer"],
}

YOU_DO_PHRASES: Dict[str, List[str]] = {
    "en": ["you do it", "you do this one", "you type it", "you run it", "do it for me"],
    "tr": ["sen yap", "sen yaz", "benim icin yap"],
    "es": ["hazlo tu", "hazlo por mi", "tu lo haces"],
    "de": ["mach du es", "mach du das", "mach es fur mich"],
    "fr": ["fais-le toi", "fais-le pour moi", "c'est toi qui le fais"],
}

# The phrases are folded (accents and case removed) before they are compared, so "erklär mir" is listed as
# the folded "erklar mir", and the spelled-out "erklaer mir" is listed too. A phrase with a space matches
# anywhere in a short message; a phrase without one (ensename) matches only a message that is that word.
QUIET_OFF_PHRASES: Dict[str, List[str]] = {
    "en": ["quiet mode off", "teaching on", "lessons on", "turn teaching on", "you can teach again", "teach me again",
           "teach me"],
    "tr": ["sessiz modu kapat", "ogretmeye basla", "ders ver", "dersleri ac", "bana ogret", "bana anlat"],
    "es": ["modo silencioso off", "ensena otra vez", "lecciones si", "puedes ensenar", "ensename"],
    "de": ["stiller modus aus", "wieder erklaren", "lektionen an", "erklar mir", "erklaer mir"],
    "fr": ["mode silencieux off", "enseigne a nouveau", "lecons oui", "explique moi"],
}

NOT_NOW_PHRASES: Dict[str, List[str]] = {
    "en": ["not now", "skip", "later", "no thanks", "no thank you", "maybe later", "skip it"],
    "tr": ["simdi degil", "sonra", "gec", "hayir tesekkurler", "atla"],
    "es": ["ahora no", "luego", "despues", "no gracias", "salta"],
    "de": ["jetzt nicht", "spater", "nein danke", "uberspringen"],
    "fr": ["pas maintenant", "plus tard", "non merci", "passe"],
}

CONFUSION: Dict[str, List[str]] = {
    "en": [r"i (?:do not|don't|dont) (?:understand|get)", r"(?:do not|don't|dont) get (?:it|this|that)", r"\bconfused\b",
           r"what does (?:that|this) mean", r"makes? no sense", r"(?:you )?lost me", r"too (?:complicated|confusing|much)",
           r"i'?m lost", r"no idea what", r"what\?\?+", r"i can'?t follow"],
    "tr": [r"anlamadim", r"anlamiyorum", r"kafam karisti", r"cok karisik", r"ne demek", r"mantikli degil", r"kayboldum",
           r"cok karmasik", r"anlasilmiyor", r"bir sey anlamadim"],
    "es": [r"no entiendo", r"no comprendo", r"estoy confundid", r"que significa", r"no tiene sentido", r"me perdi", r"demasiado complicado"],
    "de": [r"ich verstehe (?:es |das )?nicht", r"verstehe ich nicht", r"verwirrt", r"was bedeutet", r"keinen sinn", r"bin verloren", r"zu kompliziert"],
    "fr": [r"je ne comprends pas", r"je comprends pas", r"je suis perdu", r"qu'est-ce que (?:ca|cela) veut dire", r"n'a pas de sens", r"confus", r"trop compliqu"],
}

FRUSTRATION: Dict[str, List[str]] = {
    "en": [r"this is (?:stupid|ridiculous|useless)", r"so annoying", r"\bannoying\b", r"\bi hate\b", r"still (?:does not|doesn't|doesnt|not) work",
           r"doesn'?t work again", r"\bwtf\b", r"\bugh+\b", r"\buseless\b", r"waste of time", r"i give up", r"\bffs\b", r"!{3,}", r"again\?+"],
    "tr": [r"sinir", r"biktim", r"calismiyor yine", r"hala calismiyor", r"yine mi", r"sacma", r"berbat", r"vazgectim", r"ise yaramaz", r"lanet"],
    "es": [r"otra vez no", r"sigue sin funcionar", r"estoy harto", r"estoy harta", r"que asco", r"me rindo", r"inutil", r"no funciona otra vez"],
    "de": [r"schon wieder", r"geht (?:immer )?noch nicht", r"\bnervt\b", r"ich gebe auf", r"nutzlos", r"\bmist\b", r"funktioniert immer noch nicht"],
    "fr": [r"encore une fois", r"ne marche toujours pas", r"\bmarre\b", r"j'abandonne", r"\bnul\b", r"inutile", r"enerv", r"ca m'enerve"],
}

ERROR_PATTERNS: Dict[str, List[str]] = {
    "en": [r"Traceback \(most recent call last\)", r"\b\w*Error:", r"\bException\b", r"\bENOENT\b", r"\bEACCES\b", r"\bat line \d+",
           r"is not recognized as", r"command not found", r"npm ERR!", r"\bfatal: ", r"Uncaught ", r"Cannot find module",
           r"ModuleNotFoundError", r"Permission denied", r"No such file or directory", r"\bFAILED\b", r"\bpanic:"],
    "tr": [r"\bhata:", r"hata mesaj", r"bulunamad"],
    "es": [r"\bError de\b", r"no se encontr", r"\bexcepci[oó]n\b"],
    "de": [r"\bFehler:", r"\bAusnahme\b", r"nicht gefunden"],
    "fr": [r"\bErreur ?:", r"\bexception\b", r"introuvable"],
}

GUESS_WORDS: Dict[str, List[str]] = {
    "en": ["i think", "maybe", "probably", "i guess", "perhaps", "because", "looks like", "seems", "my guess", "i suspect"],
    "tr": ["bence", "sanirim", "galiba", "belki", "muhtemelen", "gibi gorunuyor", "tahminim", "cunku"],
    "es": ["creo que", "tal vez", "quizas", "probablemente", "parece", "mi idea", "porque"],
    "de": ["ich glaube", "vielleicht", "wahrscheinlich", "ich denke", "scheint", "weil", "ich vermute"],
    "fr": ["je pense", "peut-etre", "probablement", "je crois", "il semble", "parce que", "je suppose"],
}

# Phrases that mark a "decision sentence" (I chose X over Y because Z); accent-folded when compared.
DECISION: Dict[str, List[str]] = {lang: [str(p) for p in LABELS[lang]["gloss"]] for lang in LANGS}

SYSTEM_PREFIXES: Tuple[str, ...] = ("<task-notification", "<scheduled-task", "<system-reminder", "<command-name",
                                    "<agent-message", "[subagent hand-back]")

# CLAUDE_CODE_ENTRYPOINT value -> (display name, kind). kind: terminal | desktop | vscode | other
SURFACES: Dict[str, Tuple[str, str]] = {
    "cli": ("terminal", "terminal"),
    "sdk-cli": ("terminal (headless)", "terminal"),
    "claude-desktop": ("Desktop app", "desktop"),
    "claude-vscode": ("VS Code extension", "vscode"),
    "claude-jetbrains": ("JetBrains plugin", "other"),
    "claude-code-github-action": ("GitHub Action", "other"),
    "remote": ("web or remote session", "other"),
    "mcp": ("MCP server", "other"),
}


def surface(entrypoint: Optional[str]) -> Tuple[str, str]:
    """(display name, kind) for an entrypoint value; ('unknown', 'unknown') when not set or not known."""
    key = (entrypoint or "").strip().lower()
    if not key:
        return "unknown", "unknown"
    return SURFACES.get(key, (key[:30], "other"))


def is_system_prefix(text: str) -> bool:
    low = text.lstrip().lower()
    return any(low.startswith(p) for p in SYSTEM_PREFIXES)
