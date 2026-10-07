"""secrets.py - finds text that looks like a secret and hides it.

What it is: the one secrets engine of the tutor (SPEC 7.3). Public names:
  redact(text)            the same text with every secret replaced by "[hidden: <kind>]"
  find_secrets(text)      where the secrets are (kind, start, end, masked preview)
  scan_and_redact(text)   both of the above in one pass: (redacted text, hits)
  scan_text(text, ...)    the same search tuned for the guard: only things that are almost
                          certainly real, and example keys from documentation are left alone
  mask(value)             a safe preview of a value (asterisks and the length only)
  is_secret_filename(p)   does this file name usually hold secrets (.env, id_rsa, *.pem ...)
  looks_like_real(value)  is this value a real secret, or a placeholder / hash / identifier
  compiled_regexes()      every compiled regex of this module, for the regex fuzz test
  Hit, HitList, WEAK_KINDS, MAX_SCAN   result types and limits

Why it exists: a beginner pastes keys into chat, the model may write one into a file, and
a commit may carry one. One engine means the chat copy, the guard and the push scanner agree.

How it fails safely:
  * redact() never returns its input after an internal error, a time overrun or a bad
    regex. It returns "[hidden: redaction failed, N chars]" instead. Text longer than
    MAX_SCAN characters is cut: the unchecked rest is replaced by a "[hidden: ...]" note.
  * find_secrets() and scan_text() never raise. They return a HitList (a plain list) with the
    extra attributes .truncated, .error and .scanned, so the guard can ask instead of
    guessing when a scan was incomplete.
  * Every regex is linear: it starts at a literal prefix or at a token start (look-behind),
    the repeats are bounded or end the match, and no repeat sits in front of a keyword. The
    keyword is found first; the code then looks a bounded distance around it. selftest_secrets
    fuzzes every compiled regex on eight pathological shapes at 100 KB.
  * Work is capped: 256 KB per call in 64 KB windows with 512 characters of overlap, a
    time budget per call, and a skip for whitespace-free runs over 400 characters for the
    rules that have no provider prefix.

Two modes (the only difference between redact/find_secrets and scan_text):
  store mode  (redact, find_secrets)  hides everything that could be a secret. Over-hiding
                                      our own copy of a message costs nothing.
  guard mode  (scan_text)             also ignores keyboard-run documentation keys such as
                                      ghp_1234567890abcdef..., so a README example is not a
                                      false alarm. Obvious placeholders (EXAMPLE, xxxxx,
                                      your-key-here, 00000000, <token>) are ignored in both.

Who calls it: user_prompt (redact + find_secrets), chatlog, activity, ledger (redact),
guardrules / pre_tool (scan_text, is_secret_filename, mask), scanner (scan_text on diffs).
No other module is imported, so it loads fast. Python 3.9, standard library only.
"""
from __future__ import annotations

import math
import re
import sys
import time
from bisect import bisect_left, bisect_right
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

sys.dont_write_bytecode = True

# --------------------------------------------------------------------------- limits

MAX_SCAN = 262144          # characters looked at per redact / find_secrets call (256 KB)
HARD_MAX = 4 * 1024 * 1024  # scan_text never looks at more than this, whatever the caller asks
CHUNK = 65536              # window size
OVERLAP = 512              # characters two neighbouring windows share
TIME_BUDGET = 2.5          # seconds one call may use before it gives up
MAX_BARE_RUN = 400         # whitespace-free runs longer than this are skipped by rules without a prefix
_MAX_QUOTED = 800          # longest quoted value the NAME=value rule reads (unquoted: 600, see _UNQ)

# --------------------------------------------------------------------------- result types


class Hit:
    """One secret found in a text. Unpacks like a tuple of the first four fields.

    kind            plain-words name, e.g. "GitHub token"; it is the text inside [hidden: ...]
    start, end      character offsets of the secret value in the scanned text
    preview_masked  asterisks plus the length, never a character of the secret
    strong          True when it is almost certainly a real secret (guard blocks on these);
                    False for weak shapes: short passwords, prose passwords, card numbers,
                    JWTs, Google API keys (public in web apps), local database URLs.
    """

    __slots__ = ("kind", "start", "end", "preview_masked", "strong")

    def __init__(self, kind: str, start: int, end: int, preview_masked: str, strong: bool = True) -> None:
        self.kind = kind
        self.start = start
        self.end = end
        self.preview_masked = preview_masked
        self.strong = strong

    @property
    def preview(self) -> str:
        return self.preview_masked

    def _tuple(self) -> Tuple[str, int, int, str]:
        return (self.kind, self.start, self.end, self.preview_masked)

    def __iter__(self):
        return iter(self._tuple())

    def __len__(self) -> int:
        return 4

    def __getitem__(self, index):
        return self._tuple()[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Hit):
            return self._tuple() == other._tuple() and self.strong == other.strong
        if isinstance(other, tuple):
            return self._tuple() == other
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._tuple())

    def __repr__(self) -> str:
        return "Hit(%r, %d, %d, %r, strong=%r)" % (self.kind, self.start, self.end,
                                                   self.preview_masked, self.strong)


class HitList(list):
    """A list of Hit with three extra facts about the scan.

    truncated  True when part of the text was not looked at (too long, or the time ran out)
    error      "" or a short reason ("time budget", "internal error")
    scanned    how many characters were looked at
    """

    def __init__(self, items: Iterable[Hit] = ()) -> None:
        list.__init__(self, items)
        self.truncated = False
        self.error = ""
        self.scanned = 0

    @property
    def complete(self) -> bool:
        return not self.truncated and not self.error


class _Timeout(Exception):
    """Internal: the time budget of one call ran out."""


# --------------------------------------------------------------------------- small helpers

def _to_str(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return bytes(value).decode("utf-8", "replace")
    return str(value)


def _entropy(value: str) -> float:
    """Shannon entropy in bits per character of the first 256 characters."""
    value = value[:256]
    n = len(value)
    if n == 0:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in value:
        counts[ch] = counts.get(ch, 0) + 1
    total = 0.0
    for c in counts.values():
        p = c / n
        total -= p * math.log2(p)
    return total


def mask(value: Any) -> str:
    """A safe preview: asterisks and the length. No character of the value is ever returned (inject-11):
    the callers show the kind and the length, and the guard text never shows a leading character."""
    n = len(_to_str(value))
    return "*" * min(max(n, 1), 8) + " (%d chars)" % n if n <= 8 else "***" + " (%d chars)" % n


def _classes(v: str) -> Tuple[bool, bool, bool, bool]:
    has_digit = has_lower = has_upper = has_other = False
    for ch in v:
        if ch.isdigit():
            has_digit = True
        elif ch.islower():
            has_lower = True
        elif ch.isupper():
            has_upper = True
        else:
            has_other = True
    return has_digit, has_lower, has_upper, has_other


def _digit_or_mixed(v: str) -> bool:
    d, lo, up, _o = _classes(v)
    return d or (lo and up)


def _wordy(v: str) -> bool:
    """kebab-case or snake_case words ("my-very-long-name") are identifiers, not keys."""
    parts = [p for p in re.split(r"[-_. ]+", v) if p]
    return len(parts) >= 2 and all(p.isalpha() and p.islower() for p in parts)


def _random_looking(v: str) -> bool:
    """True for strings that look machine-made: digits or a real mix of upper and lower case."""
    d, lo, up, other = _classes(v)
    if not (d or (lo and up)):
        return False
    if not d and not other:
        letters = sum(1 for ch in v if ch.isalpha())
        ratio = sum(1 for ch in v if ch.isupper()) / float(max(letters, 1))
        if ratio < 0.2 or ratio > 0.8:   # PascalCase / camelCase identifiers have few capitals
            return False
    if _wordy(v):
        return False
    if v.count(" ") >= 2:
        return False
    return True


_PW_SYMBOLS = frozenset("!@#$%^&*+=~?|;:<>")


def _password_looking(v: str) -> bool:
    """Looser than _random_looking: a human-chosen password with a digit, a symbol or inner capitals."""
    if any(ch.isdigit() for ch in v):
        return True
    if any(ch in _PW_SYMBOLS for ch in v):
        return True
    return _interior_mixed(v)


def _interior_mixed(v: str) -> bool:
    """HunterTwo, UserPassword: starts with a capital, has another capital and a lower-case letter.
    camelCase (starts lower case) is an identifier and does not count."""
    if len(v) < 2 or not v[0].isupper():
        return False
    return any(ch.isupper() for ch in v[1:]) and any(ch.islower() for ch in v)


# --------------------------------------------------------------------------- placeholder filters

# Obvious placeholders and documentation examples. Applied in both modes.
_PLACEHOLDER = re.compile(
    r"(?i)x{5,}|\*{3,}|\.\.\.|\u2026|0{8,}"
    r"|<[^<>\s]{1,40}>|\$\{|\{\{|%[A-Za-z_]{2,30}%"
    r"|example|dummy|sample|placeholder|changeme|change[-_ ]?it|replace[-_ ]?me|redacted"
    r"|not[-_ ]?a[-_ ]?(?:real|secret)"
    r"|your[-_ ]?(?:own|real|actual|api|access|auth|secret|private|key|token|pass|pw|value|here)"
    r"|(?<![a-z])(?:fake|test|demo|my)[-_](?:key|token|secret|pass|password|api)"
    r"|(?<![a-z])(?:insert|enter|paste|put)[-_ ]|[-_ ]here\b|\btodo\b|\btbd\b"
    r"|process\.env|os\.environ|getenv|import\.meta|\benv\(|\benv\["
    r"|\[hidden"
)

# Keyboard runs that documentation uses inside fake machine tokens. Guard mode only:
# a machine-made token never contains them, but a human-chosen password can.
_SEQUENCE = re.compile(r"(?i)1234567|abcdefgh|qwerty")

_NONSECRET = frozenset("""
password passwd pass pwd secret secrets token key apikey api_key none null nil true false
undefined string str int bool boolean required optional changeme changeit default defaults
example test testing demo foo bar baz admin root user username email todo tbd n/a na
yes no on off enabled disabled secret_key password_hash
""".split())

# A hit that touches the end of a window is stretched over the rest of its token (at most 4,096 characters).
_TAIL = re.compile(r"[A-Za-z0-9_\-+/=.]{0,4096}")


def _tok_ok(v: str, guard: bool, mixed: bool = False, min_entropy: float = 2.5) -> bool:
    """Checks that apply to every token that starts with a provider prefix."""
    if _PLACEHOLDER.search(v):
        return False
    if guard and _SEQUENCE.search(v):
        return False
    if len(set(v)) < 8:
        return False
    if _entropy(v) < min_entropy:
        return False
    if mixed and not _digit_or_mixed(v):
        return False
    return True


def _cred_ok(v: str) -> bool:
    """Checks for credentials that follow a Bearer / Basic / Authorization word."""
    if _PLACEHOLDER.search(v) or len(set(v)) < 8:
        return False
    return _entropy(v) >= 3.0 and _digit_or_mixed(v)


# --------------------------------------------------------------------------- rule table
#
# A check function gets (match, guard) and returns None (rejected) or
# (start, end, kind, strong) in text offsets.

Span = Tuple[int, int, str, bool]


def _blob_run(text: str, a: int, b: int) -> int:
    """Length of the whitespace-free run around [a, b), counted up to MAX_BARE_RUN + 1 each side."""
    n = len(text)
    left = a
    stop = max(0, a - MAX_BARE_RUN - 1)
    while left > stop and not text[left - 1].isspace():
        left -= 1
    right = b
    stop = min(n, b + MAX_BARE_RUN + 1)
    while right < stop and not text[right].isspace():
        right += 1
    return right - left


def _token_check(kind: str, group: int = 0, strong: bool = True, mixed: bool = False,
                 min_entropy: float = 2.5, bare: bool = False) -> Callable[[Any, bool], Optional[Span]]:
    def check(m: Any, guard: bool) -> Optional[Span]:
        a, b = m.span(group)
        v = m.string[a:b]
        if not _tok_ok(v, guard, mixed, min_entropy):
            return None
        if bare and _blob_run(m.string, a, b) > MAX_BARE_RUN:
            return None
        return (a, b, kind, strong)
    return check


def _chk_jwt(m: Any, guard: bool) -> Optional[Span]:
    a, b = m.span()
    if _PLACEHOLDER.search(m.string[a:b]):
        return None
    return (a, b, "JSON Web Token", False)


def _chk_authhdr(m: Any, guard: bool) -> Optional[Span]:
    scheme = m.group(1).lower()
    a, b = m.span(2)
    if not _cred_ok(m.string[a:b]):
        return None
    return (a, b, "Basic auth credentials" if scheme == "basic" else "bearer token", True)


def _chk_bearer(m: Any, guard: bool) -> Optional[Span]:
    a, b = m.span(1)
    if not _cred_ok(m.string[a:b]):
        return None
    return (a, b, "bearer token", True)


_DB_SCHEMES = frozenset(["postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongodb+srv", "redis",
                         "rediss", "amqp", "amqps", "mssql", "sqlserver", "couchdb", "cassandra",
                         "neo4j", "clickhouse", "oracle", "cockroachdb"])
_LOCAL_HOST = re.compile(r"(?i)@(?:localhost|127\.0\.0\.1|0\.0\.0\.0|\[::1\]|host\.docker\.internal"
                         r"|db|postgres|mysql|mongo|mongodb|redis|database)(?:[:/?]|$)")


def _chk_urlpw(m: Any, guard: bool) -> Optional[Span]:
    scheme = m.group(1).lower()
    user = m.group(2)
    pw = m.group(3)
    low = pw.lower()
    if low in _NONSECRET or low == user.lower():
        return None
    if pw[0] in "$%@{[(<" or _PLACEHOLDER.search(pw):
        return None
    a, b = m.span(3)
    if scheme in _DB_SCHEMES:
        if _LOCAL_HOST.match(m.string, m.end() - 1):
            return (a, b, "local database URL password", False)
        return (a, b, "database URL password", True)
    if len(pw) < 6:
        return None
    return (a, b, "password in a URL", True)


def _luhn(digits: str) -> bool:
    total = 0
    alt = False
    for ch in reversed(digits):
        n = ord(ch) - 48
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def _card_shape_ok(d: str, formatted: bool) -> bool:
    """Known card prefix with a matching length (keeps timestamps, order numbers and barcodes out)."""
    n = len(d)
    c = d[0]
    if c == "4":
        return n in (16, 19) or (n == 13 and formatted)
    if c == "5":
        return 16 <= n <= 19 and d[1] in "012345678"
    if c == "6":
        return 16 <= n <= 19
    if c == "3":
        p = d[:2]
        if p in ("34", "37"):
            return n == 15
        if p == "35":
            return 16 <= n <= 19
        if p in ("30", "36", "38", "39"):
            return 14 <= n <= 19
        return False
    if c == "2":
        return n == 16 and "2221" <= d[:4] <= "2720"
    return False


def _chk_card(m: Any, guard: bool) -> Optional[Span]:
    raw = m.group(1)
    digits = re.sub(r"\D", "", raw)
    formatted = len(digits) != len(raw)
    if not 13 <= len(digits) <= 19:
        return None
    if formatted:
        groups = re.split(r"[ \-]", raw)
        sizes = [len(g) for g in groups]
        regular = all(s == 4 for s in sizes[:-1]) and 1 <= sizes[-1] <= 4
        if not (regular or sizes in ([4, 6, 5], [4, 6, 4])):
            return None
        if len(set(re.findall(r"[ \-]", raw))) > 1:
            return None
    if not _card_shape_ok(digits, formatted) or not _luhn(digits):
        return None
    a, b = m.span(1)
    if _blob_run(m.string, a, b) > MAX_BARE_RUN:
        return None
    return (a, b, "card", False)


_CARD_CTX = 600                       # characters either side of a card number that its note may use
_BLANK_LINE = re.compile(r"\n[ \t\r]*\n")


def _card_block(text: str, a: int, b: int, blocked: List[Tuple[int, int]]) -> Span:
    """Widen a card number to its note: the lines up to the next blank line, at most _CARD_CTX characters
    each way. The CVC, a security code and the expiry date are usually written on the same lines, so they
    go too. The span stops at a hidden or base64 region (`blocked`, sorted) so that _run keeps it."""
    s, e = max(0, a - _CARD_CTX), min(len(text), b + _CARD_CTX)
    blank = None
    for m in _BLANK_LINE.finditer(text, s, a):
        blank = m
    if blank is not None:
        s = blank.end()
    after = _BLANK_LINE.search(text, b, e)
    if after is not None:
        e = after.start()
    starts = [r[0] for r in blocked]
    i = bisect_right(starts, a) - 1
    if i >= 0 and blocked[i][1] > a:
        return (a, b, "card", False)           # the number itself is already inside a hidden region
    if i >= 0:
        s = max(s, blocked[i][1])
    k = bisect_left(starts, b)
    if k < len(blocked):
        e = min(e, blocked[k][0])
    return (s, e, "card", False)


class _Rule:
    """One compiled-on-demand pattern with a cheap pre-test and a check function."""

    __slots__ = ("name", "src", "flags", "needles", "check", "_rx")

    def __init__(self, name: str, src: str, needles: Tuple[str, ...], check: Callable[[Any, bool], Optional[Span]],
                 flags: int = 0) -> None:
        self.name = name
        self.src = src
        self.flags = flags
        self.needles = needles          # lower-case literals; the rule runs only if one is present
        self.check = check
        self._rx = None

    def regex(self) -> Any:
        rx = self._rx
        if rx is None:
            rx = re.compile(self.src, self.flags)
            self._rx = rx
        return rx

    def wants(self, low: str) -> bool:
        for n in self.needles:
            if n in low:
                return True
        return False


_B = r"(?<![A-Za-z0-9])"   # a provider prefix must not sit inside a longer word

_RULES: List[_Rule] = []


def _add(name: str, kind: str, src: str, needles: Tuple[str, ...], group: int = 0, strong: bool = True,
         mixed: bool = False, min_entropy: float = 2.5, bare: bool = False, flags: int = 0) -> None:
    _RULES.append(_Rule(name, src, needles,
                        _token_check(kind, group, strong, mixed, min_entropy, bare), flags))


def _add_custom(name: str, src: str, needles: Tuple[str, ...], check: Callable[[Any, bool], Optional[Span]],
                flags: int = 0) -> None:
    _RULES.append(_Rule(name, src, needles, check, flags))


# AI providers (most specific first: when two rules hit the same text the earlier kind is kept)
_add("anthropic", "Anthropic API key", _B + r"sk-ant-[A-Za-z0-9_\-]{16,}", ("sk-ant-",))
_add("openrouter", "OpenRouter API key", _B + r"sk-or-[A-Za-z0-9_\-]{16,}", ("sk-or-",))
_add("openai-scoped", "OpenAI API key", _B + r"sk-(?:proj|svcacct|admin)-[A-Za-z0-9_\-]{16,}", ("sk-",))
_add("deepseek", "DeepSeek API key", _B + r"sk-[a-f0-9]{32}(?![A-Za-z0-9])", ("sk-",))
_add("openai", "OpenAI-style API key", _B + r"sk-[A-Za-z0-9]{20,}", ("sk-",), mixed=True)
_add("groq", "Groq API key", _B + r"gsk_[A-Za-z0-9]{20,}", ("gsk_",))
_add("xai", "xAI API key", _B + r"xai-[A-Za-z0-9]{20,}", ("xai-",))
_add("perplexity", "Perplexity API key", _B + r"pplx-[A-Za-z0-9]{20,}", ("pplx-",))
_add("replicate", "Replicate API token", _B + r"r8_[A-Za-z0-9]{20,}", ("r8_",))
_add("huggingface", "Hugging Face token", _B + r"hf_[A-Za-z0-9]{30,}", ("hf_",))
# Developer platforms
_add("github", "GitHub token", _B + r"gh[pousr]_[A-Za-z0-9]{20,}", ("gh",))
_add("github-fine", "GitHub token", _B + r"github_pat_[A-Za-z0-9_]{20,}", ("github_pat_",))
_add("gitlab", "GitLab token", _B + r"glpat-[A-Za-z0-9_\-]{20,}", ("glpat-",))
_add("npm", "npm token", _B + r"npm_[A-Za-z0-9]{30,}", ("npm_",))
_add("pypi", "PyPI token", _B + r"pypi-AgE[A-Za-z0-9_\-]{40,}", ("pypi-",))
_add("docker", "Docker token", _B + r"dckr_pat_[A-Za-z0-9_\-]{20,}", ("dckr_pat_",))
_add("notion-ntn", "Notion token", _B + r"ntn_[A-Za-z0-9]{20,}", ("ntn_",))
_add("notion-secret", "Notion token", _B + r"secret_[A-Za-z0-9]{30,}", ("secret_",), mixed=True, min_entropy=3.5)
_add("shopify", "Shopify token", _B + r"shp(?:at|ss|ca|pa)_[A-Fa-f0-9]{32}(?![A-Za-z0-9])", ("shp",))
_add("supabase-pat", "Supabase token", _B + r"sbp_[A-Fa-f0-9]{40}(?![A-Za-z0-9])", ("sbp_",))
_add("supabase-secret", "Supabase key", _B + r"sb_secret_[A-Za-z0-9_\-]{20,}", ("sb_secret_",))
_add("sentry", "Sentry token", _B + r"sntrys_[A-Za-z0-9+/=_\-]{30,}", ("sntrys_",))
_add("linear", "Linear API key", _B + r"lin_api_[A-Za-z0-9]{30,}", ("lin_api_",))
_add("square", "Square token", _B + r"sq0(?:atp|csp)-[A-Za-z0-9_\-]{20,}", ("sq0",))
_add("digitalocean", "DigitalOcean token", _B + r"do[opr]_v1_[a-f0-9]{64}", ("_v1_",))
# Cloud
_add("aws-id", "AWS access key ID", _B + r"(?:AKIA|ASIA|ABIA|ACCA)[A-Z0-9]{16}(?![A-Za-z0-9])", ("akia", "asia", "abia", "acca"))
_add("google-api", "Google API key", _B + r"AIza[0-9A-Za-z_\-]{30,}", ("aiza",), strong=False)
_add("gcp-oauth", "Google OAuth token", _B + r"ya29\.[A-Za-z0-9_\-]{30,}", ("ya29.",))
_add("gcp-client", "Google client secret", _B + r"GOCSPX-[A-Za-z0-9_\-]{20,}", ("gocspx-",))
_add("azure-key", "Azure storage key", r"(?i)(?:account|sharedaccess)key=([A-Za-z0-9+/]{30,}={0,3})", ("key=",),
     group=1, min_entropy=3.0)
_add("azure-sas", "Azure SAS signature", r"(?<=[?&;])sig=([A-Za-z0-9%+/=_\-]{20,})", ("sig=",), group=1,
     min_entropy=3.0)
# Payments and messaging
_add("stripe", "Stripe key", _B + r"(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{10,}", ("sk_", "rk_"))
_add("stripe-hook", "Stripe webhook secret", _B + r"whsec_[A-Za-z0-9]{20,}", ("whsec_",))
_add("slack", "Slack token", _B + r"xox[abprs]-[A-Za-z0-9\-]{10,}", ("xox",))
_add("slack-app", "Slack token", _B + r"xapp-\d-[A-Z0-9]+-\d+-[a-z0-9]+", ("xapp-",))
_add("slack-hook", "Slack webhook URL", r"https://hooks\.slack\.com/(?:services|workflows|triggers)/[A-Za-z0-9+/]{20,}",
     ("hooks.slack.com",))
_add("discord-hook", "Discord webhook URL",
     r"https://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d{15,}/[A-Za-z0-9_\-]{30,}",
     ("/api/webhooks/",))
_add("discord-bot", "Discord bot token",
     r"(?<![A-Za-z0-9_\-])[MNO][A-Za-z0-9_\-]{23,25}\.[A-Za-z0-9_\-]{6}\.[A-Za-z0-9_\-]{27,38}(?![A-Za-z0-9_\-])",
     (".",), min_entropy=3.5, bare=True)
_add("telegram", "Telegram bot token", r"(?<![0-9A-Za-z_])\d{8,10}:A[A-Za-z0-9_\-]{34}(?![A-Za-z0-9_\-])",
     (":a",), bare=True)
_add("twilio", "Twilio API key", _B + r"SK[0-9a-f]{32}(?![A-Za-z0-9])", ("sk",), min_entropy=3.0, bare=True)
_add("sendgrid", "SendGrid API key", _B + r"SG\.[A-Za-z0-9_\-]{16,}\.[A-Za-z0-9_\-]{16,}", ("sg.",))
_add("mailgun", "Mailgun API key", _B + r"key-[0-9a-f]{32}(?![A-Za-z0-9])", ("key-",), min_entropy=3.0, bare=True)
# Tokens and headers
_add_custom("jwt", r"(?<![A-Za-z0-9_\-])eyJ(?=([A-Za-z0-9_\-]{8,}))\1\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}",
            ("eyj",), _chk_jwt)
_add_custom("auth-header",
            r"""(?i)(?<![A-Za-z0-9])authorization["']?[ \t]{0,3}[:=][ \t]{0,3}["']?(bearer|basic|token|apikey)[ \t]{1,4}"""
            r"""([A-Za-z0-9._~+/\-]{16,}={0,3})""",
            ("authorization",), _chk_authhdr)
_add_custom("bearer", r"(?i)(?<![A-Za-z0-9])bearer[ \t]{1,3}([A-Za-z0-9._~+/\-]{20,}={0,3})",
            ("bearer",), _chk_bearer)
_add_custom("url-password",
            r"""(?i)(?<![A-Za-z0-9+.\-])([a-z][a-z0-9+.\-]{1,30})://([^\s:/@"'<>]{0,100}):([^\s@/"'<>]{3,200})@""",
            ("://",), _chk_urlpw)
_add_custom("card", r"(?<![\w.\-])(\d(?:[ \-]?\d){12,18})(?![\w\-]|\.\d)",
            ("0", "1", "2", "3", "4", "5", "6", "7", "8", "9"), _chk_card)

# --------------------------------------------------------------------------- NAME=value rule
#
# The keyword (key, token, secret, password ...) is found first. Then the code looks at a
# bounded number of characters before and after it. This keeps the work linear.

_KW = re.compile(
    r"(?i)(?:apikey|accesskey|secretkey|privatekey|authtoken|accesstoken|refreshtoken|clientsecret"
    r"|sessionkey|signingkey|encryptionkey|masterkey|passwords?|passwd|passphrase|passwort|pwd|pass"
    r"|secrets?|tokens?|credentials?|auth|keys?)"
)
_NAMECHARS = re.compile(r"[A-Za-z0-9_\-.]{0,40}")
_SEP = re.compile(r"""["'`\]]?[ \t]{0,3}(?::=|=>|[:=])[ \t]{0,3}""")
_UNQ = re.compile(r"""[^\s"'`<>]{1,600}""")
_RUN = re.compile(r"""[^\s"'`<>]{0,4096}""")     # the rest of a value that is longer than 600 characters
_RUN_ANY = re.compile(r"\S{0,4096}")
_CODEISH = re.compile(r"[()\[\]{}]")
_NAMED_NEEDLES = ("key", "token", "secret", "pass", "pwd", "credential", "auth")


def _left_ok(text: str, s: int) -> bool:
    if s == 0:
        return True
    p = text[s - 1]
    if not p.isalnum():
        return True
    return text[s].isupper() and (p.islower() or p.isdigit())   # camelCase: apiKey


def _right_ok(text: str, e: int) -> bool:
    if e >= len(text):
        return True
    c = text[e]
    if not c.isalpha():
        return True
    return c.isupper() and text[e - 1].islower()                # camelCase: passwordHash


def _named_kind(kw: str) -> str:
    k = kw.lower()
    if "pass" in k or k == "pwd":
        return "password"
    if "private" in k:
        return "private key"
    if "token" in k:
        return "token"
    if "secret" in k:
        return "secret"
    if "credential" in k:
        return "credential"
    if k == "auth":
        return "auth value"
    return "API key"


def _jwt_is_public(token: str) -> bool:
    """True for a JWT whose payload says role=anon (a Supabase anon key is public by design)."""
    try:
        import base64  # noqa: PLC0415 - only needed here; keeps the import cost out of every hook
        parts = token.split(".")
        if len(parts) < 2:
            return False
        seg = parts[1] + "=" * (-len(parts[1]) % 4)
        payload = base64.urlsafe_b64decode(seg.encode("ascii"))
        return b'"role":"anon"' in payload.replace(b" ", b"")
    except Exception:  # noqa: BLE001
        return False


def _named_eval(v: str, pw: bool, quoted: bool, guard: bool = False) -> Tuple[bool, bool]:
    """Decide whether the value after NAME= is a secret. Returns (hide, strong)."""
    if not v or "[hidden" in v:
        return False, False
    if v[0] in "$%@{[(<=":
        return False, False                      # a reference, a template or a comparison, not a value
    if v.lower() in _NONSECRET or _PLACEHOLDER.search(v):
        return False, False
    if guard and not pw and _SEQUENCE.search(v):
        return False, False                      # documentation key such as abcdefgh...
    if v.startswith(("pk_live_", "pk_test_")):
        return False, False                      # a publishable key is meant for the browser
    if guard and v.startswith("eyJ") and _jwt_is_public(v):
        return False, False                      # a Supabase anon key is public by design
    if v.startswith(("/", "./", "../", "~", "\\", "http://", "https://", "file://", "data:")):
        return False, False
    if not quoted and _CODEISH.search(v):
        return False, False                      # a function call or an index, not a value
    n = len(v)
    entropy = _entropy(v)
    distinct = len(set(v))
    if pw:
        if n < 8 or distinct < 5 or entropy < 2.0 or not _password_looking(v):
            return False, False
        strong = n >= 16 and entropy >= 3.0 and distinct >= 6 and _random_looking(v)
        return True, strong
    if n < 16 or entropy < 3.0 or distinct < 6 or not _random_looking(v):
        return False, False
    return True, True


def _scan_named(text: str, lo: int, hi: int, ctx: "_Ctx", out: List[Span]) -> None:
    skip_to = lo
    count = 0
    n = len(text)
    for m in _KW.finditer(text, lo, hi):
        s = m.start()
        if s < skip_to:
            continue
        count += 1
        if (count & 255) == 0 and time.monotonic() > ctx.deadline:
            raise _Timeout()
        if ctx.inside_blocked(s) or not _left_ok(text, s):
            continue
        e = m.end()
        if not _right_ok(text, e):
            continue
        b = s
        stop = max(0, s - 60)
        while b > stop and (text[b - 1].isalnum() or text[b - 1] in "_-."):
            b -= 1
        if "public" in text[b:s].lower():
            continue                             # NEXT_PUBLIC_*, public_key: meant to be seen
        p = _NAMECHARS.match(text, e, hi).end()
        sm = _SEP.match(text, p, hi)
        if sm is None:
            continue
        vs = sm.end()
        if vs >= hi:
            continue
        pw = _named_kind(m.group()) == "password"
        ch = text[vs]
        quoted = False
        ve = vs
        if ch in "\"'`":
            close = text.find(ch, vs + 1, min(n, vs + 1 + _MAX_QUOTED))
            if close >= 0 and text.find("\n", vs + 1, close) < 0:
                quoted = True
                vs += 1
                ve = close
            else:
                vs += 1
        if not quoted:
            um = _UNQ.match(text, vs, hi)
            if um is None:
                continue
            ve = um.end()
            if ve - vs >= 600:
                ve = _RUN.match(text, ve).end()          # never leave the tail of a long value visible
            semi = text.find(";", vs, ve)
            if semi >= 0:
                ve = semi
            while ve > vs and text[ve - 1] in ",)]}.:'":
                ve -= 1
        v = text[vs:ve]
        key = (v[:200], pw, quoted)
        res = ctx.memo.get(key)
        if res is None:
            res = _named_eval(v, pw, quoted, ctx.guard)
            if len(ctx.memo) < 5000:
                ctx.memo[key] = res
        if res[0]:
            skip_to = sm.end()                   # the other keywords of this name (SECRET_KEY) add nothing
            out.append((vs, ve, _named_kind(m.group()), res[1]))


# --------------------------------------------------------------------------- prose rule
#
# "my password is Hunter2Hunter2", "sifrem: Kedi1234kedi", "here is my api key: <token>".

_PW_KW = re.compile(
    r"(?i)(?<![A-Za-z0-9_])(?:passwords?|passwd|passwort|passphrase|pwd|sifre|\u015fifre|parola"
    r"|contrase[n\u00f1]a|clave|kennw[o\u00f6]rt|code[ \t\u00a0]{1,3}secret"
    r"|mot[ \t\u00a0\-]{1,3}de[ \t\u00a0\-]{1,3}passe"
    r"|cl[e\u00e9]s?(?![^\W\d_]))[^\W\d_]{0,4}"     # cle, cles, cl\u00e9: a whole word only (clean, client)
)
_SK_KW = re.compile(
    r"(?i)(?<![A-Za-z0-9])(?:api[ _\-]?keys?|access[ _\-]?keys?|access[ _\-]?tokens?|auth[ _\-]?tokens?"
    r"|secret[ _\-]?access[ _\-]?keys?|secret[ _\-]?keys?|private[ _\-]?keys?|client[ _\-]?secrets?|tokens?"
    r"|secrets?|credentials?|keys?)(?![A-Za-z0-9])"
)
_WORD = re.compile(r"\S+")
_TECHWORD = re.compile(
    r"(?i)^(?:sha-?\d{1,3}|md5|utf-?\d{1,2}|base\d{2}|aes-?\d{3}|rsa-?\d{3,4}|bcrypt\d*|argon2\w*|pbkdf2|scrypt"
    r"|oauth\d?|http\d|html\d|css\d|es\d{1,4}|ipv\d|python\d?|node\d*|v\d+(?:\.\d+)*|\d+(?:\.\d+)+|sqlite\d"
    r"|mysql\d|mp\d|x86|x64|win\d+|java\d+|php\d+|ruby\d|k8s|i18n|l10n|a11y|2fa|3d|1password)$"
)
_FILELIKE = re.compile(
    r"(?i)^[\w\-]+(?:\.[\w\-]+){0,4}\.(?:json|jsonl|js|ts|tsx|jsx|py|md|txt|yml|yaml|env|toml|ini|cfg|conf|html|css"
    r"|csv|xml|log|sh|ps1|bat|pem|key|cer|crt|lock|rb|go|rs|java|php|sql|db|sqlite|png|jpg|jpeg|gif|svg|pdf|zip|tar"
    r"|gz|tgz|bak|exe|dll|map|ico|webp|woff2?|ttf)$"
)
_EMAILISH = re.compile(r"^[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+$")
_LEAD = "\"'`([{<\u00ab\u201c\u2018:"
_TRAIL = ",;:.\"'`)]}>\u00bb\u201d\u2019"


def _trim(tok: str, lead: str = _LEAD) -> Tuple[int, int]:
    a = 0
    b = len(tok)
    while a < b and tok[a] in lead:
        a += 1
    while b > a and tok[b - 1] in _TRAIL:
        b -= 1
    return a, b


def _pw_word_ok(t: str, guard: bool = False) -> bool:
    if not 6 <= len(t) <= 200:
        return False
    if t.lower() in _NONSECRET or _PLACEHOLDER.search(t):
        return False
    if "://" in t or t[0] in "/~\\$@" or any(c in t for c in "(){}<>=;,\"'`"):
        return False                              # a path, a hash ($2b$...), a host (@db), or code
    if _EMAILISH.match(t) or _FILELIKE.match(t) or _TECHWORD.match(t):
        return False
    if re.fullmatch(r"[\d\-/.:]+", t):
        return t.isdigit() and len(t) >= 8
    if any(ch.isdigit() for ch in t):
        return True
    return _interior_mixed(t)


def _sk_word_ok(t: str, guard: bool = False) -> bool:
    if not 20 <= len(t) <= 300 or len(set(t)) < 8:
        return False
    if "://" in t or t[0] in "/~\\" or _PLACEHOLDER.search(t):
        return False
    if guard and _SEQUENCE.search(t):
        return False
    if t.startswith(("pk_live_", "pk_test_")):
        return False                              # a publishable key is meant for the browser
    if not re.fullmatch(r"[A-Za-z0-9._~+/=\-]+", t):
        return False
    if _FILELIKE.match(t):
        return False
    return _entropy(t) >= 3.5 and (any(ch.isdigit() for ch in t) or _random_looking(t))


def _scan_prose(text: str, lo: int, hi: int, ctx: "_Ctx", out: List[Span]) -> None:
    n = len(text)
    # (pattern, word check, fixed kind, strong, how many words after the keyword, characters to strip in front)
    families = ((_PW_KW, _pw_word_ok, "password", False, 5, _LEAD),
                (_SK_KW, _sk_word_ok, "", True, 4, _LEAD + "="))
    for rx, ok, fixed_kind, strong, budget, lead in families:
        count = 0
        for m in rx.finditer(text, lo, hi):
            count += 1
            if (count & 255) == 0 and time.monotonic() > ctx.deadline:
                raise _Timeout()
            e = m.end()
            if ctx.inside_blocked(m.start()):
                continue
            if e < n:
                nxt = text[e]
                if nxt in "_.([/\\@" or (nxt == "-" and e + 1 < n and text[e + 1].isalnum()):
                    continue
            if "public" in text[max(0, m.start() - 7):m.start()].lower():
                continue                         # "my public key: ..." is meant to be shared
            end = min(n, e + 160)
            nl = text.find("\n", e, end)
            if nl >= 0:
                end = nl
            words = 0
            for wm in _WORD.finditer(text, e, end):
                if ctx.inside_blocked(wm.start()):
                    break                        # a secret after this keyword was already hidden
                tok = wm.group()
                if not any(ch.isalnum() for ch in tok):
                    continue
                words += 1
                a, b = _trim(tok, lead)
                if b > a:
                    word = tok[a:b]
                    good = ctx.words.get((fixed_kind, word))
                    if good is None:
                        good = ok(word, ctx.guard)
                        if len(ctx.words) < 5000:
                            ctx.words[(fixed_kind, word)] = good
                    if good:
                        start_at = wm.start() + a
                        stop_at = wm.start() + b
                        if wm.end() >= end and end < n and not text[end].isspace():
                            # the look-ahead window cut a long token: take the rest of it
                            stop_at = _RUN_ANY.match(text, wm.end()).end()
                            while stop_at > start_at and text[stop_at - 1] in _TRAIL:
                                stop_at -= 1
                        out.append((start_at, stop_at, fixed_kind or _named_kind(m.group()), strong))
                        break
                if words >= budget:
                    break


# --------------------------------------------------------------------------- private key blocks

_PEM_MAX = 16000
_PEM_BODY = re.compile(r"[A-Za-z0-9+/=]{16,}")


def _scan_pem(text: str, out: List[Span]) -> None:
    pos = 0
    n = len(text)
    while pos < n:
        i = text.find("-----BEGIN ", pos)
        if i < 0:
            return
        j = text.find("-----", i + 11, i + 11 + 100)
        if j < 0:
            pos = i + 11
            continue
        label = text[i + 11:j].upper()
        pos = j + 5
        if "PRIVATE KEY" not in label:
            continue
        end = j + 5
        e = text.find("-----END ", j + 5, j + 5 + _PEM_MAX)
        if e >= 0:
            k = text.find("-----", e + 9, e + 9 + 100)
            end = k + 5 if k >= 0 else e + 9
        else:
            # no end line: take the lines after the header that look like key material
            p = j + 5
            for _ in range(400):
                if text.startswith("\\n", p):
                    p += 2
                    continue
                if p < n and text[p] in "\r\n":
                    p += 1
                    continue
                m = _PEM_BODY.match(text, p)
                if m is None:
                    break
                p = m.end()
                end = p
        out.append((i, end, "private key", True))
        pos = max(pos, end)


# bare key material that lost its header line (a pasted second line, for example)
# The starts below are the fixed first bytes of OpenSSH, PKCS#1 RSA, PKCS#8 RSA, SEC1 EC, PKCS#8 EC
# and PKCS#8 Ed25519 private keys. A public certificate starts differently and is left alone.
_add_custom("key-body",
            r"(?<![A-Za-z0-9+/])(?:b3BlbnNzaC1rZXktdjE|MII[A-Za-z0-9+/]{3}(?:IBADANBgkqhkiG9w0BAQEFAASC|IBAAKC|IBAAKB)"
            r"|MIG[A-Za-z0-9+/]AgEAMBMGByqGSM49|MH[cQ]CAQEEI|MIGkAgEBBDA|MIHcAgEBBEIB|MC4CAQAwBQYDK2VwBCIEI)"
            r"[A-Za-z0-9+/=]{20,}",
            ("b3blbnnzac1rzxkt", "ibadanbgkqhkig9w0baqefaasc", "ibaak", "ageambmgbyqgsm49", "caqeei", "agebbd",
             "agebbei", "mc4caqawbqydk2vw"),
            _token_check("private key", 0, True, False, 3.0))

# --------------------------------------------------------------------------- blocked regions
#
# Things that are never secrets even when they contain a secret-shaped piece: our own
# [hidden: ...] markers, base64 image data, lockfile integrity hashes.

_MARKER = re.compile(r"\[hidden: [^\]\n]{1,80}\]")
_B64RUN = re.compile(r"[A-Za-z0-9+/=_\-]{64,}")
_INTEGRITY = re.compile(r"sha(?:1|256|384|512)-[A-Za-z0-9+/]{20,}={0,2}")


def _blocked_regions(text: str) -> List[Tuple[int, int]]:
    regions: List[Tuple[int, int]] = []
    if "[hidden: " in text:
        for m in _MARKER.finditer(text):
            regions.append(m.span())
    pos = 0
    while True:
        i = text.find(";base64,", pos)
        if i < 0:
            break
        j = i + 8
        m = _B64RUN.match(text, j)
        if m is not None:
            regions.append((j, m.end()))
            pos = m.end()
        else:
            pos = j
    if "sha" in text:
        for m in _INTEGRITY.finditer(text):
            regions.append(m.span())
    if not regions:
        return regions
    regions.sort()
    merged = [regions[0]]
    for a, b in regions[1:]:
        if a <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return merged


# --------------------------------------------------------------------------- driver


class _Ctx:
    """State of one scan call: the mode, the deadline and two small caches for repeated values."""

    __slots__ = ("guard", "deadline", "memo", "words", "blocked", "bstarts")

    def __init__(self, guard: bool, deadline: float, blocked: List[Tuple[int, int]]) -> None:
        self.guard = guard
        self.deadline = deadline
        self.memo: Dict[Any, Tuple[bool, bool]] = {}
        self.words: Dict[Any, bool] = {}
        self.blocked = blocked
        self.bstarts = [r[0] for r in blocked]

    def inside_blocked(self, pos: int) -> bool:
        """True when pos lies inside one of our own [hidden: ...] markers or inside base64 image data."""
        if not self.bstarts:
            return False
        i = bisect_right(self.bstarts, pos) - 1
        return i >= 0 and self.blocked[i][1] > pos


def _windows(n: int) -> Iterable[Tuple[int, int]]:
    step = CHUNK - OVERLAP
    s = 0
    while True:
        e = min(n, s + CHUNK)
        yield s, e
        if e >= n:
            return
        s += step


def _scan_window(text: str, lo: int, hi: int, ctx: _Ctx, out: List[Span]) -> None:
    low = text[lo:hi].lower()
    for rule in _RULES:
        if not rule.wants(low):
            continue
        for m in rule.regex().finditer(text, lo, hi):
            res = rule.check(m, ctx.guard)
            if res is not None:
                out.append(res)
    for needle in _NAMED_NEEDLES:
        if needle in low:
            _scan_named(text, lo, hi, ctx, out)
            break
    _scan_prose(text, lo, hi, ctx, out)


def _run(text: str, cap: int, guard: bool, spans: List[Span], budget: float = TIME_BUDGET) -> Tuple[bool, str]:
    """Fill `spans` with the secrets in text[:cap]. Returns (truncated, error)."""
    n = len(text)
    truncated = n > cap
    if truncated:
        text = text[:cap]
        n = cap
    blocked = _blocked_regions(text)
    ctx = _Ctx(guard, time.monotonic() + budget, blocked)
    raw: List[Span] = []
    pem: List[Span] = []
    _scan_pem(text, pem)
    try:
        for lo, hi in _windows(n):
            if time.monotonic() > ctx.deadline:
                raise _Timeout()
            found: List[Span] = []
            _scan_window(text, lo, hi, ctx, found)
            for a, b, kind, strong in found:
                if b >= hi and hi < n:           # the window cut the token: take the rest of it
                    b = _TAIL.match(text, b).end()
                raw.append((a, b, kind, strong))
        error = ""
    except _Timeout:
        truncated = True
        error = "time budget"
    if blocked:
        starts = ctx.bstarts
        kept: List[Span] = []
        for a, b, kind, strong in raw:
            i = bisect_right(starts, b - 1) - 1
            if i >= 0 and blocked[i][1] > a:
                continue
            kept.append((a, b, kind, strong))
        raw = kept
    raw = [_card_block(text, a, b, blocked) if kind == "card" else (a, b, kind, strong) for a, b, kind, strong in raw]
    spans.extend(pem)
    spans.extend(raw)
    return truncated, error


def _merge(spans: List[Span]) -> List[Span]:
    """Sort and join overlapping spans. The earliest span keeps its kind; strong if any part is."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s[0], -s[1]))
    merged: List[Span] = []
    ca, cb, ck, cs = ordered[0]
    for a, b, kind, strong in ordered[1:]:
        if a < cb:
            if b > cb:
                cb = b
            cs = cs or strong
        else:
            merged.append((ca, cb, ck, cs))
            ca, cb, ck, cs = a, b, kind, strong
    merged.append((ca, cb, ck, cs))
    return merged


def _hits(text: str, merged: List[Span]) -> List[Hit]:
    out: List[Hit] = []
    for a, b, kind, strong in merged:
        value = text[a:b]
        if kind == "private key":
            head = value.split("-----", 2)
            preview = "-----%s----- (%d chars)" % (head[1], len(value)) if len(head) > 2 else mask(value)
        else:
            preview = mask(value)
        out.append(Hit(kind, a, b, preview, strong))
    return out


def _scan(text: Any, cap: int, guard: bool, strong_only: bool, budget: float = TIME_BUDGET) -> HitList:
    result = HitList()
    try:
        s = _to_str(text)
        cap = MAX_SCAN if cap is None else max(0, min(int(cap), HARD_MAX))
        spans: List[Span] = []
        truncated, error = _run(s, cap, guard, spans, budget)
        merged = _merge(spans)
        if strong_only:
            merged = [x for x in merged if x[3]]
        result.extend(_hits(s, merged))
        result.truncated = truncated
        result.error = error
        result.scanned = min(len(s), cap)
    except Exception:  # noqa: BLE001 - the contract is "never raises"
        result.truncated = True
        result.error = "internal error"
    return result


# --------------------------------------------------------------------------- public API

def find_secrets(text: Any) -> HitList:
    """Every secret-shaped piece of `text`, in store mode (hides as much as possible)."""
    return _scan(text, MAX_SCAN, False, False)


def scan_text(text: Any, max_bytes: int = MAX_SCAN, strong_only: bool = True) -> HitList:
    """Guard mode: secrets in text that a tool is about to write, run or commit.

    max_bytes   how many characters to look at (counted in characters; at most HARD_MAX)
    strong_only keep only hits that are almost certainly real (default). Pass False to also
                get weak shapes (short passwords, card numbers, JWTs, local database URLs).
    The result is a list of Hit. Check `.truncated` / `.error`: when a scan was incomplete the
    guard should ask instead of allowing.
    """
    return _scan(text, max_bytes, True, strong_only)


def scan_and_redact(text: Any) -> Tuple[str, HitList]:
    """redact() and find_secrets() in one pass: (redacted text, hits)."""
    s = _to_str(text)
    hits = _scan(s, MAX_SCAN, False, False)
    if hits.error:
        return _fail(len(s)), hits
    return _apply(s, hits), hits


def _fail(n: int) -> str:
    return "[hidden: redaction failed, %d chars]" % n


def _apply(s: str, hits: List[Hit]) -> str:
    parts: List[str] = []
    pos = 0
    for h in hits:
        parts.append(s[pos:h.start])
        parts.append("[hidden: %s]" % h.kind)
        pos = h.end
    limit = min(len(s), MAX_SCAN)
    parts.append(s[pos:limit])
    if len(s) > MAX_SCAN:
        parts.append("[hidden: %d more characters not checked]" % (len(s) - MAX_SCAN))
    return "".join(parts)


def redact(text: Any) -> str:
    """The text with every secret replaced by "[hidden: <kind>]".

    After an internal error or a time overrun the result is "[hidden: redaction failed, N chars]"
    and contains none of the input. Text beyond MAX_SCAN characters is replaced by a short note.
    """
    n = 0
    try:
        s = _to_str(text)
        n = len(s)
        hits = _scan(s, MAX_SCAN, False, False)
        if hits.error:
            return _fail(n)
        return _apply(s, hits)
    except Exception:  # noqa: BLE001 - redact must not raise and must not leak
        return _fail(n)


def looks_like_real(value: Any) -> bool:
    """True when `value` looks like a real secret rather than a placeholder, a hash or an identifier."""
    try:
        v = _to_str(value).strip().strip("\"'`")
        if len(v) < 8 or "[hidden" in v:
            return False
        if _PLACEHOLDER.search(v) or _SEQUENCE.search(v) or v.lower() in _NONSECRET:
            return False
        hits = _scan(v, MAX_SCAN, True, True)
        for h in hits:
            if h.end - h.start >= 0.9 * len(v):
                return True
        if len(v) < 16 or v.startswith(("/", "./", "../", "~", "http://", "https://", "data:")):
            return False
        if re.fullmatch(r"[0-9a-fA-F]{32,128}", v):
            return False                                   # hash digest or commit id
        if re.fullmatch(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", v):
            return False                                   # uuid
        if re.match(r"(?i)sha\d+-", v) or re.fullmatch(r"v?\d+(?:\.\d+)+\S*", v):
            return False                                   # integrity string, version
        return _entropy(v) >= 3.0 and len(set(v)) >= 6 and _random_looking(v)
    except Exception:  # noqa: BLE001
        return False


def compiled_regexes() -> List[Tuple[str, Any]]:
    """Every compiled regex of this module (for the regex fuzz test): (name, pattern)."""
    out: List[Tuple[str, Any]] = []
    seen = set()
    for rule in _RULES:
        rx = rule.regex()
        out.append(("rule:" + rule.name, rx))
        seen.add(id(rx))
    for name, value in sorted(globals().items()):
        if isinstance(value, re.Pattern) and id(value) not in seen:
            out.append((name, value))
            seen.add(id(value))
    return out


# --------------------------------------------------------------------------- file names

_SAFE_WORDS = frozenset(["example", "sample", "template", "dist", "default", "defaults", "tpl"])
_SECRET_DIRS = frozenset([".ssh", ".gnupg", ".aws", ".kube"])
_SSH_SAFE = frozenset(["config", "known_hosts", "known_hosts.old", "authorized_keys"])
_CODE_RECEIVERS = frozenset(["process", "import.meta", "meta", "rails", "deno", "bun", "window", "globalthis",
                             "global", "self", "this", "os", "sys", "django", "vite", "nuxt", "node", "env",
                             "runtime", "import", "bundle"])
_SECRET_EXT = (".pem", ".p12", ".pfx", ".jks", ".keystore", ".ppk", ".kdbx", ".key", ".p8", ".pk8", ".jceks",
               ".pkcs12", ".tfstate", ".tfstate.backup")
_SECRET_NAMES = frozenset([".npmrc", ".pypirc", ".netrc", "_netrc", ".git-credentials", ".pgpass", ".htpasswd",
                           ".dockercfg", ".s3cfg", ".boto", "kubeconfig", "terraform.tfvars",
                           "terraform.tfvars.json", "google-services.json", "googleservice-info.plist",
                           "wp-config.php", "local.settings.json", ".secret", ".secrets", ".envrc",
                           ".credentials", ".credentials.json", "credentials", "credentials.json",
                           "credentials.csv", "credentials.yml", "credentials.yaml", "credentials.xml"])
_RX_ENVFILE = re.compile(r"^\.env(?:[._\-].*)?$")
_RX_IDKEY = re.compile(r"^id_(?:rsa|dsa|ecdsa|ed25519)(?:[_\-.][\w.\-]*)?$")
_RX_SECRETSFILE = re.compile(r"(?:^|[._\-])secrets?(?:\.[\w\-]+)*\.(?:ya?ml|json|toml|env|txt|ini|conf)$")
_RX_CLIENTSECRET = re.compile(r"^(?:client[_\-]secrets?[\w.\-]*\.json|service[_\-]?account[\w.\-]*\.json"
                              r"|firebase-adminsdk[\w.\-]*\.json|[\w.\-]+\.auto\.tfvars)$")


_RX_ADS = re.compile(r"(?i)::\$[a-z_]{1,20}$")      # NTFS alternate data stream: .env::$DATA is the same file
_GLOB_CANDIDATES = (".env", ".env.local", ".env.production", ".envrc", "id_rsa", "id_ed25519", ".npmrc",
                    ".netrc", ".pgpass")


def _norm_path(path: Any) -> str:
    p = _to_str(path).strip().strip("\"'` \t")
    p = _RX_ADS.sub("", p)
    p = p.replace("\\", "/")
    while "//" in p:
        p = p.replace("//", "/")
    return p


def _glob_may_match_secret(base: str) -> bool:
    """A name with * or ? (cat .env*, type .e*) could expand to a secret file: say yes when it can."""
    if len(base) > 64 or sum(1 for c in base if c not in "*?") < 2:
        return False
    pattern = "".join(".*" if c == "*" else "." if c == "?" else re.escape(c) for c in base)
    rx = re.compile("^" + pattern + "$")
    return any(rx.match(name) for name in _GLOB_CANDIDATES)


def _has_safe_word(base: str) -> bool:
    parts = base.split(".")
    return any(part in _SAFE_WORDS for part in parts[1:] if part) or (len(parts) > 1 and parts[0] in _SAFE_WORDS)


def is_secret_filename(path: Any) -> bool:
    """True when the file name usually holds secrets: .env files, private keys, credentials ...

    Safe exceptions: .env.example / .sample / .template / .dist / .defaults / .tpl, *.pub,
    known_hosts, ~/.ssh/config. Code such as process.env, import.meta.env and Rails.env is not a file.
    """
    try:
        p = _norm_path(path)
        if not p:
            return False
        if any(c in p for c in "()[]{};,=$`\"'|<>"):
            return False                                     # code or a pipeline, not a path
        parts = [x for x in p.split("/") if x]
        if not parts:
            return False
        base = parts[-1].lower()
        dirs = [x.lower() for x in parts[:-1]]
        if base.endswith(".pub") or (base.endswith("~") and base[:-1].endswith(".pub")):
            return False
        safe_word = _has_safe_word(base)
        if ".ssh" in dirs:
            return not (base in _SSH_SAFE or base.startswith("known_hosts"))
        if any(d in _SECRET_DIRS for d in dirs):
            return not safe_word
        if "gh" in dirs and ".config" in dirs:
            return True
        if ".docker" in dirs and base == "config.json":
            return True
        if "*" in base or "?" in base:
            return _glob_may_match_secret(base)
        if safe_word:
            return False
        if _RX_ENVFILE.match(base):
            return True
        if base.endswith(".env"):
            stem = base[:-4]
            if not stem or stem in _CODE_RECEIVERS or stem.rsplit(".", 1)[-1] in _CODE_RECEIVERS:
                return False
            return True
        if _RX_IDKEY.match(base):
            return True
        if base in _SECRET_NAMES:
            return True
        if base.endswith(_SECRET_EXT):
            return True
        if _RX_SECRETSFILE.search(base) or _RX_CLIENTSECRET.match(base):
            return True
        return False
    except Exception:  # noqa: BLE001
        return False


# --------------------------------------------------------------------------- facts for callers

# Kinds that are weak by shape. Hit.strong is the per-hit truth; this set is for documentation
# and for callers that only have a kind name.
WEAK_KINDS = frozenset(["card", "JSON Web Token", "Google API key", "local database URL password"])
