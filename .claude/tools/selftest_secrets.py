"""selftest_secrets.py - tests for hooks/lib/secrets.py (the secrets engine).

What it is: a test module with run() -> list of failure messages (empty list = pass). The runner
tools/selftest.py calls run(). You can also run it alone:
    python tools/selftest_secrets.py              (prints failures, exit code 1 if any)
    python tools/selftest_secrets.py --write-report   (rewrites selftest_data/secrets_report.md)
Why it exists: the secrets engine is the last line of defence for keys a beginner pastes into
chat, so every claim of SPEC 7.3 gets a test: the "must catch" provider list, the false-positive
filters, regex safety, the failure path, idempotence, file names.
How it fails safely: every check is wrapped, a crash in one check becomes one failure message,
and nothing here writes outside selftest_data/ (only with --write-report).

Fake secrets are never stored as literals. They are built at run time from fragments and a seeded
random generator, so no scanner finds a key-shaped string in this file and the results repeat.
Python 3.9, standard library only. The regex fuzz runs in a child process with a time limit,
because a regex that backtracks forever cannot be interrupted inside its own process.
"""
from __future__ import annotations

import ast
import base64
import json
import os

_TIME_FACTOR = float(os.environ.get("TUTOR_SELFTEST_TIME_FACTOR", "1") or 1)  # raise it on a slow or shared computer
import random
import re
import string
import subprocess
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

_HERE = os.path.dirname(os.path.abspath(__file__))
_HOOKS = os.path.join(os.path.dirname(_HERE), "hooks")
_LIB_FILE = os.path.join(_HOOKS, "lib", "secrets.py")
_DATA = os.path.join(_HERE, "selftest_data")
_REPORT = os.path.join(_DATA, "secrets_report.md")

A62 = string.ascii_letters + string.digits
B64URL = A62 + "_-"
B64STD = A62 + "+/"
HEX = "0123456789abcdef"
UP27 = string.ascii_uppercase + "234567"
_AT = "@"   # kept apart so that no source line looks like an e-mail address


def _j(*parts: str) -> str:
    """Join fragments. Prefixes of keys are written in pieces so this file holds no key-shaped literal."""
    return "".join(parts)


def _load() -> Any:
    if _HOOKS not in sys.path:
        sys.path.insert(0, _HOOKS)
    from lib import secrets  # noqa: PLC0415 - imported late on purpose
    return secrets


class _Fails:
    """Collects failure messages; each check calls ok(condition, message)."""

    def __init__(self) -> None:
        self.items: List[str] = []

    def ok(self, condition: Any, message: str) -> bool:
        if not condition:
            self.items.append(message)
            return False
        return True


# --------------------------------------------------------------------------- generators


class _Gen:
    def __init__(self, seed: int, sec: Any) -> None:
        self.r = random.Random(seed)
        self.sec = sec

    def pick(self, n: int, alphabet: str) -> str:
        return "".join(self.r.choice(alphabet) for _ in range(n))

    def alnum(self, n: int) -> str:
        return self.pick(n, A62)

    def b64url(self, n: int) -> str:
        return self.pick(n, B64URL)

    def b64(self, n: int) -> str:
        return self.pick(n, B64STD)

    def hex(self, n: int) -> str:
        return self.pick(n, HEX)

    def digits(self, n: int) -> str:
        return self.pick(n, string.digits)

    def letters(self, n: int) -> str:
        return self.pick(n, string.ascii_letters)

    def up27(self, n: int) -> str:
        return self.pick(n, UP27)

    def make(self, fn: Callable[[], str]) -> str:
        """Call fn until the result is not a documentation-style placeholder."""
        for _ in range(500):
            v = fn()
            if not self.sec._PLACEHOLDER.search(v) and not self.sec._SEQUENCE.search(v) and not v.startswith("/"):
                return v
        raise RuntimeError("could not build a fake that avoids the placeholder filter")

    def luhn_number(self, prefix: str, length: int) -> str:
        body = prefix + self.digits(length - len(prefix) - 1)
        for d in range(10):
            if _luhn_ok(body + str(d)):
                return body + str(d)
        raise RuntimeError("no check digit")

    def password(self) -> str:
        words = ["Kedi", "Hunter", "Perro", "Hund", "Chien", "Summer", "Maple", "Falcon", "Zebra", "Tulip", "Nimbus"]
        tail = self.pick(self.r.randint(2, 3), "abcdefghijkmnpqrstuvwxyz")
        sym = self.r.choice(["", "!", "#", "&", "*", "_"])
        return self.r.choice(words) + self.digits(4) + tail + sym


def _luhn_ok(digits: str) -> bool:
    total = 0
    alt = False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


class _Item:
    def __init__(self, label: str, text: str, name: str = "SERVICE_API_KEY", bare: bool = True, strong: bool = True,
                 secret: Optional[str] = None, needles: Optional[List[str]] = None, kind: str = "") -> None:
        self.label = label
        self.text = text
        self.name = name
        self.bare = bare
        self.strong = strong
        self.kind = kind
        core = secret if secret is not None else text
        if needles is None:
            n = len(core)
            needles = [core[-10:], core[n // 2:n // 2 + 8]] if n >= 24 else [core[-8:]]
        self.needles = needles
        self.multiline = "\n" in text


def _corpus(sec: Any) -> List[_Item]:
    g = _Gen(20261007, sec)
    items: List[_Item] = []

    def add(label: str, fn: Callable[[], str], n: int = 2, name: str = "SERVICE_API_KEY", bare: bool = True,
            strong: bool = True, kind: str = "") -> None:
        for i in range(n):
            v = g.make(fn)
            nm = name if (i % 2 == 0 or not bare) else "SERVICE_VALUE"
            items.append(_Item("%s#%d" % (label, i + 1), v, nm, bare, strong, kind=kind))

    # AI providers
    add("anthropic", lambda: _j("sk", "-ant-", "api03-") + g.b64url(93) + "AA", 3)
    add("anthropic-admin", lambda: _j("sk", "-ant-", "admin01-") + g.b64url(93) + "AA", 1)
    add("openai-proj", lambda: _j("sk", "-proj-") + g.b64url(74) + "T3BlbkFJ" + g.b64url(74), 2)
    add("openai-svcacct", lambda: _j("sk", "-svcacct-") + g.b64url(80), 1)
    add("openai-admin", lambda: _j("sk", "-admin-") + g.b64url(80), 1)
    add("openai-legacy", lambda: _j("sk", "-") + g.alnum(48), 2)
    add("openai-classic", lambda: _j("sk", "-") + g.alnum(20) + "T3BlbkFJ" + g.alnum(20), 1)
    add("openrouter", lambda: _j("sk", "-or-v1-") + g.hex(64), 2)
    add("deepseek", lambda: _j("sk", "-") + g.hex(32), 2)
    add("groq", lambda: _j("gsk", "_") + g.alnum(52), 2)
    add("xai", lambda: _j("xai", "-") + g.alnum(80), 2)
    add("perplexity", lambda: _j("pplx", "-") + g.alnum(48), 2)
    add("replicate", lambda: _j("r8", "_") + g.alnum(37), 2)
    add("notion-ntn", lambda: _j("ntn", "_") + g.alnum(46), 1)
    add("notion-secret", lambda: _j("secret", "_") + g.alnum(43), 1)
    add("shopify-at", lambda: _j("shp", "at_") + g.hex(32), 1)
    add("shopify-ss", lambda: _j("shp", "ss_") + g.hex(32), 1)
    add("supabase-pat", lambda: _j("sbp", "_") + g.hex(40), 1)
    add("supabase-secret", lambda: _j("sb_", "secret_") + g.alnum(30), 1)
    # Developer platforms
    for pre in ("ghp", "gho", "ghu", "ghs", "ghr"):
        add("github-" + pre, lambda pre=pre: _j(pre, "_") + g.alnum(36), 1)
    add("github-fine", lambda: _j("github", "_pat_") + g.alnum(22) + "_" + g.alnum(59), 2)
    add("gitlab", lambda: _j("glpat", "-") + g.b64url(20), 2)
    add("npm", lambda: _j("npm", "_") + g.alnum(36), 2)
    add("huggingface", lambda: _j("hf", "_") + g.letters(34), 2)
    add("pypi", lambda: _j("pypi", "-AgEIcHlwaS5vcmc") + g.b64url(70), 1)
    add("docker", lambda: _j("dckr", "_pat_") + g.b64url(27), 1)
    add("sentry", lambda: _j("sntrys", "_") + g.alnum(64), 1)
    add("linear", lambda: _j("lin", "_api_") + g.alnum(40), 1)
    add("square", lambda: _j("sq0", "atp-") + g.b64url(22), 1)
    add("digitalocean", lambda: _j("dop", "_v1_") + g.hex(64), 1)
    # Cloud
    for pre in ("AKIA", "ASIA", "ABIA", "ACCA"):
        add("aws-" + pre, lambda pre=pre: pre + g.up27(16), 1)
    add("aws-secret", lambda: g.b64(40), 2, name="aws_secret_access_key", bare=False)
    add("google-api", lambda: _j("AI", "za") + g.b64url(35), 2, strong=False)
    add("gcp-oauth", lambda: _j("ya", "29.") + g.b64url(100), 1)
    add("gcp-client", lambda: _j("GOCSPX", "-") + g.b64url(28), 1)
    for i in range(2):
        key = g.make(lambda: g.b64(86))
        conn = "DefaultEndpointsProtocol=https;AccountName=demo;AccountKey=" + key + "==;EndpointSuffix=core.windows.net"
        items.append(_Item("azure-key#%d" % (i + 1), conn, "AZURE_STORAGE_CONNECTION_STRING", True, True, secret=key))
    sig = g.make(lambda: g.b64(43))
    items.append(_Item("azure-sas#1", "https://demo.blob.core.windows.net/c/b?sv=2022-11-02&ss=b&sig=" + sig + "%3D",
                       "SAS_URL", True, True, secret=sig))
    # Payments and messaging
    add("stripe-live", lambda: _j("sk", "_live_") + g.alnum(24), 1)
    add("stripe-restricted", lambda: _j("rk", "_live_") + g.alnum(24), 1)
    add("stripe-test", lambda: _j("sk", "_test_") + g.alnum(24), 1)
    add("stripe-hook", lambda: _j("whsec", "_") + g.alnum(32), 1)
    add("slack-bot", lambda: _j("xox", "b-") + g.digits(12) + "-" + g.digits(12) + "-" + g.alnum(24), 1)
    add("slack-user", lambda: _j("xox", "p-") + g.digits(12) + "-" + g.digits(12) + "-" + g.digits(12) + "-" + g.hex(32), 1)
    add("slack-app", lambda: _j("xapp", "-1-") + g.up27(11) + "-" + g.digits(13) + "-" + g.hex(64), 1)
    add("slack-hook", lambda: "https://hooks.slack.com/services/T" + g.up27(8) + "/B" + g.up27(10) + "/" + g.alnum(24), 1)
    add("discord-hook", lambda: "https://discord.com/api/webhooks/" + g.digits(18) + "/" + g.b64url(68), 1)
    add("discord-bot", lambda: "M" + g.alnum(23) + "." + g.alnum(6) + "." + g.b64url(27), 2)
    add("telegram", lambda: g.digits(9) + ":A" + g.b64url(34), 2)
    add("twilio-sk", lambda: _j("S", "K") + g.hex(32), 1)
    add("sendgrid", lambda: _j("S", "G.") + g.b64url(22) + "." + g.b64url(43), 2)
    add("mailgun", lambda: _j("key", "-") + g.hex(32), 1)
    # Tokens
    add("jwt", lambda: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ" + g.b64url(36) + "." + g.b64url(43), 2, strong=False)
    for label in ("RSA PRIVATE KEY", "OPENSSH PRIVATE KEY", "EC PRIVATE KEY", "PGP PRIVATE KEY BLOCK",
                  "ENCRYPTED PRIVATE KEY", "PRIVATE KEY"):
        body = [g.make(lambda: g.b64(64)) for _ in range(5)]
        pem = _pem(label.replace(" PRIVATE KEY", "").replace(" BLOCK", ""), "\n".join(body))
        if label.endswith("BLOCK"):
            pem = pem.replace("KEY-----", "KEY BLOCK-----")
        items.append(_Item("pem-" + label.split()[0].lower(), pem, "PRIVATE_KEY", True, True, secret=body[0],
                           needles=[body[0][10:30], body[3][20:40]]))
    for scheme in ("postgres", "postgresql", "mysql", "mongodb+srv", "rediss", "amqps", "mssql"):
        pw = g.make(lambda: g.alnum(14))
        user = "" if scheme == "rediss" else "appuser"
        url = "%s://%s:%s" % (scheme, user, pw) + _AT + "db-prod.internal.net:5432/app"
        items.append(_Item("dburl-" + scheme, url, "DATABASE_URL", True, True, secret=pw, needles=[pw]))
    for i in range(2):
        pw = g.make(lambda: g.alnum(24))
        items.append(_Item("url-basic#%d" % (i + 1), "https://ada:%s" % pw + _AT + "git.internal.net/team/repo.git", "REMOTE_URL",
                           True, True, secret=pw, needles=[pw[-12:]]))
    for i in range(2):
        tok = g.make(lambda: g.alnum(40))
        items.append(_Item("bearer#%d" % (i + 1), "Authorization: Bearer " + tok, "HEADER", True, True, secret=tok))
    basic = base64.b64encode(("ada:" + g.make(lambda: g.alnum(14))).encode()).decode()
    items.append(_Item("basic#1", "Authorization: Basic " + basic, "HEADER", True, True, secret=basic, needles=[basic[-12:]]))
    tok = g.make(lambda: g.hex(40))
    items.append(_Item("token-header#1", "Authorization: token " + tok, "HEADER", True, True, secret=tok))
    # Cards (Luhn-valid, known prefixes)
    cards = [("visa16", g.luhn_number("4", 16), False), ("visa19", g.luhn_number("4", 19), False),
             ("mastercard", g.luhn_number("5" + str(g.r.randint(1, 5)), 16), False),
             ("mastercard2", g.luhn_number("2" + str(g.r.randint(3, 6)), 16), False),
             ("discover", g.luhn_number("6011", 16), False), ("jcb", g.luhn_number("35", 16), False),
             ("diners", g.luhn_number("36", 14), False)]
    for label, number, _f in cards:
        items.append(_Item("card-" + label, number, "CARD", True, False, needles=[number[-9:]], kind="card"))
    v = g.luhn_number("4", 16)
    spaced = " ".join([v[0:4], v[4:8], v[8:12], v[12:16]])
    items.append(_Item("card-visa-spaced", spaced, "CARD", True, False, needles=[spaced[-9:]], kind="card"))
    v = g.luhn_number("37", 15)
    amex = " ".join([v[0:4], v[4:10], v[10:15]])
    items.append(_Item("card-amex-spaced", amex, "CARD", True, False, needles=[amex[-9:]], kind="card"))
    v = g.luhn_number("5" + str(g.r.randint(1, 5)), 16)
    dashed = "-".join([v[0:4], v[4:8], v[8:12], v[12:16]])
    items.append(_Item("card-mc-dashed", dashed, "CARD", True, False, needles=[dashed[-9:]], kind="card"))
    # Values that only a name gives away
    add("mistral-style", lambda: g.alnum(32), 2, name="MISTRAL_API_KEY", bare=False)
    add("cohere-style", lambda: g.alnum(40), 1, name="CO_API_KEY", bare=False)
    add("twilio-auth", lambda: g.hex(32), 1, name="TWILIO_AUTH_TOKEN", bare=False)
    add("heroku-uuid", lambda: "-".join([g.hex(8), g.hex(4), g.hex(4), g.hex(4), g.hex(12)]), 1,
        name="HEROKU_API_KEY", bare=False)
    add("vercel-style", lambda: g.alnum(24), 1, name="VERCEL_TOKEN", bare=False)
    add("cloudflare-style", lambda: g.alnum(40), 1, name="CLOUDFLARE_API_TOKEN", bare=False)
    add("jwt-secret", lambda: g.alnum(32), 2, name="JWT_SECRET", bare=False)
    add("service-role-jwt", lambda: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJyb2xlIjoic2VydmljZV9yb2xlIn0." + g.b64url(43), 1,
        name="SUPABASE_SERVICE_ROLE_KEY", bare=True, strong=False)
    # Human-chosen passwords (weak by shape) and one long random one (strong)
    for i in range(6):
        pw = g.make(g.password)
        items.append(_Item("password#%d" % (i + 1), pw, "DB_PASSWORD", False, False, needles=[pw[-6:], pw[:6]], kind="password"))
    add("password-long", lambda: g.pick(22, A62 + "!#&*"), 2, name="ADMIN_PASSWORD", bare=False)
    return items


def _json_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _contexts(item: _Item) -> Dict[str, str]:
    s = item.text
    out: Dict[str, str] = {}
    if item.bare:
        out["bare"] = s
    if item.multiline:
        out["env"] = '%s="%s"\n' % (item.name, s)
        out["prose"] = "Here is my key:\n%s\nand I need help." % s
    else:
        out["env"] = "%s=%s\n" % (item.name, s)
        if item.kind == "password":
            out["prose"] = "my password is %s and I need help." % s
        else:
            out["prose"] = "Here is my api key: %s and I need help." % s
    out["json"] = '{"%s": "%s"}' % (item.name.lower(), _json_escape(s))
    return out


def _check_context(f: _Fails, sec: Any, item: _Item, ctx: str, text: str) -> None:
    tag = "%s/%s" % (item.label, ctx)
    out = sec.redact(text)
    f.ok("[hidden:" in out, "corpus %s: nothing was hidden" % tag)
    for n in item.needles:
        f.ok(n not in out, "corpus %s: secret piece survived redact: %r" % (tag, n[:6] + "..."))
    if item.kind == "card":
        # Changed on purpose: a card number hides its whole note (the lines up to a blank line), so the
        # name, the JSON quotes and the words around the number are hidden too (CVC and expiry included).
        f.ok(out.strip() == "[hidden: card]", "corpus %s: the card note was not hidden as a whole: %r" % (tag, out[:60]))
    elif ctx == "env":
        f.ok(out.startswith(item.name + "="), "corpus %s: the NAME= part was damaged: %r" % (tag, out[:40]))
    elif ctx == "json":
        f.ok(out.startswith('{"' + item.name.lower() + '": "') and out.endswith('"}'),
             "corpus %s: JSON shape damaged: %r" % (tag, out[-30:]))
    elif ctx == "prose":
        f.ok(out.rstrip().endswith("help."), "corpus %s: words after the secret were swallowed: %r" % (tag, out[-30:]))
    f.ok(sec.redact(out) == out, "corpus %s: redact is not idempotent" % tag)
    hits = sec.find_secrets(text)
    f.ok(len(hits) >= 1, "corpus %s: find_secrets found nothing" % tag)
    for h in hits:
        f.ok(0 <= h.start < h.end <= len(text), "corpus %s: hit offsets out of range" % tag)
        value = text[h.start:h.end]
        f.ok(h.preview_masked != value or len(value) <= 3, "corpus %s: preview is the whole secret" % tag)
        for n in item.needles:
            f.ok(n not in h.preview_masked, "corpus %s: preview leaks a secret piece" % tag)
    if ctx == "bare":
        strong_hits = sec.scan_text(text)
        weak_hits = sec.scan_text(text, strong_only=False)
        f.ok(len(weak_hits) >= 1, "corpus %s: scan_text(strong_only=False) found nothing" % tag)
        if item.strong:
            f.ok(len(strong_hits) >= 1, "corpus %s: scan_text found no strong hit" % tag)
        else:
            f.ok(len(strong_hits) == 0, "corpus %s: weak shape reported as strong: %r" % (tag, list(strong_hits)))


def _test_corpus(f: _Fails, sec: Any) -> None:
    items = _corpus(sec)
    f.ok(len(items) >= 120, "corpus has only %d fakes (need >= 120)" % len(items))
    for item in items:
        for ctx, text in _contexts(item).items():
            try:
                _check_context(f, sec, item, ctx, text)
            except Exception as exc:  # noqa: BLE001
                f.ok(False, "corpus %s/%s raised %s" % (item.label, ctx, type(exc).__name__))
    # prose passwords in five languages
    g = _Gen(77, sec)
    templates = {
        "en": ["my password is {}", "the password: {}", "password {}"],
        "tr": ["\u015fifrem: {}", "\u015fifre {}", "parolam {}"],
        "es": ["mi contrase\u00f1a es {}", "mi contrasena es {}", "contrase\u00f1a: {}"],
        "de": ["mein Passwort ist {}", "Passwort: {}", "mein passwort {}"],
        "fr": ["mon mot de passe est {}", "mot de passe : {}", "mon mot de passe {}"],
    }
    count = 0
    for lang, forms in templates.items():
        for form in forms:
            for _ in range(2):
                pw = g.make(g.password)
                text = "ok, " + form.format(pw) + " ok thanks"
                out = sec.redact(text)
                count += 1
                f.ok(pw not in out and pw[:6] not in out and "[hidden:" in out,
                     "prose password (%s) not hidden: %r" % (lang, form))
                f.ok(out.startswith("ok, ") and out.endswith(" ok thanks"),
                     "prose password (%s) swallowed neighbours: %r" % (lang, out))
                f.ok(sec.redact(out) == out, "prose password (%s) not idempotent" % lang)
    f.ok(count >= 30, "prose password test ran %d cases" % count)


def _test_notes_and_cards(f: _Fails, sec: Any) -> None:
    """Prose passwords named in German, Spanish and French, and card notes (CVC, security code, expiry)."""
    g = _Gen(91, sec)
    templates = {
        "de": ["mein Kennwort ist {}", "Kennwort: {}", "mein kennwort {}"],
        "es": ["mi clave es {}", "clave: {}", "mi clave {}"],
        "fr": ["ma clé est {}", "clé : {}", "mon code secret est {}", "mot de passe : {}",
               "mot-de-passe : {}"],
    }
    count = 0
    for lang, forms in templates.items():
        for form in forms:
            pw = g.make(g.password)
            text = "ok, " + form.format(pw) + " ok thanks"
            out = sec.redact(text)
            count += 1
            f.ok(pw not in out and pw[:6] not in out and "[hidden:" in out,
                 "prose password (%s) not hidden: %r" % (lang, form))
            f.ok(out.startswith("ok, ") and out.endswith(" ok thanks"),
                 "prose password (%s) swallowed neighbours: %r" % (lang, out))
            f.ok(sec.redact(out) == out, "prose password (%s) not idempotent" % lang)
    f.ok(count == 11, "prose password (five languages) ran %d cases, wanted 11" % count)
    # the new keywords are whole words or the named forms only: "clean" and "client" are not passwords
    f.ok(sec.redact("the client uses Node20 in production") == "the client uses Node20 in production",
         "clean/client must not trigger the cle keyword")
    # card notes: the card number and the words of its note are hidden, in five languages
    card = g.luhn_number("4", 16)
    notes = [
        "card %s exp 12/30 cvc 123",
        "kart %s son kullanma 12/30 cvv 123 tamam",
        "Karte %s gültig bis 12/30 Sicherheitscode 123 danke",
        "tarjeta %s caduca 12/30 código de seguridad 123 gracias",
        "carte %s expire 12/30 cryptogramme 123 merci",
    ]
    for form in notes:
        out = sec.redact(form % card)
        f.ok(out == "[hidden: card]", "card note hidden as a whole: %r -> %r" % (form[:12], out[:60]))
        f.ok(card not in out and "12/30" not in out and "123" not in out, "card note leaks its CVC or expiry: %r" % out[:60])
    # a note over several lines is hidden up to its blank line only
    multi = "Card: %s\nExpiry: 12/30\nCVC: 123\n\nnext paragraph stays" % card
    out = sec.redact(multi)
    f.ok(out == "[hidden: card]\n\nnext paragraph stays", "multi-line card note: %r" % out[:80])
    two = "first note line one\n\nCard %s exp 12/30\n\nlast note line" % card
    f.ok(sec.redact(two) == "first note line one\n\n[hidden: card]\n\nlast note line",
         "a card note does not cross a blank line: %r" % sec.redact(two)[:90])
    # a long line keeps its words far from the card (about 600 characters each side)
    far = "w " * 1000 + "card " + card + " " + "z " * 1000
    out = sec.redact(far)
    f.ok(out.startswith("w w w") and out.rstrip().endswith("z z z") and card not in out,
         "a card note is widened by at most 600 characters each way")
    # an earlier hidden marker is never covered by the widened note (the marker stays, the card is hidden)
    marked = "pw [hidden: password] card %s cvc 123" % card
    out = sec.redact(marked)
    f.ok(out.startswith("pw [hidden: password]") and card not in out and "123" not in out,
         "a card note next to a hidden marker: %r" % out[:80])
    f.ok(sec.redact(out) == out, "card notes are idempotent")


# --------------------------------------------------------------------------- false positives


def _fp_probes(sec: Any) -> List[str]:
    r = random.Random(4242)

    def hexs(n: int) -> str:
        return "".join(r.choice(HEX) for _ in range(n))

    def b64(n: int) -> str:
        return "".join(r.choice(B64STD) for _ in range(n))

    at = "@"
    email = "ada" + at + "example.org"
    home_key = _j("/ho", "me/ada/.ssh/id_rsa")
    png = base64.b64encode(bytes(r.randint(0, 255) for _ in range(900))).decode()
    mini = ["function(e,t,n){return e&&t?n[e](t):void 0}", "if(e.key===\"Enter\"){this.submit(e.target.value)}",
            "var a=e.token?e.token:null,b=a&&a.length>3;", "t.keys=Object.keys(n).map(function(k){return k+\"=\"+n[k]})",
            "case\"password\":return e.password===t.password;", "key=>key.length>2&&key[0]!==\"_\"",
            "const s=await getToken(),i={headers:{Authorization:`Bearer ${s}`}};"]
    minified = ";".join(r.choice(mini) + "," + hexs(3) for _ in range(60))
    probes = [
        # hashes and ids
        "commit 3f786850e387550fdab836ed7e6dc881de23001b",
        "9fceb02d0ae598e95dc970b74767f19372d61af8 Fix typo in README",
        "id: 123e4567-e89b-12d3-a456-426614174000",
        "digest: " + hexs(64),
        "md5 " + hexs(32),
        '"integrity": "sha512-' + b64(86) + '=="',
        "integrity sha512-" + b64(86) + "==",
        'hash = "sha256:' + hexs(64) + '"',
        'checksum = "' + hexs(64) + '"',
        "golang.org/x/text v0.3.0 h1:" + b64(43) + "=",
        "data:image/png;base64," + png,
        "src: url(data:font/woff2;base64," + b64(600) + ") format('woff2');",
        '<img src="data:image/jpeg;base64,' + b64(900) + '" alt="x">',
        minified,
        "version = 1.2.3-beta.4+build.5",
        "Python 3.12.1 on win32 and node v20.11.0",
        "ts=1700000000000 at 2026-10-07T19:42:00+03:00",
        "call +90 555 123 45 67 or 0090 555 123 4567",
        "server 192.168.0.1 and 2001:0db8:85a3:0000:0000:8a2e:0370:7334",
        "color: #ff00aa; background: #00112233;",
        "mail " + email + " or git" + at + "github.com:me/repo.git",
        "open http://localhost:3000/api/users?page=2&limit=50",
        "order 4111111111111112 was refused",          # 16 digits, fails the Luhn test
        "barcode 4006381333931",                       # 13 digits, no separators
        "snowflake 1100000000000000001 id",
        "numbers 12 34 56 78 90 12 34 56 78 90 12 34 56 78",
        # code that mentions names without values
        'password = request.form["password"]',
        "def check_password(password):",
        'const [password, setPassword] = useState("")',
        "password: str",
        "password: Optional[str] = None",
        'password = input("Password: ")',
        '<input type="password" name="password" placeholder="Password">',
        "const key = process.env.OPENAI_API_KEY",
        "process.env.API_KEY",
        'api_key = os.environ["API_KEY"]',
        'token = os.getenv("TOKEN")',
        "import.meta.env.VITE_API_KEY",
        "TOKEN_EXPIRY=3600",
        "KEYBOARD_LAYOUT=us",
        "AUTHOR=Ada Lovelace",
        "MONKEY=banana",
        'const token = localStorage.getItem("token")',
        'headers = {"Authorization": f"Bearer {token}"}',
        'curl -H "Authorization: Bearer $TOKEN" https://api.example.com',
        "if (user.password !== password) { return false }",
        "bcrypt.hash(password, 10)",
        "password_hash = generate_password_hash(password)",
        'passwordHash: "$2b$10$abcdefghijklmnopqrstuuABCDEFGHIJKLMNOPQRSTUVWXYZ012"',
        "secret = secrets.token_hex(16)",
        'SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")',
        "key: ${{ secrets.NPM_TOKEN }}",
        "NEXT_PUBLIC_API_URL=https://api.example.com",
        "GOOGLE_APPLICATION_CREDENTIALS=./service-account.json",
        "SSH_KEY_PATH=" + home_key,
        '"keywords": ["api", "key"], "keyboard": true',
        "auth: required",
        "auth_method: oauth2",
        "AUTHORS=Ada, Grace",
        "token_type: bearer",
        '"key": "welcome_message_title_text"',
        'description: "This token is used to access the API and must be kept private"',
        "if (e.key === 'Enter') submit()",
        # README and chat text
        "Never commit your API key to Git.",
        "Put your token in the .env file and add .env to .gitignore.",
        "The password field should be hashed before it is stored.",
        "A strong password has at least 12 characters, for example a passphrase of four words.",
        "Reset your password from the login screen; the reset email arrives within 5 minutes.",
        "password must contain Uppercase letters",
        "Password: Required",
        "Enter your password (8+ characters)",
        "The secret to good code is tests.",
        "the key is to keep functions small",
        "the client uses Node20 in production",         # cle is a whole word only
        "clean build with Python3 today",
        "la clave del examen es importante",            # no digits, no value
        "la clé de voûte est fragile",
        "El código secreto es un mito",           # a Spanish word, not the keyword code secret
        "palabra clave importante para el examen",
        "Kennwort vergessen? Bitte zurücksetzen.",
        "mot de passe oublié, réinitialisez-le depuis l'écran de connexion",
        "the authentication token expires after 24 hours",
        "I forgot my password again",
        "\u015fifremi unuttum, \u015fifre s\u0131f\u0131rlama ekran\u0131n\u0131 yaz",
        "parola alan\u0131 bo\u015f olmamal\u0131",
        "contrase\u00f1a incorrecta",
        "Passwort vergessen? mot de passe oubli\u00e9",
        "password hashing with sha256 and bcrypt2",
        "password changed on 2024-01-15",
        "password length 12",
        "password reset at 10:45:30",
        "password in config2.json",
        "password sent to ada2" + at + "example.org",
        # placeholders and examples
        "OPENAI_API_KEY=your-api-key-here",
        "ANTHROPIC_API_KEY=" + _j("sk", "-ant-") + "xxxxxxxx",
        "AWS_ACCESS_KEY_ID=" + _j("AKIA", "IOSFODNN7", "EXAMPLE"),
        "aws_secret_access_key = " + _j("wJalrXUtnFEMI/K7MDENG/bPxRfiCY", "EXAMPLEKEY"),
        "GITHUB_TOKEN=" + _j("gh", "p_") + "x" * 36,
        "Authorization: Bearer <token>",
        'password: "${DB_PASSWORD}"',
        "DATABASE_URL=postgres://user:password@localhost:5432/mydb",
        'password = ""',
        'password = "abc"',
        "# password: the password you chose",
        "STRIPE_KEY=" + _j("sk", "_live_") + "<your key>",
        "API_KEY=...",
        "TOKEN=<paste your token here>",
        "secret: changeme",
        # plain language
        "The quick brown fox jumps over the lazy dog. " * 40,
        "Istanbul'da hava g\u00fczel, \u00e7ay i\u00e7elim \u2615 ve kod yazal\u0131m \U0001F600",
    ]
    return probes


def _test_false_positives(f: _Fails, sec: Any) -> None:
    probes = _fp_probes(sec)
    f.ok(len(probes) >= 60, "only %d false-positive probes (need >= 60)" % len(probes))
    for p in probes:
        out = sec.redact(p)
        if out != p:
            f.ok(False, "false positive: %r became %r" % (p[:70], out[:90]))
        hits = sec.find_secrets(p)
        f.ok(len(hits) == 0, "false positive hit in find_secrets: %r -> %r" % (p[:60], list(hits)[:2]))
        f.ok(len(sec.scan_text(p, strong_only=False)) == 0, "false positive hit in scan_text: %r" % p[:60])


# --------------------------------------------------------------------------- the two modes


def _test_key_bodies(f: _Fails, sec: Any) -> None:
    """Key material pasted without its header line is still hidden; a public certificate is not."""
    g = _Gen(6, sec)
    starts = {"openssh": "b3BlbnNzaC1rZXktdjE", "pkcs8 rsa": "MIIEvQIBADANBgkqhkiG9w0BAQEFAASC",
              "pkcs1 rsa": "MIIEowIBAAKC", "pkcs1 rsa 1024": "MIICXAIBAAKB", "sec1 ec": "MHcCAQEEI",
              "pkcs8 ec": "MIGHAgEAMBMGByqGSM49", "ed25519": "MC4CAQAwBQYDK2VwBCIEI"}
    for name, start in starts.items():
        body = start + g.b64(60)
        out = sec.redact("line: " + body + "\nnext")
        f.ok(out == "line: [hidden: private key]\nnext", "key body (%s) not hidden: %r" % (name, out[:50]))
        f.ok(len(sec.scan_text(body)) == 1, "key body (%s) must be a strong guard hit" % name)
    cert = "MIIDdzCCAl+gAwIBAgIEAgAAuTANBgkqhkiG9w0BAQUFADBaMQswCQYDVQQGEwJJRTESMBAGA1UEChMJQmFsdGltb3JlMRMwEQYDVQQLEwpDeWJlclRydXN0"
    f.ok(sec.redact(cert) == cert, "a public certificate body must stay visible")


def _test_modes(f: _Fails, sec: Any) -> None:
    g = _Gen(5, sec)
    keyboard = _j("gh", "p_") + "abcdefghijklmnopqrstuvwxyz0123456789"
    f.ok(sec.redact("token " + keyboard) != "token " + keyboard, "store mode must hide a keyboard-run token")
    f.ok(len(sec.scan_text("token " + keyboard)) == 0, "guard mode must ignore a keyboard-run documentation token")
    real = _j("gh", "p_") + g.make(lambda: g.alnum(36))
    f.ok(len(sec.scan_text("token " + real)) == 1, "guard mode must catch a random token")
    doc = _j("AKIA", "IOSFODNN7", "EXAMPLE")
    f.ok(sec.redact(doc) == doc, "the AWS documentation example key must stay visible")
    f.ok(len(sec.scan_text(doc, strong_only=False)) == 0, "the AWS documentation example key must not be a guard hit")
    # human passwords that contain a keyboard run are still passwords
    f.ok("[hidden:" in sec.redact("DB_PASSWORD=Summer" + "1234567" + "x"), "a password with a digit run must be hidden")
    # weak hits are not reported to the guard by default
    weak = "my password is " + g.make(g.password)
    f.ok(len(sec.scan_text(weak)) == 0, "a prose password is weak and must not reach the guard by default")
    f.ok(len(sec.scan_text(weak, strong_only=False)) == 1, "a prose password must be visible with strong_only=False")


# --------------------------------------------------------------------------- failure path, caps, idempotence


class _Boom:
    """A stand-in for a compiled regex that raises."""

    def finditer(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("boom")

    def match(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("boom")

    def search(self, *a: Any, **k: Any) -> Any:
        raise RuntimeError("boom")


def _test_failure_path(f: _Fails, sec: Any) -> None:
    g = _Gen(9, sec)
    secret_text = "hello Ada, my key is " + _j("gh", "p_") + g.make(lambda: g.alnum(36)) + " thanks"
    rule = next(r for r in sec._RULES if r.name == "github")
    saved = rule._rx
    try:
        rule._rx = _Boom()
        out = sec.redact(secret_text)
        f.ok(out == "[hidden: redaction failed, %d chars]" % len(secret_text), "failure marker wrong: %r" % out[:60])
        f.ok("hello" not in out and "thanks" not in out, "failure output contains input text")
        hits = sec.find_secrets(secret_text)
        f.ok(hits.error != "" and hits.truncated, "find_secrets must flag an internal error")
        f.ok(sec.scan_text(secret_text).error != "", "scan_text must flag an internal error")
    finally:
        rule._rx = saved
    f.ok("[hidden:" in sec.redact(secret_text) and "thanks" in sec.redact(secret_text), "redact does not work again after the patch")
    # a failing procedural scanner
    saved_named = sec._scan_named
    try:
        def boom(*a: Any, **k: Any) -> None:
            raise ValueError("boom")
        sec._scan_named = boom
        txt = "SERVICE_PASSWORD=" + g.make(g.password) + " and more words"
        out = sec.redact(txt)
        f.ok(out.startswith("[hidden: redaction failed") and "more words" not in out, "scanner failure leaked text: %r" % out[:50])
    finally:
        sec._scan_named = saved_named
    # a time overrun
    real_monotonic = sec.time.monotonic
    ticks = [0.0]

    def fast_clock() -> float:
        ticks[0] += 1000.0
        return ticks[0]
    try:
        sec.time.monotonic = fast_clock
        out = sec.redact("plain text " * 50 + " password: " + g.make(g.password))
        f.ok(out.startswith("[hidden: redaction failed"), "a time overrun must return the failure marker: %r" % out[:40])
    finally:
        sec.time.monotonic = real_monotonic
    # odd input
    f.ok(sec.redact("") == "" and sec.redact(None) == "", "empty input")
    f.ok(sec.redact(b"plain bytes") == "plain bytes", "bytes input")
    f.ok(isinstance(sec.redact(12345), str), "non-text input")
    f.ok(len(sec.find_secrets(None)) == 0 and len(sec.find_secrets(b"")) == 0, "find_secrets on empty input")
    f.ok(sec.is_secret_filename(None) is False and sec.looks_like_real(None) is False, "None input to helpers")


def _test_caps_and_time(f: _Fails, sec: Any) -> None:
    g = _Gen(11, sec)
    filler = "The quick brown fox jumps over the lazy dog. "
    token = _j("gh", "p_") + g.make(lambda: g.alnum(36))
    head_text = "start " + token + " end\n" + filler * 60000      # about 2.7 MB
    t = time.perf_counter()
    out = sec.redact(head_text)
    dt = time.perf_counter() - t
    f.ok(dt < 3.0, "redact of 2.7 MB took %.2f s (limit 3 s)" % dt)
    f.ok(token[-12:] not in out and "[hidden: GitHub token]" in out, "secret in the first 256 KB must be hidden in a big text")
    f.ok(out.endswith("characters not checked]") and len(out) < sec.MAX_SCAN + 200, "the unchecked tail must be replaced by a note")
    tail_text = filler * 60000 + token
    out = sec.redact(tail_text)
    f.ok(token[-12:] not in out, "a secret beyond the scan cap must not appear in the output")
    t = time.perf_counter()
    hits = sec.scan_text(head_text, 2 * 1024 * 1024)
    dt = time.perf_counter() - t
    f.ok(dt < 3.0, "scan_text of 2 MB took %.2f s (limit 3 s)" % dt)
    f.ok(hits.truncated and hits.scanned == 2 * 1024 * 1024, "scan_text must report truncation and scanned size")
    hits = sec.find_secrets(head_text)
    f.ok(hits.truncated and hits.scanned == sec.MAX_SCAN, "find_secrets must report the 256 KB cap")
    f.ok(sec.scan_text("short", 3).scanned == 3 and sec.scan_text("short", 3).truncated, "scan_text(max_bytes=3)")
    # pathological shapes through the whole pipeline
    n = 100000
    shapes = {"a.": "a." * (n // 2), "sk-": "sk-" * (n // 3), "x": "x" * n, "space": " " * n,
              "password=": "password=" * (n // 9), "A=": "A" * n + "=", "newline": "\n" * n, "curl": "curl " * (n // 5),
              "key=": "key=" * (n // 4), "eyJ": "eyJ" * (n // 3), "token: ": "token: " * (n // 7),
              "my password is ": "my password is " * (n // 15), "1 ": "1 " * (n // 2), "ghp_": "ghp_" * (n // 4),
              "-----BEGIN ": "-----BEGIN " * (n // 11), "Bearer ": "Bearer " * (n // 7)}
    for name, text in shapes.items():
        t = time.perf_counter()
        sec.redact(text)
        sec.scan_text(text, strong_only=False)
        dt = time.perf_counter() - t
        f.ok(dt < 1.5, "pipeline on shape %r (100 KB) took %.2f s" % (name, dt))


def _test_boundaries(f: _Fails, sec: Any) -> None:
    g = _Gen(13, sec)
    filler = "The quick brown fox jumps over the lazy dog. "
    base = (filler * 3000)
    step = sec.CHUNK - sec.OVERLAP
    token = _j("gh", "p_") + g.make(lambda: g.alnum(36))
    long_token = _j("sk", "-ant-", "api03-") + g.make(lambda: g.b64url(700))
    named = "SERVICE_API_KEY=" + g.make(lambda: g.alnum(40))
    for boundary in (sec.CHUNK, step, step + sec.CHUNK - sec.OVERLAP, 2 * sec.CHUNK - 2 * sec.OVERLAP):
        for label, tok, pieces in (("token", token, (token[:12], token[-12:])),
                                   ("long token", long_token, (long_token[40:60], long_token[300:320], long_token[-20:])),
                                   ("named value", named, (named[20:32], named[-12:]))):
            span = len(tok)
            for off in range(-span - 8, 10, max(1, span // 9 + 1)):
                at = boundary + off
                text = base[:at] + " " + tok + " " + base[:50]
                out = sec.redact(text)
                bad = [p for p in pieces if p in out]
                if bad or out.count("[hidden:") != 1:
                    f.ok(False, "%s across the %d boundary at offset %d: pieces left %d, markers %d"
                         % (label, boundary, off, len(bad), out.count("[hidden:")))
                    break


def _test_mixed_texts(f: _Fails, sec: Any) -> None:
    """Secrets glued between other secrets and harmless lines, with Unix and Windows line ends."""
    r = random.Random(32)
    pieces: List[Tuple[str, List[str]]] = []
    for it in _corpus(sec):
        for text in _contexts(it).values():
            pieces.append((text, it.needles))
    probes = _fp_probes(sec)
    seps = [" ", "\n", ", ", " and ", "\r\n", "\t", "; "]
    for i in range(250):
        chosen = [r.choice(pieces) for _ in range(r.randint(2, 5))]
        parts = [c[0] for c in chosen]
        if r.random() < 0.6:
            parts.insert(r.randint(0, len(parts)), r.choice(probes))
        text = r.choice(seps).join(parts)
        if r.random() < 0.3:
            text = text.replace("\n", "\r\n")
        out = sec.redact(text)
        bad = [n for c in chosen for n in c[1] if n in out]
        if bad:
            f.ok(False, "mixed text %d: %d secret pieces survived (first %r)" % (i, len(bad), bad[0][:6] + "..."))
            break
        if sec.redact(out) != out:
            f.ok(False, "mixed text %d: not idempotent" % i)
            break
    for it in _corpus(sec)[:60]:
        for ctx, text in _contexts(it).items():
            crlf = text.replace("\n", "\r\n")
            out = sec.redact(crlf)
            if any(n in out for n in it.needles):
                f.ok(False, "CRLF %s/%s: a secret piece survived" % (it.label, ctx))


def _test_long_values(f: _Fails, sec: Any) -> None:
    """A value or token longer than the look-ahead windows must not leave its tail visible."""
    g = _Gen(41, sec)
    for n in (300, 700, 1500, 3000):
        blob = g.make(lambda: g.b64(n).replace("/", "A").replace("+", "B"))
        pieces = [blob[i:i + 20] for i in (0, 200, 590, 610, n // 2, n - 30) if i + 20 <= n]
        cases = {
            "env": "SERVICE_CREDENTIALS_B64=%s\nNEXT=1" % blob,
            "json": '{"service_secret": "%s", "ok": true}' % blob,
            "prose": "my token is %s and that is all" % blob,
            "prose-key": "api key: %s thanks" % blob,
        }
        for label, text in cases.items():
            out = sec.redact(text)
            left = [p for p in pieces if p in out]
            f.ok(not left and out.count("[hidden:") == 1,
                 "long value (%d chars, %s): %d pieces left, %d markers" % (n, label, len(left), out.count("[hidden:")))
        f.ok(sec.redact(cases["env"]).endswith("\nNEXT=1"), "long value swallowed the next line")
        f.ok(sec.redact(cases["json"]).endswith('", "ok": true}'), "long value swallowed the JSON tail")


def _test_idempotence_and_text(f: _Fails, sec: Any) -> None:
    samples = []
    for item in _corpus(sec):
        samples.extend(_contexts(item).values())
    for s in samples:
        once = sec.redact(s)
        f.ok(sec.redact(once) == once, "not idempotent: %r" % s[:40])
    mixed = "Merhaba! \u015eifre s\u0131f\u0131rlama sayfas\u0131n\u0131 yaz\u0131yoruz. \u00c7\u0131k\u0131\u015f d\u00fc\u011fmesi \u2615 \U0001F600 ok"
    f.ok(sec.redact(mixed) == mixed, "Turkish and emoji text must stay untouched")
    marker_text = "x [hidden: password] y [hidden: card] z"
    f.ok(sec.redact(marker_text) == marker_text, "existing markers must stay as they are")
    f.ok(sec.redact("password: [hidden: Anthropic API key]") == "password: [hidden: Anthropic API key]",
         "a marker after the word password must not be hidden again")


# --------------------------------------------------------------------------- file names


def _test_filenames(f: _Fails, sec: Any) -> None:
    win_ssh = _j("C:", "\\Users\\me\\.ssh\\config")
    yes = [".env", ".env.local", ".env.production", "app/.env", _j("C:", "\\proj\\.env"), "prod.env", ".envrc", "id_rsa",
           "id_ed25519", "~/.ssh/id_rsa", "server.pem", "cert.p12", "my.keystore", "release.jks", ".npmrc", ".pypirc",
           ".netrc", ".git-credentials", "credentials.json", "client_secret.json", "client_secret_123.apps.json",
           "service-account-prod.json", "terraform.tfstate", "terraform.tfstate.backup", "terraform.tfvars",
           ".aws/credentials", "kubeconfig", "secrets.yaml", "secrets.json", "google-services.json", "wp-config.php",
           ".pgpass", "private.key",
           ".env.bak", ".env.staging.local", "docker.env", ".ENV", _j("C:", "\\proj\\sub\\.env.production"),
           "~/.aws/config", "~/.config/gh/hosts.yml", "~/.docker/config.json", "id_rsa_work", "id_ed25519_sk",
           "server.key", "AuthKey_ABC123.p8", "app.keystore", "firebase-adminsdk-abc12.json", "prod.auto.tfvars",
           "secrets.production.yml", "appsettings.secrets.json", ".htpasswd", ".kube/config", "credentials.csv",
           "~/.gnupg/secring.gpg", "~/.ssh/id_ed25519", "GoogleService-Info.plist", "config/.env", '".env"',
           ".env*", ".en?", "id_r*", ".e*", ".env::$DATA", _j("C:", "\\proj\\.env::$DATA"), ".env.", "ID_RSA"]
    no = [".env.example", ".env.sample", ".env.template", ".env.dist", ".env.defaults", ".env.tpl", ".env.local.example",
          ".env.production.sample", "sample.env", "example.env", "env.py", "environment.ts", "README.md", "src/keys.ts",
          "id_rsa.pub", "package.json", "docs/credentials-guide.md", "keyboard.js", "monkey.py", "turkey.txt",
          "settings.json", "config.json", "tsconfig.json", ".gitignore", "Makefile", "public.pem.txt", "secret-santa.md",
          "terraform.tfvars.example", "known_hosts", "~/.ssh/known_hosts", "~/.ssh/config", win_ssh,
          "~/.ssh/authorized_keys", "~/.ssh/id_ed25519.pub", "secrets.example.yml", "process.env", "import.meta.env",
          "Rails.env", "Deno.env", "Bun.env", "console.log(process.env)", "os.environ", "env", ".environment",
          "src/config/env.js", "docs/secrets.md", "", "   ", "src/components/Password.tsx", "tests/test_keys.py",
          "*", "*.md", "*.json", "src/*", "?", ".env.exam*", "*.py", "a*b"]
    f.ok(len(yes) >= 54 or len(yes) + len(no) >= 108, "file name table too small")
    for p in yes:
        if not sec.is_secret_filename(p):
            f.ok(False, "file name should be secret: %r" % p)
    for p in no:
        if sec.is_secret_filename(p):
            f.ok(False, "file name should NOT be secret: %r" % p)
    f.ok(sec.is_secret_filename(12) is False, "non-text file name")
    f.ok(isinstance(sec.is_secret_filename(".env\n"), bool), "newline in a file name must not raise")


# --------------------------------------------------------------------------- helpers


def _test_helpers(f: _Fails, sec: Any) -> None:
    g = _Gen(21, sec)
    # mask
    for n in range(1, 120):
        v = "".join(g.r.choice(A62) for _ in range(n))
        m = sec.mask(v)
        if n > 3:
            f.ok(v not in m, "mask returns the whole value for length %d" % n)
        # inject-11: the preview has asterisks and the length only; no character of the value (not even the first)
        f.ok(set(m.split(" (")[0]) <= {"*"}, "mask shows a character of the value (length %d)" % n)
        f.ok(m.endswith(" (%d chars)" % n), "mask does not end with the length (length %d)" % n)
        if n <= 8:
            f.ok(m.startswith("*" * n), "mask of a short value must not show characters (length %d)" % n)
        else:
            shown = len(m.split("***")[0]) if "***" in m else 0
            f.ok(shown <= 6, "mask shows %d characters for length %d" % (shown, n))
    # Hit behaves like a 4-tuple and as an object
    hits = sec.find_secrets("my password is " + g.make(g.password))
    f.ok(len(hits) == 1, "expected one prose password hit")
    if hits:
        kind, start, end, preview = hits[0]
        f.ok(kind == "password" and start == 15 and end > start and preview, "Hit does not unpack as 4 fields")
        f.ok(hits[0].kind == kind and hits[0].preview == preview and hits[0].strong is False, "Hit attributes")
    f.ok(hits.complete, "HitList.complete for a normal scan")
    # looks_like_real
    real_tok = _j("gh", "p_") + g.make(lambda: g.alnum(36))
    f.ok(sec.looks_like_real(real_tok), "a random GitHub-shaped token looks real")
    f.ok(sec.looks_like_real(g.make(lambda: g.alnum(32) + "Qz")), "a random 34-character value looks real")
    for fake in (_j("AKIA", "IOSFODNN7", "EXAMPLE"), "your_api_key_here", "<token>", "x" * 30, "0" * 30,
                 "3f786850e387550fdab836ed7e6dc881de23001b", "123e4567-e89b-12d3-a456-426614174000",
                 "sha512-" + g.b64(86), "1.2.3-beta.4", "changeme", "password", "short", "", "https://example.org/a/b/c",
                 "my-very-long-kebab-case-name", "ProcessEnvironmentConfiguration", "[hidden: password]",
                 _j("gh", "p_") + "x" * 36):
        f.ok(not sec.looks_like_real(fake), "looks_like_real should be False for %r" % fake[:30])
    # scan_and_redact agrees with redact + find_secrets
    text = "A " + real_tok + " B password: " + g.make(g.password)
    red, found = sec.scan_and_redact(text)
    f.ok(red == sec.redact(text) and len(found) == len(sec.find_secrets(text)), "scan_and_redact disagrees with redact")
    # every module level pattern is in the fuzz list
    names = {n for n, _rx in sec.compiled_regexes()}
    for name, value in vars(sec).items():
        if isinstance(value, re.Pattern):
            f.ok(name in names, "compiled_regexes() misses %s" % name)
    f.ok(len(names) >= 60, "compiled_regexes() lists only %d patterns" % len(names))


# --------------------------------------------------------------------------- regex fuzz (child process)

_FUZZ_CHILD = r'''
import sys, time, json
sys.dont_write_bytecode = True
sys.path.insert(0, sys.argv[1])
t0 = time.perf_counter()
from lib import secrets as s
s.redact("hello there")
import_ms = (time.perf_counter() - t0) * 1000.0
N = 100000
shapes = [("a.", "a." * (N // 2)), ("sk-", "sk-" * (N // 3)), ("x", "x" * N), ("space", " " * N),
          ("password=", "password=" * (N // 9)), ("A=", "A" * N + "="), ("newline", "\n" * N), ("curl", "curl " * (N // 5)),
          ("eyJ", "eyJ" * (N // 3)), ("eyJ-", "eyJ-" * (N // 4)), ("1 ", "1 " * (N // 2)), ("1", "1" * N),
          ("key=", "key=" * (N // 4)), ("a-", "a-" * (N // 2)), ("a://b:", "a://b:" * (N // 6)), ("M", "M" * N),
          ("ghp_", "ghp_" * (N // 4)), ("Bearer ", "Bearer " * (N // 7)), ("-----BEGIN ", "-----BEGIN " * (N // 11))]
worst = {}
for name, rx in s.compiled_regexes():
    top = 0.0
    for shape, text in shapes:
        t = time.perf_counter()
        for _m in rx.finditer(text):
            pass
        top = max(top, time.perf_counter() - t)
    worst[name] = top
sys.stdout.write(json.dumps({"worst": worst, "import_ms": import_ms}))
'''


def _test_regex_fuzz(f: _Fails) -> None:
    try:
        proc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", "-c", _FUZZ_CHILD, _HOOKS],
                              capture_output=True, timeout=90)
    except subprocess.TimeoutExpired:
        f.ok(False, "regex fuzz timed out (a regex backtracks badly)")
        return
    if proc.returncode != 0:
        f.ok(False, "regex fuzz child failed: %s" % proc.stderr.decode("utf-8", "replace")[-200:])
        return
    data = json.loads(proc.stdout.decode("utf-8"))
    worst = data["worst"]
    f.ok(len(worst) >= 60, "fuzz covered only %d regexes" % len(worst))
    for name, secs in sorted(worst.items()):
        if secs >= 0.5 * _TIME_FACTOR:
            f.ok(False, "regex %s needs %.2f s on a pathological shape (limit 0.5 s)" % (name, secs))
    f.ok(data["import_ms"] < 400.0, "import plus first redact took %.0f ms (limit 400 ms)" % data["import_ms"])


# --------------------------------------------------------------------------- the 34 prototype samples

_AZ = "abcdefghijklmnopqrstuvwxyz"
_D10 = "0123456789"


def _pem(kind: str, body: str) -> str:
    """A private key block, assembled so that this file holds no key header as one literal."""
    label = kind + " PRIV" + "ATE KEY"
    return "-----" + "BEGIN " + label + "-----\n" + body + "\n-----" + "END " + label + "-----"


def _prototype_samples() -> List[Tuple[str, str, bool]]:
    """(label, text, expected to be kept by the new engine). Built from fragments."""
    return [
        ("anthropic", _j("sk", "-ant-", "api03-") + _AZ + "0123", False),
        ("openai classic", _j("sk", "-") + _AZ + _D10 + "ABCD", False),
        ("openai proj", _j("sk", "-proj-") + _AZ + "_" + _D10 + "-ABCDEFG", False),
        ("gh pat ghp", _j("gh", "p_") + _AZ + _D10, False),
        ("gh oauth gho", _j("gh", "o_") + _AZ + _D10, False),
        ("gh server ghs", _j("gh", "s_") + _AZ + _D10, False),
        ("github_pat", _j("github", "_pat_") + "11ABCDEFG0" + _AZ + _D10, False),
        ("aws AKIA (docs example)", _j("AKIA", "IOSFODNN7", "EXAMPLE"), True),
        ("aws secret (docs example)", "aws_secret_access_key = " + _j("wJalrXUtnFEMI/K7MDENG/bPxRfiCY", "EXAMPLEKEY"), True),
        ("google AIza", _j("AI", "za") + "SyA-" + _AZ + "012345", False),
        ("slack", _j("xox", "b-") + "123456789012-" + "abcdefghijkl", False),
        ("stripe live", _j("sk", "_live_") + "abcdefghijklmnopqrstuvwx", False),
        ("stripe test", _j("sk", "_test_") + "abcdefghijklmnopqrstuvwx", False),
        ("hf token", _j("hf", "_") + _AZ + "ABCDEFGH", False),
        ("npm", _j("npm", "_") + _AZ + _D10, False),
        ("gitlab", _j("glpat", "-") + "abcdefghijklmnopqrst", False),
        ("jwt", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0." + "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U", False),
        ("bearer", "Authorization: Bearer " + _AZ + "0123", False),
        ("db url", "DATABASE_URL=postgres://admin:SuperSecret123" + _AT + "db.example.com:5432/app", False),
        ("mongodb url", "mongodb+srv://user:p4ssw0rd" + _AT + "cluster0.mongodb.net/test", False),
        ("pw colon", "password: hunter22", False),
        ("pw equals quoted", 'PASSWORD="hunter22"', False),
        ("pw short", "password: abc", True),
        ("pw sentence", "my password is hunter2222", False),
        ("pw turkish", "\u015fifre: hunter2222", False),
        ("private key", _pem("RSA", "MIIEow..."), False),
        ("openssh key", _pem("OPENSSH", "b3BlbnNzaC1rZXk="), False),
        ("env line", "OPENAI_API_KEY" + "=" + "abc123def456ghi789", False),
        ("env line2", "SUPABASE_SERVICE_ROLE_KEY" + "=" + _j("eyJhbGciOiJ", "IUzI1NiJ9", ".abc.", "def"), False),
        ("credit card", "4242 4242 4242 4242", False),
        ("ordinary", "I read the secret: it was easy to understand", True),
        ("ordinary2", "the password field should be hashed", True),
        ("uuid prompt", "550e8400-e29b-41d4-a716-446655440000", True),
        ("sha", "commit 3f786850e387550fdab836ed7e6dc881de23001b", True),
    ]


# The ten patterns of the prototype's hide_secrets (research/old-hooks.md, section 3.1).
_OLD_PATTERNS = [
    (r"-----BEGIN [A-Z ]*PRIV" r"ATE KEY-----.*?(?:-----END [A-Z ]*PRIV" r"ATE KEY-----|\Z)", re.S),
    (r"sk-ant-[A-Za-z0-9_\-]{10,}", 0), (r"\bsk-[A-Za-z0-9]{20,}", 0), (r"\bghp_[A-Za-z0-9]{20,}", 0),
    (r"\bgithub_pat_[A-Za-z0-9_]{20,}", 0), (r"\bAKIA[0-9A-Z]{16}\b", 0), (r"\bAIza[0-9A-Za-z_\-]{30,}", 0),
    (r"\bxox[baprs]-[A-Za-z0-9\-]{10,}", 0), (r"(?i)\bbearer\s+[A-Za-z0-9._\-]{20,}", 0),
    (r"(?i)\b(?:password|passwd|secret|api[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*\S{6,}", 0),
]


def _old_hides(text: str) -> bool:
    for src, flags in _OLD_PATTERNS:
        if re.search(src, text, flags):
            return True
    return False


def _prototype_numbers(sec: Any) -> Dict[str, Any]:
    rows = []
    for label, text, keep in _prototype_samples():
        rows.append({"label": label, "keep": keep, "old": _old_hides(text), "new": sec.redact(text) != text,
                     "guard": len(sec.scan_text(text)) > 0})
    secret_rows = [r for r in rows if r["label"] not in ("pw short", "ordinary", "ordinary2", "uuid prompt", "sha", "credit card")]
    nums = {
        "samples": len(rows),
        "secret_samples": len(secret_rows),
        "old_hidden": sum(1 for r in secret_rows if r["old"]),
        "old_leaks": sum(1 for r in secret_rows if not r["old"]),
        "new_hidden": sum(1 for r in secret_rows if r["new"]),
        "new_deliberate_keeps": sum(1 for r in secret_rows if not r["new"] and r["keep"]),
        "new_leaks": sum(1 for r in secret_rows if not r["new"] and not r["keep"]),
        "new_false_positives": sum(1 for r in rows if r["label"] in ("pw short", "ordinary", "ordinary2", "uuid prompt", "sha") and r["new"]),
        "card_hidden_new": next(r["new"] for r in rows if r["label"] == "credit card"),
        "card_hidden_old": next(r["old"] for r in rows if r["label"] == "credit card"),
        "guard_flags": sum(1 for r in secret_rows if r["guard"]),
    }
    nums["rows"] = rows
    return nums


def _report_line(n: Dict[str, Any]) -> str:
    return ("<!-- secrets-report old_hidden=%d old_leaks=%d new_hidden=%d new_deliberate_keeps=%d new_leaks=%d "
            "new_false_positives=%d -->" % (n["old_hidden"], n["old_leaks"], n["new_hidden"], n["new_deliberate_keeps"],
                                             n["new_leaks"], n["new_false_positives"]))


def _test_prototype(f: _Fails, sec: Any) -> None:
    n = _prototype_numbers(sec)
    f.ok(n["samples"] == 34, "expected the 34 prototype samples, got %d" % n["samples"])
    f.ok(n["old_hidden"] == 12 and n["old_leaks"] == 16, "the old engine baseline changed: %r" % ((n["old_hidden"], n["old_leaks"]),))
    f.ok(n["new_leaks"] == 0, "the new engine leaks %d prototype samples" % n["new_leaks"])
    f.ok(n["new_deliberate_keeps"] == 2, "expected exactly 2 deliberate keeps (AWS documentation examples), got %d" % n["new_deliberate_keeps"])
    f.ok(n["new_false_positives"] == 0, "the new engine hides %d of the 5 plain samples" % n["new_false_positives"])
    f.ok(n["card_hidden_new"] and not n["card_hidden_old"], "the card number must be hidden now and was not before")
    for r in n["rows"]:
        if r["keep"] and r["new"]:
            f.ok(False, "sample %r should stay visible" % r["label"])
    if os.path.isfile(_REPORT):
        with open(_REPORT, encoding="utf-8") as fh:
            body = fh.read()
        f.ok(_report_line(n) in body, "selftest_data/secrets_report.md is out of date (run with --write-report)")
    else:
        f.ok(False, "selftest_data/secrets_report.md is missing (run with --write-report)")


def write_report() -> str:
    """Rewrite selftest_data/secrets_report.md from live numbers. Returns the path."""
    sec = _load()
    n = _prototype_numbers(sec)

    def mark(v: bool) -> str:
        return "hidden" if v else "visible"

    lines = [
        "# Secrets engine report: the 34 prototype samples, before and after",
        "",
        _report_line(n),
        "",
        "What this is: the 34 sample strings of the prototype probe (research/old-hooks.md, PROBE 2) run through",
        "the prototype's `hide_secrets` (10 patterns) and through the new `hooks/lib/secrets.py`.",
        "The samples are rebuilt from fragments at run time (`tools/selftest_secrets.py`); no key-shaped",
        "literal is stored. The report is rewritten with `python tools/selftest_secrets.py --write-report`",
        "and the self-test fails when it is out of date.",
        "",
        "## Numbers",
        "",
        "| Measure | Prototype | New engine |",
        "|---|---|---|",
        "| Secret samples hidden (of %d) | %d | %d |" % (n["secret_samples"], n["old_hidden"], n["new_hidden"]),
        "| Real leaks (secret shown) | %d | %d |" % (n["old_leaks"], n["new_leaks"]),
        "| Deliberate keeps (AWS documentation examples) | 0 | %d |" % n["new_deliberate_keeps"],
        "| Card number `4242 4242 4242 4242` | %s | %s |" % (mark(n["card_hidden_old"]), mark(n["card_hidden_new"])),
        "| Plain samples hidden by mistake (of 5) | 0 | %d |" % n["new_false_positives"],
        "",
        "Reading the numbers: the prototype hid 12 of 28 secret samples and leaked 16. The new engine hides 26 and",
        "leaks none. The 2 samples it keeps are the AWS documentation example key and its example secret",
        "(`...EXAMPLE...`); SPEC 7.3 says documentation examples must stay visible. The prototype also",
        "left the card number visible; the new engine hides every Luhn-valid card number with a known prefix.",
        "",
        "Guard mode (`scan_text`) is stricter about false alarms: it also ignores keyboard-run tokens such as",
        "`abcdefgh...` and `1234567...`, which documentation uses and real machine-made keys never contain.",
        "Of the %d secret samples, guard mode reports %d as strong hits; the rest are documentation-style" % (n["secret_samples"], n["guard_flags"]),
        "examples, short passwords, prose passwords, or weak shapes (JWT, Google API key).",
        "",
        "## Per sample",
        "",
        "| Sample | Prototype | New (store mode) | Guard mode |",
        "|---|---|---|---|",
    ]
    for r in n["rows"]:
        lines.append("| %s | %s | %s | %s |" % (r["label"], mark(r["old"]), mark(r["new"]), "strong hit" if r["guard"] else "no hit"))
    lines += [
        "",
        "## Known limits",
        "",
        "- A password made only of lower-case letters (`correcthorsebatterystaple`) is not hidden unless it follows",
        "  the word password in a sentence with a digit or inner capital. Shapes without a name or a prefix are not guessed.",
        "- An unquoted password that contains `;` after the first `;` stays visible (connection strings use `;`).",
        "- Text beyond 256 KB is replaced by a note, not scanned.",
        "",
    ]
    os.makedirs(_DATA, exist_ok=True)
    with open(_REPORT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(lines))
    return _REPORT


# --------------------------------------------------------------------------- static checks of the two files

_FORBIDDEN_IMPORTS = {"socket", "ssl", "urllib", "http", "ftplib", "smtplib", "xmlrpc", "telnetlib", "webbrowser",
                      "requests", "ctypes", "pickle", "marshal", "importlib"}
_FORBIDDEN_CALLS = {"eval", "exec", "compile", "__import__"}
_TYPE_NAMES = {"int", "str", "float", "bool", "list", "dict", "tuple", "set", "bytes", "type", "object"}


def _lint_file(path: str, allow_subprocess: bool) -> List[str]:
    msgs: List[str] = []
    name = os.path.basename(path)
    with open(path, encoding="utf-8") as fh:
        src = fh.read()
    if "\r" in src:
        msgs.append("%s: has CR characters (LF only)" % name)
    if src.startswith("\ufeff"):
        msgs.append("%s: has a BOM" % name)
    tree = ast.parse(src)
    if "from __future__ import annotations" not in src:
        msgs.append("%s: missing `from __future__ import annotations`" % name)
    if "sys.dont_write_bytecode = True" not in src:
        msgs.append("%s: missing sys.dont_write_bytecode = True" % name)
    in_annotation = set()
    for node in ast.walk(tree):
        for attr in ("annotation", "returns"):
            sub_root = getattr(node, attr, None)
            if sub_root is not None:
                for sub in ast.walk(sub_root):
                    in_annotation.add(id(sub))
    match_type = getattr(ast, "Match", None)
    trystar = getattr(ast, "TryStar", None)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if match_type is not None and isinstance(node, match_type):
            msgs.append("%s:%d: match statement (Python 3.10)" % (name, line))
        if trystar is not None and isinstance(node, trystar):
            msgs.append("%s:%d: except* (Python 3.11)" % (name, line))
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root in _FORBIDDEN_IMPORTS or root == "tomllib" or (root == "subprocess" and not allow_subprocess):
                    msgs.append("%s:%d: forbidden import %s" % (name, line, a.name))
        if isinstance(node, ast.ImportFrom) and node.module:
            root = node.module.split(".")[0]
            if root in _FORBIDDEN_IMPORTS or root == "tomllib" or (root == "subprocess" and not allow_subprocess):
                msgs.append("%s:%d: forbidden import from %s" % (name, line, node.module))
            for a in node.names:
                if (root, a.name) in (("typing", "Self"), ("itertools", "pairwise"), ("contextlib", "chdir"), ("datetime", "UTC")):
                    msgs.append("%s:%d: %s.%s needs a newer Python" % (name, line, root, a.name))
        if isinstance(node, ast.Call):
            fn = node.func
            if isinstance(fn, ast.Name) and fn.id in _FORBIDDEN_CALLS:
                msgs.append("%s:%d: forbidden call %s()" % (name, line, fn.id))
            if isinstance(fn, ast.Name) and fn.id == "print":
                msgs.append("%s:%d: print() (write bytes instead)" % (name, line))
            if isinstance(fn, ast.Name) and fn.id == "zip" and any(k.arg == "strict" for k in node.keywords):
                msgs.append("%s:%d: zip(strict=) needs Python 3.10" % (name, line))
            if isinstance(fn, ast.Attribute) and fn.attr in ("system", "popen") and isinstance(fn.value, ast.Name) and fn.value.id == "os":
                msgs.append("%s:%d: os.%s" % (name, line, fn.attr))
        if isinstance(node, ast.Attribute):
            if node.attr == "UTC" and isinstance(node.value, ast.Name) and node.value.id == "datetime":
                msgs.append("%s:%d: datetime.UTC needs Python 3.11" % (name, line))
            if node.attr in ("pairwise", "bit_count", "removeprefix_") or (node.attr == "chdir" and isinstance(node.value, ast.Name) and node.value.id == "contextlib"):
                msgs.append("%s:%d: .%s needs a newer Python" % (name, line, node.attr))
            if node.attr == "walk" and not (isinstance(node.value, ast.Name) and node.value.id in ("os", "ast")):
                msgs.append("%s:%d: .walk() may be Path.walk (Python 3.12)" % (name, line))
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) and id(node) not in in_annotation:
            for side in (node.left, node.right):
                if (isinstance(side, ast.Constant) and side.value is None) or (isinstance(side, ast.Name) and side.id in _TYPE_NAMES):
                    msgs.append("%s:%d: `X | Y` type union outside an annotation (Python 3.10)" % (name, line))
    personal = [r"[A-Za-z]:\\Users\\", r"/Users/[a-z]", r"/home/[a-z]", r"[\w.+-]+@[\w-]+\.[a-z]{2,}"]
    for rx in personal:
        m = re.search(rx, src)
        if m:
            msgs.append("%s: looks like personal data: %r" % (name, m.group(0)))
    return msgs


def _test_static(f: _Fails) -> None:
    for path, sub in ((_LIB_FILE, False), (os.path.join(_HERE, "selftest_secrets.py"), True)):
        for m in _lint_file(path, sub):
            f.ok(False, "lint: " + m)
    with open(_LIB_FILE, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    allowed = {"__future__", "math", "re", "sys", "time", "bisect", "typing", "base64"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                f.ok(a.name in allowed, "secrets.py imports %s (allowed: %s)" % (a.name, sorted(allowed)))
        if isinstance(node, ast.ImportFrom):
            f.ok((node.module or "") in allowed, "secrets.py imports from %s" % node.module)
    data_dir_files = os.listdir(_DATA) if os.path.isdir(_DATA) else []
    f.ok("secrets_report.md" in data_dir_files, "selftest_data/secrets_report.md is missing")
    # The commit scanner reads every committed file. Our own files must not trip it.
    sec = _load()
    for path in (_LIB_FILE, os.path.join(_HERE, "selftest_secrets.py"), _REPORT):
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            body = fh.read()
        for h in sec.scan_text(body, len(body)):
            line = body.count("\n", 0, h.start) + 1
            f.ok(False, "%s line %d looks like a real secret to the commit scanner (%s)" % (os.path.basename(path), line, h.kind))
    # A learner who commits the kit must not be blocked by the kit's own files: scan the whole product folder.
    product = os.path.dirname(_HERE)
    for dirpath, dirnames, filenames in os.walk(product):
        dirnames[:] = [d for d in dirnames if d not in ("__pycache__", "agent-memory", ".git")]
        for name in filenames:
            if not name.endswith((".py", ".md", ".json", ".jsonl", ".tsv", ".txt", ".yml", ".yaml")):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, encoding="utf-8") as fh:
                    body = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            for h in sec.scan_text(body, len(body)):
                if getattr(h, "strong", True):
                    line = body.count("\n", 0, h.start) + 1
                    f.ok(False, "%s line %d looks like a real secret to the commit scanner (%s)" % (os.path.relpath(path, product).replace(os.sep, "/"), line, h.kind))


# --------------------------------------------------------------------------- entry points


def run() -> List[str]:
    """Run every check. Returns a list of failure messages (empty = all passed)."""
    f = _Fails()
    try:
        sec = _load()
    except Exception as exc:  # noqa: BLE001
        return ["cannot import hooks/lib/secrets.py: %s: %s" % (type(exc).__name__, exc)]
    steps: List[Tuple[str, Callable[[], None]]] = [
        ("corpus", lambda: _test_corpus(f, sec)),
        ("notes and cards", lambda: _test_notes_and_cards(f, sec)),
        ("false positives", lambda: _test_false_positives(f, sec)),
        ("modes", lambda: _test_modes(f, sec)),
        ("key bodies", lambda: _test_key_bodies(f, sec)),
        ("failure path", lambda: _test_failure_path(f, sec)),
        ("caps and time", lambda: _test_caps_and_time(f, sec)),
        ("boundaries", lambda: _test_boundaries(f, sec)),
        ("idempotence", lambda: _test_idempotence_and_text(f, sec)),
        ("mixed texts", lambda: _test_mixed_texts(f, sec)),
        ("long values", lambda: _test_long_values(f, sec)),
        ("file names", lambda: _test_filenames(f, sec)),
        ("helpers", lambda: _test_helpers(f, sec)),
        ("regex fuzz", lambda: _test_regex_fuzz(f)),
        ("prototype samples", lambda: _test_prototype(f, sec)),
        ("static checks", lambda: _test_static(f)),
    ]
    for name, step in steps:
        try:
            step()
        except Exception as exc:  # noqa: BLE001
            f.ok(False, "step '%s' crashed: %s: %s" % (name, type(exc).__name__, str(exc)[:120]))
    return f.items


def main(argv: List[str]) -> int:
    if "--write-report" in argv:
        path = write_report()
        sys.stdout.buffer.write(("wrote " + path + "\n").encode("utf-8"))
        return 0
    started = time.perf_counter()
    failures = run()
    out = sys.stdout.buffer
    if failures:
        out.write(("secrets: %d failure(s)\n" % len(failures)).encode("utf-8"))
        for line in failures[:60]:
            out.write(("  - " + line + "\n").encode("utf-8"))
        if len(failures) > 60:
            out.write(("  ... and %d more\n" % (len(failures) - 60)).encode("utf-8"))
        return 1
    out.write(("secrets: all checks passed in %.1f s\n" % (time.perf_counter() - started)).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
