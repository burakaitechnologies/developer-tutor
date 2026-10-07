"""archrules.py - architecture tripwires for the PostToolUse hook (SPEC 7.5).

What it is: a small rule set that looks at one file (or one shell command)
the agent just wrote or ran and reports patterns a beginner project should
not carry silently: new dependencies, new top-level folders, very long files,
a CI workflow, and twenty code patterns (SQL built from strings, eval, open
database ports, and so on).

Why it exists: the model writes fast. A short fact in its context ("this file
builds SQL from text") lets it explain the risk in one plain sentence while
the learner can still follow. Tripwires are nudges. They never block.

How it fails safely: every public function catches all errors and returns an
empty list. Every regular expression uses bounded gaps (no unbounded
`[^x]*`), so a 100 KB hostile file cannot stall the hook. Files over 200 KB,
lines over 2,000 characters, lockfiles, minified files and build or vendor
folders are skipped before any pattern runs.

Who calls it: hooks/handlers/post_tool.py (check_file after Write, Edit and
NotebookEdit; check_command after Bash and PowerShell). The caller keeps the
"once per file per session" set and passes the `once_key` values back through
select_visible(). Twelve rules are logged only (model_visible False).

A Tripwire is a plain dict, safe to store as JSON:
    rule_id, kind, name, text, model_visible, once_key
plus optional extras: queued (bool), rel (str), line (int), items (list).
kind is one of: code, manifest, top-dir, big-file, workflow.
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

try:
    from . import untrusted as _untrusted
except ImportError:  # loaded as a flat module (tests, scripts)
    try:
        import untrusted as _untrusted  # type: ignore
    except ImportError:
        _untrusted = None  # type: ignore

# ---------------------------------------------------------------- limits

MAX_FILE_BYTES = 200 * 1024     # larger files are skipped
MAX_LINE_CHARS = 2000           # longer lines are blanked before matching
BIG_FILE_LINES = 400            # "file > 400 lines" tripwire
MAX_NAMES_SHOWN = 6             # dependency names listed in one tripwire
MAX_DEPS_PARSED = 400           # stop reading a manifest after this many names

SKIP_DIRS = (
    "node_modules", "dist", "build", "vendor", ".git", "__pycache__", ".venv",
    "venv", "site-packages", ".next", ".nuxt", ".svelte-kit", ".cache",
    "coverage", ".claude",
)
LOCKFILES = frozenset((
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json",
    "cargo.lock", "poetry.lock", "go.sum", "gemfile.lock", "composer.lock",
    "uv.lock", "pdm.lock", "pipfile.lock", "bun.lockb", "bun.lock",
))

# ---------------------------------------------------------------- messages
# {rule_id: {short, why, safe, lesson}}. `lesson` is a concept id in
# knowledge/concepts/*.jsonl. The guard rules keep their texts in
# hooks/guard-messages.json; these texts stay here (see SPEC 7.5).

MESSAGES: Dict[str, Dict[str, str]] = {
    "sql-concat": {
        "short": "SQL is built by joining text with variables",
        "why": "A user can type SQL into an input box and it would run.",
        "safe": "Use placeholders (? or %s) and pass the values separately.",
        "lesson": "arch-anti-sql-strings",
    },
    "eval-exec": {
        "short": "text is run as code or as a shell command",
        "why": "If a user controls that text, they can run anything on this computer.",
        "safe": "Call the function directly, or pass the command as a list without a shell.",
        "lesson": "sec-input-validation",
    },
    "innerhtml": {
        "short": "raw HTML is put into the page",
        "why": "If it holds text a user typed, a script in it runs in other people's browsers.",
        "safe": "Use textContent, or let the framework escape the text.",
        "lesson": "sec-xss",
    },
    "unsafe-deserialize": {
        "short": "data is loaded in a way that can run code",
        "why": "Loading outside data with pickle or a plain yaml.load can run code hidden in it.",
        "safe": "Use JSON, or yaml.safe_load.",
        "lesson": "sec-input-validation",
    },
    "frontend-secret-env": {
        "short": "a secret-looking variable name ships to the browser",
        "why": "Names that start with NEXT_PUBLIC_, VITE_ or similar are copied into the page everyone can read.",
        "safe": "Keep the secret on the server and let the browser ask your server.",
        "lesson": "arch-anti-frontend-secrets",
    },
    "debug-on": {
        "short": "debug mode is switched on",
        "why": "Debug pages show internal details, and the Flask debugger can run code.",
        "safe": "Read the setting from an environment variable and keep it off by default.",
        "lesson": "arch-security-by-default",
    },
    "bind-all": {
        "short": "the server listens on every network address (0.0.0.0)",
        "why": "Anyone on the same network can reach it, not only you.",
        "safe": "Use 127.0.0.1 while building. Widen it only when you deploy on purpose.",
        "lesson": "arch-security-by-default",
    },
    "db-port-published": {
        "short": "a database port is open to the whole network",
        "why": "Scanners find open database ports within minutes.",
        "safe": "Write 127.0.0.1:5432:5432, or publish no port at all.",
        "lesson": "arch-security-by-default",
    },
    "weak-hash-password": {
        "short": "a fast hash is used for a password",
        "why": "Fast hashes can be guessed billions of times per second.",
        "safe": "Use bcrypt, argon2 or scrypt through a library.",
        "lesson": "sec-password-storage",
    },
    "plaintext-password-store": {
        "short": "a password is stored as received",
        "why": "If the database is copied, every password can be read.",
        "safe": "Store only a hash made by a password library.",
        "lesson": "sec-password-storage",
    },
    "insecure-random": {
        "short": "a predictable random number makes something secret",
        "why": "Predictable numbers can be guessed.",
        "safe": "Use the secrets module or crypto.randomBytes.",
        "lesson": "arch-anti-custom-auth",
    },
    "open-firewall": {
        "short": "access is open to the whole internet or to any website",
        "why": "Anyone can call it, not only your own app.",
        "safe": "Name the exact addresses or websites that may connect.",
        "lesson": "arch-security-by-default",
    },
    "firebase-open-rules": {
        "short": "anyone may read or write the database",
        "why": "The rules say yes to every visitor.",
        "safe": "Require a signed-in user and check that the record is theirs.",
        "lesson": "arch-security-by-default",
    },
    "no-timeout": {
        "short": "a network call has no timeout",
        "why": "It can wait forever and freeze the program.",
        "safe": "Add timeout=10 (seconds) to the call.",
        "lesson": "arch-error-handling",
    },
    "swallowed-error": {
        "short": "an error is silently ignored",
        "why": "Small bugs turn into mysteries when nothing is shown.",
        "safe": "Log the error, or handle the one case you expect.",
        "lesson": "arch-error-handling",
    },
    "unbounded-paid-loop": {
        "short": "a loop calls an outside service with no visible limit",
        "why": "A bug can run it all night and spend money.",
        "safe": "Add a maximum number of calls and a pause between them.",
        "lesson": "arch-anti-paid-api-loop",
    },
    "retry-no-cap": {
        "short": "retries have no upper limit",
        "why": "A failing call can repeat forever and multiply costs.",
        "safe": "Stop after a few attempts, for example 3.",
        "lesson": "arch-anti-paid-api-loop",
    },
    "path-traversal": {
        "short": "a file path comes from the user",
        "why": "A path like ../../secret can read files outside the folder you meant.",
        "safe": "Allow only known file names, or clean the name first.",
        "lesson": "sec-input-validation",
    },
    "open-redirect": {
        "short": "the app redirects to an address the user supplies",
        "why": "A link on your site can send visitors to a fake site.",
        "safe": "Redirect only to paths you list.",
        "lesson": "sec-input-validation",
    },
    "secret-in-localstorage": {
        "short": "a token is kept in localStorage",
        "why": "Any script on the page can read localStorage.",
        "safe": "Let the server set an HttpOnly cookie.",
        "lesson": "web-cookies-sessions",
    },
    "new-dependency": {
        "short": "new dependency",
        "why": "Every package is other people's code that runs on your computer.",
        "safe": "Check the spelling, the download count and the date of the last release.",
        "lesson": "arch-dependency-cost",
    },
    "new-top-dir": {
        "short": "new top-level folder",
        "why": "Top-level folders shape how the whole project is organised.",
        "safe": "Name the folder by its purpose and keep related files together.",
        "lesson": "arch-folders-by-purpose",
    },
    "big-file": {
        "short": "very long file",
        "why": "A file this long is hard to read, review and change safely.",
        "safe": "Split it by job when it makes sense.",
        "lesson": "arch-simplicity-size",
    },
    "workflow-added": {
        "short": "GitHub Actions workflow added",
        "why": "It runs commands on GitHub every time someone pushes.",
        "safe": "Keep it small, and never print secrets in it.",
        "lesson": "proj-ci",
    },
}

# These eight code patterns plus the four structural rules reach the model.
# The other twelve are only logged to activity.jsonl.
MODEL_VISIBLE_RULES = frozenset((
    "sql-concat", "eval-exec", "innerhtml", "unsafe-deserialize",
    "frontend-secret-env", "debug-on", "bind-all", "db-port-published",
    "new-dependency", "new-top-dir", "big-file", "workflow-added",
))
# Kinds that the greenfield rule queues instead of showing.
QUEUED_KINDS = frozenset(("manifest", "top-dir", "big-file", "workflow"))

# Order in which tripwires are returned (the caller shows at most one per turn).
PRIORITY = (
    "frontend-secret-env", "sql-concat", "eval-exec", "unsafe-deserialize",
    "innerhtml", "db-port-published", "debug-on", "bind-all",
    "new-dependency", "workflow-added", "new-top-dir", "big-file",
)

_HEAVY_DIRS = frozenset((
    "services", "microservices", "k8s", "kubernetes", "helm", "terraform",
    "infra", "infrastructure",
))
_QUIET_DIRS = frozenset((
    "docs", "doc", "test", "tests", "__tests__", "spec", "specs", "tmp",
    "temp", "out", "target", "bin", "obj", "logs", "log",
))

# ---------------------------------------------------------------- text helpers


def _fallback_clean(text: str, n: int) -> str:
    out = []
    for ch in str(text):
        if ch in "<>`":
            out.append("'")
        elif ch.isprintable():
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())[:n]


def _clean(text: Any, n: int) -> str:
    """Neutralise text that came from a file, a path or a command."""
    try:
        if _untrusted is not None:
            return str(_untrusted.neutralize(str(text), n))
    except Exception:
        pass
    return _fallback_clean(str(text), n)


_NAME_OK = re.compile(r"[^A-Za-z0-9@/._+~:-]")
_NAME_CHARS = frozenset("._-/ ")


def _clean_name(name: str) -> str:
    """A package or folder name: strict character set, then neutralised."""
    return _clean(_NAME_OK.sub("", str(name))[:60], 60)


def _name_text(name: Any, n: int = 80) -> str:
    """A file or folder name as tripwire text may show it: letters, digits, dot, dash, underscore, slash and
    space only (any other character becomes a question mark), neutralised, at most n characters."""
    safe = "".join(c if (c.isalnum() or c in _NAME_CHARS) else "?" for c in str(name))
    return _clean(safe, n)


def _fence(body: str, label: str) -> str:
    """Put text that came from a name inside an untrusted fence: the model reads it as data, never as an
    instruction, even when the name is a sentence."""
    try:
        if _untrusted is not None:
            return _untrusted.fence(label, body)
    except Exception:  # noqa: BLE001 - fall through to the plain fence
        pass
    return '<<untrusted label="%s">> %s <</untrusted>>' % (label, body)


def _shown(name: Any, label: str = "file", n: int = 80) -> str:
    """A file or folder name inside tripwire text: the strict characters, then the fence."""
    return _fence(_name_text(name, n), label)


def _norm_rel(rel: str) -> str:
    r = str(rel or "").replace("\\", "/")
    while r.startswith("./"):
        r = r[2:]
    return r.lstrip("/")


def _basename(rel: str) -> str:
    return rel.rsplit("/", 1)[-1]


def _rx(pattern: str, flags: int = 0) -> "re.Pattern[str]":
    return re.compile(pattern, flags)


# ---------------------------------------------------------------- patterns
# Every gap is bounded ({0,N}). Lookaheads are bounded too. A line that holds
# only the trigger word repeated 20,000 times costs a few hundred steps per
# trigger, never a quadratic scan.

_I = re.I
_M = re.M
_SQLKW = r"\b(?:select|insert|update|delete|drop)\b"
_SQLVERB = r"\b(?:execute|executemany|query|raw|exec|prepare|run|all|get|each)"

SQL_PATTERNS = (
    # Python f-string with a SQL word and a {placeholder}
    _rx(_SQLVERB + r"\s{0,3}\(\s{0,3}f\"(?=[^\"\n]{0,200}" + _SQLKW + r")(?=[^\"\n]{0,200}\{)", _I),
    _rx(_SQLVERB + r"\s{0,3}\(\s{0,3}f'(?=[^'\n]{0,200}" + _SQLKW + r")(?=[^'\n]{0,200}\{)", _I),
    # "..." + x   or   "..." % x   or   "...".format(
    _rx(r"\b(?:execute|query|raw)\s{0,3}\(\s{0,3}\"(?=[^\"\n]{0,200}" + _SQLKW +
        r")[^\"\n]{0,200}\"\s{0,3}(?:\+|%\s{0,3}[\w(]|\.format\()", _I),
    _rx(r"\b(?:execute|query|raw)\s{0,3}\(\s{0,3}'(?=[^'\n]{0,200}" + _SQLKW +
        r")[^'\n]{0,200}'\s{0,3}(?:\+|%\s{0,3}[\w(]|\.format\()", _I),
    # JavaScript template literal with ${...}
    _rx(r"\b(?:query|execute|raw|all|get|run)\s{0,3}\(\s{0,3}`(?=[^`]{0,400}" + _SQLKW +
        r")[^`]{0,400}\$\{", _I),
    # PHP and Java
    _rx(r"\b(?:mysqli_query|mysql_query|pg_query)\s{0,3}\([^;\n]{0,300}\$_(?:GET|POST|REQUEST|COOKIE)", _I),
    _rx(r"\bcreateStatement\s{0,3}\(\s{0,3}\)\s{0,3}\.\s{0,3}execute(?:Query|Update)?\s{0,3}\([^;\n]{0,300}\+", _I),
    # a SQL sentence in quotes, ending with = or LIKE or ( , then + variable
    _rx(r"\"(?=[^\"\n]{0,200}\b(?:select|insert|update|delete)\b)(?=[^\"\n]{0,200}\b(?:from|into|set|where|values)\b)"
        r"[^\"\n]{0,200}(?:[=<>(,]|\blike|\bin)\s{0,3}'?%?\s{0,3}\"\s{0,3}\+\s{0,3}[A-Za-z_(]", _I),
    _rx(r"'(?=[^'\n]{0,200}\b(?:select|insert|update|delete)\b)(?=[^'\n]{0,200}\b(?:from|into|set|where|values)\b)"
        r"[^'\n]{0,200}(?:[=<>(,]|\blike|\bin)\s{0,3}\"?%?\s{0,3}'\s{0,3}\+\s{0,3}[A-Za-z_(]", _I),
    # a SQL sentence kept in a variable: a value is put in after = / LIKE / VALUES / SET by f-string,
    # template literal, % or .format (a prompt such as "select a file from {folder}" does not match)
    _rx(r"f\"(?=[^\"\n]{0,120}\b(?:select|insert|update|delete)\b)(?=[^\"\n]{0,120}\b(?:from|into|set)\b)"
        r"[^\"\n]{0,120}(?:=|\blike\b|\bvalues\b|\bset\b)\s{0,3}\(?\s{0,3}'?%?\{", _I),
    _rx(r"f'(?=[^'\n]{0,120}\b(?:select|insert|update|delete)\b)(?=[^'\n]{0,120}\b(?:from|into|set)\b)"
        r"[^'\n]{0,120}(?:=|\blike\b|\bvalues\b|\bset\b)\s{0,3}\(?\s{0,3}\"?%?\{", _I),
    _rx(r"`(?=[^`]{0,200}\b(?:select|insert|update|delete)\b)(?=[^`]{0,200}\b(?:from|into|set)\b)"
        r"[^`]{0,200}(?:=|\blike\b|\bvalues\b|\bset\b)\s{0,3}\(?\s{0,3}'?%?\$\{", _I),
    _rx(r"\"(?=[^\"\n]{0,120}\b(?:select|insert|update|delete)\b)(?=[^\"\n]{0,120}\b(?:from|into|set)\b)"
        r"[^\"\n]{0,120}(?:=|\blike\b)\s{0,3}'?%[sd]'?[^\"\n]{0,60}\"\s{0,3}%\s{0,3}[\w(]", _I),
    _rx(r"\"(?=[^\"\n]{0,120}\b(?:select|insert|update|delete)\b)(?=[^\"\n]{0,120}\b(?:from|into|set)\b)"
        r"[^\"\n]{0,120}(?:=|\blike\b)\s{0,3}'?\{\w{0,20}\}'?[^\"\n]{0,60}\"\s{0,3}\.format\(", _I),
)

_LIT_ARG = r"(?![\"'][^\"'\n]{0,200}[\"']\s{0,5}\))"
EVAL_PATTERNS = (
    _rx(r"(?<![\w.$])(?:eval|exec|execSync)\s{0,5}\(\s{0,5}(?!\))" + _LIT_ARG),
    _rx(r"\bnew\s{1,5}Function\s{0,5}\("),
    _rx(r"\bchild_process\s{0,3}\.\s{0,3}exec(?:Sync)?\s{0,3}\(\s{0,3}[`'\"][^`'\"\n]{0,200}(?:\$\{|['\"]\s{0,3}\+)"),
    _rx(r"\bos\.(?:system|popen)\s{0,3}\(\s{0,3}" + _LIT_ARG),
    _rx(r"\bsubprocess\.(?:run|call|Popen|check_output|check_call)\s{0,3}\([^)]{0,300}shell\s{0,3}=\s{0,3}True"),
)

_EMPTY_OR_STATIC = (
    r"(?![ \t]{0,3}(?:\"[^\"\n]{0,300}\"|'[^'\n]{0,300}'|`[^`$\n]{0,300}`)[ \t]{0,3};?[ \t]{0,3}(?:\n|$))"
)
INNERHTML_PATTERNS = (
    _rx(r"\.innerHTML[ \t]{0,3}\+?=(?!=)" + _EMPTY_OR_STATIC, _M),
    _rx(r"\.outerHTML[ \t]{0,3}\+?=(?!=)" + _EMPTY_OR_STATIC, _M),
    _rx(r"dangerouslySetInnerHTML"),
    _rx(r"v-html[ \t]{0,3}="),
    _rx(r"document\.write(?:ln)?\s{0,3}\("),
    _rx(r"insertAdjacentHTML\s{0,3}\("),
)

DESERIALIZE_PATTERNS = (
    _rx(r"\b(?:c?[Pp]ickle|_pickle|dill|cloudpickle)\.loads?\s{0,3}\("),
    _rx(r"\byaml\.(?:load|load_all)\s{0,3}\((?![^)\n]{0,200}(?:Loader\s{0,3}=\s{0,3})?(?:yaml\.)?(?:Safe|CSafe)Loader)"),
    _rx(r"\bmarshal\.loads?\s{0,3}\("),
    _rx(r"\bunserialize\s{0,3}\("),
)

WEAK_HASH_PATTERNS = (
    _rx(r"\b(?:md5|sha1|sha256|sha512)\s{0,3}\([^)\n]{0,100}pass", _I),
    _rx(r"createHash\s{0,3}\(\s{0,3}[\"'](?:md5|sha1|sha256|sha512)[\"']\s{0,3}\)[^;\n]{0,100}pass", _I),
)

PLAINTEXT_PATTERNS = (
    _rx(r"insert\s{1,5}into\s{1,5}\w{0,30}users?\b(?=[^;\n]{0,150}\bpassword\b)[^;\n]{0,150}values", _I),
    _rx(r"\busers?\s{0,3}\.\s{0,3}(?:create|insert|save)\s{0,3}\(\s{0,3}\{[^}]{0,200}\bpassword\s{0,3}:\s{0,3}"
        r"(?:req\.body|request\.|data\.|body\.)", _I),
    _rx(r"\.password[ \t]{0,3}=[ \t]{0,3}(?:req\.body|request\.(?:form|json|data)|data)\b", _I),
)

# insecure-random: the anchor is the random call; the secret-looking name
# must stand before it on the same line (checked in code, see _find_insecure_random).
RANDOM_CALL = _rx(r"(?:Math\.random\s{0,3}\(|\brandom\.(?:random|randint|choice|choices|getrandbits)\s{0,3}\()")
RANDOM_NAME = _rx(
    r"(?:token|secret|session|reset|otp|password|apikey|api_key|nonce|csrf)\w{0,30}[ \t]{0,3}(?<![=!<>])=(?!=)", _I)

FRONTEND_SECRET_PATTERNS = (
    _rx(r"\b(?:NEXT_PUBLIC|VITE|REACT_APP|PUBLIC|EXPO_PUBLIC|NUXT_PUBLIC|GATSBY|VUE_APP)_\w{0,60}"
        r"(?:SECRET|PRIVATE|PASSWORD|PASSWD|SERVICE_ROLE|ADMIN_?KEY|API_?SECRET|TOKEN)\w{0,40}\b", _I),
)

DEBUG_PATTERNS = (
    _rx(r"\bapp\.run\s{0,3}\([^)\n]{0,200}debug\s{0,3}=\s{0,3}True", _I),
    _rx(r"^[ \t]{0,20}DEBUG[ \t]{0,3}=[ \t]{0,3}(?:True|true|1)\b", _M),
    _rx(r"\bFLASK_DEBUG[ \t]{0,3}=[ \t]{0,3}(?:1|true)\b", _I),
    _rx(r"\"debug\"\s{0,3}:\s{0,3}true[^\n]{0,100}prod", _I),
    _rx(r"NODE_ENV[ \t]{0,3}=[ \t]{0,3}development[^\n]{0,100}(?:deploy|prod)", _I),
    _rx(r"\bapp\.debug[ \t]{0,3}=[ \t]{0,3}True\b", _I),
)

BIND_ALL_PATTERNS = (
    _rx(r"\bhost[ \t]{0,3}[=:][ \t]{0,3}[\"']0\.0\.0\.0[\"']", _I),
    _rx(r"\.listen\s{0,3}\(\s{0,3}[\w.]{1,30}\s{0,3},\s{0,3}[\"']0\.0\.0\.0[\"']", _I),
    _rx(r"--host[= ]0\.0\.0\.0", _I),
    _rx(r"\bbind[ \t]{0,3}[=:][ \t]{0,3}[\"']?0\.0\.0\.0", _I),
    _rx(r"\bhost[ \t]{0,3}[=:][ \t]{0,3}0\.0\.0\.0\b", _I),
)

_DBPORTS = r"(?:5432|3306|27017|6379|1433|9200|11211)"
DB_PORT_PATTERNS = (
    _rx(r"^[ \t]{0,40}-[ \t]{0,5}[\"']?(?:0\.0\.0\.0:)?\d{2,5}:" + _DBPORTS +
        r"(?:/(?:tcp|udp))?[\"']?[ \t]{0,5}(?:#[^\n]{0,100})?$", _I | _M),
)

OPEN_FIREWALL_PATTERNS = (
    _rx(r"\b(?:cidr(?:_blocks?|ip)?|source_ranges|ingress)[ \t]{0,3}[=:\[][ \t]{0,3}\[?[ \t]{0,3}[\"']0\.0\.0\.0/0[\"']", _I),
    _rx(r"AllowAnyOrigin\s{0,3}\(", _I),
    _rx(r"Access-Control-Allow-Origin[\"']?[ \t]{0,3}[:,][ \t]{0,3}[\"']\*[\"']", _I),
    _rx(r"\bcors\s{0,3}\(\s{0,3}\)", _I),
    _rx(r"allow_origins[ \t]{0,3}=[ \t]{0,3}\[[ \t]{0,3}[\"']\*[\"'][ \t]{0,3}\]", _I),
)

FIREBASE_PATTERNS = (
    _rx(r"\ballow[ \t]{1,5}[a-z, \t]{1,60}:[ \t]{0,3}if[ \t]{1,5}true\b", _I),
    _rx(r"\"\.(?:read|write)\"[ \t]{0,3}:[ \t]{0,3}true", _I),
)

NO_TIMEOUT_PATTERNS = (
    _rx(r"\brequests\.(?:get|post|put|delete|patch|head)\s{0,3}\((?![\s\S]{0,150}?\btimeout\s{0,3}=)"),
)

SWALLOWED_PATTERNS = (
    _rx(r"\bexcept(?:[ \t]{1,5}(?:Base)?Exception(?:[ \t]{1,5}as[ \t]{1,5}\w{1,40})?)?[ \t]{0,3}:\s{0,40}(?:pass|\.\.\.)[ \t]{0,5}$", _M),
    _rx(r"\bcatch[ \t]{0,3}(?:\([ \t]{0,3}\w{0,30}[ \t]{0,3}\))?\s{0,20}\{\s{0,20}\}"),
    _rx(r"\.catch\s{0,3}\(\s{0,3}\(\s{0,3}\w{0,20}\s{0,3}\)\s{0,3}=>\s{0,3}\{\s{0,20}\}\s{0,3}\)"),
)

# unbounded-paid-loop: the loop header is the anchor; the window after it is
# cut at the first stop word and searched for an outside call (code, below).
LOOP_HEADER = _rx(
    r"(?:while[ \t]{1,5}true[ \t]{0,3}:|while[ \t]{0,3}\([ \t]{0,3}true[ \t]{0,3}\)|"
    r"for[ \t]{0,3}\([ \t]{0,3};[ \t]{0,3};[ \t]{0,3}\)|setInterval[ \t]{0,3}\()", _I)
LOOP_STOP = _rx(r"(?:\bmax_|\bMAX_|\blimit\b|\bbreak\b|\bbudget\b)")
LOOP_CALL = _rx(
    r"(?:openai|anthropic|\.chat\.completions|\.messages\.create|generate_content|"
    r"fetch\s{0,3}\(|requests\.|httpx\.|axios\.)", _I)
LOOP_WINDOW = 400
LOOP_MAX_HEADERS = 40

RETRY_PATTERNS = (
    _rx(r"@retry[ \t]{0,3}(?:\([ \t]{0,3}\))?[ \t]{0,3}$", _I | _M),
    _rx(r"\bretry\s{0,3}\(\s{0,3}(?:forever|Infinity)", _I),
    _rx(r"\bstop\s{0,3}=\s{0,3}stop_never", _I),
    _rx(r"\bretries?[ \t]{0,3}[:=][ \t]{0,3}(?:Infinity|-1|None)\b", _I),
    _rx(r"\bmax_?(?:retries|attempts|turns|iterations)[ \t]{0,3}[:=][ \t]{0,3}(?:None|-1|Infinity|0)\b", _I),
)

PATH_TRAVERSAL_PATTERNS = (
    _rx(r"\bopen\s{0,3}\(\s{0,3}os\.path\.join\s{0,3}\([^)\n]{0,150}request\."),
    _rx(r"\bsendFile\s{0,3}\(\s{0,3}(?:req\.(?:params|query|body)|path\.join\s{0,3}\([^)\n]{0,150}req\.)"),
    _rx(r"\breadFile(?:Sync)?\s{0,3}\(\s{0,3}(?:req\.|path\.join\s{0,3}\([^)\n]{0,150}req\.)"),
)

OPEN_REDIRECT_PATTERNS = (
    _rx(r"\bredirect\s{0,3}\(\s{0,3}(?:request\.(?:args|values|form)|req\.(?:query|body))"),
)

LOCALSTORAGE_PATTERNS = (
    _rx(r"\b(?:local|session)Storage\.setItem\s{0,3}\(\s{0,3}[\"'](?:token|jwt|access_?token|auth|session|password|api_?key)[\"']"),
)

# ---------------------------------------------------------------- file-type filters

_CODE_EXTS = "py|js|jsx|ts|tsx|mjs|cjs|php|rb|java|cs|go|rs|vue|svelte"
_CODE = r"\.(?:" + _CODE_EXTS + r")$"
_WEB = r"\.(?:html?|jsx|tsx|vue|svelte|js|ts|mjs|cjs)$"
_APPLIES = {
    "code": _rx(_CODE),
    "web": _rx(_WEB),
    "secret-env": _rx(r"(?:\.env[\w.]{0,40}|[\w.-]{0,60}\.env|\.(?:js|jsx|ts|tsx|mjs|cjs|html|vue|svelte|json|ya?ml)|dockerfile)$"),
    "debug": _rx(r"(?:\.(?:py|ya?ml|json|toml|cfg|ini)|\.env[\w.]{0,40}|[\w.-]{0,60}\.env)$"),
    "bind": _rx(r"\.(?:" + _CODE_EXTS + r"|ya?ml|json|toml|sh|ps1)$"),
    "compose": _rx(r"(?:docker-)?compose[\w.-]{0,40}\.ya?ml$"),
    "firewall": _rx(r"\.(?:tf|ya?ml|json|py|js|ts|cs)$"),
    "rules": _rx(r"(?:\.rules|database\.rules\.json)$"),
    "py": _rx(r"\.py$"),
}
_LONG_FILE_EXT = _rx(r"\.(?:" + _CODE_EXTS + r"|html?|css|scss|sass|less|sh|ps1|bat)$")


def _find_first(patterns: Iterable["re.Pattern[str]"], text: str) -> int:
    """Smallest match start over several patterns, or -1."""
    best = -1
    for rx in patterns:
        m = rx.search(text)
        if m is not None and (best < 0 or m.start() < best):
            best = m.start()
    return best


def _find_insecure_random(text: str) -> int:
    count = 0
    for m in RANDOM_CALL.finditer(text):
        count += 1
        if count > 200:
            break
        line_start = text.rfind("\n", 0, m.start()) + 1
        prefix = text[max(line_start, m.start() - 160):m.start()]
        if ";" in prefix:
            prefix = prefix.rsplit(";", 1)[1]
        if RANDOM_NAME.search(prefix):
            return m.start()
    return -1


def _find_paid_loop(text: str) -> int:
    count = 0
    for m in LOOP_HEADER.finditer(text):
        count += 1
        if count > LOOP_MAX_HEADERS:
            break
        window = text[m.end():m.end() + LOOP_WINDOW]
        stop = LOOP_STOP.search(window)
        if stop is not None:
            window = window[:stop.start()]
        if LOOP_CALL.search(window) is not None:
            return m.start()
    return -1


class _Rule(object):
    """One code rule: id, file filter, cheap word filter, finder."""

    def __init__(self, rule_id: str, applies: str, hints: Tuple[str, ...],
                 finder: Callable[[str], int]) -> None:
        self.rule_id = rule_id
        self.applies = _APPLIES[applies]
        self.hints = hints
        self.finder = finder


def _first_of(patterns: Tuple["re.Pattern[str]", ...]) -> Callable[[str], int]:
    return lambda text: _find_first(patterns, text)


# Rule order here is the order they are tried; PRIORITY sorts the result.
_RULES: Tuple[_Rule, ...] = (
    _Rule("sql-concat", "code", ("select", "insert", "update", "delete", "drop", "mysql", "pg_query", "createstatement"),
          _first_of(SQL_PATTERNS)),
    _Rule("eval-exec", "code", ("eval", "exec", "function", "system", "popen", "subprocess"), _first_of(EVAL_PATTERNS)),
    _Rule("innerhtml", "web", ("innerhtml", "outerhtml", "dangerouslysetinnerhtml", "v-html", "document.write",
                               "insertadjacenthtml"), _first_of(INNERHTML_PATTERNS)),
    _Rule("unsafe-deserialize", "code", ("pickle", "yaml", "marshal", "unserialize", "dill"), _first_of(DESERIALIZE_PATTERNS)),
    _Rule("weak-hash-password", "code", ("md5", "sha1", "sha256", "sha512"), _first_of(WEAK_HASH_PATTERNS)),
    _Rule("plaintext-password-store", "code", ("password",), _first_of(PLAINTEXT_PATTERNS)),
    _Rule("insecure-random", "code", ("random",), _find_insecure_random),
    _Rule("frontend-secret-env", "secret-env", ("_public_", "vite_", "react_app_", "public_", "gatsby_", "vue_app_",
                                                 "nuxt_public", "expo_public"), _first_of(FRONTEND_SECRET_PATTERNS)),
    _Rule("debug-on", "debug", ("debug",), _first_of(DEBUG_PATTERNS)),
    _Rule("bind-all", "bind", ("0.0.0.0",), _first_of(BIND_ALL_PATTERNS)),
    _Rule("db-port-published", "compose", ("5432", "3306", "27017", "6379", "1433", "9200", "11211"),
          _first_of(DB_PORT_PATTERNS)),
    _Rule("open-firewall", "firewall", ("0.0.0.0/0", "alloworigin", "allow-origin", "cors", "allow_origins"),
          _first_of(OPEN_FIREWALL_PATTERNS)),
    _Rule("firebase-open-rules", "rules", ("allow ", ".read", ".write"), _first_of(FIREBASE_PATTERNS)),
    _Rule("no-timeout", "py", ("requests.",), _first_of(NO_TIMEOUT_PATTERNS)),
    _Rule("swallowed-error", "code", ("except", "catch"), _first_of(SWALLOWED_PATTERNS)),
    _Rule("unbounded-paid-loop", "code", ("while", "for", "setinterval"), _find_paid_loop),
    _Rule("retry-no-cap", "code", ("retr", "stop_never", "max_"), _first_of(RETRY_PATTERNS)),
    _Rule("path-traversal", "code", ("open(", "sendfile", "readfile"), _first_of(PATH_TRAVERSAL_PATTERNS)),
    _Rule("open-redirect", "code", ("redirect",), _first_of(OPEN_REDIRECT_PATTERNS)),
    _Rule("secret-in-localstorage", "web", ("storage.setitem",), _first_of(LOCALSTORAGE_PATTERNS)),
)

# ---------------------------------------------------------------- manifests

_MANIFEST_BASENAMES = ("package.json", "pyproject.toml", "cargo.toml", "go.mod", "gemfile", "composer.json")
_REQ_NAME = _rx(r"^[ \t]{0,8}([A-Za-z0-9][A-Za-z0-9._-]{0,80})")
_TOML_TABLE = _rx(r"^\[\[?[ \t]{0,3}([^\]\n]{1,120}?)[ \t]{0,3}\]\]?[ \t]{0,3}(?:#.*)?$")
_TOML_KEY = _rx(r"^[ \t]{0,8}([A-Za-z0-9_\-]{1,80})(?:\.[A-Za-z0-9_\-]{1,40})?[ \t]{0,3}=")
_TOML_STR = _rx(r"\"((?:[^\"\\\n]|\\.){0,200})\"|'([^'\n]{0,200})'")
_GEM_LINE = _rx(r"^[ \t]{0,8}gem[ \t]{1,5}['\"]([A-Za-z0-9_.\-]{1,80})['\"]")
_GOMOD_LINE = _rx(r"^[ \t]{0,8}(?:require[ \t]{1,5})?([A-Za-z0-9][A-Za-z0-9._~/\-]{0,160})[ \t]{1,5}v[0-9][^\s]{0,60}")


def _norm_py_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name.lower())


def _json_keys(text: str, fields: Tuple[str, ...]) -> Optional[Set[str]]:
    try:
        data = json.loads(text)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    names: Set[str] = set()
    for field in fields:
        block = data.get(field)
        if isinstance(block, dict):
            for key in list(block.keys())[:MAX_DEPS_PARSED]:
                names.add(str(key))
    return names


def _deps_package_json(text: str) -> Optional[Set[str]]:
    return _json_keys(text, ("dependencies", "devDependencies", "optionalDependencies"))


def _deps_composer(text: str) -> Optional[Set[str]]:
    names = _json_keys(text, ("require", "require-dev"))
    if names is None:
        return None
    return set(n for n in names if n != "php" and not n.startswith(("ext-", "lib-")))


def _deps_requirements(text: str) -> Set[str]:
    names: Set[str] = set()
    for raw in text.split("\n")[:5000]:
        line = raw.split("#", 1)[0].strip()
        if not line or line.startswith(("-", ".", "/", "git+", "http", "file:")) or "://" in line:
            continue
        m = _REQ_NAME.match(line)
        if m is not None:
            names.add(_norm_py_name(m.group(1)))
        if len(names) >= MAX_DEPS_PARSED:
            break
    return names


def _toml_array_strings(lines: List[str], i: int) -> Tuple[List[str], int]:
    """Read a TOML array that starts on lines[i]; return its strings and the next line index."""
    buf: List[str] = []
    depth = 0
    quote = ""
    started = False
    j = i
    total = 0
    while j < len(lines) and total < 20000:
        line = lines[j]
        total += len(line)
        k = 0
        if not started:
            eq = line.find("=")
            k = eq + 1 if eq >= 0 else 0
        while k < len(line):
            ch = line[k]
            if quote:
                buf.append(ch)
                if ch == "\\" and quote == '"' and k + 1 < len(line):
                    buf.append(line[k + 1])
                    k += 1
                elif ch == quote:
                    quote = ""
            elif ch in "\"'":
                quote = ch
                buf.append(ch)
            elif ch == "#":
                break
            elif ch == "[":
                depth += 1
                started = True
            elif ch == "]":
                depth -= 1
                if started and depth <= 0:
                    text = "".join(buf)
                    strings = [(m.group(1) if m.group(1) is not None else m.group(2)) for m in _TOML_STR.finditer(text)]
                    return strings, j + 1
            k += 1
        buf.append("\n")
        j += 1
    return [], j


def _req_string_name(spec: str) -> str:
    m = _REQ_NAME.match(spec.strip())
    return _norm_py_name(m.group(1)) if m else ""


def _deps_pyproject(text: str) -> Set[str]:
    names: Set[str] = set()
    lines = text.replace("\r\n", "\n").split("\n")[:5000]
    table = ""
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("["):
            m = _TOML_TABLE.match(stripped)
            table = m.group(1).strip() if m else ""
            i += 1
            continue
        key = _TOML_KEY.match(lines[i])
        if key is None:
            i += 1
            continue
        k = key.group(1)
        if table == "project" and k == "dependencies" or table in ("project.optional-dependencies", "dependency-groups") \
                or (table == "tool.uv" and k == "dev-dependencies") or table == "tool.pdm.dev-dependencies":
            strings, nxt = _toml_array_strings(lines, i)
            for s in strings:
                n = _req_string_name(s)
                if n:
                    names.add(n)
            i = max(nxt, i + 1)
            continue
        if table in ("tool.poetry.dependencies", "tool.poetry.dev-dependencies") or \
                (table.startswith("tool.poetry.group.") and table.endswith(".dependencies")):
            if k.lower() != "python":
                names.add(_norm_py_name(k))
        i += 1
        if len(names) >= MAX_DEPS_PARSED:
            break
    return names


def _deps_cargo(text: str) -> Set[str]:
    names: Set[str] = set()
    table = ""
    for raw in text.replace("\r\n", "\n").split("\n")[:5000]:
        stripped = raw.strip()
        if stripped.startswith("["):
            m = _TOML_TABLE.match(stripped)
            table = m.group(1).strip() if m else ""
            hm = re.match(r"^(?:[\w\-]+\.)?(?:dev-|build-)?dependencies\.([A-Za-z0-9_\-]{1,80})$", table)
            if hm is not None:
                names.add(hm.group(1))
            continue
        is_dep_table = table in ("dependencies", "dev-dependencies", "build-dependencies", "workspace.dependencies") or \
            (table.startswith("target.") and table.endswith(("dependencies", "dev-dependencies", "build-dependencies")))
        if is_dep_table:
            key = _TOML_KEY.match(raw)
            if key is not None:
                names.add(key.group(1))
        if len(names) >= MAX_DEPS_PARSED:
            break
    return names


def _deps_gomod(text: str) -> Set[str]:
    names: Set[str] = set()
    in_block = False
    for raw in text.replace("\r\n", "\n").split("\n")[:5000]:
        line = raw.split("//", 1)[0].strip()
        if not line:
            continue
        if line.startswith("require") and line.rstrip().endswith("("):
            in_block = True
            continue
        if in_block and line.startswith(")"):
            in_block = False
            continue
        if in_block or line.startswith("require "):
            m = _GOMOD_LINE.match(line)
            if m is not None:
                names.add(m.group(1))
        if len(names) >= MAX_DEPS_PARSED:
            break
    return names


def _deps_gemfile(text: str) -> Set[str]:
    names: Set[str] = set()
    for raw in text.replace("\r\n", "\n").split("\n")[:5000]:
        m = _GEM_LINE.match(raw)
        if m is not None:
            names.add(m.group(1))
        if len(names) >= MAX_DEPS_PARSED:
            break
    return names


def manifest_kind(rel: str) -> str:
    """Return the manifest family for a project-relative path, or ''."""
    base = _basename(_norm_rel(rel)).lower()
    if base in LOCKFILES:
        return ""
    if base == "package.json":
        return "package.json"
    if base == "composer.json":
        return "composer.json"
    if base == "pyproject.toml":
        return "pyproject.toml"
    if base == "cargo.toml":
        return "Cargo.toml"
    if base == "go.mod":
        return "go.mod"
    if base == "gemfile":
        return "Gemfile"
    if re.match(r"^requirements[\w.-]{0,30}\.txt$", base):
        return "requirements.txt"
    return ""


def manifest_dependencies(rel: str, text: str) -> Optional[Set[str]]:
    """Names listed in a manifest, or None when the file cannot be read as that format."""
    family = manifest_kind(rel)
    try:
        if family == "package.json":
            return _deps_package_json(text)
        if family == "composer.json":
            return _deps_composer(text)
        if family == "pyproject.toml":
            return _deps_pyproject(text)
        if family == "Cargo.toml":
            return _deps_cargo(text)
        if family == "go.mod":
            return _deps_gomod(text)
        if family == "Gemfile":
            return _deps_gemfile(text)
        if family == "requirements.txt":
            return _deps_requirements(text)
    except Exception:
        return None
    return None


# ---------------------------------------------------------------- tripwire builders


def _tw(rule_id: str, kind: str, name: str, text: str, once_key: str, **extra: Any) -> Dict[str, Any]:
    tw: Dict[str, Any] = {
        "rule_id": rule_id,
        "kind": kind,
        "name": name,
        "text": text,
        "model_visible": rule_id in MODEL_VISIBLE_RULES,
        "once_key": once_key,
    }
    tw.update(extra)
    return tw


def _code_text(rule_id: str, rel: str, line: int) -> str:
    msg = MESSAGES[rule_id]
    where = _shown(rel, "file", 80)
    return ("Tripwire: %s in %s, line %d. Why it matters: %s Safer way: %s "
            "Explain it to the user in one plain sentence and say what you will do about it."
            % (msg["short"], where, line, msg["why"], msg["safe"]))


def _names_phrase(names: List[str]) -> str:
    """Package names (already cut to the name characters by _clean_name) in one fence."""
    shown = names[:MAX_NAMES_SHOWN]
    phrase = _fence(", ".join(shown), "package")
    if len(names) > len(shown):
        phrase += " and %d more" % (len(names) - len(shown))
    return phrase


def _manifest_tripwire(rel: str, family: str, names: List[str]) -> Dict[str, Any]:
    clean = [n for n in (_clean_name(x) for x in names) if n]
    clean = clean[:60]
    if not clean:
        return {}
    label = _shown(_basename(rel), "file", 60)
    plural = len(clean) > 1
    text = ("Tripwire: new %s %s in %s. In one plain sentence say what %s for. "
            "If %s a framework, database, auth, payment or hosting choice, run think-first; "
            "otherwise add one line to today's journal."
            % ("dependencies" if plural else "dependency", _names_phrase(clean), label,
               "each is" if plural else "it is",
               "one is" if plural else "it is"))
    key = "new-dependency:%s:%s" % (_norm_rel(rel), ",".join(sorted(clean))[:200])
    return _tw("new-dependency", "manifest", "new dependency", text, key, rel=_norm_rel(rel), items=clean)


def _topdir_text(name: str) -> str:
    base = ("Tripwire: new top-level folder %s. In one plain sentence say what it is for." % _shown(name, "folder", 60))
    if name.lower() in _HEAVY_DIRS:
        return base + (" Folders like this often mean more moving parts than a small project needs; "
                       "run think-first before adding more.")
    return base + " If it changes how the project is organised in a way that is hard to undo, run think-first."


def _topdir_tripwire(rel_top: str) -> Dict[str, Any]:
    name = _clean_name(rel_top)
    if not name:
        return {}
    return _tw("new-top-dir", "top-dir", "new top-level folder", _topdir_text(name),
               "new-top-dir:%s" % name, rel=name, items=[name])


def _dir_is_new(path: str, rel: str) -> bool:
    """Best guess that the top-level folder of `rel` holds only the file just written."""
    try:
        norm_path = str(path).replace("\\", "/")
        if not rel or not norm_path.lower().endswith(rel.lower()):     # rel may be lower-cased on Windows
            return False
        root = norm_path[:len(norm_path) - len(rel)].rstrip("/")
        top = root + "/" + rel.split("/", 1)[0]
        seen = 0
        for _base, _dirs, files in os.walk(top):
            seen += len(files)
            if seen > 1:
                return False
        return seen <= 1
    except Exception:
        return False


# ---------------------------------------------------------------- public API


def _skipped(rel: str) -> bool:
    low = rel.lower()
    base = _basename(low)
    if base in LOCKFILES or base.endswith(".lock"):
        return True
    if ".min." in base or base.endswith((".map", ".min")):
        return True
    parts = low.split("/")[:-1]
    for part in parts:
        if part in SKIP_DIRS:
            return True
    return False


def _line_count(text: str) -> int:
    if not text:
        return 0
    n = text.count("\n")
    return n if text.endswith("\n") else n + 1


def _prepare(text: str) -> str:
    """Normalise line ends and blank out lines that are too long to scan."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if len(text) <= MAX_LINE_CHARS:
        return text
    lines = text.split("\n")
    if any(len(line) > MAX_LINE_CHARS for line in lines):
        text = "\n".join(line if len(line) <= MAX_LINE_CHARS else "" for line in lines)
    return text


_HASH_COMMENT = _rx(r"^[ \t]{0,40}#[^\n]{0,2000}", _M)
_SLASH_COMMENT = _rx(r"^[ \t]{0,40}//[^\n]{0,2000}", _M)
_HASH_FILES = _rx(r"(?:\.(?:py|rb|ya?ml|toml|cfg|ini|sh|ps1|tf|php)|\.env[\w.]{0,40}|[\w.-]{0,60}\.env|dockerfile)$")
_SLASH_FILES = _rx(r"\.(?:js|jsx|ts|tsx|mjs|cjs|java|cs|go|rs|php|vue|svelte|tf|rules)$")


def _blank_comments(base: str, text: str) -> str:
    """Remove whole-line comments (the lines stay, so line numbers do not move).

    A commented-out line or a note such as "# eval() is slow" is not code that runs.
    """
    if _HASH_FILES.search(base) is not None and "#" in text:
        text = _HASH_COMMENT.sub("", text)
    if _SLASH_FILES.search(base) is not None and "//" in text:
        text = _SLASH_COMMENT.sub("", text)
    return text


def scan_code(rel: str, text: str) -> List[Tuple[str, int]]:
    """Run the code rules on one text. Returns [(rule_id, line)] with the first match per rule.

    Exposed for tests. `rel` picks the rules by file name; `text` is capped by the caller.
    Whole-line comments are ignored.
    """
    out: List[Tuple[str, int]] = []
    base = _basename(_norm_rel(rel)).lower()
    text = _blank_comments(base, text)
    low = text.lower()
    for rule in _RULES:
        if rule.applies.search(base) is None:
            continue
        if not any(h in low for h in rule.hints):
            continue
        try:
            pos = rule.finder(text)
        except Exception:
            pos = -1
        if pos >= 0:
            out.append((rule.rule_id, text.count("\n", 0, pos) + 1))
    return out


def _sort_key(tw: Dict[str, Any]) -> int:
    try:
        return PRIORITY.index(tw["rule_id"])
    except ValueError:
        return len(PRIORITY)


def _mark_greenfield(tripwires: List[Dict[str, Any]], greenfield: bool) -> None:
    if not greenfield:
        return
    for tw in tripwires:
        if tw["kind"] in QUEUED_KINDS:
            tw["model_visible"] = False
            tw["queued"] = True


def check_file(path: str, content: Any, rel: str, previous: Optional[str] = None, greenfield: bool = False,
               created: Optional[bool] = None, known_dirs: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Tripwires for one file the agent just wrote.

    path      absolute path (used only to guess a new top-level folder)
    content   the file text after the write (str or bytes)
    rel       project-relative path
    previous  text before the write, when the caller has it (then only NEW dependencies count)
    greenfield  first session or fewer than 10 tracked files: manifest, folder, long-file and
              workflow tripwires are returned queued (model_visible False, queued True)
    created   True for a new file, False for an edit, None when unknown
    known_dirs  top-level folder names that already existed (then only others are new)
    """
    try:
        return _check_file(path, content, rel, previous, greenfield, created, known_dirs)
    except Exception:
        return []


def _check_file(path: str, content: Any, rel: str, previous: Optional[str], greenfield: bool,
                created: Optional[bool], known_dirs: Optional[Iterable[str]]) -> List[Dict[str, Any]]:
    rel = _norm_rel(rel)
    if not rel:
        rel = _basename(str(path).replace("\\", "/"))
    if not rel or _skipped(rel):
        return []
    if isinstance(content, (bytes, bytearray)):
        content = bytes(content).decode("utf-8", "replace")
    if not isinstance(content, str):
        return []
    if len(content) > MAX_FILE_BYTES or len(content.encode("utf-8", "ignore")) > MAX_FILE_BYTES:
        return []
    out: List[Dict[str, Any]] = []
    text = _prepare(content)
    base = _basename(rel).lower()

    # dependency manifests
    family = manifest_kind(rel)
    # an edit of an existing manifest without the old text: every name would look new, so stay quiet
    if family and not (created is False and previous is None):
        now = manifest_dependencies(rel, text)
        if now is not None:
            if previous is not None:
                before = manifest_dependencies(rel, _prepare(previous if isinstance(previous, str) else ""))
                added = sorted(now - before) if before is not None else sorted(now)
            else:
                added = sorted(now)
            if added:
                tw = _manifest_tripwire(rel, family, added)
                if tw:
                    out.append(tw)

    # GitHub Actions workflow
    low_rel = rel.lower()
    if (low_rel.startswith(".github/workflows/") or "/.github/workflows/" in low_rel) and \
            base.endswith((".yml", ".yaml")) and created is not False:
        msg = MESSAGES["workflow-added"]
        out.append(_tw("workflow-added", "workflow", "workflow added",
                       "Tripwire: GitHub Actions file %s added. %s In one plain sentence say what it runs and when. "
                       "If it deploys anything or uses secrets, run think-first."
                       % (_shown(rel, "file", 80), msg["why"]),
                       "workflow-added:%s" % rel, rel=rel))

    # new top-level folder
    parts = rel.split("/")
    if len(parts) >= 2 and created is not False:
        top = parts[0]
        if not top.startswith(".") and top.lower() not in SKIP_DIRS and top.lower() not in _QUIET_DIRS:
            if known_dirs is not None:
                is_new = top not in set(known_dirs)
            else:
                is_new = _dir_is_new(path, rel)
            if is_new:
                tw = _topdir_tripwire(top)
                if tw:
                    out.append(tw)

    # long file (source and markup only)
    if _LONG_FILE_EXT.search(base):
        lines = _line_count(content)
        was_big = previous is not None and _line_count(previous) > BIG_FILE_LINES
        unknown_edit = created is False and previous is None
        if lines > BIG_FILE_LINES and not was_big and not unknown_edit:
            out.append(_tw("big-file", "big-file", "very long file",
                           "Tripwire: %s now has %d lines. In one plain sentence say what this file is for and "
                           "offer to split it by job. Do not split it unless the user agrees."
                           % (_shown(rel, "file", 80), lines),
                           "big-file:%s" % rel, rel=rel, line=lines))

    # code patterns
    for rule_id, line in scan_code(rel, text):
        out.append(_tw(rule_id, "code", MESSAGES[rule_id]["short"], _code_text(rule_id, rel, line),
                       "%s:%s" % (rule_id, rel), rel=rel, line=line))

    out.sort(key=_sort_key)
    _mark_greenfield(out, greenfield)
    return out


# ---------------------------------------------------------------- commands

_SEP = _rx(r"\n|&&|\|\||[;|&]")
_WORD = _rx(r"\"([^\"]*)\"|'([^']*)'|(\S+)")
_VALUED_OPTS = frozenset((
    "--registry", "--prefix", "-c", "--cwd", "--workspace", "-w", "--filter", "--tag", "--scope", "--cache",
    "-r", "--requirement", "-e", "--editable", "--constraint", "-i", "--index-url", "--extra-index-url",
    "-f", "--find-links", "-t", "--target", "--root", "--python", "--manifest-path", "-p", "--package",
    "--features", "-F", "--git", "--branch", "--path", "--rev", "--version", "-C", "--dir",
))


def _segments(command: str) -> List[str]:
    """Split a command at unquoted ; && || | & and newlines."""
    segs: List[str] = []
    cur: List[str] = []
    quote = ""
    i, n = 0, len(command)
    while i < n:
        ch = command[i]
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            cur.append(ch)
        elif ch in ";\n|&":
            segs.append("".join(cur))
            cur = []
            if i + 1 < n and command[i + 1] in "|&" and ch in "|&":
                i += 1
        else:
            cur.append(ch)
        i += 1
    segs.append("".join(cur))
    return [s.strip() for s in segs if s.strip()]


def _words(segment: str) -> List[str]:
    out = []
    for m in _WORD.finditer(segment):
        out.append(m.group(1) if m.group(1) is not None else (m.group(2) if m.group(2) is not None else m.group(3)))
    return out


def _prog(word: str) -> str:
    p = word.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if p.endswith(suffix):
            return p[:-len(suffix)]
    return p


_WRAPPERS = frozenset(("sudo", "env", "command", "builtin", "exec", "nohup", "time", "call", "&", "."))


def _strip_wrappers(words: List[str]) -> List[str]:
    i = 0
    while i < len(words):
        w = words[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w) or _prog(w) in _WRAPPERS:
            i += 1
            continue
        break
    return words[i:]


def _package_names(args: List[str], skip_urls: bool = True) -> List[str]:
    names: List[str] = []
    skip_next = False
    for a in args:
        if skip_next:
            skip_next = False
            continue
        if a == "--":
            continue
        if a.startswith("-"):
            if a in _VALUED_OPTS:
                skip_next = True
            continue
        if skip_urls and (("://" in a) or a.startswith((".", "/", "~", "git+", "github:", "file:", "link:", "npm:")) or
                          a.endswith((".tgz", ".whl", ".zip", ".tar.gz", ".txt"))):
            continue
        # strip version: express@4  @scope/pkg@1  flask==2.0  requests[security]>=2
        m = re.match(r"^(@[A-Za-z0-9._~-]{1,60}/[A-Za-z0-9._~-]{1,60}|[A-Za-z0-9][A-Za-z0-9._~/-]{0,80})", a)
        if m is not None:
            names.append(m.group(1))
    return names


def _sub_and_rest(args: List[str]) -> Tuple[str, List[str]]:
    """The first word that is not an option (skipping option values), and the words after it."""
    skip = False
    for idx, a in enumerate(args):
        if skip:
            skip = False
            continue
        if a.startswith("-"):
            skip = a in _VALUED_OPTS
            continue
        return a, args[idx + 1:]
    return "", []


def _install_names(words: List[str]) -> Tuple[str, List[str]]:
    """Return (manifest label, names) when the command adds packages, else ('', [])."""
    if not words:
        return "", []
    prog = _prog(words[0])
    args = words[1:]
    sub, rest = _sub_and_rest(args)
    flags = set(a for a in args if a.startswith("-"))
    if prog in ("npm", "pnpm", "yarn", "bun"):
        if sub in ("install", "i", "add") and not ({"-g", "--global"} & flags):
            return "package.json", _package_names(rest)
        return "", []
    if prog in ("pip", "pip3") or re.match(r"^pip3\.\d+$", prog):
        return ("pip", _package_names(rest)) if sub == "install" else ("", [])
    if prog in ("python", "python3", "py") or re.match(r"^python3?\.\d+$", prog):
        if "-m" in args and args.index("-m") + 1 < len(args) and args[args.index("-m") + 1] == "pip":
            sub2, rest2 = _sub_and_rest(args[args.index("-m") + 2:])
            if sub2 == "install":
                return "pip", _package_names(rest2)
        return "", []
    if prog == "uv":
        if sub == "add":
            return "pyproject.toml", _package_names(rest)
        sub2, rest2 = _sub_and_rest(rest)
        if sub == "pip" and sub2 == "install":
            return "pip", _package_names(rest2)
        return "", []
    if prog in ("poetry", "pdm"):
        return ("pyproject.toml", _package_names(rest)) if sub == "add" else ("", [])
    if prog == "pipenv":
        return ("Pipfile", _package_names(rest)) if sub == "install" else ("", [])
    if prog == "cargo":
        return ("Cargo.toml", _package_names(rest)) if sub == "add" else ("", [])
    if prog == "go":
        return ("go.mod", _package_names(rest)) if sub == "get" else ("", [])
    if prog == "composer":
        return ("composer.json", _package_names(rest)) if sub == "require" else ("", [])
    if prog == "bundle":
        return ("Gemfile", _package_names(rest)) if sub == "add" else ("", [])
    return "", []


def _published_db_ports(words: List[str]) -> List[str]:
    """Return db port mappings that docker run would open to the whole network."""
    if not words or _prog(words[0]) not in ("docker", "podman"):
        return []
    args = words[1:]
    found: List[str] = []
    i = 0
    while i < len(args):
        a = args[i]
        spec = ""
        if a in ("-p", "--publish") and i + 1 < len(args):
            spec = args[i + 1]
            i += 1
        elif a.startswith("--publish="):
            spec = a[len("--publish="):]
        elif a.startswith("-p") and len(a) > 2 and a[2] not in "-=":
            spec = a[2:]
        i += 1
        if not spec:
            continue
        spec = spec.strip("\"'")
        host_ip = ""
        pieces = spec.split(":")
        if len(pieces) == 3:
            host_ip = pieces[0]
        container = pieces[-1].split("/", 1)[0]
        if container in ("5432", "3306", "27017", "6379", "1433", "9200", "11211"):
            if host_ip not in ("127.0.0.1", "localhost", "[::1]", "::1"):
                found.append(_clean_name(spec))
    return found


def _mkdir_tops(words: List[str]) -> List[str]:
    if not words:
        return []
    prog = _prog(words[0])
    args = words[1:]
    targets: List[str] = []
    if prog in ("mkdir", "md"):
        targets = [a for a in args if not a.startswith("-") and not (prog == "md" and a.startswith("/"))]
    elif prog in ("new-item", "ni"):
        lowered = [a.lower() for a in args]
        if any(x.startswith("-itemtype") for x in lowered) and "directory" in lowered:
            for k, a in enumerate(lowered):
                if a in ("-path", "-name") and k + 1 < len(args):
                    targets.append(args[k + 1])
    tops: List[str] = []
    for t in targets:
        t = t.replace("\\", "/")
        if t.startswith(("/", "~", "$", "%", "../")) or re.match(r"^[A-Za-z]:", t) or ".." in t.split("/"):
            continue
        t = t.lstrip("./")
        top = t.split("/", 1)[0]
        if top and not top.startswith(".") and top.lower() not in SKIP_DIRS and top.lower() not in _QUIET_DIRS:
            tops.append(top)
    return tops


def check_command(command: str, greenfield: bool = False,
                  known_dirs: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    """Tripwires for one shell command the agent just ran (package installs, new folders, open DB ports)."""
    try:
        return _check_command(command, greenfield, known_dirs)
    except Exception:
        return []


def _check_command(command: str, greenfield: bool, known_dirs: Optional[Iterable[str]]) -> List[Dict[str, Any]]:
    if not isinstance(command, str) or not command.strip() or len(command) > 20000:
        return []
    out: List[Dict[str, Any]] = []
    changed_dir = False
    known = set(known_dirs) if known_dirs is not None else None
    for seg in _segments(command)[:40]:
        words = _strip_wrappers(_words(seg))
        if not words:
            continue
        prog = _prog(words[0])
        if prog in ("cd", "chdir", "pushd", "set-location", "sl"):
            changed_dir = True
            continue
        label, names = _install_names(words)
        if label and names:
            clean = [n for n in (_clean_name(x) for x in names) if n][:60]
            if clean:
                plural = len(clean) > 1
                if label.endswith((".json", ".toml", "go.mod", "Gemfile")):
                    where = "in %s" % _shown(label, "file", 60)
                else:
                    where = "(installed with %s)" % _shown(label, "tool", 40)
                text = ("Tripwire: new %s %s %s. In one plain sentence say what %s for. "
                        "If %s a framework, database, auth, payment or hosting choice, run think-first; "
                        "otherwise add one line to today's journal."
                        % ("dependencies" if plural else "dependency", _names_phrase(clean), where,
                           "each is" if plural else "it is", "one is" if plural else "it is"))
                key = "new-dependency:%s:%s" % (label, ",".join(sorted(clean))[:200])
                out.append(_tw("new-dependency", "manifest", "new dependency", text, key, rel=label, items=clean))
        ports = _published_db_ports(words)
        if ports:
            msg = MESSAGES["db-port-published"]
            text = ("Tripwire: %s in a docker command (%s). Why it matters: %s Safer way: %s "
                    "Explain it to the user in one plain sentence and say what you will do about it."
                    % (msg["short"], _fence(", ".join(ports[:3]), "port"), msg["why"], msg["safe"]))
            out.append(_tw("db-port-published", "code", msg["short"], text, "db-port-published:cmd:%s" % ",".join(ports[:3]),
                           rel="docker"))
        if not changed_dir:
            for top in _mkdir_tops(words):
                if known is not None and top in known:
                    continue
                tw = _topdir_tripwire(top)
                if tw:
                    out.append(tw)
    out.sort(key=_sort_key)
    _mark_greenfield(out, greenfield)
    return out


# ---------------------------------------------------------------- helpers for the caller


def select_visible(tripwires: Iterable[Dict[str, Any]], seen_keys: Iterable[str]) -> Optional[Dict[str, Any]]:
    """Pick the one tripwire to show this turn: the first model-visible one not shown before."""
    seen = set(seen_keys)
    for tw in tripwires:
        if tw.get("model_visible") and not tw.get("queued") and tw.get("once_key") not in seen:
            return tw
    return None


def log_only(tripwires: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """The tripwires that are only written to activity.jsonl."""
    return [tw for tw in tripwires if not tw.get("model_visible") and not tw.get("queued")]


def summarise_queued(queued: Iterable[Dict[str, Any]], max_items: int = 5, at_save_point: bool = True) -> str:
    """One line for the first save point of a new project (at_save_point True), or for a fact queued in an
    earlier turn that is shown at a later tool call (False, H5); '' when nothing was queued."""
    packages: List[str] = []
    folders: List[str] = []
    other: List[str] = []
    for tw in queued:
        try:
            kind = tw.get("kind")
            if kind == "manifest":
                packages.extend(str(x) for x in (tw.get("items") or []))
            elif kind == "top-dir":
                folders.extend(str(x) for x in (tw.get("items") or [tw.get("rel", "")]))
            elif kind == "big-file":
                other.append("%s (%s lines)" % (_name_text(tw.get("rel", ""), 60), tw.get("line", "")))
            elif kind == "workflow":
                other.append(_name_text(tw.get("rel", ""), 60))
        except Exception:
            continue

    def uniq(items: List[str]) -> List[str]:
        seen: List[str] = []
        for it in items:
            c = _clean_name(it) if "(" not in it else _clean(it, 60)
            if c and c not in seen:
                seen.append(c)
        return seen

    parts: List[str] = []
    for label, items in (("packages", uniq(packages)), ("folders", uniq(folders)), ("files", uniq(other))):
        if items:
            shown = items[:max_items]
            extra = " and %d more" % (len(items) - len(shown)) if len(items) > len(shown) else ""
            parts.append("%s %s%s" % (label, _fence(", ".join(shown), label), extra))
    if not parts:
        return ""
    if not at_save_point:
        return ("Noticed earlier and not yet mentioned: %s. "
                "In your next message say in one plain sentence what each is for." % "; ".join(parts))
    return ("Noticed while the project was new and not yet mentioned: %s. "
            "At this save point say in one plain sentence what each is for." % "; ".join(parts))


def all_regexes() -> List["re.Pattern[str]"]:
    """Every compiled expression of this module (the selftest fuzzes each one)."""
    found: List["re.Pattern[str]"] = []
    for value in list(globals().values()):
        if isinstance(value, re.Pattern):
            found.append(value)
        elif isinstance(value, (tuple, list)):
            found.extend(v for v in value if isinstance(v, re.Pattern))
        elif isinstance(value, dict):
            found.extend(v for v in value.values() if isinstance(v, re.Pattern))
    return found
