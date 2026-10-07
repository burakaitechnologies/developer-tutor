"""guardrules.py - the rules of the PreToolUse safety guard (SPEC 7.2): what is dangerous in a shell
command or a file write, and how serious it is.

What: analyze_shell(command, shell, cwd) and analyze_file_op(tool, path, content, cwd) return a list of
Finding (rule_id, tier, message_key, detail). decide(findings, permission_mode) turns them into one
decision: deny, ask, warn or none, plus the teaching text. panic_check(command) is the short list of
six linear rules that still blocks when the rich analysis fails. scan_scripts reads a script the
command is about to run. is_observe_only tells whether a command only looks.
Why: a beginner and an AI agent together can delete a project, publish a key, or pipe a stranger's
script into a shell with one line. Static permission rules cannot see inside `git -C . push -f`, a
PowerShell call operator, `bash -c "..."` or `Get-ChildItem | Remove-Item -Recurse`. This module reads
the command the way a shell does (quotes, pipes, substitutions, wrappers, aliases), one pipeline
segment at a time, so a word inside a commit message or an echo string never counts.
Tiers: block = deny (never needed in a beginner project, or a known attack), ask = the learner decides
with the reason in front of them, warn = a one-line heads-up for the model. Every rule has a plain
message in hooks/guard-messages.json (short, why, safe, lesson); teach once, then short.
How it fails safely: the rich analyser has a time limit and a size limit (a command over 20,000
characters is an ask). A bug in it is caught by the caller (handlers/pre_tool.py), which keeps the
panic-list block, and turns a command with a danger word into the ask `guard-error`; any other
command is allowed (the guard fails open on its own bugs, SPEC P6). Nothing here writes files, makes
network calls or runs a program; reading a script or package.json is limited to 64 KB.
Honest limits (docs/how-it-works.md, tests/guard-known-gaps.txt): scripts the model did not write,
compiled programs, shell aliases and functions from the user's profile, inline interpreter code beyond
one level or from non-literal strings, a download in one command and the run in another, `grep -r KEY .`,
and anything the user types with `!`. The guard stops accidents and obvious mistakes. It does not stop
a prompt-injected or determined agent.
Who calls it: handlers/pre_tool.py (every Bash, PowerShell, Write, Edit and NotebookEdit call),
tools/selftest_guard.py, and the learner engine (is_observe_only).
Python 3.9, standard library only. Regexes are linear: literal starts, bounded repeats, no nested
quantifiers (selftest fuzzes every compiled regex on pathological input).
"""
from __future__ import annotations

import json
import os
import posixpath
import re
import sys
import time
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from . import fsio
from . import paths
from . import secrets as _secrets

sys.dont_write_bytecode = True

BLOCK, ASK, WARN = "block", "ask", "warn"
_RANK = {BLOCK: 3, ASK: 2, WARN: 1}

MAX_COMMAND_CHARS = 20000       # longer commands skip the rich analysis and become an ask
MAX_DEPTH = 6                   # nested shells, substitutions, literals, scripts
MAX_SEGMENTS = 600              # work cap for one command (all levels together)
BUDGET_SECONDS = 2.5            # the rich analyser stops after this long
SCRIPT_MAX_BYTES = 64 * 1024    # a script or package.json is read up to this size
MAX_SCRIPTS = 6                 # scripts read for one command
MAX_LITERALS = 14               # string literals of one python -c / node -e analysed


# --------------------------------------------------------------------------- rules and findings

# rule_id -> default tier. A finding may carry another tier (for example chown-r is a block on
# a root-like target and an ask elsewhere). hooks/guard-messages.json holds one message per rule_id;
# selftest_guard fails when the two lists differ.
RULE_TIERS: Dict[str, str] = {
    # deleting and wiping
    "rm-danger": BLOCK, "rm-git": BLOCK, "rm-git-inside": ASK, "rm-recursive": ASK, "win-delete-danger": BLOCK,
    "win-delete": ASK, "delete-outside-project": ASK,
    "ps-pipe-delete": ASK, "sync-delete": ASK, "format-disk": BLOCK, "dd-device": BLOCK, "forkbomb": BLOCK,
    "inline-delete": ASK, "memory-wipe": ASK, "wide-folder": ASK,
    # git
    "git-force": BLOCK, "git-force-lease-main": BLOCK, "git-force-lease": ASK, "git-push-mirror": BLOCK,
    "git-push-delete": ASK, "git-push": ASK, "git-reset-hard": ASK, "git-clean": ASK, "git-clean-x": BLOCK,
    "git-discard": ASK, "git-branch-D": ASK, "git-branch-main": BLOCK, "git-stash-drop": ASK,
    "git-history": BLOCK, "git-rebase": ASK, "git-amend": ASK, "git-no-verify": ASK, "git-rm": ASK,
    "git-config-exec": BLOCK, "git-config-cred": BLOCK, "git-config-global": ASK, "git-remote": ASK,
    "git-url-cred": BLOCK, "git-init-home": ASK, "commit-default-branch": WARN, "no-gitignore": WARN,
    # GitHub
    "gh-repo-delete": BLOCK, "gh-visibility": ASK, "gh-token": BLOCK, "gh-secret": ASK,
    "gh-api-write": ASK, "gh-gist": ASK,
    # running hidden or remote code, changing the computer
    "pipe-shell": BLOCK, "encoded-ps": BLOCK, "lolbin-download": BLOCK, "obfuscated": BLOCK,
    "system-config": BLOCK, "persistence": ASK, "reg-write": ASK, "cred-store": BLOCK,
    "env-redirect": BLOCK, "env-exec": BLOCK, "sudo": ASK, "chmod-777": ASK, "chown-r": ASK,
    "kill-all": ASK, "shutdown": ASK, "unresolvable-program": ASK, "claude-config": ASK,
    "claude-guard-off": ASK, "helper-script": ASK,
    # packages, containers, databases, cloud, publishing
    "pkg-add": WARN, "pkg-run": WARN, "pkg-url": ASK, "pkg-index": ASK, "pkg-global": ASK,
    "pkg-sudo": BLOCK, "pkg-break": BLOCK, "docker-danger": ASK, "docker-prune": ASK,
    "db-destroy": ASK, "db-destroy-prod": BLOCK, "cloud-destroy": ASK, "publish": ASK,
    # secrets and data leaving the computer
    "read-secret": BLOCK, "env-dump": ASK, "exfil-secret": BLOCK, "exfil-upload": ASK,
    "remote-xfer": ASK, "copy-secret": ASK, "tunnel": ASK, "bind-all": ASK, "secret-in-command": BLOCK,
    # files the guard protects, and the guard itself
    "hook-only-path": BLOCK, "config-write": ASK, "guard-off": BLOCK, "guard-error": ASK,
    "secret-in-file": BLOCK, "secret-file-write": ASK, "write-outside-project": ASK,
    "script-with-danger": ASK, "command-too-long": ASK, "secret-scan-incomplete": ASK,
    # the commit and push scanner (lib/scanner.py) uses these ids
    "scan-secret-file": BLOCK, "scan-secret-content": BLOCK, "scan-private-notes-add": BLOCK,
    "scan-private-notes-push": BLOCK, "scan-incomplete": ASK,
}


class Finding(dict):
    """{rule_id, tier, message_key, detail}. A dict (so it can be dumped) with attribute access."""

    def __init__(self, rule_id: str, tier: str, message_key: str = "", detail: str = "") -> None:
        dict.__init__(self, rule_id=rule_id, tier=tier, message_key=message_key or rule_id, detail=detail)

    def __getattr__(self, name: str) -> Any:
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)


def F(rule_id: str, detail: str = "", tier: Optional[str] = None) -> Finding:
    return Finding(rule_id, tier or RULE_TIERS.get(rule_id, ASK), rule_id, detail)


def _field(finding: Any, name: str, default: str = "") -> str:
    try:
        if isinstance(finding, dict):
            return str(finding.get(name, default) or default)
        return str(getattr(finding, name, default) or default)
    except Exception:  # noqa: BLE001
        return default


class BudgetExceeded(Exception):
    """The rich analyser ran out of time or work."""


_QUIET: frozenset = frozenset()


def set_quiet(rules: Iterable[str]) -> None:
    """Warnings the learner's session has already had (the handler passes them in): they are not computed again.
    This saves the git calls of the commit heads-up on every later commit."""
    global _QUIET
    _QUIET = frozenset(str(r) for r in rules)


def _note(where: str, exc: BaseException) -> None:
    """One line in state/hook-errors.log: where and what kind of error (never command text). Never raises."""
    try:
        fsio.log_line("guardrules %s: %s" % (where, type(exc).__name__))
    except Exception:  # noqa: BLE001 - logging must not fail the guard
        return


# --------------------------------------------------------------------------- words and lists

# Words that make a command worth an ask when the guard itself fails (guard-error policy, SPEC 7.3).
_DANGER_WORDS = re.compile(
    r"(?i)(?<![\w-])(?:rm|del|erase|rd|rmdir|remove-item|ri|git|reset|clean|curl|wget|iwr|irm|iex|"
    r"invoke-expression|invoke-webrequest|invoke-restmethod|sudo|chmod|chown|format|dd|mkfs|drop|truncate|kill|"
    r"taskkill|stop-process|shutdown|reg|schtasks|docker|gh|powershell|pwsh|bash|sh|cmd|eval|npm|pip|"
    r"rsync|robocopy|shred|diskpart|netsh|setx)(?![\w-])")

_ENV_EXEC_NAMES = frozenset(
    "NODE_OPTIONS BASH_ENV ENV PYTHONSTARTUP PYTHONPATH LD_PRELOAD LD_LIBRARY_PATH GIT_SSH_COMMAND "
    "GIT_ASKPASS GIT_EXTERNAL_DIFF GIT_PAGER PAGER EDITOR VISUAL PROMPT_COMMAND RUBYOPT PERL5OPT "
    "JAVA_TOOL_OPTIONS PIP_INDEX_URL PIP_EXTRA_INDEX_URL GIT_CONFIG_GLOBAL GIT_CONFIG_SYSTEM".split())
_ENV_REDIRECT_NAMES = frozenset(
    "ANTHROPIC_BASE_URL ANTHROPIC_API_URL OPENAI_BASE_URL OPENAI_API_BASE HTTP_PROXY HTTPS_PROXY ALL_PROXY "
    "NODE_TLS_REJECT_UNAUTHORIZED SSL_CERT_FILE REQUESTS_CA_BUNDLE NODE_EXTRA_CA_CERTS GIT_SSL_NO_VERIFY "
    "CURL_CA_BUNDLE".split())
_NODE_CODE_OPTS = re.compile(r"(?i)(?:^|\s)(?:-r|--require|--import|--loader|--experimental-loader|--eval|-e|--env-file)(?:[\s=]|$)")

# Keys that, written into a settings file, switch the guard or the permission system off.
_GUARD_OFF_KEYS = re.compile(
    r"(?i)(?:disableAllHooks|skipDangerousModePermissionPrompt|enableAllProjectMcpServers|apiKeyHelper|"
    r"bypassPermissions|ANTHROPIC_BASE_URL|\"hooks\"\s{0,4}:\s{0,4}\{\s{0,4}\})")

SAFE_ARTIFACTS = frozenset(
    "node_modules dist build out target .next .nuxt .svelte-kit .turbo .cache .parcel-cache __pycache__ "
    ".pytest_cache .mypy_cache .ruff_cache .venv venv coverage htmlcov .gradle obj .angular .expo .vite "
    "tmp temp .tox .eggs .ds_store .astro .output .dart_tool site .nyc_output .docusaurus storybook-static .gatsby .pnpm-store "
    ".sass-cache .eslintcache .jest-cache .terraform .serverless".split())
_SAFE_GLOB = re.compile(r"(?i)^(?:\*\.(?:pyc|pyo|log|tmp|bak|swp|orig)|[\w.-]{1,80}\.egg-info|\*\.egg-info)$")

# Programs that only print the text they are given: their arguments are never commands or file reads.
_TEXT_PROGS = frozenset("echo printf write-host write-output write print say".split())
# Programs that print the content of the files named in their arguments.
_READERS = frozenset(
    "cat type more less head tail bat nl tac strings xxd od hexdump base64 cut sort uniq tr sed awk gawk "
    "grep egrep fgrep rg ag ack findstr get-content gc select-string sls python python3 py node ruby perl php "
    "pwsh powershell jq yq xargs paste column fold expand rev tee diff cmp comm ngrep import-csv "
    "convertfrom-json".split())
_PATTERN_FIRST = frozenset("grep egrep fgrep rg ag ack findstr select-string sls sed awk gawk".split())
# Programs that send data out of the computer.
_SENDERS = frozenset(
    "curl wget nc ncat netcat socat telnet scp sftp rsync ftp tftp iwr irm invoke-webrequest "
    "invoke-restmethod send-mailmessage certutil bitsadmin openssl nslookup dig ping start-bitstransfer".split())
# Last pipeline step that cannot show content to the model (it prints a count or a hash, or nothing).
_SILENT_SINKS = frozenset(
    "wc md5sum sha1sum sha256sum sha512sum cksum shasum test true false measure-object out-null "
    "get-filehash".split())

_DOWNLOADERS = frozenset(
    "curl wget iwr irm invoke-webrequest invoke-restmethod fetch aria2c http xh lwp-download start-bitstransfer".split())
_SHELL_PROGS = frozenset("sh bash zsh dash ksh fish csh tcsh ash".split())
_PS_PROGS = frozenset(["powershell", "pwsh"])
_INTERPRETERS = frozenset("python python3 py node ruby perl php deno bun".split())
_EXEC_SINKS = frozenset(list(_SHELL_PROGS) + ["iex", "invoke-expression", "eval", "source", "pwsh", "powershell"])
_DB_CLIENTS = frozenset(
    "psql mysql mariadb sqlite3 sqlcmd mongosh mongo redis-cli cockroach duckdb clickhouse-client usql pgcli "
    "litecli isql sqlplus".split())

# Wrappers that run the next word as a program.
_WRAPPERS = frozenset(
    "command builtin exec nohup time setsid stdbuf ionice noglob nocorrect xargs watch unbuffer caffeinate "
    "chrt nice timeout sudo doas gsudo pkexec runas env winpty busybox toybox".split())

# PowerShell command names and aliases -> one canonical lower-case name.
_PS_ALIAS = {
    "rm": "remove-item", "ri": "remove-item", "del": "remove-item", "erase": "remove-item", "rd": "remove-item",
    "rmdir": "remove-item", "iex": "invoke-expression", "iwr": "invoke-webrequest", "irm": "invoke-restmethod",
    "gc": "get-content", "cat": "get-content", "type": "get-content", "sls": "select-string",
    "ls": "get-childitem", "dir": "get-childitem", "gci": "get-childitem", "cp": "copy-item", "copy": "copy-item",
    "cpi": "copy-item", "mv": "move-item", "move": "move-item", "mi": "move-item", "sc": "set-content",
    "ac": "add-content", "cd": "set-location", "sl": "set-location", "chdir": "set-location",
    "kill": "stop-process", "spps": "stop-process", "saps": "start-process", "start": "start-process",
    "ni": "new-item", "echo": "write-output", "write": "write-output", "gi": "get-item", "gp": "get-itemproperty",
    "sp": "set-itemproperty", "wget": "invoke-webrequest", "curl": "invoke-webrequest",
}
# PowerShell 5.1 aliases that name a real program elsewhere. `curl.exe` and `curl` are one thing for the guard.


# --------------------------------------------------------------------------- path helpers

# an NTFS alternate data stream suffix: settings.json::$DATA and file.txt:stream are the same file for the guard
_RX_STREAM = re.compile(r"(?i)(?<=[^:/])(?:::\$[a-z_]{1,20}|:[^:/]{1,80})$")


def _norm(p: Any) -> str:
    """A path-like string with '/' separators, no quotes, no doubled slashes (a leading // is kept)."""
    s = str(p or "").strip().strip("\"'`")
    s = s.replace("\\", "/")
    s = _RX_STREAM.sub("", s)
    # Win32 drops trailing dots and spaces of every path part: ".claude./settings.json" is ".claude/settings.json"
    if "." in s or " " in s:
        s = "/".join((part.rstrip(". ") or part) if part not in (".", "..") else part for part in s.split("/"))
    lead = "//" if s.startswith("//") and not s.startswith("///") else ""
    s = re.sub(r"/{2,}", "/", s)
    if lead:
        s = "/" + s
    if len(s) > 1 and s.endswith("/") and not re.match(r"^[A-Za-z]:/$", s):
        s = s.rstrip("/") or "/"
    return s


def _home() -> str:
    try:
        return _norm(os.path.expanduser("~"))
    except Exception:  # noqa: BLE001
        return ""


def _abs(p: Any, cwd: str = "", lower: bool = True) -> str:
    """Absolute path with '/' separators (lower case unless lower=False); '~' and a leading drive are
    understood. No file system access (no realpath), so it is safe to call on any text."""
    s = _norm(p)
    if not s:
        return ""
    if s == "~" or s.startswith("~/"):
        s = (_home() + s[1:]) if _home() else s
    base = _norm(cwd or paths.project_root())
    if not (s.startswith("/") or re.match(r"^[A-Za-z]:(?:/|$)", s)):
        s = base.rstrip("/") + "/" + s
    out = posixpath.normpath(s)
    if out.startswith("//") and not s.startswith("//"):
        out = out[1:]
    return out.lower() if lower else out


def _root() -> str:
    return _abs(paths.project_root())


def _under(p: str, folder: str) -> bool:
    return bool(folder) and (p == folder or p.startswith(folder.rstrip("/") + "/"))


def _wide_reason(root: str = "") -> str:
    """'' or the reason why the project folder is a WIDE one (SPEC 6.8, path logic only): the home folder,
    Desktop, Documents, Downloads, a drive root, '/', '/Users', 'C:/Users', the cloud-sync versions of
    those, or a direct parent of them. The extra check on the number of entries lives in session_start."""
    try:
        r = _abs(root or paths.project_root())
        h = _abs(_home())
        if not h:
            return ""
        cands = [h, h + "/desktop", h + "/documents", h + "/downloads", h + "/onedrive", h + "/onedrive/desktop",
                 h + "/onedrive/documents", h + "/onedrive/downloads", h + "/dropbox", h + "/google drive",
                 h + "/icloud drive", h + "/library/mobile documents/com~apple~clouddocs",
                 h + "/library/mobile documents/com~apple~clouddocs/desktop",
                 h + "/library/mobile documents/com~apple~clouddocs/documents"]
        if r in cands:
            return "home or a personal folder"
        if re.match(r"^(?:[a-z]:|)$", r) or re.match(r"^[a-z]:/?$", r):
            return "a drive root"
        if r in ("/", "/users", "/home", "c:/users", "/mnt/c", "/mnt/c/users", "/c/users", "/c"):
            return "a system folder"
        parent = posixpath.dirname(h)
        if r == parent:
            return "the folder that holds all user folders"
        return ""
    except Exception:  # noqa: BLE001
        return ""


def _temp_claude() -> str:
    """<OS temp folder>/claude: Claude Code's own scratchpad area (never flagged)."""
    try:
        import tempfile
        return _abs(tempfile.gettempdir()) + "/claude"
    except Exception:  # noqa: BLE001
        return ""


_NEVER_FLAGGED_HOME = ("/.claude/plans", "/.claude/jobs")


def never_flagged_path(path: str, cwd: str = "", scratchpad: str = "") -> bool:
    """Paths the guard never asks about: the scratchpad from stdin, <temp>/claude, ~/.claude/plans,
    ~/.claude/jobs, ~/.claude/projects/*/memory (SPEC 7.2, mechanics F11)."""
    p = _abs(path, cwd)
    if not p:
        return False
    if scratchpad and _under(p, _abs(scratchpad)):
        return True
    t = _temp_claude()
    if t and _under(p, t):
        return True
    h = _abs(_home())
    if h:
        for tail in _NEVER_FLAGGED_HOME:
            if _under(p, h + tail):
                return True
        if re.match(re.escape(h) + r"/\.claude/projects/[^/]{1,200}/memory(?:/|$)", p):
            return True
    return False


# the product's own folders under the project's .claude folder
_CONFIG_REL = re.compile(
    r"^\.claude/(?:settings\.json|settings\.local\.json|claude\.md|(?:hooks|rules|output-styles|skills|agents|commands|tools)(?:/.*)?)$"
    r"|^\.mcp\.json$|^\.vscode/tasks\.json$|^\.git/hooks(?:/.*)?$|^\.git/config$|^\.claude$")


def _data_rel() -> str:
    return str(getattr(paths, "DATA_REL", ".claude/agent-memory/tutor-data")).lower()


def _rel_to_root(p_abs: str) -> Optional[str]:
    root = _root()
    if _under(p_abs, root):
        return p_abs[len(root):].lstrip("/")
    return None


def _model_writable(sub: str) -> bool:
    """sub = path inside tutor-data (lower case, '/' separators). True for the Markdown files the model may write."""
    files = [str(x).lower() for x in getattr(paths, "MODEL_FILES", ("now.md", "learner/profile.md", "learner/notes.md"))]
    dirs = [str(x).lower() for x in getattr(paths, "MODEL_DIRS", ("journal", "inbox"))]
    if sub in files:
        return True
    for d in dirs:
        if sub.startswith(d + "/") and sub.endswith(".md"):
            name = sub[len(d) + 1:]
            if d == "inbox" and "/" in name:
                return False                       # one level only: inbox/sub/x.md is not a record
            if re.match(r"(?i)^(?:con|prn|aux|nul|com[1-9]|lpt[1-9])$", name.split(".", 1)[0].strip()):
                return False                       # CON.md writes to the console, not to a file
            return True
    return False


def path_tags(path: str, cwd: str = "", scratchpad: str = "") -> Set[str]:
    """What a path is to the guard: {'never'}, or any of 'hook-only', 'config', 'memory-root', 'outside'."""
    tags: Set[str] = set()
    p = _abs(path, cwd)
    if not p:
        return tags
    if never_flagged_path(path, cwd, scratchpad):
        tags.add("never")
        return tags
    rel = _rel_to_root(p)
    if rel is None:
        h = _abs(_home())
        if h and (_under(p, h + "/.claude") or p == h + "/.claude.json"):
            tags.add("config")
        else:
            tags.add("outside")
        return tags
    data = _data_rel()
    if rel == data or rel == ".claude/agent-memory":
        tags.add("memory-root")
    elif _under(rel, data):
        if not _model_writable(rel[len(data):].lstrip("/")):
            tags.add("hook-only")
    elif _under(rel, ".claude/agent-memory"):
        pass                                   # another agent's memory folder: Claude Code's own business
    elif _CONFIG_REL.match(rel):
        tags.add("config")
    return tags


# --------------------------------------------------------------------------- messages

_MESSAGES: Optional[Dict[str, Any]] = None


def messages() -> Dict[str, Any]:
    """hooks/guard-messages.json as a dict ({} when missing or damaged: decide() then falls back to a plain text)."""
    global _MESSAGES
    if _MESSAGES is None:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data = fsio.read_json(os.path.join(here, "guard-messages.json"), {})
        _MESSAGES = data if isinstance(data, dict) else {}
    return _MESSAGES


def lesson_of(rule_id: str) -> str:
    entry = messages().get(rule_id)
    return str(entry.get("lesson", "")) if isinstance(entry, dict) else ""


# --------------------------------------------------------------------------- reading a command

SH, PS, CMD = "sh", "ps", "cmd"


class Tok(object):
    """One word of a command. v = the text without quotes; quoted = part of it was quoted or escaped;
    dyn = it holds an expansion the guard cannot resolve ($x, ${x}, $(...), %X%)."""
    __slots__ = ("v", "quoted", "dyn")

    def __init__(self, v: str, quoted: bool = False, dyn: bool = False) -> None:
        self.v = v
        self.quoted = quoted
        self.dyn = dyn

    def __repr__(self) -> str:
        return "Tok(%r%s%s)" % (self.v, ",q" if self.quoted else "", ",dyn" if self.dyn else "")


class Seg(object):
    """One simple command: words, redirections (op, Tok), nested command texts (kind, text) found inside it
    ($(...), backticks, <(...), PowerShell ( ), { } and $( )), and heredocs [delimiter, body, quoted, herestring]."""
    __slots__ = ("toks", "redirs", "nested", "heredocs", "kind")

    def __init__(self, kind: str) -> None:
        self.toks: List[Tok] = []
        self.redirs: List[Tuple[str, Tok]] = []
        self.nested: List[Tuple[str, str]] = []
        self.heredocs: List[List[Any]] = []
        self.kind = kind

    def values(self) -> List[str]:
        return [t.v for t in self.toks]


class Parsed(object):
    """pipelines: list of pipelines; a pipeline is a list of Seg joined by | or |&. notes: facts about the text."""
    __slots__ = ("pipelines", "notes")

    def __init__(self) -> None:
        self.pipelines: List[List[Seg]] = []
        self.notes: Set[str] = set()


_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,60}")
_PS_VAR = re.compile(r"(?:env:|global:|script:|local:|private:)?[A-Za-z_?][A-Za-z0-9_]{0,60}|\{[^}\n]{0,80}\}")
_SH_ESC = " \t\"'$`\\;&|()<>#!*?[]{}~"
_ASSIGN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,60}\+?=")
_PS_ASSIGN = re.compile(r"^\$([A-Za-z_][A-Za-z0-9_:]{0,60})(?:\s{0,3})(\+?=)(.*)$", re.S)
_PS_LITERALS = frozenset(["$true", "$false", "$null"])
_ANSI_ESC = {"n": "\n", "t": "\t", "r": "\r", "a": "\a", "b": "\b", "f": "\f", "v": "\v", "e": "\x1b",
             "\\": "\\", "'": "'", '"': '"', "?": "?"}


def match_paren(s: str, i: int, kind: str = SH) -> Tuple[int, str]:
    """s[i] is '(' (or '{'). Returns (index after the matching close, inner text); quotes are respected.
    An unbalanced text returns (len(s), rest of the text)."""
    open_c = s[i]
    close_c = ")" if open_c == "(" else "}"
    depth = 0
    j = i
    n = min(len(s), i + MAX_COMMAND_CHARS)
    while j < n:
        c = s[j]
        if c == "\\" and kind == SH:
            j += 2
            continue
        if c == "`" and kind == PS:
            j += 2
            continue
        if c == "'":
            k = s.find("'", j + 1)
            if k < 0:
                break
            j = k + 1
            continue
        if c == '"':
            k = j + 1
            while k < n and s[k] != '"':
                if s[k] == "\\" and kind == SH:
                    k += 1
                elif s[k] == "`" and kind == PS:
                    k += 1
                k += 1
            j = k + 1
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return j + 1, s[i + 1:j]
        j += 1
    return len(s), s[i + 1:]


class _Lex(object):
    """A small shell reader for sh (bash), ps (PowerShell) and cmd. It never runs anything."""

    def __init__(self, s: str, kind: str, deadline: float = 0.0) -> None:
        self.s = s
        self.n = len(s)
        self.i = 0
        self.kind = kind
        self.deadline = deadline
        self.out = Parsed()
        self.pipe: List[Seg] = []
        self.seg = Seg(kind)
        self.buf: List[str] = []
        self.started = False
        self.q = False
        self.dyn = False
        self.redir: Optional[str] = None
        self.hq: List[Tuple[List[Any], bool]] = []
        self.vars: Dict[str, str] = {}
        self.ticks = 0

    # ---- words and segments
    def add(self, text: str, quoted: bool = False, dyn: bool = False) -> None:
        self.buf.append(text)
        self.started = True
        if quoted:
            self.q = True
        if dyn:
            self.dyn = True

    def end_word(self) -> None:
        if not self.started:
            return
        tok = Tok("".join(self.buf), self.q, self.dyn)
        self.buf = []
        self.started = False
        self.q = False
        self.dyn = False
        if self.redir == "<<<":
            self.seg.heredocs.append(["<<<", tok.v, tok.quoted, True])
            self.redir = None
        elif self.redir is not None:
            self.seg.redirs.append((self.redir, tok))
            self.redir = None
        else:
            self.seg.toks.append(tok)

    def end_seg(self, op: str = "") -> None:
        self.end_word()
        seg = self.seg
        self.redir = None
        if seg.toks or seg.redirs or seg.nested or seg.heredocs:
            self.capture_vars(seg)
            self.pipe.append(seg)
        self.seg = Seg(self.kind)
        if op not in ("|", "|&") and self.pipe:
            self.out.pipelines.append(self.pipe)
            self.pipe = []

    def capture_vars(self, seg: Seg) -> None:
        """A segment that only assigns plain text (X=/ ; $g='git') lets later words use the value."""
        try:
            toks = seg.toks
            if not toks or seg.redirs:
                return
            if self.kind == SH:
                items = toks
                if toks[0].v in ("export", "declare", "local", "readonly", "typeset"):
                    items = [t for t in toks[1:] if not t.v.startswith("-")]
                for t in items:
                    m = _ASSIGN.match(t.v)
                    if not m:
                        return
                for t in items:
                    name, _, val = t.v.partition("=")
                    name = name.rstrip("+")
                    if t.dyn:
                        self.vars.pop(name, None)
                    else:
                        self.vars[name] = val
            elif self.kind == PS:
                first = toks[0].v
                if not first.startswith("$"):
                    return
                text = first if len(toks) == 1 else " ".join(t.v for t in toks)
                m = _PS_ASSIGN.match(text)
                if m and not any(t.dyn for t in toks):
                    if m.group(2) == "=":
                        self.vars[m.group(1).lower()] = m.group(3).strip()
        except Exception:  # noqa: BLE001
            return

    # ---- expansions
    def dollar(self, in_dq: bool) -> None:
        s, i, n = self.s, self.i, self.n
        nx = s[i + 1] if i + 1 < n else ""
        if nx == "(":
            j, inner = match_paren(s, i + 1, self.kind)
            if inner.startswith("(") and inner.endswith(")"):
                self.add("$((...))", quoted=in_dq, dyn=True)          # arithmetic
            else:
                self.seg.nested.append((self.kind, inner))
                self.add("$(...)", quoted=in_dq, dyn=True)
            self.i = j
            return
        if self.kind == PS:
            m = _PS_VAR.match(s, i + 1)
            if m:
                name = m.group(0)
                self.i = i + 1 + m.end() - m.start()
                key = name.strip("{}").lower()
                low = "$" + key
                assign = (not self.started and not in_dq
                          and re.match(r"\s{0,3}[+]?=(?!=)", s[self.i:self.i + 6]) is not None)
                if low in _PS_LITERALS or assign:
                    self.add("$" + name, quoted=in_dq)               # a literal, or the left side of =
                elif key in self.vars:
                    self.add(self.vars[key], quoted=True)
                else:
                    self.add("$" + name, quoted=in_dq, dyn=True)
                return
            self.add("$", quoted=in_dq)
            self.i = i + 1
            return
        if self.kind == CMD:
            self.add("$", quoted=in_dq)
            self.i = i + 1
            return
        # sh
        if nx == "{":
            j = s.find("}", i + 2)
            if j < 0 or j - i > 200:
                self.add("${", quoted=in_dq, dyn=True)
                self.i = i + 2
                return
            name = s[i + 2:j]
            self.i = j + 1
            if _IDENT.fullmatch(name) and name in self.vars:
                self.add(self.vars[name], quoted=True)
            else:
                self.add("${" + name + "}", quoted=in_dq, dyn=True)
            return
        if nx == "'" and not in_dq:
            self.ansi_c()
            return
        m = _IDENT.match(s, i + 1)
        if m:
            name = m.group(0)
            self.i = i + 1 + len(name)
            if name in self.vars:
                self.add(self.vars[name], quoted=True)
            else:
                self.add("$" + name, quoted=in_dq, dyn=True)
            return
        if nx and nx in "?$!@*#-0123456789":
            self.add("$" + nx, quoted=in_dq, dyn=True)
            self.i = i + 2
            return
        self.add("$", quoted=in_dq)
        self.i = i + 1

    def ansi_c(self) -> None:
        """$'...' with \\xHH, octal, \\n ... escapes (hides letters from a plain text search)."""
        s, n = self.s, self.n
        i = self.i + 2
        out: List[str] = []
        while i < n and s[i] != "'":
            c = s[i]
            if c == "\\" and i + 1 < n:
                e = s[i + 1]
                if e == "x":
                    m = re.match(r"[0-9a-fA-F]{1,2}", s[i + 2:i + 4])
                    if m:
                        out.append(chr(int(m.group(0), 16)))
                        i += 2 + len(m.group(0))
                        continue
                elif e in "01234567":
                    m = re.match(r"[0-7]{1,3}", s[i + 1:i + 4])
                    out.append(chr(int(m.group(0), 8)))
                    i += 1 + len(m.group(0))
                    continue
                elif e == "u" or e == "U":
                    m = re.match(r"[0-9a-fA-F]{1,8}", s[i + 2:i + 10])
                    if m:
                        try:
                            out.append(chr(int(m.group(0), 16)))
                        except (ValueError, OverflowError):
                            pass
                        i += 2 + len(m.group(0))
                        continue
                out.append(_ANSI_ESC.get(e, e))
                i += 2
                continue
            out.append(c)
            i += 1
        self.add("".join(out), quoted=True)
        self.i = min(i + 1, n)

    # ---- quotes
    def single(self) -> None:
        s, i, n = self.s, self.i, self.n
        if self.kind == PS:
            parts: List[str] = []
            j = i + 1
            while j < n:
                if s[j] == "'":
                    if j + 1 < n and s[j + 1] == "'":
                        parts.append("'")
                        j += 2
                        continue
                    break
                parts.append(s[j])
                j += 1
            self.add("".join(parts), quoted=True)
            self.i = min(j + 1, n)
            return
        j = s.find("'", i + 1)
        if j < 0:
            self.out.notes.add("unterminated")
            self.add(s[i + 1:], quoted=True)
            self.i = n
        else:
            self.add(s[i + 1:j], quoted=True)
            self.i = j + 1

    def double(self) -> None:
        s, n = self.s, self.n
        i = self.i + 1
        self.add("", quoted=True)
        while i < n:
            c = s[i]
            if c == '"':
                if self.kind in (PS, CMD) and i + 1 < n and s[i + 1] == '"':
                    self.add('"', quoted=True)
                    i += 2
                    continue
                self.i = i + 1
                return
            if c == "\\" and self.kind == SH and i + 1 < n:
                e = s[i + 1]
                if e in '"\\$`':
                    self.add(e, quoted=True)
                    i += 2
                    continue
                if e == "\n":
                    i += 2
                    continue
                self.add("\\", quoted=True)
                i += 1
                continue
            if c == "`" and self.kind == PS and i + 1 < n:
                self.add(s[i + 1], quoted=True)
                i += 2
                continue
            if c == "$":
                self.i = i
                self.dollar(True)
                i = self.i
                continue
            if c == "`" and self.kind == SH:
                j = s.find("`", i + 1)
                if j < 0:
                    j = n
                self.seg.nested.append((SH, s[i + 1:j]))
                self.add("`...`", quoted=True, dyn=True)
                i = j + 1
                continue
            if c == "%" and self.kind == CMD:
                j = s.find("%", i + 1)
                if 0 < j - i <= 64:
                    self.add(s[i:j + 1], quoted=True, dyn=True)
                    i = j + 1
                    continue
            self.add(c, quoted=True)
            i += 1
        self.out.notes.add("unterminated")
        self.i = n

    # ---- redirections and heredocs
    def redirect(self) -> None:
        s, n = self.s, self.n
        i = self.i
        c = s[i]
        if self.started and not self.q and self.buf and "".join(self.buf).isdigit() and len(self.buf) <= 2:
            self.buf = []
            self.started = False
        else:
            self.end_word()
        if c == "&":                                          # &> and &>>
            op = "&>"
            i += 2
            if s[i:i + 1] == ">":
                op = "&>>"
                i += 1
            self.redir = op
            self.i = i
            return
        if c == "*":                                          # PowerShell *> and *>>
            i += 1
            c = ">"
        op = c
        i += 1
        nxt = s[i:i + 1]
        if nxt == c:
            op = c + c
            i += 1
        elif nxt == "|" and c == ">":
            i += 1
        elif nxt == "&":
            i += 1
            m = re.match(r"[0-9]{1,2}-?|-", s[i:i + 4])
            if m:
                self.i = i + m.end()
                return
            self.redir = ">" if c == ">" else "<"
            self.i = i
            return
        elif nxt == "(" and self.kind == SH:                   # process substitution <( ) >( )
            j, inner = match_paren(s, i, SH)
            self.seg.nested.append((SH, inner))
            self.add("<(...)", dyn=True)
            self.i = j
            return
        if op == "<<":
            if s[i:i + 1] == "<":
                self.redir = "<<<"
                self.i = i + 1
                return
            strip = False
            if s[i:i + 1] == "-":
                strip = True
                i += 1
            while i < n and s[i] in " \t":
                i += 1
            quoted = False
            d: List[str] = []
            while i < n and s[i] not in " \t\r\n;|&<>()":
                ch = s[i]
                if ch in "'\"":
                    j = s.find(ch, i + 1)
                    if j < 0:
                        j = n
                    d.append(s[i + 1:j])
                    quoted = True
                    i = j + 1
                    continue
                if ch == "\\" and i + 1 < n:
                    d.append(s[i + 1])
                    quoted = True
                    i += 2
                    continue
                d.append(ch)
                i += 1
            rec: List[Any] = ["".join(d), None, quoted, False]
            if rec[0]:
                self.seg.heredocs.append(rec)
                self.hq.append((rec, strip))
            self.i = i
            return
        self.redir = op
        self.i = i

    def read_heredocs(self) -> None:
        s, n = self.s, self.n
        for rec, strip in self.hq:
            delim = rec[0]
            lines: List[str] = []
            while self.i < n:
                j = s.find("\n", self.i)
                line = s[self.i:j if j >= 0 else n]
                self.i = (j + 1) if j >= 0 else n
                cmp_line = line.rstrip("\r")
                if (cmp_line.lstrip("\t") if strip else cmp_line) == delim:
                    break
                lines.append(line)
            rec[1] = "\n".join(lines)
        self.hq = []

    def here_string_ps(self) -> bool:
        """PowerShell @' ... '@ and @" ... "@ blocks. True when one was read."""
        s, i, n = self.s, self.i, self.n
        q = s[i + 1:i + 2]
        m = re.match(r"[ \t]{0,20}\r?\n", s[i + 2:i + 30])
        if q not in ("'", '"') or not m:
            return False
        body_start = i + 2 + m.end()
        end = s.find("\n" + q + "@", body_start - 1)
        if end < 0:
            body = s[body_start:]
            self.i = n
        else:
            body = s[body_start:end]
            self.i = end + 3
        body = body.replace("\r", "")
        self.add(body, quoted=True)
        if q == '"':
            for m2 in re.finditer(r"\$\(", body[:20000]):
                j, inner = match_paren(body, m2.start() + 1, PS)
                self.seg.nested.append((PS, inner))
        return True

    # ---- the main loop
    def run(self) -> Parsed:
        s, n = self.s, self.n
        kind = self.kind
        while self.i < n:
            self.ticks += 1
            if self.deadline and (self.ticks & 1023) == 0 and time.monotonic() > self.deadline:
                raise BudgetExceeded("time")
            i = self.i
            c = s[i]
            if c in " \t\r\f\v\x00":
                self.end_word()
                self.i += 1
                continue
            if c == "\n":
                self.end_seg("\n")
                self.i += 1
                if self.hq:
                    self.read_heredocs()
                continue
            if c == "#" and not self.started and kind != CMD:
                j = s.find("\n", i)
                self.i = n if j < 0 else j
                continue
            if c == "<" and kind == PS and s[i + 1:i + 2] == "#" and not self.started:
                j = s.find("#>", i + 2)
                self.i = n if j < 0 else j + 2
                continue
            if c == "\\" and kind == SH:
                nx = s[i + 1] if i + 1 < n else ""
                if nx == "\n":
                    self.i += 2
                    continue
                if nx == "":
                    self.add("\\")
                    self.i += 1
                    continue
                if nx in _SH_ESC:
                    self.add(nx, quoted=True)
                    self.i += 2
                    continue
                if nx.isalpha() and (not self.started or re.fullmatch(r"[A-Za-z_-]{0,40}", "".join(self.buf))):          # \rm : the alias-bypass spelling
                    self.add(nx, quoted=True)
                    self.i += 2
                    continue
                self.add("\\" + nx)                            # a Windows path: keep the backslash
                self.i += 2
                continue
            if c == "`" and kind == PS:
                nx = s[i + 1] if i + 1 < n else ""
                if nx == "\n":
                    self.i += 2
                    continue
                if nx:
                    self.add(nx, quoted=True)
                self.i += 2
                continue
            if c == "^" and kind == CMD and i + 1 < n:
                self.add(s[i + 1], quoted=True)
                self.i += 2
                continue
            if c == "'" and kind != CMD:
                self.single()
                continue
            if c == '"':
                self.double()
                continue
            if c == "$":
                self.dollar(False)
                continue
            if c == "%" and kind == CMD:
                j = s.find("%", i + 1)
                if 0 < j - i <= 64 and " " not in s[i:j]:
                    name = s[i + 1:j].lower()
                    if name in self.vars:
                        self.add(self.vars[name], quoted=True)
                    else:
                        self.add(s[i:j + 1], dyn=True)
                    self.i = j + 1
                    continue
            if c == "`" and kind == SH:
                j = s.find("`", i + 1)
                if j < 0:
                    j = n
                self.seg.nested.append((SH, s[i + 1:j]))
                self.add("`...`", dyn=True)
                self.i = j + 1
                continue
            if c == "@" and kind == PS:
                if self.here_string_ps():
                    continue
                nx = s[i + 1:i + 2]
                if nx in ("(", "{"):
                    j, inner = match_paren(s, i + 1, PS)
                    self.seg.nested.append((PS, inner))
                    self.add("@" + nx + "...", dyn=nx == "(")
                    self.i = j
                    continue
            if c == ";" and kind != CMD:
                self.end_seg(";")
                self.i += 1
                continue
            if c == "|":
                if s[i + 1:i + 2] == "|":
                    self.end_seg("||")
                    self.i += 2
                elif s[i + 1:i + 2] == "&" and kind == SH:
                    self.end_seg("|&")
                    self.i += 2
                else:
                    self.end_seg("|")
                    self.i += 1
                continue
            if c == "&":
                nx = s[i + 1:i + 2]
                if nx == "&":
                    self.end_seg("&&")
                    self.i += 2
                    continue
                if nx == ">" and kind == SH:
                    self.redirect()
                    continue
                if kind == PS and not self.started and not self.seg.toks:
                    self.add("&", quoted=True)               # the call operator
                    self.end_word()
                    self.i += 1
                    continue
                self.end_seg("&")
                self.i += 1
                continue
            if c in "<>" or (c == "*" and kind == PS and s[i + 1:i + 2] == ">" and not self.started):
                self.redirect()
                continue
            if c == "(":
                if kind == PS:
                    j, inner = match_paren(s, i, PS)
                    self.seg.nested.append((PS, inner))
                    self.add("(...)", dyn=True)
                    self.i = j
                    continue
                if not self.started:
                    self.end_seg(";")
                    self.i += 1
                    continue
            if c == ")":
                if kind != PS and not self.started:
                    self.end_seg(";")
                    self.i += 1
                    continue
                if kind == PS:
                    self.end_word()
                    self.i += 1
                    continue
            if c == "{" and kind == PS:
                j, inner = match_paren(s, i, PS)
                self.seg.nested.append((PS, inner))
                self.add("{...}")
                self.i = j
                continue
            if c == "}" and kind == PS:
                self.end_word()
                self.i += 1
                continue
            self.add(c)
            self.i += 1
        self.end_seg("")
        for rec, _strip in self.hq:
            if rec[1] is None:
                rec[1] = ""
        return self.out


def parse_command(text: str, kind: str = SH, deadline: float = 0.0) -> Parsed:
    """Read one command text. kind: 'sh' (bash), 'ps' (PowerShell) or 'cmd' (cmd.exe)."""
    return _Lex(text, kind, deadline).run()


# --------------------------------------------------------------------------- which program runs

_KEYWORDS = frozenset(["do", "then", "else", "elif", "if", "while", "until", "!", "{", "}", "fi", "done", "esac", "&&", "||"])
_SKIP_STARTS = frozenset(["for", "case", "select", "function", "coproc"])


class Cmd(object):
    """One resolved simple command.
    prog      lower-case program name without path and .exe ('' when none, e.g. an assignment)
    raw       the program word as written (with its path)
    args      the words after the program (list of Tok)
    wrappers  names of wrappers that were skipped (sudo, env, xargs, timeout ...)
    envs      NAME=value assignments before the program: list of (name, value, dyn)
    unresolved  the program is a variable or substitution the guard cannot read
    callop    the command was started with & or . (call operator / dot-source)
    """
    __slots__ = ("seg", "prog", "raw", "args", "wrappers", "envs", "unresolved", "callop", "kind", "assign")

    def __init__(self, seg: Seg, kind: str) -> None:
        self.seg = seg
        self.prog = ""
        self.raw = ""
        self.args: List[Tok] = []
        self.wrappers: Set[str] = set()
        self.envs: List[Tuple[str, str, bool]] = []
        self.unresolved = False
        self.callop = False
        self.kind = kind
        self.assign = False

    def vals(self) -> List[str]:
        return [t.v for t in self.args]


def _pname(v: str) -> str:
    v = str(v or "").strip()
    if v.startswith("\\") and len(v) > 1 and not v.startswith("\\\\"):
        v = v[1:]
    comp = re.split(r"[\\/]", v)[-1].lower()
    for ext in (".exe", ".cmd", ".bat", ".com"):
        if comp.endswith(ext) and len(comp) > len(ext):
            return comp[:-len(ext)]
    return comp


_DYN_MARKS = ("$", "`", "(...)", "{...}", "%", "<(...)")


def _dyn_name(tok: Tok) -> bool:
    if not tok.dyn:
        return False
    comp = re.split(r"[\\/]", tok.v)[-1]
    return any(m in comp for m in _DYN_MARKS)


def resolve(seg: Seg, kind: str) -> Cmd:
    """Find the program of a segment: skip keywords, NAME=value prefixes, call operators and wrappers."""
    c = Cmd(seg, kind)
    toks = seg.toks
    n = len(toks)
    i = 0
    while i < n and toks[i].v in _KEYWORDS and not toks[i].quoted:
        i += 1
    if i >= n:
        return c
    if kind == SH and toks[i].v in _SKIP_STARTS and not toks[i].quoted:
        return c
    # assignments
    if kind == PS:
        first = toks[i].v
        if first.startswith("$"):
            text = first
            if "=" not in first and len(toks) > i + 1 and toks[i + 1].v in ("=", "+="):
                text = first + toks[i + 1].v + " ".join(t.v for t in toks[i + 2:])
            m = re.match(r"^\$([A-Za-z_][A-Za-z0-9_:]{0,60})(\+?)=(.*)$", text, re.S)
            if m:
                c.envs.append((m.group(1), m.group(3).strip(), any(t.dyn for t in toks[i + 1:])))
                c.assign = True
                return c
    elif kind == SH:
        while i < n and _ASSIGN.match(toks[i].v):
            name, _, val = toks[i].v.partition("=")
            c.envs.append((name.rstrip("+"), val, toks[i].dyn))
            i += 1
        if i >= n:
            c.assign = True
            return c
    # call operators
    if toks[i].v == "&" and kind == PS:
        c.callop = True
        i += 1
    elif toks[i].v == "." and n > i + 1 and kind in (PS, SH):
        c.callop = True
        i += 1
        c.prog = "source" if kind == SH else "."
        c.raw = c.prog
        c.args = toks[i:]
        return c
    if i >= n:
        return c
    # wrappers
    while i < n:
        name = _pname(toks[i].v)
        if toks[i].dyn and _dyn_name(toks[i]):
            break
        if name in ("sudo", "doas", "gsudo", "pkexec", "runas"):
            c.wrappers.add("sudo")
            i += 1
            while i < n and toks[i].v.startswith("-"):
                i += 2 if toks[i].v in ("-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D") else 1
            continue
        if name == "env":
            c.wrappers.add("env")
            i += 1
            while i < n and (toks[i].v.startswith("-") or "=" in toks[i].v):
                if "=" in toks[i].v and not toks[i].v.startswith("-"):
                    nm, _, val = toks[i].v.partition("=")
                    c.envs.append((nm, val, toks[i].dyn))
                    i += 1
                else:
                    i += 2 if toks[i].v in ("-u", "-C", "-S") else 1
            continue
        if name == "timeout":
            c.wrappers.add("timeout")
            i += 1
            while i < n and toks[i].v.startswith("-"):
                i += 2 if toks[i].v in ("-s", "-k", "--signal", "--kill-after") else 1
            if i < n and re.match(r"^[0-9.]+[smhd]?$", toks[i].v):
                i += 1
            continue
        if name == "nice":
            c.wrappers.add("nice")
            i += 1
            while i < n and toks[i].v.startswith("-"):
                i += 2 if toks[i].v == "-n" else 1
            continue
        if name in _WRAPPERS:
            c.wrappers.add(name)
            i += 1
            while i < n and toks[i].v.startswith("-") and name in ("xargs", "watch", "stdbuf", "ionice", "command", "exec", "caffeinate"):
                i += 2 if toks[i].v in ("-n", "-I", "-P", "-d", "-L", "-s", "-d") and name == "xargs" else 1
            continue
        break
    if i >= n:
        last = sorted(c.wrappers)[-1] if c.wrappers else ""
        c.prog = last
        c.raw = last
        return c
    tok = toks[i]
    c.raw = tok.v
    c.args = toks[i + 1:]
    if _dyn_name(tok):
        if kind == PS and not c.callop and not c.wrappers:
            return c                                     # a PowerShell expression such as $x.Name -eq 1
        c.unresolved = True
        return c
    c.prog = _pname(tok.v)
    if kind == SH and "\\" in tok.v and not re.match(r"^(?:[A-Za-z]:|\.{1,2}[\\/]|\\\\)", tok.v):
        c.prog = _pname(tok.v.replace("\\", ""))             # gi\t is git in a shell (an escaped letter)
    if kind == PS or c.prog in ("remove-item", "invoke-expression", "get-childitem", "get-content"):
        c.prog = _PS_ALIAS.get(c.prog, c.prog)
    return c


# --------------------------------------------------------------------------- options and targets

def split_flags(vals: Sequence[str]) -> Tuple[Set[str], Set[str], List[str]]:
    """(short flags, long flags lower-case, other words). '--' ends the flags."""
    short: Set[str] = set()
    long_: Set[str] = set()
    targets: List[str] = []
    end = False
    for a in vals:
        if end:
            targets.append(a)
            continue
        if a == "--":
            end = True
        elif a.startswith("--"):
            long_.add(a[2:].split("=", 1)[0].lower())
        elif a.startswith("-") and len(a) > 1 and not re.match(r"^-\d", a):
            short.update(a[1:])
        else:
            targets.append(a)
    return short, long_, targets


def _prefix_match(word: str, names: Iterable[str]) -> Optional[str]:
    names = list(names)
    if word in names:
        return word
    hits = [x for x in names if x.startswith(word)] if word else []
    return hits[0] if len(hits) == 1 else None


_PS_COMMON_VALUE = frozenset("erroraction ea warningaction wa informationaction ia errorvariable ev warningvariable wv "
                             "informationvariable iv outvariable ov outbuffer ob pipelinevariable pv".split())


def ps_params(vals: Sequence[str], specs: Dict[str, bool]) -> Tuple[Dict[str, Any], List[str]]:
    """PowerShell parameters with abbreviations. specs: name -> takes a value. Returns (named, positional)."""
    named: Dict[str, Any] = {}
    pos: List[str] = []
    i = 0
    vals = list(vals)
    while i < len(vals):
        a = vals[i]
        if len(a) > 1 and a[0] == "-" and re.match(r"^-[A-Za-z]", a):
            body, _, val = a[1:].partition(":")
            canon = _prefix_match(body.lower(), specs)
            if canon is None and body.lower() in _PS_COMMON_VALUE:
                i += 1 if val else 2                         # -ErrorAction Stop : the value is not a path
                continue
            if canon is None:
                if re.match(r"^[rRfF]+$", body):
                    named["recurse"] = True                  # bash style -rf typed into PowerShell
                i += 1
                continue
            if specs[canon] and not val and i + 1 < len(vals):
                val = vals[i + 1]
                i += 1
            named[canon] = val if (specs[canon] or val) else True
            if not specs[canon] and val.lower() in ("$false", "false", "0"):
                named[canon] = False
        else:
            pos.append(a)
        i += 1
    return named, pos


_DANGER_PATH = None


def _danger_rx():
    global _DANGER_PATH
    if _DANGER_PATH is None:
        _DANGER_PATH = re.compile(r"""(?ix)^(?:
            /|/\*|/\.|/\.\.|/\*/\*|
            ~|~/|~/\*|~/\.\*|~/\.[^/]{0,80}|~[a-z_][\w-]{0,40}/?\*?|
            \$\{?home\}?/?\*?|\$home/?\*?|%userprofile%/?\*?|%cd%/?\*?|
            (?:~|\$\{?home\}?|%userprofile%|\$env:userprofile|[a-z]:/users/[^/]{1,80}|/(?:home|users)/[^/]{1,80}|/(?:c|d|mnt/c)/users/[^/]{1,80})
                /(?:desktop|documents|downloads|pictures|music|videos|onedrive[^/]{0,40})(?:/\*)?|
            \$env:(?:userprofile|homepath|homedrive|systemroot|windir|programfiles|programdata|appdata|localappdata)/?\*?|
            \.|\./|\.\.|\.\./|\.\./\.\.(?:/\.\.){0,10}/?|\*|\./\*|\.\*|\.\[!\.\]\*|\.\./\*|\*/|\*\.\*|
            [a-z]:/?\*?|/[a-z]/?\*?|/mnt/[a-z]/?\*?|
            [a-z]:/(?:windows|users|program\ files(?:\ \(x86\))?|programdata|system32)/?\*?|
            [a-z]:/users/[^/]{1,80}/?\*?|/(?:c|d|mnt/c)/users/[^/]{1,80}/?\*?|
            /[^/]{1,80}/?\*?|
            /(?:home|users)/[^/]{1,80}/?\*?|
            \$\{?\w{1,60}\}?/?\*?|"?\$\{?\w{1,60}\}?"?/\*
        )$""")
    return _DANGER_PATH


def is_danger_target(t: str, cwd: str = "") -> bool:
    """A delete target that is the root, the home folder, a drive, a top-level folder, the current folder,
    its parent, a lone variable or everything ('*')."""
    p = _norm(t)
    if not p:
        return False
    if p[:1] in "/~$" and ".." in p.split("/"):
        return True
    if _danger_rx().match(p):
        return True
    if p.startswith("/") or re.match(r"^[A-Za-z]:/", p):
        a = _abs(p, cwd)
        root = _root()
        if a == root or (root and root.startswith(a.rstrip("/") + "/")):
            return True                                      # the project folder or one of its parents
        if _wide_reason() and a == _abs(paths.project_root()):
            return True
    return False


def is_root_like(t: str) -> bool:
    p = _norm(t)
    return bool(_danger_rx().match(p)) and (p[:1] in "/~$%" or bool(re.match(r"(?i)^[a-z]:", p)))


def is_git_dir(t: str) -> bool:
    return bool(re.search(r"(?:^|/)\.git/?\*?$", _norm(t)))


def is_safe_artifact(t: str) -> bool:
    p = _norm(t)
    if not p or p.startswith("/") or re.match(r"(?i)^[a-z]:", p) or p.startswith("~") or ".." in p.split("/"):
        return False
    if "$" in p or "(...)" in p or "`" in p:
        return False
    parts = [x for x in p.split("/") if x not in ("", ".")]
    if not parts:
        return False
    last = parts[-1]
    if last == "*" and len(parts) >= 2:
        last = parts[-2]
    return last.lower() in SAFE_ARTIFACTS or bool(_SAFE_GLOB.match(last))


_HOME_VAR = re.compile(r"(?i)^(?:\$\{?home\}?|\$env:userprofile|%userprofile%)(?=/|$)")
_TEMP_VAR = re.compile(r"(?i)^(?:\$\{?(?:tmpdir|tmp|temp)\}?|\$env:(?:tmp|temp)|%(?:tmp|temp)%)(?=/|$)")
_HERE_VAR = re.compile(r"(?i)^(?:\$pwd|\$\{pwd\}|%cd%)(?=/|$)")
_GIT_INSIDE = re.compile(r"(?i)(?:^|/)\.git/[^/]")
_POSIX_TEMP = ("/tmp", "/var/tmp")          # the same place as the Windows temp folder in Git Bash


def _temp_dir() -> str:
    try:
        import tempfile
        return _abs(tempfile.gettempdir())
    except Exception:  # noqa: BLE001
        return ""


def is_outside_project(t: str, cwd: str = "") -> bool:
    """True when a delete target resolves OUTSIDE the project folder and outside the operating system temp folder.
    Relative paths (with '..' too) resolve from the payload cwd, absolute and home-folder paths count, and the
    project folder is paths.project_root() (CLAUDE_PROJECT_DIR). A target with a variable that is not known here is
    not judged (it keeps the old behaviour). DENIZ-1 / H1."""
    try:
        s = _norm(t)
        if not s:
            return False
        base = _norm(cwd or paths.project_root())
        m = _HOME_VAR.match(s)
        if m:
            s = (_home() or "~") + s[m.end():]
        m = _HERE_VAR.match(s)
        if m:
            s = base + s[m.end():]
        m = _TEMP_VAR.match(s)
        if m:
            s = _temp_dir() + s[m.end():]
        if s.startswith("~") and not s.startswith("~/") and s != "~":
            return True                                  # ~someone/... is another person's folder
        a = _abs(s, base)
        if not a:
            return False
        if _under(a, _root()):
            return False
        if _temp_dir() and _under(a, _temp_dir()):
            return False
        if any(_under(a, _abs(x)) for x in _POSIX_TEMP):
            return False
        return True
    except Exception:  # noqa: BLE001
        return False


def _is_git_inside(t: str) -> bool:
    """A path inside the .git folder (the index, config, objects ...), not the folder itself (that is rm-git)."""
    return bool(_GIT_INSIDE.search(_norm(t)))


def _short_target(t: Any) -> str:
    """One delete target cut by whole segments (walk-23). A root-anchored path keeps its leading '/'."""
    raw = str(t)
    s = paths.short_path(raw)
    if raw.replace("\\", "/").startswith("/") and not s.startswith(("/", ".../")):
        s = "/" + s
    return s


def _shown_path(p: str, cwd: str = "") -> str:
    """A file path for a guard message (walk-23): the project-relative spelling inside the project, else the
    last three segments. Never cut inside a segment."""
    try:
        a = _abs(p, cwd, lower=False)
        if not a:
            return ""
        if _under(_abs(a), _root()):
            return paths.shown(a) or "."
        return paths.short_path(a, 3)
    except Exception:  # noqa: BLE001
        return short_text(_norm(p), 60)


def _targets_text(targets: Iterable[Any]) -> str:
    """Delete targets for a guard message: each path cut by whole segments, redacted, one line."""
    return short_text(" ".join(_short_target(t) for t in targets), 90)


def _outside_only(ctx: "Ctx", targets: Iterable[str]) -> None:
    """The outside-the-project rule alone (rmdir, unlink, del, rd, find -delete targets)."""
    outside = [t for t in targets if t and is_outside_project(t, ctx.vcwd)]
    if outside:
        ctx.add("delete-outside-project", _targets_text(outside))


def short_text(text: Any, n: int = 80) -> str:
    """A short, single-line, redacted piece of command text for a finding detail (never a whole secret).
    A longer text is cut at the last space or path separator before the limit, so no word or path segment is
    shown in two pieces (walk-23)."""
    try:
        s = str(text)[:400]
        s = _secrets.redact(s) if s else s
        s = " ".join(s.split())
        s = "".join(ch for ch in s if ch.isprintable())
        if len(s) <= n:
            return s
        cut = s[:n - 3]
        k = max(cut.rfind(" "), cut.rfind("/"), cut.rfind("\\"))
        if k >= (n - 3) // 2:
            cut = cut[:k]
        return cut.rstrip(" /\\") + "..."
    except Exception:  # noqa: BLE001
        return ""


# --------------------------------------------------------------------------- patterns (compiled on first use)

_RX_SRC: Dict[str, str] = {
    "lolbin": r"(?i)\b(?:certutil\b[^|;&\n]{0,100}?-urlcache|bitsadmin\b[^|;&\n]{0,100}?/transfer|mshta\s+https?://"
              r"|regsvr32\b[^|;&\n]{0,100}?/i:https?://|rundll32\b[^|;&\n]{0,100}?javascript:)",
    "system_config": r"""(?ix)\b(?:
        set-executionpolicy\b[^|;&\n]{0,100}?\b(?:unrestricted|bypass)\b|
        set-mppreference\b[^|;&\n]{0,100}?-disable\w{0,40}|add-mppreference\b[^|;&\n]{0,100}?-exclusion\w{0,40}|
        netsh\s+(?:adv\w{0,12}\s+)?(?:firewall|advfirewall)\b[^|;&\n]{0,100}?\b(?:off|disable|delete)|
        bcdedit\b|net\s+user\s+\S{1,60}\s+\S{1,60}\s+/add|net\s+localgroup\s+administrators\b[^|;&\n]{0,60}?/add|
        icacls\s+[^|;&\n]{0,200}?(?:/grant\s+(?:\*S-1-1-0|everyone)|/reset\s+/t\s+/c\s+/q)|
        takeown\s+[^|;&\n]{0,100}?(?:/f\s+(?:[a-z]:\\?|%\w{1,20}%)\s|/r)|
        ufw\s+disable|setenforce\s+0|systemctl\s+(?:disable|mask)\s+(?:firewalld|ufw|apparmor)|iptables\s+-F
    )""",
    "persistence": r"""(?ix)(?:
        \bcrontab\s+(?:-\w{1,6}\s+){0,3}(?:-|[^\s-]\S{0,200})\s{0,5}$|\bcrontab\s+-[a-z]{0,3}r(?![\w-])|\bcrontab\s+-e\b|
        \bschtasks(?:\.exe)?\s+/create\b|\bregister-scheduledtask\b|\bnew-scheduledtask\b|
        \breg(?:\.exe)?\s+add\s+[^|;&\n]{0,200}?\\run(?:once)?\b|
        \bnew-itemproperty\b[^|;&\n]{0,200}?\\run(?:once)?\b|
        \\start\ menu\\programs\\startup\\|\blaunchctl\s+(?:load|bootstrap)\b|\bsystemctl\s+(?:--user\s+)?enable\b
    )""",
    "reg_write": r"(?i)\b(?:reg(?:\.exe)?\s+(?:delete|add|import)\b|(?:set|new|remove)-itemproperty\b[^|;&\n]{0,200}?"
                 r"\b(?:hklm|hkcu|hkey_)|remove-item\b[^|;&\n]{0,200}?\b(?:hklm|hkcu):)",
    "cred_store": r"(?i)\b(?:cmdkey\s+/list|vaultcmd\b|security\s+find-(?:generic|internet)-password|secret-tool\s+lookup"
                  r"|mimikatz|lazagne)",
    "tunnel": r"(?i)\b(?:ngrok(?:\.exe)?\s+(?:http|tcp|tls)|cloudflared\s+tunnel|localtunnel|lt\s+--port|serveo|bore\s+local"
              r"|tailscale\s+funnel|zrok\s+share)\b|\bssh\b[^|;&\n]{0,200}?\s-R\s+\S{1,100}",
    "bind_all": r"(?i)(?:--host(?:name)?[= ]+(?:0\.0\.0\.0|::)(?![\w.])|(?<![\w.])-H\s+0\.0\.0\.0(?![\w.])"
                r"|\bHOST=0\.0\.0\.0\b|runserver\s+0\.0\.0\.0|\bserve\s+-l\s+tcp://0\.0\.0\.0)",
    "http_server": r"(?i)\bhttp\.server\b",
    "bind_local": r"(?i)--bind[= ]+(?:127\.0\.0\.1|localhost|::1)\b|(?:^|\s)-b\s+(?:127\.0\.0\.1|localhost)\b",
    "docker_danger": r"(?i)\bdocker\b[^|;&\n]{0,300}?\s(?:--privileged|--pid[= ]host|--net(?:work)?[= ]host|-v\s+/:"
                     r"|-v\s+[\"']?/var/run/docker\.sock|--volume[= ]+/(?::|\s)|--cap-add[= ]+(?:all|sys_admin))",
    "docker_prune": r"(?i)\bdocker(?:\s+compose|-compose)?\s+(?:system\s+prune\b[^|;&\n]{0,100}?(?:-a|--all|--volumes)"
                    r"|volume\s+(?:prune|rm)\b|down\b[^|;&\n]{0,100}?(?:-v|--volumes)|container\s+prune|rm\s+-f\s+\$\()",
    "db_sql": r"(?i)\b(?:drop\s+(?:database|table|schema)|truncate\s+(?:table\s+)?\w{1,60}|"
              r"delete\s+from\s+[\w.\"`]{1,80}\s{0,3}(?:;|\"|'|$)|update\s+[\w.\"`]{1,80}\s+set\s+[^;]{1,200}?(?:;|\"|'|$))",
    "sql_where": r"(?i)\bwhere\b",
    "db_tools": r"(?i)(?:\bdropdb\b|\bmysqladmin\s+(?:-\S{1,40}\s+){0,4}drop\b|\bflush(?:all|db)\b|\bdb\.dropDatabase\(|\bdropDatabase\("
                r"|prisma\s+migrate\s+reset|prisma\s+db\s+push\b[^|;&\n]{0,100}?--force-reset|\b(?:rails|rake)\s+db:(?:drop|reset|schema:load)"
                r"|manage\.py\s+(?:flush|sqlflush)|supabase\s+db\s+reset|sequelize\S{0,20}\s+db:(?:drop|migrate:undo:all)"
                r"|typeorm\s+schema:drop|flask\s+db\s+downgrade\s+base|alembic\s+downgrade\s+base"
                r"|knex\s+migrate:rollback\s+--all|artisan\s+(?:migrate:fresh|db:wipe))",
    "db_prod": r"(?i)\bprod(?:uction)?\b|\.rds\.|\.supabase\.co|\.neon\.tech|planetscale|mongodb\+srv",
    "cloud_destroy": r"(?i)\b(?:terraform\s+(?:destroy|apply\b[^|;&\n]{0,100}?-auto-approve)|pulumi\s+destroy|cdk\s+destroy"
                     r"|aws\s+s3\s+(?:rm\b[^|;&\n]{0,100}?--recursive|rb\b)|aws\s+\w{1,30}\s+delete-\S{1,60}"
                     r"|gcloud\s+(?:\S{1,40}\s+){1,5}delete\b|az\s+group\s+delete|az\s+\S{1,40}\s+delete\b|kubectl\s+delete\b"
                     r"|heroku\s+apps:destroy|fly(?:ctl)?\s+(?:apps\s+destroy|destroy)|vercel\s+(?:remove|rm)\b|netlify\s+sites:delete"
                     r"|firebase\s+(?:projects:delete|firestore:delete|database:remove)|doctl\s+\S{1,30}\s+delete|railway\s+(?:down|delete))",
    "publish": r"(?i)\b(?:npm\s+publish|pnpm\s+publish|yarn\s+npm\s+publish|twine\s+upload|cargo\s+publish|gem\s+push"
               r"|vercel\s+(?:deploy\s+)?--prod|netlify\s+deploy\s+[^|;&\n]{0,100}?--prod|firebase\s+deploy|docker\s+push"
               r"|git\s+push\s+(?:heroku|dokku)|flyctl?\s+deploy|wrangler\s+(?:deploy|publish)|dotnet\s+nuget\s+push"
               r"|poetry\s+publish|uv\s+publish)\b",
    "dry_run": r"(?i)(?:^|\s)(?:--dry-run|-n)(?:\s|$)",
    "curl_upload": r"(?i)\bcurl\b[^|;&\n]{0,400}?\s(?:(?:-d|--data(?:-binary|-raw|-urlencode|-ascii)?|-F|--form(?:-string)?|--json)(?:\s+|=)[\"']?(?:[\w.-]{1,40}=)?@"
                   r"|(?:-T|--upload-file)\s+\S)",
    "wget_post": r"(?i)\bwget\b[^|;&\n]{0,300}?--(?:post-file|body-file)\b",
    "ps_upload": r"(?i)\b(?:invoke-webrequest|invoke-restmethod|iwr|irm)\b[^|;&\n]{0,400}?(?:-infile\b|-method\s+(?:post|put|patch)\b|-body\b|-form\b)",
    "inline_delete": r"(?i)(?:shutil\.rmtree|os\.(?:removedirs|rmdir)|\brimraf\b|\.(?:rmSync|rmdirSync|rm)\s*\([^)]{0,200}recursive|"
                     r"\bFileUtils\.rm_rf|\[(?:System\.)?IO\.(?:Directory|File)\]::Delete|Remove-Item\b[^|;]{0,200}-Recurse|"
                     r"shell_exec\s*\(\s*['\"]rm\s)",
    "read_call": r"(?i)\b(?:open|read_text|read_bytes|readFile(?:Sync)?|createReadStream|Get-Content|File\.read|file_get_contents|"
                 r"cat|type)\s*\(|(?:fs|Path)\b[^;]{0,80}\.read\w{0,12}\(",
    "code_fetch": r"(?i)\b(?:urlopen|urlretrieve|requests\.get|httpx\.get|axios\.get|https?\.get|XMLHttpRequest)\b|\bfetch\s{0,3}\(",
    "code_exec": r"(?i)(?:\bexec\s{0,3}\(|\beval\s{0,3}\(|\.then\s{0,3}\(\s{0,3}eval|new\s{1,3}Function\s{0,3}\(|\bos\.system\s{0,3}\(|\bsubprocess\.|child_process|execSync\s{0,3}\()",
    "code_b64": r"(?i)(?:b64decode|\batob\s{0,3}\(|\bfrom\s{0,3}\(\s{0,3}['\"][^'\"\n]{4,400}['\"]\s{0,3},\s{0,3}['\"]base64|fromhex\s{0,3}\(|frombase64string)",
    "env_print_code": r"(?i)(?:print\s*\(\s*(?:dict\s*\(\s*)?os\.environ\s*\)|console\.log\s*\(\s*process\.env\s*\)|"
                      r"JSON\.stringify\s*\(\s*process\.env|json\.dumps\s*\(\s*(?:dict\s*\(\s*)?os\.environ|os\.environ\.items\s*\(|"
                      r"puts\s+ENV\.to_h|System\.getenv\s*\(\s*\))",
    "env_dumper_ps": r"(?i)\[environment\]::getenvironmentvariables|get-item\s+env:\*",
    "fork_bomb": r":\s{0,3}\(\s{0,3}\)\s{0,3}\{\s{0,3}:\s{0,3}\|\s{0,3}:\s{0,3}&\s{0,3}\}\s{0,3};\s{0,3}:",
    "device_target": r"(?i)^(?:/dev/(?:sd|hd|nvme|disk|rdisk|mmcblk|vd|xvd)\w{0,20}|\\\\\.\\\S{1,40})$",
    "profile_file": r"(?i)(?:\.bashrc|\.zshrc|\.profile|\.bash_profile|\.zprofile|\.zshenv|\$profile|microsoft\.powershell_profile\.ps1|[\\/]profile\.ps1)$",
    "startup_folder": r"(?i)start menu/programs/startup/",
    "url_cred": r"://[^/@\s:]{1,80}:[^/@\s]{1,200}@",
    "url_local": r"(?i)^(?:https?://)?(?:localhost|127\.\d{1,3}\.\d{1,3}\.\d{1,3}|\[::1\]|0\.0\.0\.0)(?::\d{1,5})?(?:[/?#]|$)",
    "url_any": r"(?i)^(?:[a-z][a-z0-9+.-]{1,12}://|www\.)\S{1,500}",
    "protected_branch": r"(?i)^(?:refs/heads/)?(?:main|master|trunk|develop|production|prod|release(?:/.*)?)$",
    "git_exec_key": r"(?i)^(?:core\.(?:fsmonitor|sshcommand|askpass|hookspath|gitproxy)|diff\.external|protocol\.ext\.allow|"
                    r"uploadpack\.packobjectshook|gpg\.program|sequence\.editor|filter\.[^.]{1,40}\.(?:clean|smudge|process))$",
    "git_soft_exec_key": r"(?i)^(?:core\.(?:editor|pager)|pager\.[\w-]{1,40}|merge\.tool|mergetool\.[^.]{1,40}\.cmd|difftool\.[^.]{1,40}\.cmd)$",
    "git_safe_helper": r"(?i)^(?:cache|manager|manager-core|osxkeychain|wincred|libsecret|gnome-keyring|microsoft-credential-manager)(?:\s.*)?$",
    "known_runner": r"(?i)^(?:create-[\w.-]{1,60}|vite|tsc|typescript|prettier|eslint|serve|http-server|live-server|nodemon|ts-node|tsx|"
                    r"tailwindcss|postcss|prisma|jest|vitest|mocha|playwright|cypress|next|nuxt|astro|svelte|svelte-kit|vue|ng|"
                    r"expo|eas|nx|turbo|degit|esbuild|webpack|rollup|parcel|storybook|sb|netlify|vercel|wrangler|firebase|"
                    r"supabase|tsup|concurrently|cross-env|rimraf|npm|pnpm|yarn|corepack|node|ruff|black|isort|flake8|pytest|"
                    r"mypy|pip|pipx|uv|poetry|tox|nox|cookiecutter|pre-commit|jupyter|jupyterlab|streamlit|gradio|flask|uvicorn|"
                    r"fastapi|django-admin|mkdocs|sphinx-build|http\.server)(?:@[\w.^~<>=*-]{1,40})?$",
    "secret_word": r"(?i)KEY|TOKEN|SECRET|PASSW(?:OR)?D|PASSWD|CREDENTIAL|PRIVATE|AUTH",
    "sensitive_dir_name": r"(?i)(?:^|/)\.(?:ssh|aws|gnupg|kube)/?$",
    "package_name": r"^(?:@[\w.~-]{1,100}/)?[\w.~-]{1,100}$",
    "pip_skip": r"(?i)^(?:pip|setuptools|wheel)$",
}
_RXC: Dict[str, Any] = {}


def _rx(key: str) -> Any:
    r = _RXC.get(key)
    if r is None:
        r = re.compile(_RX_SRC[key])
        _RXC[key] = r
    return r


def all_regexes() -> List[Tuple[str, Any]]:
    """Every compiled expression of this module as (name, pattern), for the regex-fuzz selftest."""
    out = [(k, _rx(k)) for k in sorted(_RX_SRC)]
    for k, v in sorted(globals().items()):
        if isinstance(v, re.Pattern) and k not in ("_DANGER_PATH",):
            out.append((k, v))
    out.append(("danger_path", _danger_rx()))
    for rid, src in _PANIC:
        out.append(("panic:" + rid, re.compile(src)))
    return out


# --------------------------------------------------------------------------- the analysis state

class Ctx(object):
    """State of one analysis run. Child runs (nested shells, literals, scripts) share the counters."""

    def __init__(self, kind: str, cwd: str, shared: Optional[Dict[str, Any]] = None, depth: int = 0,
                 mode: str = "command") -> None:
        self.kind = kind
        self.cwd = cwd or paths.project_root()
        self.vcwd = self.cwd
        self.depth = depth
        self.mode = mode                      # command | script | literal : the last two skip generic asks
        self.out: List[Finding] = []
        self.shared = shared if shared is not None else {
            "segments": 0, "scripts": 0, "deadline": time.monotonic() + BUDGET_SECONDS, "wide": None, "deps": None}
        self.downloaded: Set[str] = set()
        self.hidden = False                   # the output of this (nested) command does not reach the model
        self.sender_parent = False            # the outer command sends its arguments somewhere

    def tick(self) -> None:
        self.shared["segments"] += 1
        if self.shared["segments"] > MAX_SEGMENTS or time.monotonic() > self.shared["deadline"]:
            raise BudgetExceeded("limit")

    def add(self, rule_id: str, detail: str = "", tier: Optional[str] = None) -> None:
        t = tier or RULE_TIERS.get(rule_id, ASK)
        if self.mode != "command" and (t == WARN or rule_id in ("unresolvable-program", "no-gitignore")):
            return
        if t == WARN and rule_id in _QUIET:
            return
        for f in self.out:
            if f["rule_id"] == rule_id and _RANK[f["tier"]] >= _RANK[t]:
                return
        self.out = [f for f in self.out if not (f["rule_id"] == rule_id and _RANK[f["tier"]] < _RANK[t])]
        self.out.append(Finding(rule_id, t, rule_id, detail))

    def child(self, kind: str, mode: Optional[str] = None) -> "Ctx":
        c = Ctx(kind, self.vcwd, self.shared, self.depth + 1, mode or self.mode)
        return c

    @property
    def wide(self) -> str:
        if self.shared.get("wide") is None:
            self.shared["wide"] = _wide_reason()
        return str(self.shared["wide"])


def _kind_of(shell: str) -> str:
    s = (shell or "bash").lower()
    if s in ("powershell", "pwsh", "ps", "ps1"):
        return PS
    if s in ("cmd", "cmd.exe", "bat"):
        return CMD
    return SH


def _join_tokens(vals: Sequence[str]) -> str:
    out = []
    for v in vals:
        if v and re.fullmatch(r"[\w@%+=:,./\\-]+", v):
            out.append(v)
        else:
            out.append("'" + v.replace("'", "'\"'\"'") + "'")
    return " ".join(out)


# --------------------------------------------------------------------------- deleting

_REMOVE_SPECS = {"path": True, "literalpath": True, "include": True, "exclude": True, "filter": True, "recurse": False,
                 "force": False, "confirm": False, "whatif": False, "stream": True, "credential": True}


def _split_targets(vals: Iterable[str]) -> List[str]:
    out: List[str] = []
    for v in vals:
        for part in str(v).split(","):
            part = part.strip()
            if part:
                out.append(part)
    return out


def _delete_targets_rules(ctx: Ctx, targets: List[str], recursive: bool, rule_danger: str, rule_ask: str,
                          sudo: bool = False) -> None:
    """The shared decision for rm, Remove-Item and cmd delete."""
    if not targets:
        return
    cwd = ctx.vcwd
    if any(is_git_dir(t) for t in targets):
        ctx.add("rm-git", _targets_text(targets))
        return
    if any(_is_git_inside(t) for t in targets):
        ctx.add("rm-git-inside", _targets_text(targets))
    _outside_only(ctx, targets)                           # DENIZ-1: outside the project folder is an ask
    if any(is_danger_target(t, cwd) for t in targets):
        if recursive or sudo or any(_norm(t) in ("/*", "~/*", "$HOME/*", "/") for t in targets):
            ctx.add(rule_danger, _targets_text(targets))
        else:
            ctx.add("rm-recursive" if rule_ask == "rm-recursive" else rule_ask, _targets_text(targets))
        return
    if recursive and not all(is_safe_artifact(t) for t in targets):
        ctx.add(rule_ask, _targets_text(targets))
    if ctx.wide and recursive and not all(is_safe_artifact(t) for t in targets):
        ctx.add("wide-folder", ctx.wide)


def rm_rules(ctx: Ctx, c: Cmd) -> None:
    short, long_, tg = split_flags(c.vals())
    recursive = bool(short & {"r", "R"}) or "recursive" in long_
    xargs = "xargs" in c.wrappers
    if "no-preserve-root" in long_:
        ctx.add("rm-danger", "--no-preserve-root")
        return
    targets = [t for t in tg if not (xargs and t == "{}")]
    if not targets:
        if xargs and recursive:
            ctx.add("rm-recursive", "the list of folders comes from the pipe")
        return
    if "sudo" in c.wrappers and recursive:
        ctx.add("rm-danger", "sudo rm -r")
        return
    _delete_targets_rules(ctx, targets, recursive, "rm-danger", "rm-recursive")


def shred_rules(ctx: Ctx, c: Cmd) -> None:
    ctx.add("rm-danger", c.prog)


def ps_remove_rules(ctx: Ctx, c: Cmd, pipe: List[Seg], cmds: List[Cmd], idx: int) -> None:
    vals = c.vals()
    if any(re.match(r"^/[A-Za-z]$", v) for v in vals):
        cmd_delete_rules(ctx, c)
        return
    named, pos = ps_params(vals, _REMOVE_SPECS)
    if named.get("whatif") is True:
        return
    targets = _split_targets(pos + [str(named[k]) for k in ("path", "literalpath") if k in named and named[k] is not True])
    here = [re.match(r"(?i)^\s*\(?\s*(?:get-location|pwd)\b", t) is not None for _k, t in c.seg.nested]
    targets = ["." if (t.startswith("(...)") and any(here)) else t for t in targets]
    rec = named.get("recurse") is True
    if not targets and idx > 0 and (rec or _wide_listing(cmds, idx)):
        _ps_pipe_delete(ctx, cmds, idx)
        return
    _delete_targets_rules(ctx, targets, rec, "win-delete-danger", "win-delete")


def _wide_listing(cmds: List[Cmd], idx: int) -> bool:
    """Get-ChildItem -Recurse with no filter, piped on: every file below the current folder."""
    prev = cmds[idx - 1]
    if prev.prog != "get-childitem":
        return False
    named, pos = ps_params(prev.vals(), {"path": True, "literalpath": True, "filter": True, "include": True, "exclude": True,
                                          "recurse": False, "force": False, "name": False, "directory": False, "file": False, "depth": True})
    return named.get("recurse") is True and not pos and not any(k in named for k in ("filter", "include", "exclude", "path", "literalpath"))


def _ps_pipe_delete(ctx: Ctx, cmds: List[Cmd], idx: int) -> None:
    """Get-ChildItem | Remove-Item -Recurse (no path): what is deleted is whatever the left side lists."""
    prev = cmds[idx - 1]
    if prev.prog in ("get-childitem", "get-item"):
        named, pos = ps_params(prev.vals(), {"path": True, "literalpath": True, "filter": True, "include": True,
                                              "exclude": True, "recurse": False, "force": False, "name": False,
                                              "directory": False, "file": False, "depth": True})
        src = _split_targets(pos + [str(named[k]) for k in ("path", "literalpath") if k in named and named[k] is not True])
        if src and all(is_safe_artifact(t) for t in src):
            return
        if not src or any(is_danger_target(t, ctx.vcwd) for t in src):
            at_root = _abs(ctx.vcwd) == _root() or not ctx.cwd or bool(ctx.wide)
            ctx.add("ps-pipe-delete", "everything in the current folder", BLOCK if at_root or any(
                is_danger_target(t, ctx.vcwd) for t in src) else ASK)
            return
    ctx.add("ps-pipe-delete", "the list comes from the pipe")


def cmd_delete_rules(ctx: Ctx, c: Cmd) -> None:
    flags = [a.lower() for a in c.vals() if re.match(r"^/[A-Za-z]$", a)]
    tg = [a for a in c.vals() if not re.match(r"^/[A-Za-z]$", a)]
    rec = "/s" in flags
    if c.prog in ("del", "erase", "remove-item") and not (rec or "/f" in flags):
        _outside_only(ctx, tg)
        if any(is_danger_target(t, ctx.vcwd) for t in tg):
            ctx.add("win-delete-danger", _targets_text(tg))
        return
    _delete_targets_rules(ctx, tg, True, "win-delete-danger", "win-delete")


def find_rules(ctx: Ctx, c: Cmd) -> None:
    vals = c.vals()
    short, long_, _tg = split_flags(vals)
    exec_rm = False
    for k, v in enumerate(vals):
        if v in ("-exec", "-execdir", "-ok", "-okdir") and k + 1 < len(vals):
            exec_rm = _pname(vals[k + 1]) in ("rm", "rmdir", "unlink", "shred")
    if "-delete" in vals or exec_rm:
        starts = [t for t in vals if not t.startswith("-")][:1]
        _outside_only(ctx, starts)
        if starts and starts[0] not in (".", "./") and is_danger_target(starts[0], ctx.vcwd):
            ctx.add("rm-danger", _targets_text(starts))
        else:
            ctx.add("rm-recursive", "find ... -delete")
    # find ... -exec <command> {} ; : look at the command
    for k, v in enumerate(vals):
        if v in ("-exec", "-execdir", "-ok", "-okdir"):
            j = k + 1
            inner: List[str] = []
            while j < len(vals) and vals[j] not in (";", "+", "\\;"):
                inner.append("x" if vals[j] == "{}" else vals[j])
                j += 1
            if inner and _pname(inner[0]) in _READERS and any(
                    _secret_token(vals[n + 1]) for n, x in enumerate(vals[:-1]) if x.lower() in ("-name", "-iname", "-path", "-ipath")):
                ctx.add("read-secret", "find -exec " + _pname(inner[0]) + " on a secret file name")
            if inner and _pname(inner[0]) not in ("rm", "rmdir", "unlink", "shred"):
                nested_text(ctx, _join_tokens(inner), SH)


def sync_rules(ctx: Ctx, c: Cmd) -> None:
    vals = [v.lower() for v in c.vals()]
    if c.prog == "robocopy" and any(v in ("/mir", "/purge") for v in vals):
        ctx.add("sync-delete", "robocopy /mir or /purge deletes files in the target that are not in the source")
    elif c.prog == "rsync" and any(v == "--delete" or v.startswith("--delete-") or v == "--del" or v == "--remove-source-files" for v in vals):
        ctx.add("sync-delete", "rsync --delete removes files in the target that are not in the source")


# claude flags that start a session without this project's hooks or prompts (guard-3)
_CLAUDE_GUARD_OFF = frozenset(["bare", "safe-mode", "settings", "dangerously-skip-permissions", "allow-dangerously-skip-permissions"])
_KIT_SCRIPTS = frozenset(["doctor.py", "install.py"])


def _kit_script_rules(ctx: Ctx, prog: str, vals: Sequence[str]) -> None:
    """doctor.py and install.py (walk-9): the verbs that rewrite settings, remove the kit or send notes out are asks.
    check, progress, envcheck, audit and verify only read, so they stay silent."""
    start, name = 0, prog
    if prog not in _KIT_SCRIPTS:
        found = [k for k, v in enumerate(vals) if _pname(v) in _KIT_SCRIPTS]
        if not found:
            return
        start, name = found[0] + 1, _pname(vals[found[0]])
    args = [str(v).lower() for v in vals[start:]]
    if name == "doctor.py":
        if "wipe" in args:
            ctx.add("memory-wipe", "doctor.py wipe")
            return
        verb = next((a for a in args if not a.startswith("-")), "")
        if verb in ("enable-hooks", "disable-hooks", "share-notes"):
            ctx.add("helper-script", "doctor.py " + verb)
    else:
        flags = [a for a in args if a in ("--update", "--uninstall", "--enable-hooks")]
        if flags:
            ctx.add("helper-script", "install.py " + flags[0])


def misc_system_rules(ctx: Ctx, c: Cmd) -> None:
    """format, dd, shred, sudo, chmod, chown, kill, shutdown ..."""
    prog = c.prog
    vals = c.vals()
    short, long_, tg = split_flags(vals)
    if prog == "format" and any(re.match(r"(?i)^[a-z]:\\?$", t) for t in tg):
        ctx.add("format-disk", "format " + tg[0])
    elif prog in ("format-volume", "clear-disk", "initialize-disk", "remove-partition", "diskpart", "fdisk", "sfdisk",
                  "parted", "gdisk", "wipefs", "cfdisk") or prog.startswith("mkfs") or prog.startswith("newfs"):
        ctx.add("format-disk", prog)
    if prog in ("shred", "wipe", "srm", "sdelete") or (prog == "cipher" and any(a.lower().startswith("/w") for a in vals)):
        shred_rules(ctx, c)
    if prog == "dd" and any(re.match(r"^of=(/dev/|\\\\\.\\)", a) for a in vals):
        ctx.add("dd-device", "dd of=<disk device>")
    if prog in ("mv", "move", "move-item") and tg and tg[-1] in ("/dev/null", "nul", "NUL", "$null") and len(tg) >= 2:
        ctx.add("rm-recursive", "moved to /dev/null")
    if prog in ("sudo", "su", "doas", "runas", "gsudo", "pkexec") or "sudo" in c.wrappers:
        if prog not in ("rm",) and not (prog in ("npm", "pnpm", "yarn", "pip", "pip3", "gem", "pipx") and "sudo" in c.wrappers):
            ctx.add("sudo", prog if prog in ("su", "runas") else "")
    if prog == "start-process" and any(a.lower() == "runas" for a in vals):
        ctx.add("sudo", "Start-Process -Verb RunAs")
    if prog == "chmod":
        modes = [t for t in tg if re.match(r"^(?:0?777|a\+rwx|ugo\+rwx|[ugo]*=rwx)$", t)]
        if modes:                                        # SPEC 7.2: chmod -R 777 is a block, a single file is an ask
            ctx.add("chmod-777", short_text(" ".join(vals)), BLOCK if ("R" in short or "recursive" in long_) else ASK)
    if prog in ("chown", "chgrp") and ("R" in short or "recursive" in long_):
        ctx.add("chown-r", short_text(" ".join(vals)), BLOCK if any(is_root_like(t) for t in tg[1:]) else ASK)
    if prog in ("killall", "pkill", "taskkill", "stop-process", "kill"):
        if prog == "kill" and ("-1" in vals or "-- -1" in " ".join(vals)):
            ctx.add("kill-all", "kill -1", BLOCK)
        elif prog in ("killall", "pkill"):
            ctx.add("kill-all", prog)
        elif prog == "taskkill" and any(a.lower() == "/im" for a in vals):
            ctx.add("kill-all", "taskkill by program name")
        elif prog == "stop-process" and any(re.match(r"(?i)^-n(?:a(?:m(?:e)?)?)?$", a) for a in vals):
            ctx.add("kill-all", "Stop-Process by name")
    if prog in ("shutdown", "reboot", "halt", "poweroff", "restart-computer", "stop-computer") or (prog == "init" and tg[:1] in (["0"], ["6"])):
        ctx.add("shutdown", prog)
    if prog == "claude" and (long_ & _CLAUDE_GUARD_OFF or any(v.lower().endswith("bypasspermissions") for v in vals)):
        ctx.add("claude-guard-off", "claude " + " ".join(vals[:4]))
    if prog == "claude" and len(vals) >= 2:
        a0, a1 = vals[0].lower(), vals[1].lower()
        if (a0 == "mcp" and a1 in ("add", "add-json", "add-from-claude-desktop")) or (a0 == "plugin" and a1 in ("install", "add")) \
                or (a0 == "config" and a1 in ("set", "add", "remove")) or (a0 == "plugins" and a1 == "install"):
            ctx.add("claude-config", "claude " + a0 + " " + a1)
    if prog in _KIT_SCRIPTS or _interp(prog) == "python":
        _kit_script_rules(ctx, prog, vals)


# --------------------------------------------------------------------------- git and GitHub

_GIT_OPT_WITH_ARG = frozenset(["-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix",
                               "--config-env", "--attr-source"])


def git_parse(vals: Sequence[str]) -> Tuple[str, List[str], List[str]]:
    """(subcommand, its arguments, the -c key=value settings), skipping the options before the subcommand."""
    i = 0
    n = len(vals)
    cfgs: List[str] = []
    while i < n:
        a = vals[i]
        if a == "-c" and i + 1 < n:
            cfgs.append(vals[i + 1])
            i += 2
            continue
        if a in _GIT_OPT_WITH_ARG:
            i += 2
            continue
        if a.startswith("--") and "=" in a and a.split("=", 1)[0] in _GIT_OPT_WITH_ARG:
            if a.startswith("--config-env"):
                cfgs.append(a.split("=", 1)[1])
            i += 1
            continue
        if a.startswith("-"):
            i += 1
            continue
        break
    if i >= n:
        return "", [], cfgs
    return vals[i], list(vals[i + 1:]), cfgs


def _git_branch_now(ctx: Ctx) -> str:
    try:
        from . import gitq
        return str(gitq.branch(ctx.vcwd) or "")
    except Exception:  # noqa: BLE001
        return ""


def _config_exec(ctx: Ctx, key: str, value: str, one_shot: bool) -> None:
    k = key.strip().lower()
    if not k:
        return
    if k == "credential.helper":
        v = value.strip()
        if v.startswith("store") or v.startswith("!store"):
            ctx.add("git-config-cred", "credential.helper " + short_text(v, 30))
        elif v and not _rx("git_safe_helper").match(v):
            ctx.add("git-config-exec", "credential.helper " + short_text(v, 30))
        return
    if k.startswith("alias."):
        v = value.strip()
        if v.startswith("!"):
            ctx.add("git-config-exec", k)
            nested_text(ctx, v[1:], SH)
        elif v:
            nested_text(ctx, "git " + v, SH)              # an alias that hides `push -f` is still a force push
        return
    if _rx("git_exec_key").match(k):
        ctx.add("git-config-exec", k)
    elif _rx("git_soft_exec_key").match(k):
        ctx.add("git-config-exec", k, BLOCK if one_shot else ASK)


def git_rules(ctx: Ctx, c: Cmd) -> None:
    vals = c.vals()
    sub, sa, cfgs = git_parse(vals)
    for cf in cfgs:
        key, _, val = cf.partition("=")
        _config_exec(ctx, key, val, True)
    if not sub:
        return
    for cf in cfgs:                                       # git -c alias.p='push -f' p
        key, _, val = cf.partition("=")
        if key.lower() == "alias." + sub.lower() and val.strip() and not val.strip().startswith("!"):
            nested_text(ctx, "git " + val.strip() + " " + _join_tokens(sa), SH)
            return
    short, long_, tg = split_flags(sa)
    # reading a secret file through git
    if sub in ("show", "diff", "blame", "annotate", "cat-file", "grep", "log", "stash", "difftool") and \
            (sub != "log" or "p" in short or "patch" in long_ or "L" in short) and (sub != "stash" or tg[:1] == ["show"]):
        for t in sa:
            if t.startswith("-"):
                continue
            tail = t.rsplit(":", 1)[-1] if ":" in t and not re.match(r"^[A-Za-z]:[\\/]", t) else t
            if _secrets.is_secret_filename(tail):
                ctx.add("read-secret", "git " + sub + " " + short_text(tail, 40))
                break
    if sub == "push":
        _git_push(ctx, c, sa, short, long_, tg)
    elif sub == "send-pack":
        if "f" in short or "force" in long_ or any(t.startswith("+") for t in tg):
            ctx.add("git-force", "git send-pack --force")
    elif sub == "reset":
        if "hard" in long_ or "keep" in long_:
            ctx.add("git-reset-hard", "git reset --" + ("hard" if "hard" in long_ else "keep"))
    elif sub == "clean":
        if "n" in short or "dry-run" in long_:
            return
        if "f" in short or "force" in long_:
            if "x" in short or "X" in short:
                ctx.add("git-clean-x", "git clean -x")
            else:
                ctx.add("git-clean", "git clean -f")
    elif sub == "checkout":
        if "b" in short or "B" in short or "orphan" in long_:
            return
        if "--" in sa or any(t in (".", "./", ":/") for t in tg) or "f" in short or "force" in long_:
            ctx.add("git-discard", "git checkout " + ("-- ." if "." in tg or "--" in sa else "-f"))
    elif sub == "restore":
        if "staged" in long_ and "worktree" not in long_ and "W" not in short:
            return
        ctx.add("git-discard", "git restore")
    elif sub == "switch":
        if "f" in short or "force" in long_ or "discard-changes" in long_:
            ctx.add("git-discard", "git switch -f")
    elif sub == "worktree":
        if tg[:1] == ["remove"] and ("f" in short or "force" in long_):
            ctx.add("git-discard", "git worktree remove --force")
    elif sub == "submodule":
        if tg[:1] == ["deinit"] and ("f" in short or "force" in long_):
            ctx.add("git-discard", "git submodule deinit -f")
    elif sub == "branch":
        _git_branch(ctx, short, long_, tg)
    elif sub == "stash":
        if tg and tg[0] in ("drop", "clear"):
            ctx.add("git-stash-drop", "git stash " + tg[0])
    elif sub in ("filter-branch", "filter-repo", "replace", "prune"):
        ctx.add("git-history", "git " + sub)
    elif sub == "update-ref":
        if "d" in short:
            ctx.add("git-history", "git update-ref -d")
    elif sub == "reflog":
        if tg and tg[0] in ("expire", "delete"):
            ctx.add("git-history", "git reflog " + tg[0])
    elif sub == "gc":
        if any(x.startswith("--prune=now") or x == "--prune=all" for x in sa):
            ctx.add("git-history", "git gc --prune=now")
    elif sub == "rebase":
        if not (long_ & {"abort", "continue", "skip", "quit", "edit-todo", "show-current-patch"}):
            ctx.add("git-rebase", "git rebase")
    elif sub == "commit":
        _git_commit(ctx, short, long_, tg)
    elif sub == "rm":
        if ("r" in short or "R" in short or "f" in short) and "cached" not in long_:
            ctx.add("git-rm", "git rm -r")
    elif sub == "config":
        _git_config(ctx, short, long_, tg)
    elif sub == "remote":
        if tg and tg[0] in ("add", "set-url", "rename", "remove", "rm"):
            if any(_rx("url_cred").search(t) for t in tg):
                ctx.add("git-url-cred", "a password or token inside the address")
            else:
                ctx.add("git-remote", "git remote " + tg[0])
    elif sub == "init":
        _git_init(ctx, tg)
    elif sub == "add":
        _git_add(ctx, short, long_, tg)
    elif sub in ("clone", "fetch", "pull"):
        if any(_rx("url_cred").search(t) for t in sa):
            ctx.add("git-url-cred", "a password or token inside the address")


def _git_push(ctx: Ctx, c: Cmd, sa: List[str], short: Set[str], long_: Set[str], tg: List[str]) -> None:
    force = "f" in short or "force" in long_
    lease = any(l.startswith("force-with-lease") for l in long_)
    refs = tg[1:] if len(tg) > 1 else []
    plus = any(t.startswith("+") for t in tg)
    mirror = "mirror" in long_
    delete = "d" in short or "delete" in long_ or "prune" in long_ or any(t.startswith(":") and len(t) > 1 for t in tg)
    dsts = []
    for r in refs:
        r = r.lstrip("+")
        dsts.append(r.split(":")[-1] if ":" in r else r)
    prot_rx = _rx("protected_branch")
    prot = any(prot_rx.match(d) for d in dsts)
    if not dsts and lease:
        prot = bool(prot_rx.match(_git_branch_now(ctx)))
    if mirror:
        ctx.add("git-push-mirror", "git push --mirror")
    if force or plus:
        ctx.add("git-force", "git push --force")
    elif lease:
        ctx.add("git-force-lease-main" if prot else "git-force-lease", "git push --force-with-lease", BLOCK if prot else ASK)
    if delete:
        names = [d.lstrip(":") for d in dsts] + [t.lstrip(":") for t in tg[1:]]
        if any(prot_rx.match(x) for x in names):
            ctx.add("git-branch-main", "deleting a protected branch on the remote")
        else:
            ctx.add("git-push-delete", "git push --delete")
    if "no-verify" in long_:
        ctx.add("git-no-verify", "git push --no-verify")
    if not (force or plus or lease or mirror or delete):
        ctx.add("git-push", "git push")
    if any(a.lower() in ("heroku", "dokku") for a in tg[:1]):
        ctx.add("publish", "git push " + tg[0])


def _git_branch(ctx: Ctx, short: Set[str], long_: Set[str], tg: List[str]) -> None:
    prot_rx = _rx("protected_branch")
    forced_delete = "D" in short or (("d" in short or "delete" in long_) and ("f" in short or "force" in long_))
    safe_delete = ("d" in short or "delete" in long_) and not forced_delete
    rename = "m" in short or "M" in short or "move" in long_
    force_move = "f" in short or "force" in long_
    if forced_delete or safe_delete:
        if any(prot_rx.match(x) for x in tg):
            ctx.add("git-branch-main", "deleting a protected branch")
        elif forced_delete:
            ctx.add("git-branch-D", "git branch -D")
        return
    if rename:
        if "M" in short and len(tg) >= 2 and prot_rx.match(tg[-1]):
            ctx.add("git-branch-D", "git branch -M onto " + short_text(tg[-1], 30))
        return
    if force_move and tg:
        ctx.add("git-branch-D", "git branch -f")


def _git_commit(ctx: Ctx, short: Set[str], long_: Set[str], tg: List[str]) -> None:
    if "amend" in long_:
        remote = False
        try:
            from . import gitq
            remote = bool(gitq.has_remote(ctx.vcwd))
        except Exception:  # noqa: BLE001
            remote = True
        ctx.add("git-amend", "git commit --amend", ASK if remote else WARN)
    if "no-verify" in long_ or "n" in short:
        ctx.add("git-no-verify", "git commit --no-verify")
    if ctx.mode == "command" and not ctx.shared.get("commit_checked") and "commit-default-branch" not in _QUIET:
        ctx.shared["commit_checked"] = True
        try:
            from . import gitq
            if gitq.has_remote(ctx.vcwd):
                now = gitq.branch(ctx.vcwd)
                if now and now == gitq.default_branch(ctx.vcwd):
                    ctx.add("commit-default-branch", "committing on " + short_text(now, 30))
        except Exception as exc:  # noqa: BLE001
            _note("commit check", exc)                     # an optional heads-up: a git problem is not a reason to stop


def _git_config(ctx: Ctx, short: Set[str], long_: Set[str], tg: List[str]) -> None:
    if long_ & {"unset", "unset-all"} and tg and tg[0].lower() == "core.hookspath":
        ctx.add("git-no-verify", "git config --unset core.hooksPath")
    reading = bool(long_ & {"get", "get-all", "list", "get-regexp", "get-urlmatch", "unset", "unset-all"}) or \
        "l" in short or "list" in long_
    if reading or not tg:
        return
    key = tg[0]
    value = tg[1] if len(tg) > 1 else ""
    _config_exec(ctx, key, value, False)
    if key.lower() == "credential.helper":
        return
    if ("global" in long_ or "system" in long_) and len(tg) >= 2:
        ctx.add("git-config-global", "git config --" + ("global" if "global" in long_ else "system") + " " + short_text(key, 40))


def _git_init(ctx: Ctx, tg: List[str]) -> None:
    target = tg[0] if tg else ""
    base = _abs(target, ctx.vcwd) if target else _abs(ctx.vcwd)
    h = _abs(_home())
    if h and base in (h, h + "/desktop", h + "/documents", h + "/downloads", h + "/onedrive", h + "/onedrive/desktop",
                      h + "/onedrive/documents", h + "/onedrive/downloads") or re.match(r"^(?:[a-z]:)?/?$", base):
        ctx.add("git-init-home", short_text(target or ".", 40))
    elif ctx.wide and _abs(ctx.vcwd) == _root() and not target:
        ctx.add("wide-folder", ctx.wide)


def _git_add(ctx: Ctx, short: Set[str], long_: Set[str], tg: List[str]) -> None:
    everything = ("A" in short or "all" in long_ or any(t in (".", "./", "*", ":/", ":/*") for t in tg))
    if not everything:
        return
    if ctx.wide:
        ctx.add("wide-folder", ctx.wide)
    if ctx.mode == "command":
        base = _abs(ctx.vcwd)
        if base == _root() and not os.path.exists(os.path.join(paths.project_root(), ".gitignore")):
            ctx.add("no-gitignore", "there is no .gitignore yet")


def gh_rules(ctx: Ctx, c: Cmd) -> None:
    a = [x.lower() for x in c.vals()]
    joined = " ".join(a)
    if a[:2] == ["repo", "delete"]:
        ctx.add("gh-repo-delete", "gh repo delete")
    elif a[:2] == ["auth", "token"] or (a[:2] == ["auth", "status"] and ("-t" in a or "--show-token" in a)) or "--show-token" in a:
        ctx.add("gh-token", "gh auth token")
    elif a[:2] == ["repo", "edit"] and re.search(r"--visibility[= ]+public", joined):
        ctx.add("gh-visibility", "gh repo edit --visibility public")
    elif a[:2] in (["repo", "create"], ["repo", "fork"]) and ("--public" in a or re.search(r"--visibility[= ]+public", joined)):
        ctx.add("gh-visibility", "gh repo " + a[1] + " --public")
    elif a[:1] == ["secret"] and len(a) > 1 and a[1] in ("set", "delete", "remove"):
        ctx.add("gh-secret", "gh secret " + a[1])
    elif a[:1] == ["api"]:
        if re.search(r"(?:-x|--method)[= ]*(?:delete|put|patch|post)", joined):
            ctx.add("gh-api-write", "gh api with a write method")
    elif a[:2] == ["gist", "create"]:
        ctx.add("gh-gist", "gh gist create" + (" --public" if "--public" in a else ""))
    elif a[:2] in (["release", "create"], ["release", "delete"]):
        ctx.add("publish", "gh release " + a[1])


# --------------------------------------------------------------------------- packages

_PKG_VERBS = {
    "npm": {"install", "i", "add", "in", "ins"}, "pnpm": {"add", "install", "i"}, "yarn": {"add"}, "bun": {"add", "install", "i"},
    "pip": {"install"}, "pip3": {"install"}, "uv": {"add"}, "poetry": {"add"}, "cargo": {"add", "install"},
    "gem": {"install"}, "composer": {"require"}, "go": {"get", "install"}, "dotnet": {"add"}, "pipx": {"install"},
    "conda": {"install"},
    "choco": {"install"}, "winget": {"install"}, "scoop": {"install"},
}
_SYSTEM_PKG = frozenset(["brew", "apt", "apt-get", "dnf", "yum", "pacman", "zypper", "apk", "snap"])
_RUNNERS = frozenset(["npx", "bunx", "uvx", "dlx"])
_URL_SPEC = re.compile(r"(?i)^(?:https?://|git\+|git://|ssh://|github:|gitlab:|bitbucket:|file:|\S+\.tgz$|\S+\.whl$|\S+\.zip$|[\w.-]+/[\w.-]+#)")


def _project_deps(ctx: Ctx) -> Set[str]:
    deps = ctx.shared.get("deps")
    if deps is not None:
        return deps
    deps = set()
    ctx.shared["deps"] = deps
    try:
        base = paths.project_root()
        text = fsio.read_text(os.path.join(base, "package.json"), "", SCRIPT_MAX_BYTES)
        if text:
            data = json.loads(text)
            for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
                if isinstance(data.get(key), dict):
                    deps.update(str(k).lower() for k in data[key])
        for name in ("requirements.txt", "requirements-dev.txt"):
            for line in fsio.read_text(os.path.join(base, name), "", SCRIPT_MAX_BYTES).split("\n"):
                m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]{0,80})", line)
                if m:
                    deps.add(m.group(1).lower().replace("_", "-"))
        text = fsio.read_text(os.path.join(base, "pyproject.toml"), "", SCRIPT_MAX_BYTES)
        for m in re.finditer(r"(?m)^\s*[\"']?([A-Za-z0-9][A-Za-z0-9._-]{0,80})[\"']?\s*(?:[=<>~!]|\[|\s*,)", text):
            deps.add(m.group(1).lower().replace("_", "-"))
    except Exception as exc:  # noqa: BLE001
        _note("dependency list", exc)
    return deps


def pkg_rules(ctx: Ctx, c: Cmd) -> None:
    prog = c.prog
    vals = c.vals()
    if prog in ("python", "python3", "py") and vals[:2] == ["-m", "pip"]:
        vals = vals[2:]
        prog = "pip"
    elif prog == "uv" and vals[:1] == ["pip"]:
        vals = vals[1:]
        prog = "pip"
    elif prog == "python3" or prog == "python":
        return
    sudo = "sudo" in c.wrappers
    # runners: npx, bunx, uvx, pnpm dlx, yarn dlx, pipx run, npm exec, npm create / init <initializer>
    runner_args: Optional[List[str]] = None
    if prog in _RUNNERS:
        runner_args = vals
    elif prog in ("pnpm", "yarn") and vals[:1] in (["dlx"], ["create"]):
        runner_args = (["create-" + vals[1]] + vals[2:]) if vals[:1] == ["create"] and len(vals) > 1 else vals[1:]
    elif prog in ("npm", "bun") and vals[:1] in (["create"], ["init"], ["exec"]) and len(vals) > 1:
        runner_args = (["create-" + vals[1]] + vals[2:]) if vals[0] in ("create", "init") else vals[1:]
    elif prog == "pipx" and vals[:1] == ["run"]:
        runner_args = vals[1:]
    if runner_args is not None:
        short, long_, tg = split_flags([a for a in runner_args if a != "--"])
        if "no-install" in long_ or not tg:
            return
        name = tg[0]
        base = re.sub(r"@[\w.^~<>=*-]*$", "", name) if not name.startswith("@") else name
        if _URL_SPEC.match(name):
            ctx.add("pkg-url", short_text(name, 50))
        elif _rx("known_runner").match(name) or base.lower() in _project_deps(ctx) or name.startswith("./") or name.startswith("."):
            return
        else:
            ctx.add("pkg-run", short_text(name, 50))
        return
    if prog in ("npm", "pnpm", "yarn") and len(vals) >= 3 and vals[0] == "config" and vals[1] in ("set", "add") \
            and "registry" in vals[2].lower():
        ctx.add("pkg-index", "npm config set registry")          # a package source other than the default
        return
    verbs = _PKG_VERBS.get(prog)
    if prog in _SYSTEM_PKG:
        if vals[:1] and vals[0] in ("install", "add", "-S") and sudo:
            ctx.add("sudo", prog + " install")
        return
    if verbs is None or not vals or vals[0] not in verbs:
        return
    sub, rest = vals[0], vals[1:]
    short, long_, tg = split_flags(rest)
    if sudo:
        ctx.add("pkg-sudo", "sudo " + prog)
        return
    if "break-system-packages" in long_:
        ctx.add("pkg-break", "--break-system-packages")
        return
    if long_ & {"index-url", "extra-index-url", "trusted-host", "registry", "find-links", "proxy"} or (prog.startswith("pip") and "i" in short):
        ctx.add("pkg-index", "a package source other than the default")
    names = [t for t in tg if not t.startswith("-")]
    if prog.startswith("pip"):
        if "r" in short or "requirement" in long_ or "c" in short or "constraint" in long_:
            names = [t for t in names if not t.endswith(".txt")]
        names = [t for t in names if not re.match(r"^(?:\.|\.\.|\./.*|\.\./.*)$", t)]
        if "e" in short:
            names = [t for t in names if not t.startswith(".")]
    if any(_URL_SPEC.match(t) for t in names):
        ctx.add("pkg-url", "installing from a web address")
        return
    if (("g" in short or "global" in long_) and prog in ("npm", "pnpm", "yarn", "bun")) or (prog in ("cargo", "go") and sub == "install"):
        ctx.add("pkg-global", short_text(" ".join([prog] + vals), 60))
        return
    if prog == "cargo" and sub == "install":
        return
    deps = _project_deps(ctx)
    new = []
    for t in names:
        bare = re.sub(r"(?:@|==|>=|<=|~=|\^)[\w.^~<>=*-]*$", "", t) if not t.startswith("@") else re.sub(r"(?<=.)@[\w.^~<>=*-]*$", "", t)
        bare = bare.lower().replace("_", "-")
        if _rx("pip_skip").match(bare) or t.startswith(("./", "../", "/")) or not _rx("package_name").match(bare):
            continue
        if bare not in deps:
            new.append(bare)
    if new:
        ctx.add("pkg-add", short_text(", ".join(new[:4]), 60))


# --------------------------------------------------------------------------- secrets, environment, data leaving

def _secret_token(t: str) -> bool:
    """Does a command word name a secret file or a folder of secrets? (the safe exceptions are inside is_secret_filename)"""
    if not t or len(t) > 400:
        return False
    s = re.sub(r"(?i)^(?:\$\{home\}|\$home|\$env:userprofile|\$env:home|%userprofile%|%homepath%)(?=[\\/]|$)", "~", t)
    if s.startswith("@"):
        s = s[1:]
    if "=@" in s:
        s = s.split("=@", 1)[1]
    elif "=" in s and not s.startswith("-") and "/" not in s.split("=", 1)[0]:
        s = s.split("=", 1)[1] or s
    if "@" in s and ":" in s.split("@", 1)[1][:80]:
        s = s.split("@", 1)[1]
    s = re.sub(r"^(?:\$\{?[A-Za-z_][A-Za-z0-9_]{0,40}\}?|%[A-Za-z_][A-Za-z0-9_]{0,40}%)[\\/](?=.)", "", s)
    s = s.rstrip("/\\")
    if _secrets.is_secret_filename(s):
        return True
    return bool(_rx("sensitive_dir_name").search(_norm(s)))


_PATTERN_VALUE_FLAGS = frozenset(["-e", "--regexp", "-f", "--file", "--expression", "-m", "--max-count", "-A", "-B", "-C", "--after-context",
                                  "--before-context", "--context", "--include", "--exclude", "--exclude-dir", "-g", "--glob", "-t",
                                  "--type", "-T"])
_PATTERN_GIVEN = frozenset(["-e", "--regexp", "-f", "--file", "--expression"])
_OTHER_VALUE_FLAGS = {
    "head": ("-n", "-c", "--lines", "--bytes"), "tail": ("-n", "-c", "--lines", "--bytes"),
    "sort": ("-o", "-k", "-t", "-T", "-S"), "cut": ("-d", "-f", "-c", "-b"),
    "ssh": ("-i", "-F", "-J", "-o", "-p", "-l", "-L", "-R", "-D", "-b", "-c", "-E", "-e", "-m", "-O", "-Q", "-S", "-W", "-w"),
    "scp": ("-i", "-F", "-J", "-o", "-P", "-l", "-S", "-c"), "sftp": ("-i", "-F", "-J", "-o", "-P", "-l", "-S", "-c", "-b"),
    "rsync": ("-e", "--rsh", "-i"),
    "curl": ("--cert", "-E", "--key", "--cacert", "--capath", "-K", "--config", "-x", "--proxy", "-H", "--header", "-A", "--user-agent",
             "-u", "--user", "-X", "--request", "-w", "--write-out", "-m", "--max-time", "-o", "--output", "-b", "--cookie", "-c",
             "--cookie-jar", "-e", "--referer"),
}


def _positional(c: Cmd) -> List[str]:
    """The words of a command that can be files: options and their values are dropped; for grep, sed and awk the
    pattern or script word is dropped too (it is text, not a file)."""
    vals = c.vals()
    if c.prog in ("select-string", "sls") and c.kind == PS:
        named, pos = ps_params(vals, {"pattern": True, "path": True, "literalpath": True, "inputobject": True, "include": True,
                                      "exclude": True, "context": True, "encoding": True, "simplematch": False, "casesensitive": False,
                                      "quiet": False, "list": False, "notmatch": False, "allmatches": False, "raw": False})
        files = _split_targets([str(named[k]) for k in ("path", "literalpath") if k in named and named[k] is not True])
        return files + (pos if "pattern" in named else pos[1:])
    first_pattern = c.prog in _PATTERN_FIRST
    value_flags = _PATTERN_VALUE_FLAGS if first_pattern else frozenset(_OTHER_VALUE_FLAGS.get(c.prog, ()))
    pos: List[str] = []
    skip = False
    pattern_given = False
    for v in vals:
        if skip:
            skip = False
            continue
        if v in value_flags:
            skip = True
            if v in _PATTERN_GIVEN:
                pattern_given = True
            continue
        if v.startswith("-") and len(v) > 1:
            continue
        pos.append(v)
    if first_pattern and not pattern_given and pos:
        pos = pos[1:]
    return pos


def _is_silent_grep(c: Cmd) -> bool:
    if c.prog not in ("grep", "egrep", "fgrep", "rg", "findstr", "select-string", "sls", "ag", "ack"):
        return False
    short, long_, _ = split_flags(c.vals())
    return bool(short & {"q", "c", "l", "L"}) or bool(long_ & {"quiet", "count", "files-with-matches", "files-without-match", "silent"}) \
        or any(a.lower() in ("-quiet", "-list") for a in c.vals())


def _visible(ctx: Ctx, cmds: List[Cmd], idx: int) -> str:
    """What happens to the output of command idx of a pipeline: 'visible' (it reaches the model), 'silent'
    (only a count, a hash or nothing), 'sent' (a sender gets it) or 'file' (written to a file)."""
    if ctx.hidden:
        return "silent"
    for j in range(idx, len(cmds)):
        cj = cmds[j]
        if cj.prog in _SENDERS:
            return "sent"
        if cj.prog in ("set-content", "out-file", "add-content", "export-csv", "export-clixml", "clear-content") and j > idx:
            return "file"
        if any(op in (">", ">>", ">|", "&>", "&>>") and t.v not in ("/dev/null", "nul", "NUL", "$null") for op, t in cj.seg.redirs):
            return "file"
    last = cmds[-1]
    if last.prog in _SILENT_SINKS or _is_silent_grep(last):
        return "silent"
    if any(t.v in ("/dev/null", "nul", "NUL", "$null") for _, t in last.seg.redirs) and any(op.startswith(">") or op.startswith("&>") for op, _ in last.seg.redirs):
        return "silent"
    if last.prog in ("out-null",):
        return "silent"
    return "visible"


def _lists_secret(c: Cmd) -> bool:
    """find -name .env or Get-ChildItem -Filter .env: a listing that names a secret file (its names reach the next reader)."""
    vals = c.vals()
    if c.prog == "find":
        return any(_secret_token(vals[k + 1]) for k, v in enumerate(vals[:-1]) if v.lower() in ("-name", "-iname", "-path", "-ipath"))
    if c.prog == "get-childitem":
        named, pos = ps_params(vals, {"path": True, "literalpath": True, "filter": True, "include": True, "exclude": True,
                                      "recurse": False, "force": False, "name": False, "directory": False, "file": False,
                                      "depth": True})
        words = pos + [str(named[k]) for k in ("path", "literalpath", "filter", "include") if k in named and named[k] is not True]
        return any(_secret_token(w) for w in words)
    return False


def secret_flow_rules(ctx: Ctx, pipe: List[Seg], cmds: List[Cmd]) -> None:
    """Secret files and secret variables: reading them into the conversation or sending them out (one pipeline)."""
    for i, c in enumerate(cmds):
        prog = c.prog
        if prog in ("git", "gh") or prog in _TEXT_PROGS:
            continue
        looped = _interp(prog) in ("perl", "ruby") and any(re.match(r"^-[A-Za-z]*[np]", v) for v in c.vals())
        if (_interp(prog) or prog in _PS_PROGS or prog in _SHELL_PROGS) and not looped:       # perl -ne print .env reads
            continue                                          # their file words are script arguments (code is read by code_rules)
        files = [t for t in _positional(c) if _secret_token(t)] if prog else []
        for t in (c.vals() if prog else []):                  # curl -d @.env  /  -F file=@id_rsa  /  --post-file=.env
            if t in files:
                continue
            if t.startswith("--") and "=" in t:
                if prog in _SENDERS and _secret_token(t.split("=", 1)[1]):
                    files.append(t.split("=", 1)[1])
                continue
            if t.startswith("-"):
                continue
            if ("@" in t and _secret_token(t)) and prog in _SENDERS:
                files.append(t)
        redir_in = [t.v for op, t in c.seg.redirs if op == "<" and _secret_token(t.v)]
        if not files and not redir_in:
            if prog in _READERS and _visible(ctx, cmds, i) == "visible" and not _is_silent_grep(c) and \
                    any(_lists_secret(cmds[j]) for j in range(i)):
                ctx.add("read-secret", "a secret file name from the listing before the pipe")
            continue
        sender_here = prog in _SENDERS
        sender_after = ctx.sender_parent or any(cmds[j].prog in _SENDERS for j in range(i, len(cmds)))
        what = short_text((files or redir_in)[0], 40)
        if sender_here or sender_after:
            ctx.add("exfil-secret", what)
            continue
        flow = _visible(ctx, cmds, i)
        if prog in _READERS or redir_in:
            if _is_silent_grep(c) and not redir_in:
                continue
            if flow == "visible":
                ctx.add("read-secret", what)
            elif flow == "file":
                dests = [t.v for cj in cmds[i:] for op, t in cj.seg.redirs if op in (">", ">>", ">|", "&>")]
                if dests and not any(_secrets.is_secret_filename(d) for d in dests):
                    ctx.add("copy-secret", what)
        elif prog == "dd" and not any(v.startswith("of=") for v in c.vals()):
            if flow == "visible":                              # dd if=.env prints the file
                ctx.add("read-secret", what)
        elif prog in ("cp", "mv", "copy", "copy-item", "move-item", "ln", "xcopy", "robocopy", "install"):
            pos = [t for t in c.vals() if not t.startswith("-") and not re.match(r"^/[A-Za-z]$", t)]
            if len(pos) >= 2 and _secret_token(pos[0]) and not _secret_token(pos[-1]):
                ctx.add("copy-secret", what)
        elif prog in ("tar", "zip", "7z", "7za", "gzip", "bzip2", "xz", "compress-archive"):
            if i < len(cmds) - 1 and flow == "visible":
                ctx.add("read-secret", what)                      # tar czf - .env | base64
            elif flow != "silent":
                ctx.add("copy-secret", what)                      # an archive holds a copy that no .gitignore rule covers


def text_prog_rules(ctx: Ctx, c: Cmd, cmds: List[Cmd], idx: int) -> None:
    """echo / printf / Write-Host with a secret variable: it would print the secret."""
    for t in c.args:
        v = t.v
        for m in re.finditer(r"\$env:([A-Za-z_][A-Za-z0-9_]{0,60})|\$\{?([A-Za-z_][A-Za-z0-9_]{0,60})\}?|%([A-Za-z_][A-Za-z0-9_]{0,60})%", v):
            name = m.group(1) or m.group(2) or m.group(3) or ""
            if _rx("secret_word").search(name) and _visible(ctx, cmds, idx) == "visible":
                ctx.add("read-secret", "$" + name)
                return


def env_dump_rules(ctx: Ctx, c: Cmd, cmds: List[Cmd], idx: int) -> None:
    prog = c.prog
    vals = c.vals()
    dump = False
    named_var = ""
    if prog == "env" or (prog == "printenv" and not [v for v in vals if not v.startswith("-")]):
        dump = not [v for v in vals if not v.startswith("-")] if prog == "printenv" else (not vals and not c.envs)
    elif prog == "printenv":
        named_var = [v for v in vals if not v.startswith("-")][0]
    elif prog == "export" and vals[:1] in (["-p"],):
        dump = True
    elif prog == "declare" and vals[:1] in (["-x"], ["-p"], ["-xp"], ["-px"]):
        dump = True
    elif prog == "set" and not vals and c.kind in (SH, CMD):
        dump = True
    elif prog in ("get-childitem", "get-item"):
        for v in vals:
            m = re.match(r"(?i)^(?:-path:?)?env:(.*)$", v.strip("\"'"))
            if m:
                named_var = m.group(1).strip("*") if m.group(1) not in ("", "*") else ""
                dump = not named_var
    if named_var and _rx("secret_word").search(named_var):
        if _visible(ctx, cmds, idx) == "visible":
            ctx.add("read-secret", "$" + named_var)
        return
    if not dump:
        return
    # a filter that keeps only harmless names is fine
    for j in range(idx + 1, len(cmds)):
        nxt = cmds[j]
        if nxt.prog in ("grep", "egrep", "fgrep", "rg", "findstr", "select-string", "sls", "where-object", "where", "?"):
            if _is_silent_grep(nxt):
                return
            pattern = " ".join(v for v in nxt.vals() if not v.startswith("-"))
            if pattern and not _rx("secret_word").search(pattern):
                return
            ctx.add("env-dump", "environment variables with secret-looking names")
            return
        if nxt.prog in _SILENT_SINKS:
            return
        if nxt.prog in ("select-object", "select", "sort-object", "sort", "foreach-object") and any(
                v.lower() == "name" for v in nxt.vals()) and not any(v.lower() in ("value", "*") for v in nxt.vals()):
            return                                            # only the names of the variables, not their values
    if _visible(ctx, cmds, idx) == "visible":
        ctx.add("env-dump", "all environment variables")


def env_assignment_rules(ctx: Ctx, name: str, value: str) -> None:
    n = name.strip()
    if n.lower().startswith("env:"):
        n = n[4:]
    up = n.upper()
    if up in _ENV_REDIRECT_NAMES and value.strip().strip("\"'"):
        ctx.add("env-redirect", short_text(n, 40))
        return
    if up == "NODE_OPTIONS":
        if _NODE_CODE_OPTS.search(" " + value):
            ctx.add("env-exec", "NODE_OPTIONS loads code")
        return
    if up in _ENV_EXEC_NAMES or up.startswith("DYLD_") or up.startswith("NPM_CONFIG_") or re.match(r"^PIP_[A-Z_]{0,30}INDEX_URL$", up):
        ctx.add("env-exec", short_text(n, 40))
        return
    if up == "PATH":
        for entry in re.split(r"[;:](?![\\/])", value.strip("\"'")):
            e = entry.strip()
            if e.startswith(("./", ".\\", "../", "..\\")) or e == ".":
                ctx.add("env-exec", "PATH starts with a relative folder")
                return


_GIT_ENV_PAIR = re.compile(r"'([^'=]{1,120})'='([^']{0,400})'|\b([A-Za-z][\w.-]{1,120})=(\S{1,400})")


def git_env_rules(ctx: Ctx, pairs: Sequence[Tuple[str, str]]) -> None:
    """Git settings given through the environment (GIT_CONFIG_KEY_n with GIT_CONFIG_VALUE_n, GIT_CONFIG_PARAMETERS):
    judged like git -c, so an exec key such as core.fsmonitor is a block (guard-4)."""
    env: Dict[str, str] = {}
    for name, val in pairs:
        env[str(name).strip().upper()] = str(val or "").strip()
    for name in env:
        m = re.match(r"^GIT_CONFIG_KEY_(\d{1,3})$", name)
        if m:
            _config_exec(ctx, env[name], env.get("GIT_CONFIG_VALUE_" + m.group(1), ""), True)
    for m in _GIT_ENV_PAIR.finditer(env.get("GIT_CONFIG_PARAMETERS", "")):
        if m.group(1):
            _config_exec(ctx, m.group(1), m.group(2), True)
        else:
            _config_exec(ctx, m.group(3) or "", m.group(4) or "", True)


def env_command_rules(ctx: Ctx, c: Cmd) -> None:
    """export X=1 / declare -x X=1 / set X=1 / setx X 1 / Set-Item env:X."""
    vals = c.vals()
    if c.prog in ("export", "declare", "typeset", "readonly", "local"):
        pairs: List[Tuple[str, str]] = []
        for v in vals:
            if "=" in v and not v.startswith("-"):
                nm, _, val = v.partition("=")
                env_assignment_rules(ctx, nm.rstrip("+"), val)
                pairs.append((nm.rstrip("+"), val))
        git_env_rules(ctx, pairs)
    elif c.prog == "set" and c.kind == CMD and vals:
        text = " ".join(vals)
        if "=" in text:
            nm, _, val = text.partition("=")
            env_assignment_rules(ctx, nm.strip(), val)
    elif c.prog == "setx" and len(vals) >= 2:
        env_assignment_rules(ctx, vals[0], vals[1])
    elif c.prog in ("set-item", "new-item") and vals and re.match(r"(?i)^(?:-path:?)?env:", vals[0]):
        nm = re.sub(r"(?i)^(?:-path:?)?env:", "", vals[0])
        env_assignment_rules(ctx, nm, vals[1] if len(vals) > 1 else "")


# --------------------------------------------------------------------------- writing files from the shell

_WRITE_VERBS = {
    "tee": "write", "set-content": "write", "add-content": "write", "out-file": "write", "clear-content": "write",
    "new-item": "write", "touch": "write", "truncate": "write", "install": "write",
    "rm": "delete", "del": "delete", "erase": "delete", "remove-item": "delete", "rd": "delete", "rmdir": "delete",
    "unlink": "delete", "shred": "delete", "mv": "move", "move": "move", "move-item": "move", "rename-item": "move",
    "cp": "write", "copy": "write", "copy-item": "write", "ln": "write", "dd": "write",
}


_NET_WRITE = re.compile(r"(?i)^\[(?:system\.)?io\.(?:file|directory)\]::(writealltext|writeallbytes|writealllines|"
                        r"appendalltext|appendalllines|create|createtext|openwrite|open|delete|move|copy|replace)$")
_NET_READ = re.compile(r"(?i)^\[(?:system\.)?io\.(?:file|directory)\]::(?:readall\w{0,12}|opentext|openread)$")
_PS_STR = re.compile(r"'((?:[^'\n]|'')*)'|\"([^\"\n]*)\"")


def _net_call(c: Cmd) -> str:
    """The .NET static call of a PowerShell statement, lower case ([io.file]::readalltext), or ''. The guard reads
    the call word with its (...) part, so the program name is empty for these."""
    if c.kind != PS or not c.seg.toks:
        return ""
    m = re.match(r"(?i)^(\[(?:system\.)?io\.(?:file|directory)\]::\w{1,30})", c.seg.toks[0].v)
    return m.group(1).lower() if m else ""


def _ps_literals(c: Cmd) -> List[str]:
    """The string literals inside the PowerShell parts of a command (the first 2000 characters of each)."""
    out: List[str] = []
    for kind, text in c.seg.nested:
        if kind == PS:
            for m in _PS_STR.finditer(text[:2000]):
                s = m.group(1) if m.group(1) is not None else (m.group(2) or "")
                out.append(s.replace("''", "'"))
    return out


def _write_targets(c: Cmd) -> List[Tuple[str, str]]:
    """(path word, verb) for every file this command writes, deletes or moves."""
    out: List[Tuple[str, str]] = []
    for op, t in c.seg.redirs:
        if op in (">", ">>", ">|", "&>", "&>>"):
            out.append((t.v, "write"))
    prog = c.prog
    vals = c.vals()
    short, long_, tg = split_flags(vals)
    net = _net_call(c)
    if net and _NET_WRITE.match(net):                        # [IO.File]::WriteAllText('x', ...) and the like
        lits = [s for s in _ps_literals(c) if s]
        meth = net.rsplit("::", 1)[-1]
        if meth == "delete" and lits:
            out.append((lits[0], "delete"))
        elif meth == "move":
            out.extend((s, "move") for s in lits[:2])
        elif meth in ("copy", "replace") and len(lits) >= 2:
            out.append((lits[1], "write"))
        elif lits:
            out.append((lits[0], "write"))
    if prog in ("sed", "perl", "ruby") and ("i" in short or "in-place" in long_ or any(v.startswith("-i") for v in vals)):
        files = [v for v in tg][1:] if prog == "sed" and tg else tg
        out.extend((f, "write") for f in files)
    elif prog == "dd":
        out.extend((v[3:], "write") for v in vals if v.startswith("of="))
    elif prog in ("cp", "copy", "copy-item", "ln", "install", "mv", "move", "move-item", "rename-item", "robocopy", "xcopy", "rsync"):
        pos = [v for v in tg if not re.match(r"^/[A-Za-z]$", v)]
        if prog in ("cp", "copy", "copy-item", "ln", "install", "robocopy", "xcopy", "rsync") and len(pos) >= 2:
            out.append((pos[-1], "write"))
        elif prog in ("mv", "move", "move-item", "rename-item") and pos:
            out.extend((p, "move") for p in pos)
    elif prog in _WRITE_VERBS:
        verb = _WRITE_VERBS[prog]
        if c.kind == PS or prog in ("tee", "rm", "del", "erase", "rd", "rmdir", "unlink", "shred", "touch", "truncate"):
            named, pos = ps_params(vals, {"path": True, "literalpath": True, "filepath": True, "name": True, "value": True,
                                          "itemtype": True, "encoding": True, "recurse": False, "force": False}) \
                if c.kind == PS else ({}, tg)
            for k in ("path", "literalpath", "filepath", "name"):
                if k in named and named[k] is not True:
                    out.append((str(named[k]), verb))
            if c.kind == PS:
                if prog in ("set-content", "add-content", "out-file", "new-item", "clear-content"):
                    out.extend((p, verb) for p in pos[:1])
                else:
                    out.extend((p, verb) for p in pos)
            else:
                out.extend((p, verb) for p in pos)
    return [(p, v) for p, v in out if p and len(p) < 500]


def net_read_rules(ctx: Ctx, c: Cmd, cmds: List[Cmd], idx: int) -> None:
    """[IO.File]::ReadAllText('.env') and the like: a .NET read of a secret file whose text the output shows."""
    net = _net_call(c)
    if not net or not _NET_READ.match(net):
        return
    lits = _ps_literals(c)
    if lits and _secret_token(lits[0]) and _visible(ctx, cmds, idx) == "visible":
        ctx.add("read-secret", short_text(lits[0], 40))


def write_path_rules(ctx: Ctx, c: Cmd) -> None:
    targets = _write_targets(c)
    if not targets:
        return
    for word, verb in targets:
        if _norm(word).startswith(("/dev/tcp/", "/dev/udp/")):
            ctx.add("remote-xfer", "data written to a network socket")
            continue
        tags = path_tags(word, ctx.vcwd)
        if "hook-only" in tags:
            ctx.add("hook-only-path", short_text(_norm(word), 60))
        elif "config" in tags:
            ctx.add("config-write", short_text(_norm(word), 60))
        elif "memory-root" in tags and verb in ("delete", "move"):
            ctx.add("memory-wipe", short_text(_norm(word), 60))
        if _rx("profile_file").search(_norm(word)) or _rx("startup_folder").search(_norm(word).lower()):
            ctx.add("persistence", short_text(_norm(word), 60))
        if _rx("device_target").match(_norm(word)) and verb == "write":
            ctx.add("dd-device", short_text(_norm(word), 40))
        if ctx.wide and verb == "move" and c.prog in ("mv", "move", "move-item"):
            ctx.add("wide-folder", ctx.wide)


# --------------------------------------------------------------------------- program families

def family_rules(ctx: Ctx, c: Cmd) -> None:
    """Rules that read the command words as one line (docker, databases, cloud, publish, persistence ...).
    Never run for echo/printf: their words are text."""
    argline = " ".join([c.prog] + c.vals())
    if len(argline) > 4000:
        argline = argline[:4000]
    prog = c.prog
    if prog.startswith("[") and _rx("inline_delete").search(argline):
        ctx.add("inline-delete", short_text(argline, 50))      # [IO.Directory]::Delete(...)
    if _rx("lolbin").search(argline):
        ctx.add("lolbin-download", prog)
    if _rx("system_config").search(argline):
        ctx.add("system-config", short_text(argline, 50))
    elif prog == "set-executionpolicy":
        ctx.add("system-config", "execution policy", ASK)       # RemoteSigned is the usual fix, but it is a system setting
    if _rx("persistence").search(argline):
        ctx.add("persistence", short_text(argline, 50))
    if _rx("reg_write").search(argline):
        ctx.add("reg-write", short_text(argline, 50))
    if _rx("cred_store").search(argline):
        ctx.add("cred-store", prog)
    if _rx("tunnel").search(argline):
        ctx.add("tunnel", prog)
    if _rx("bind_all").search(argline) or (_rx("http_server").search(argline) and not _rx("bind_local").search(argline)):
        ctx.add("bind-all", short_text(argline, 50))
    if _rx("docker_danger").search(argline):
        ctx.add("docker-danger", short_text(argline, 50))
    if _rx("docker_prune").search(argline):
        ctx.add("docker-prune", short_text(argline, 50))
    if _rx("cloud_destroy").search(argline):
        ctx.add("cloud-destroy", short_text(argline, 50))
    if _rx("publish").search(argline) and not _rx("dry_run").search(argline):
        ctx.add("publish", short_text(argline, 50))
    if prog in _DB_CLIENTS or _rx("db_tools").search(argline):
        sql_text = argline + " " + " ".join(str(h[1] or "") for h in c.seg.heredocs)
        bad = _rx("db_tools").search(sql_text)
        if not bad and prog in _DB_CLIENTS:
            for m in _rx("db_sql").finditer(sql_text):
                chunk = m.group(0)
                if re.match(r"(?i)(?:delete\s+from|update)", chunk) and _rx("sql_where").search(sql_text[m.start():m.end() + 80]):
                    continue
                bad = m
                break
        if bad:
            ctx.add("db-destroy-prod" if _rx("db_prod").search(argline) else "db-destroy", short_text(bad.group(0), 40))
    # uploads: a local file sent to a server (not to this computer)
    if prog in ("curl", "wget", "invoke-webrequest", "invoke-restmethod") and (
            _rx("curl_upload").search(argline) or _rx("wget_post").search(argline) or _rx("ps_upload").search(argline)):
        urls = [v for v in c.vals() if _rx("url_any").match(v) or re.match(r"(?i)^(?:localhost|127\.|\[::1\])", v)]
        local = urls and all(_rx("url_local").match(u) for u in urls)
        if not local and (_rx("curl_upload").search(argline) or _rx("wget_post").search(argline) or "-infile" in argline.lower()):
            ctx.add("exfil-upload", "a local file goes to a server")


def sender_rules(ctx: Ctx, c: Cmd) -> None:
    """scp / sftp / ftp / nc / rsync to another computer."""
    prog = c.prog
    vals = c.vals()
    short, long_, tg = split_flags(vals)
    if prog in ("scp", "sftp", "ftp", "tftp", "nc", "ncat", "netcat", "socat", "telnet"):
        ctx.add("remote-xfer", prog)
    elif prog == "rsync":
        if any(":" in t and not re.match(r"^[A-Za-z]:[\\/]", t) and "/" not in t.split(":", 1)[0] for t in tg):
            ctx.add("remote-xfer", "rsync to another computer")
    elif prog == "ssh" and len(_positional(c)) >= 2:
        ctx.add("remote-xfer", "ssh with a command")


# --------------------------------------------------------------------------- code in other languages

_STR_LIT = re.compile(r"""'(?:[^'\\\n]|\\.){0,2000}'|"(?:[^"\\\n]|\\.){0,2000}"|`(?:[^`\\\n]|\\.){0,2000}`""")
_LIST_LIT = re.compile(r"""\[\s{0,4}(?:'[^'\n]{0,300}'|"[^"\n]{0,300}")(?:\s{0,4},\s{0,4}(?:'[^'\n]{0,300}'|"[^"\n]{0,300}")){1,14}\s{0,4}\]""")
_INTERP_FLAG = {"python": ("-c",), "node": ("-e", "-p", "--eval", "--print"), "ruby": ("-e",), "perl": ("-e", "-E"),
                "php": ("-r",), "deno": ("eval",), "bun": ("-e", "--eval")}


def _interp(prog: str) -> str:
    if re.fullmatch(r"python[0-9.]{0,5}w?|py", prog):
        return "python"
    if prog in ("nodejs", "node"):
        return "node"
    return prog if prog in _INTERP_FLAG else ""


def _literals(code: str, commands: bool = True) -> List[str]:
    out: List[str] = []
    for m in _LIST_LIT.finditer(code[:20000]):
        parts = [x[1:-1] for x in re.findall(r"""'[^'\n]{0,300}'|"[^"\n]{0,300}\"""", m.group(0))]
        if parts:
            out.append(" ".join(parts))
    for m in _STR_LIT.finditer(code[:20000]):
        s = m.group(0)[1:-1]
        s = s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")
        if len(s) >= 3 and (not commands or " " in s or "/" in s or "\\" in s):
            out.append(s)
        if len(out) >= MAX_LITERALS * 2:
            break
    seen: Set[str] = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s)
            uniq.append(s)
    return uniq[:MAX_LITERALS]


def code_rules(ctx: Ctx, code: str, lang: str) -> None:
    """One level of code from python -c, node -e, perl -e, ruby -e, php -r (or a script file in dangerous-call mode)."""
    code = code[:20000]
    if _rx("env_print_code").search(code):
        ctx.add("env-dump", "code that prints all environment variables")
    # recursive deletes
    for m in _rx("inline_delete").finditer(code):
        arg = re.match(r"""\s{0,3}\(?\s{0,3}(['"])([^'"\n]{0,200})\1""", code[m.end():m.end() + 260])
        if arg and (is_safe_artifact(arg.group(2)) and not is_danger_target(arg.group(2), ctx.vcwd)):
            continue
        if arg is None and ctx.mode != "command":
            continue                              # a script file: only literal paths count (no guess about variables)
        ctx.add("inline-delete", short_text(m.group(0), 40))
        break
    lits = _literals(code)
    # reading a secret file by name
    if _rx("read_call").search(code):
        for s in _literals(code, False)[:MAX_LITERALS]:
            if _secret_token(s) and " " not in s.strip():
                ctx.add("read-secret", short_text(s, 40))
                break
    # writing into protected paths or settings
    if re.search(r"(?i)\b(?:write|open|writeFile\w{0,8}|appendFile\w{0,8}|unlink|remove|rename|replace|rmtree|rmSync|truncate|echo|Set-Content)\b", code):
        for s in lits:
            if len(s) < 300 and " " not in s.strip():
                tags = path_tags(s, ctx.vcwd)
                if "hook-only" in tags:
                    ctx.add("hook-only-path", short_text(_norm(s), 60))
                elif "config" in tags:
                    ctx.add("config-write", short_text(_norm(s), 60))
        if _GUARD_OFF_KEYS.search(code):
            ctx.add("guard-off", "code that switches hooks or permissions off")
    # download and run inside the code: exec(urlopen(...).read()), fetch(...).then(eval)
    if ctx.mode == "command" and _rx("code_fetch").search(code) and _rx("code_exec").search(code):
        ctx.add("pipe-shell", "code downloads text and runs it")
    if ctx.mode == "command" and _rx("code_b64").search(code) and _rx("code_exec").search(code):
        ctx.add("obfuscated", "code decodes hidden text and runs it")
    # strings that are commands
    for s in lits:
        if ctx.depth + 1 <= MAX_DEPTH:
            nested_text(ctx, s, SH, "literal")
            if re.match(r"(?i)^\s*(?:rd|rmdir|del|erase|format|diskpart|reg|schtasks|netsh|bcdedit|cmd)\b", s):
                nested_text(ctx, s, CMD, "literal")           # Windows command lines inside os.system(...)


def interp_rules(ctx: Ctx, c: Cmd) -> None:
    lang = _interp(c.prog)
    if not lang:
        return
    vals = c.vals()
    flags = _INTERP_FLAG[lang]
    for k, v in enumerate(vals):
        if v in flags and k + 1 < len(vals):
            code_rules(ctx, vals[k + 1], lang)
            return
        if lang == "python" and re.match(r"^-[A-Za-z]*c$", v) and k + 1 < len(vals):
            code_rules(ctx, vals[k + 1], lang)
            return
        if lang == "deno" and k == 0 and v == "eval" and k + 1 < len(vals):
            code_rules(ctx, vals[k + 1], lang)
            return
    for rec in c.seg.heredocs:                               # python - <<EOF ... EOF
        if rec[1] and any(v == "-" for v in vals[:3]) or (rec[1] and not vals):
            code_rules(ctx, str(rec[1]), lang)


# --------------------------------------------------------------------------- nested shells

def nested_text(ctx: Ctx, text: str, kind: str, mode: Optional[str] = None, hidden: Optional[bool] = None,
                sender_parent: bool = False) -> None:
    if ctx.depth + 1 > MAX_DEPTH or not text or not text.strip() or len(text) > MAX_COMMAND_CHARS:
        return
    ch = ctx.child(kind, mode)
    ch.hidden = ctx.hidden if hidden is None else hidden
    ch.sender_parent = sender_parent or ctx.sender_parent
    run_text(ch, text)
    for f in ch.out:
        ctx.add(f["rule_id"], f["detail"], f["tier"])


def _shell_dash_c(vals: Sequence[str]) -> Optional[str]:
    for k, a in enumerate(vals):
        if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a) and k + 1 < len(vals):
            return vals[k + 1]
    return None


def nested_program_rules(ctx: Ctx, c: Cmd) -> None:
    """bash -c, powershell -Command, cmd /c, eval, wsl, Start-Process, iex 'text', xargs sh -c ..."""
    prog = c.prog
    vals = c.vals()
    if prog in ("su", "runuser", "script"):
        code = _shell_dash_c(vals)
        if code is not None:
            nested_text(ctx, code, SH)
    elif prog in _SHELL_PROGS:
        code = _shell_dash_c(vals)
        if code is not None:
            nested_text(ctx, code, SH)
        for rec in c.seg.heredocs:                           # bash <<< 'text' and bash <<EOF
            nested_text(ctx, str(rec[1] or ""), SH)
    elif prog in _PS_PROGS:
        k = 0
        code = None
        while k < len(vals):
            a = vals[k].lower()
            if re.match(r"^-(?:e|ec|en|enc|enco|encod|encode|encoded|encodedc\w{0,8})$", a) and k + 1 < len(vals):
                if len(vals[k + 1]) >= 8:
                    ctx.add("encoded-ps", "powershell -EncodedCommand")
                k += 2
                continue
            if re.match(r"^-(?:c|co|com|comm|comma|comman|command)$", a):
                code = " ".join(vals[k + 1:])
                break
            if a in ("-file", "-f") or a.startswith("-file"):
                break
            k += 1
        if code is None:
            pos = [v for v in vals if not v.startswith("-")]
            if pos and not any(v.lower() in ("-file", "-f") for v in vals):
                code = " ".join(pos)
        if code:
            nested_text(ctx, code, PS)
        for rec in c.seg.heredocs:
            nested_text(ctx, str(rec[1] or ""), PS)
    elif prog == "cmd":
        for k, a in enumerate(vals):
            if a.lower() in ("/c", "/k", "/r") and k + 1 < len(vals):
                nested_text(ctx, " ".join(vals[k + 1:]), CMD)
                break
    elif prog == "eval":
        nested_text(ctx, " ".join(vals), SH)
    elif prog == "wsl":
        rest = list(vals)
        out: List[str] = []
        k = 0
        while k < len(rest):
            a = rest[k]
            if a in ("-d", "--distribution", "-u", "--user", "--cd"):
                k += 2
                continue
            if a in ("-e", "--exec", "--", "-x"):
                k += 1
                continue
            if a.startswith("-") and not out:
                k += 1
                continue
            out = rest[k:]
            break
        if out:
            nested_text(ctx, _join_tokens(out), SH)
    elif prog == "start-process":
        named, pos = ps_params(vals, {"filepath": True, "argumentlist": True, "verb": True, "wait": False, "passthru": False,
                                      "nonewwindow": False, "workingdirectory": True, "windowstyle": True})
        exe = str(named.get("filepath", pos[0] if pos else ""))
        args = str(named.get("argumentlist", " ".join(pos[1:]))).replace(",", " ")
        if str(named.get("verb", "")).lower() == "runas":
            ctx.add("sudo", "Start-Process -Verb RunAs")
        if exe:
            en = _pname(exe)
            kind = PS if en in _PS_PROGS else CMD if en == "cmd" else SH
            nested_text(ctx, _join_tokens([exe]) + " " + args, kind)
    elif prog in ("invoke-expression",):
        pos = [v for v in vals if not v.startswith("-")]
        if len(pos) == 1 and not c.args[-1].dyn:
            nested_text(ctx, pos[0], PS)


# --------------------------------------------------------------------------- scripts the command runs

def _read_script(ctx: Ctx, path_word: str) -> Optional[str]:
    """The text of a script inside the project (<= 64 KB), or None."""
    try:
        if ctx.shared["scripts"] >= MAX_SCRIPTS:
            return None
        p = _abs(path_word, ctx.vcwd, False)
        root = _norm(paths.project_root())
        if not p or not _under(p.lower(), root.lower()):
            return None
        rel = p[len(root):].lstrip("/")
        if rel.lower().startswith((".claude/tools/", ".claude/hooks/")):
            return None                                      # the product's own files (checked by MANIFEST)
        if set(rel.lower().split("/")) & {"node_modules", ".venv", "venv", "site-packages", ".git", "__pycache__"}:
            return None                                      # third-party code and virtual environments (Activate.ps1 ...)
        real = os.path.join(paths.project_root(), rel) if rel else ""
        if not real or not os.path.isfile(real) or os.path.getsize(real) > SCRIPT_MAX_BYTES:
            return None
        ctx.shared["scripts"] += 1
        with open(real, "rb") as f:
            raw = f.read(SCRIPT_MAX_BYTES + 1)
        if b"\x00" in raw[:2000] and not (raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff")):
            return None                                      # a compiled program
        return fsio.read_text(real, "", SCRIPT_MAX_BYTES)
    except Exception:  # noqa: BLE001
        return None


def _package_scripts(ctx: Ctx, name: str) -> List[str]:
    base = _abs(ctx.vcwd)
    root = _root()
    folder = ctx.vcwd if _under(base, root) else paths.project_root()
    for cand in (os.path.join(folder, "package.json"), os.path.join(paths.project_root(), "package.json")):
        text = _read_script(ctx, cand)
        if text:
            try:
                data = json.loads(text)
                scripts = data.get("scripts") if isinstance(data, dict) else None
                if isinstance(scripts, dict):
                    return [str(scripts[k]) for k in ("pre" + name, name, "post" + name) if isinstance(scripts.get(k), str)]
            except ValueError:
                pass
            return []
    return []


def _makefile_lines(ctx: Ctx, target: str) -> List[str]:
    for name in ("Makefile", "makefile", "GNUmakefile"):
        text = _read_script(ctx, os.path.join(ctx.vcwd, name))
        if text is None:
            continue
        lines = text.split("\n")
        out: List[str] = []
        current = ""
        first = ""
        for ln in lines[:2000]:
            m = re.match(r"^([A-Za-z0-9_.-]{1,60})\s{0,3}:(?!=)", ln)
            if m:
                current = m.group(1)
                first = first or current
                continue
            if ln.startswith("\t") and current and current == (target or first):
                out.append(ln.strip().lstrip("@-+").strip())
        return out
    return []


def script_targets(c: Cmd, ctx: Ctx) -> List[Tuple[str, str]]:
    """What script files or named scripts this command runs: (kind, path or name)."""
    prog = c.prog
    vals = c.vals()
    short, long_, tg = split_flags(vals)
    out: List[Tuple[str, str]] = []
    raw = c.raw.replace("\\", "/")
    if re.search(r"(?i)\.(?:sh|bash|ps1|bat|cmd)$", raw) or (raw.startswith("./") and not re.search(r"\.(?:py|js|exe)$", raw)):
        ext = raw.rsplit(".", 1)[-1].lower() if "." in raw.rsplit("/", 1)[-1] else "sh"
        out.append(("ps" if ext == "ps1" else "cmd" if ext in ("bat", "cmd") else "sh", c.raw))
    if prog in _SHELL_PROGS and not _shell_dash_c(vals):
        pos = [t for t in tg if not t.startswith("-")]
        if pos and "s" not in short:
            out.append(("sh", pos[0]))
    elif prog in ("source", "."):
        pos = [t for t in tg if not t.startswith("-")]
        if pos:
            out.append(("ps" if pos[0].lower().endswith(".ps1") else "sh", pos[0]))
    elif _interp(prog) in ("python", "node") and not any(f in vals for f in ("-c", "-e", "-m", "-p", "--eval")):
        pos = [t for t in tg if not t.startswith("-")]
        if pos and re.search(r"(?i)\.(?:py|js|mjs|cjs|ts)$", pos[0]):
            out.append(("py" if pos[0].lower().endswith(".py") else "js", pos[0]))
    elif prog in _PS_PROGS:
        for k, a in enumerate(vals):
            if a.lower() in ("-file", "-f") and k + 1 < len(vals):
                out.append(("ps", vals[k + 1]))
    elif prog == "cmd":
        for k, a in enumerate(vals):
            if a.lower() in ("/c", "/k", "/r"):
                rest = [t for t in vals[k + 1:] if t.lower() != "call"]
                if rest and re.search(r"(?i)\.(?:bat|cmd)$", rest[0]):
                    out.append(("cmd", rest[0]))
                break
    elif prog in ("npm", "pnpm", "yarn", "bun") and vals:
        first = vals[0]
        if first in ("run", "run-script") and len(vals) > 1:
            out.append(("npm", vals[1]))
        elif first in ("test", "start", "stop", "restart", "t"):
            out.append(("npm", "test" if first == "t" else first))
        elif prog in ("yarn", "pnpm") and first not in (
                "install", "add", "remove", "dlx", "create", "exec", "init", "i", "up", "upgrade", "update", "why", "ls", "list",
                "info", "config", "cache", "link", "unlink", "pack", "publish", "audit", "outdated", "dedupe", "prune",
                "rebuild", "store", "env", "self-update", "set", "workspaces", "workspace", "global", "bin", "login", "logout") \
                and not first.startswith("-"):
            out.append(("npm", first))
    elif prog == "make":
        out.append(("make", tg[0] if tg else ""))
    return out[:4]


def script_rules(ctx: Ctx, c: Cmd) -> None:
    if ctx.depth >= MAX_DEPTH or ctx.mode == "literal":
        return
    for kind, ref in script_targets(c, ctx):
        found: List[str] = []
        where = short_text(ref, 40)
        if kind == "npm":
            lines = _package_scripts(ctx, ref)
            text = "\n".join(lines)
            if not text.strip():
                continue
            kinds = SH
            origin = "package.json script " + short_text(ref, 30)
        elif kind == "make":
            lines = _makefile_lines(ctx, ref)
            text = "\n".join(lines)
            if not text.strip():
                continue
            kinds = SH
            origin = "Makefile"
        else:
            text = _read_script(ctx, ref) or ""
            if not text.strip():
                continue
            kinds = {"sh": SH, "ps": PS, "cmd": CMD}.get(kind, SH)
            origin = where
        if kind in ("py", "js"):
            ch = ctx.child(SH, "script")
            code_rules(ch, text, kind)
            found = [f["rule_id"] for f in ch.out if f["tier"] != WARN]
        else:
            ch = ctx.child(kinds, "script")
            run_text(ch, text)
            found = [f["rule_id"] for f in ch.out if f["tier"] != WARN]
        if found:
            ctx.add("script-with-danger", origin + ": " + ", ".join(sorted(set(found))[:4]))


# --------------------------------------------------------------------------- one segment, one pipeline

def _has_download_signal(c: Cmd) -> bool:
    if c.prog in _DOWNLOADERS:
        return True
    for t in c.seg.toks:
        if re.search(r"(?i)downloadstring|downloaddata|downloadfile|net\.webclient", t.v):
            return True
    for _kind, text in c.seg.nested:
        if re.search(r"(?i)\b(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod|fetch)\b|webclient|downloadstring", text[:3000]):
            return True
    return False


def _stdin_sink(c: Cmd) -> bool:
    """A program that runs what it reads on stdin: sh, bash -s, iex, python -, powershell with no command."""
    prog = c.prog
    vals = c.vals()
    short, long_, tg = split_flags(vals)
    if prog in _SHELL_PROGS:
        if _shell_dash_c(vals) is not None:
            return False
        return "s" in short or not [t for t in tg if not t.startswith("-")]
    if prog in ("iex", "invoke-expression"):
        return True
    if prog in _PS_PROGS:
        return not any(v.lower() in ("-c", "-command", "-file", "-f", "-e", "-ec", "-enc", "-encodedcommand") for v in vals) \
            and not [t for t in tg if not t.startswith("-")]
    lang = _interp(prog)
    if lang in ("python", "node", "ruby", "perl", "php"):
        if any(f in vals for f in _INTERP_FLAG.get(lang, ())) or "-m" in vals:
            return False
        return not [t for t in tg if t != "-" and not t.startswith("-")]
    return False


def _download_targets(c: Cmd) -> Set[str]:
    out: Set[str] = set()
    vals = c.vals()
    urls = [v for v in vals if _rx("url_any").match(v)]
    if c.prog == "start-bitstransfer":                       # Start-BitsTransfer -Source url -Destination file
        named, _pos = ps_params(vals, {"source": True, "destination": True, "displayname": True, "priority": True,
                                       "transfertype": True, "tempdirectory": True, "credential": True,
                                       "authentication": True, "asynchronous": False})
        if isinstance(named.get("destination"), str) and named.get("destination"):
            out.add(_norm(named["destination"]).rsplit("/", 1)[-1].lower())
    for k, v in enumerate(vals):
        low = v.lower()
        nxt = vals[k + 1] if k + 1 < len(vals) else ""
        if c.prog == "curl" and (v == "-o" or low == "--output") and nxt:
            out.add(_norm(nxt).rsplit("/", 1)[-1].lower())
        elif c.prog == "curl" and (v == "-O" or low == "--remote-name" or (v.startswith("-") and not v.startswith("--") and "O" in v[1:])):
            out.update(_norm(u.split("?", 1)[0]).rsplit("/", 1)[-1].lower() for u in urls)
        elif c.prog == "wget" and (v in ("-O",) or low == "--output-document") and nxt and nxt != "-":
            out.add(_norm(nxt).rsplit("/", 1)[-1].lower())
        elif c.prog == "wget" and not any(x in ("-O", "--output-document") for x in vals):
            out.update(_norm(u.split("?", 1)[0]).rsplit("/", 1)[-1].lower() for u in urls)
        elif c.prog in ("invoke-webrequest", "invoke-restmethod") and re.match(r"(?i)^-o\w{0,6}$", v) and nxt:
            out.add(_norm(nxt).rsplit("/", 1)[-1].lower())
    for op, t in c.seg.redirs:
        if op in (">", ">>"):
            out.add(_norm(t.v).rsplit("/", 1)[-1].lower())
    if any(re.search(r"(?i)downloadfile", t.v) for t in c.seg.toks):       # (New-Object Net.WebClient).DownloadFile(url, file)
        for _k, text in c.seg.nested:
            m = re.search(r"""['"]\s{0,3},\s{0,3}['"]([^'"\n]{1,200})['"]\s{0,3}$""", text)
            if m:
                out.add(_norm(m.group(1)).rsplit("/", 1)[-1].lower())
    out.discard("")
    return out


def _runs_downloaded(c: Cmd, names: Set[str]) -> bool:
    if not names:
        return False
    base = _norm(c.raw).rsplit("/", 1)[-1].lower()
    if base in names and c.raw != c.prog.upper():
        if re.search(r"\.[A-Za-z0-9]{1,5}$", base) or c.raw.startswith(("./", ".\\")):
            return True
    runs = c.prog in _SHELL_PROGS or c.prog in ("source", ".", "sh", "iex", "start-process", "start", "invoke-item", "ii") \
        or c.prog in _PS_PROGS or _interp(c.prog) in ("python", "node", "ruby", "perl")
    if runs:
        for v in c.vals():
            if not v.startswith("-") and _norm(v).rsplit("/", 1)[-1].lower() in names:
                return True
    return False


def seg_rules(ctx: Ctx, pipe: List[Seg], cmds: List[Cmd], idx: int) -> None:
    c = cmds[idx]
    seg = c.seg
    prog = c.prog
    assign_like = c.assign or prog in ("export", "declare", "local", "readonly", "typeset", "set", "setx")
    vis = _visible(ctx, cmds, idx) if seg.nested else "visible"
    for kind, text in seg.nested:
        nested_text(ctx, text, kind, hidden=True if (assign_like or vis in ("silent", "file")) else None,
                    sender_parent=prog in _SENDERS or vis == "sent")
    for name, val, _dyn in c.envs:
        env_assignment_rules(ctx, name, val)
    git_env_rules(ctx, [(n, v) for n, v, _d in c.envs])
    if c.assign:
        return
    write_path_rules(ctx, c)
    net_read_rules(ctx, c, cmds, idx)
    if c.unresolved:
        ctx.add("unresolvable-program", "the program name comes from a variable or a substitution")
        return
    if not prog:
        if c.kind == PS:
            # a PowerShell statement that only prints a secret variable
            if len(seg.toks) == 1 and re.search(r"(?i)\$env:[A-Za-z_]{0,40}(?:KEY|TOKEN|SECRET|PASSW|CREDENTIAL|PRIVATE|AUTH)", seg.toks[0].v) \
                    and _visible(ctx, cmds, idx) == "visible":
                ctx.add("read-secret", short_text(seg.toks[0].v, 40))
            # [IO.Directory]::Delete(...) and [ScriptBlock]::Create(...)
            joined = " ".join(t.v for t in seg.toks)
            if _rx("inline_delete").search(joined):
                ctx.add("inline-delete", short_text(joined, 50))
        return
    if prog in ("cd", "chdir", "set-location", "pushd", "push-location"):
        arg = [t for t in c.args if not t.v.startswith("-")]
        ctx.vcwd = _abs(arg[0].v, ctx.vcwd, False) if arg and not arg[0].dyn else ctx.cwd
        return
    if prog in _TEXT_PROGS:
        text_prog_rules(ctx, c, cmds, idx)
        return
    kind = c.kind
    if prog == "rm":
        rm_rules(ctx, c)
    elif prog == "remove-item":
        ps_remove_rules(ctx, c, pipe, cmds, idx)
    elif prog in ("rd", "rmdir", "del", "erase") and kind == CMD:
        cmd_delete_rules(ctx, c)
    elif prog in ("rd", "rmdir", "del", "erase") and any(v.lower() == "/s" for v in c.vals()):
        ctx.add("win-delete", short_text(" ".join(c.vals())))   # cmd-style recursive delete typed into bash: ask
    elif prog == "find":
        find_rules(ctx, c)
    elif prog in ("robocopy", "rsync", "xcopy"):
        sync_rules(ctx, c)
    if prog in ("rmdir", "unlink", "rd", "del", "erase") and kind != CMD:
        # typed in a Bash shell: the outside-the-project rule (DENIZ-1, H1)
        _outside_only(ctx, [a.v for a in c.args if not a.v.startswith("-") and not re.match(r"^/[A-Za-z]$", a.v)])
    if prog == "git":
        git_rules(ctx, c)
    elif prog == "gh":
        gh_rules(ctx, c)
    elif prog == "git-filter-repo":                             # the hyphen form is the same history rewrite
        ctx.add("git-history", "git filter-repo")
    else:
        pkg_rules(ctx, c)
    misc_system_rules(ctx, c)
    env_command_rules(ctx, c)
    env_dump_rules(ctx, c, cmds, idx)
    sender_rules(ctx, c)
    if prog not in ("git", "gh"):
        family_rules(ctx, c)
    interp_rules(ctx, c)
    nested_program_rules(ctx, c)
    script_rules(ctx, c)


def _runs_substitution(c: Cmd) -> bool:
    """The text of a substitution becomes the code that runs: bash <(curl ..), sh -c "$(curl ..)", eval "$(..)",
    source <(..), iex (iwr ..), source /dev/stdin <<< "$(..)". (As an ordinary argument it is only data.)"""
    args = c.args
    prog = c.prog
    if c.seg.nested and any(rec[3] for rec in c.seg.heredocs) and (prog in _SHELL_PROGS or prog in ("source", ".") or _interp(prog)):
        return True
    if not args:
        return False
    if prog in ("eval", "source", ".", "iex", "invoke-expression"):
        return any(t.dyn for t in args)
    if prog in _SHELL_PROGS or prog in ("su", "runuser", "script"):
        vals = c.vals()
        for k, a in enumerate(vals):
            if re.match(r"^-[A-Za-z]*c[A-Za-z]*$", a) and k + 1 < len(args):
                return args[k + 1].dyn
        return any(t.v == "<(...)" for t in args[:2])
    if _interp(prog) or prog in _PS_PROGS:
        return any(t.v == "<(...)" for t in args[:2])
    return False


def pipeline_rules(ctx: Ctx, pipe: List[Seg], cmds: List[Cmd]) -> None:
    # run what is downloaded
    for j, c in enumerate(cmds):
        if not c.prog and not c.unresolved:
            continue
        if _stdin_sink(c) and any(_has_download_signal(cmds[i]) for i in range(j)):
            ctx.add("pipe-shell", "a downloaded script is run without being read")
        elif _stdin_sink(c) and j > 0 and cmds[j - 1].prog in ("echo", "printf", "write-output", "write-host"):
            nested_text(ctx, " ".join(cmds[j - 1].vals()), PS if c.prog in ("iex", "invoke-expression") or c.prog in _PS_PROGS else SH)
        sinkish = c.prog in _EXEC_SINKS or c.prog in ("sh", ".") or _interp(c.prog) in ("python", "node", "ruby", "perl")
        runs_sub = (sinkish or c.prog in ("iex", "invoke-expression")) and _runs_substitution(c)
        if runs_sub and _has_download_signal(c) and c.prog not in _DOWNLOADERS:
            ctx.add("pipe-shell", "a downloaded script is run without being read")
        if runs_sub:
            joined_nested = " ".join(t for _k, t in c.seg.nested)[:6000]
            tok_text = " ".join(t.v for t in c.seg.toks)
            if re.search(r"(?i)frombase64string|base64\s+(?:-d|-D|--decode)|certutil\b.{0,40}-decode", joined_nested + " " + tok_text):
                ctx.add("obfuscated", "a hidden command is decoded and run")
        if j > 0 and sinkish and cmds[j - 1].prog in ("base64", "certutil", "xxd", "openssl") and any(
                v in ("-d", "-D", "--decode", "-decode", "-r") or v.startswith("-d") for v in cmds[j - 1].vals()):
            ctx.add("obfuscated", "a hidden command is decoded and run")
        if j > 0 and sinkish and any(p.prog == "base64" and any(v in ("-d", "-D", "--decode") for v in p.vals()) for p in cmds[:j]):
            ctx.add("obfuscated", "a hidden command is decoded and run")
        if j > 0 and sinkish and cmds[j - 1].prog in ("echo", "printf") and \
                re.search(r"\\(?:[0-7]{3}|x[0-9a-fA-F]{2})", " ".join(cmds[j - 1].vals())):
            ctx.add("obfuscated", "escaped text is decoded and run")
    # download in this command, run in the same command
    for c in cmds:
        if any(re.search(r"(?i)scriptblock\]::create", t.v) for t in c.seg.toks) and _has_download_signal(c):
            ctx.add("pipe-shell", "a downloaded script is run without being read")
        if _has_download_signal(c) and (c.prog in _DOWNLOADERS or any(re.search(r"(?i)downloadfile", t.v) for t in c.seg.toks)):
            ctx.downloaded |= _download_targets(c)
        elif ctx.downloaded and _runs_downloaded(c, ctx.downloaded):
            ctx.add("pipe-shell", "the file that was just downloaded is run")
    secret_flow_rules(ctx, pipe, cmds)
    # text that switches the guard off, written by any member of the pipeline
    if any(_write_targets(c) for c in cmds):
        blob = " ".join(" ".join(c.vals()) + " " + " ".join(str(h[1] or "") for h in c.seg.heredocs) for c in cmds)
        if _GUARD_OFF_KEYS.search(blob):
            ctx.add("guard-off", "text that switches hooks or permissions off")


def analyze_pipeline(ctx: Ctx, pipe: List[Seg]) -> None:
    cmds = [resolve(seg, seg.kind) for seg in pipe]
    for idx in range(len(cmds)):
        ctx.tick()
        seg_rules(ctx, pipe, cmds, idx)
    pipeline_rules(ctx, pipe, cmds)


def run_text(ctx: Ctx, text: str) -> None:
    parsed = parse_command(text, ctx.kind, ctx.shared["deadline"])
    for pipe in parsed.pipelines:
        analyze_pipeline(ctx, pipe)


# --------------------------------------------------------------------------- public API: shell commands

def _sorted(findings: List[Finding]) -> List[Finding]:
    return sorted(findings, key=lambda f: -_RANK.get(str(f["tier"]), 0))


def guard_error_findings(command: str) -> List[Finding]:
    """What to do when the rich analysis failed: ask when the command has a danger word, else nothing."""
    try:
        if isinstance(command, str) and _DANGER_WORDS.search(command[:MAX_COMMAND_CHARS]):
            return [F("guard-error", "the safety check could not finish")]
    except Exception as exc:  # noqa: BLE001
        _note("danger words", exc)
    return []


def _raw_rules(ctx: Ctx, command: str) -> None:
    """Checks on the whole text, quoted parts included: a secret typed into a command, a fork bomb."""
    text = command[:262144]
    full = _secrets.scan_text(text)
    hits = list(full)
    if re.search(r"[\"'`]", text):                 # a key split by quote pairs (sk-ant-a''pi03) is one word for bash
        hits += list(_secrets.scan_text(re.sub(r"[\"'`]", "", text)))
    strong = [h for h in hits if getattr(h, "strong", True)]
    if strong:
        ctx.add("secret-in-command", ", ".join(sorted(set(str(h.kind) for h in strong))[:3]))
    elif getattr(full, "error", "") or getattr(full, "truncated", False):
        ctx.add("secret-scan-incomplete", "the secret check did not finish")
    if _rx("fork_bomb").search(command):
        ctx.add("forkbomb", "a fork bomb")


def _too_long_findings(command: str, shell: str, cwd: str) -> List[Finding]:
    """A command over MAX_COMMAND_CHARS is not analysed in full, but the short lists still run: a deny-level
    pattern or a secret wins over the size ask (guard-12)."""
    out: List[Finding] = [F("command-too-long", "%d characters" % len(command))]
    try:
        out += panic_check(command)
        ctx = Ctx(_kind_of(shell), cwd)
        _raw_rules(ctx, command)
        out += ctx.out
    except Exception as exc:  # noqa: BLE001
        _note("long command", exc)
    return _sorted(out)


def analyze_shell(command: str, shell: str = "bash", cwd: str = "", raise_errors: bool = False) -> List[Finding]:
    """Findings for one shell command (SPEC 7.2), strongest first. shell: 'bash' (default) or 'powershell' / 'cmd'.
    A bug inside raises only when raise_errors is True; otherwise a command with a danger word becomes `guard-error`."""
    if not isinstance(command, str) or not command.strip():
        return []
    if len(command) > MAX_COMMAND_CHARS:
        return _too_long_findings(command, shell, cwd)
    ctx = Ctx(_kind_of(shell), cwd)
    try:
        _raw_rules(ctx, command)
        run_text(ctx, command)
    except Exception:
        if raise_errors:
            raise
        extra = guard_error_findings(command)
        return _sorted(ctx.out + extra)
    return _sorted(ctx.out)


def scan_scripts(command: str, shell: str = "bash", cwd: str = "") -> List[Finding]:
    """Only the script-indirection part: the scripts this command would run, read from the project (<= 64 KB each)."""
    ctx = Ctx(_kind_of(shell), cwd)
    try:
        parsed = parse_command(command, ctx.kind, ctx.shared["deadline"])
        for pipe in parsed.pipelines:
            for seg in pipe:
                script_rules(ctx, resolve(seg, seg.kind))
    except Exception:  # noqa: BLE001
        return []
    return _sorted([f for f in ctx.out if f["rule_id"] == "script-with-danger"])


_PANIC: List[Tuple[str, str]] = [
    ("rm-danger", r"(?i)\b(?:rm|rmdir|del|erase|remove-item|ri|rd)\b[^|;&\n]{0,80}?\s(?:/|/\*|~|~/|~/\*|\$home/?|\$\{home\}/?|\.git/?|[a-z]:\\?|%userprofile%\\?)(?=\s|$|[;&|)\"'])"),
    ("git-force", r"(?i)\bgit\b[^|;&\n]{0,120}?\bpush\b[^|;&\n]{0,200}?(?:\s-[a-zA-Z]{0,6}f[a-zA-Z]{0,6}(?=\s|$)|\s--force(?=\s|$|=)|\s\+\S)"),
    ("pipe-shell", r"(?i)\b(?:curl|wget|iwr|irm|invoke-webrequest|invoke-restmethod)\b[^\n;]{0,300}?\|\s{0,3}(?:sudo\s{1,3})?(?:(?:ba|z|da|k)?sh|iex|invoke-expression)\b"),
    ("env-redirect", r"(?i)\b(?:ANTHROPIC_BASE_URL|HTTPS?_PROXY|ALL_PROXY|NODE_TLS_REJECT_UNAUTHORIZED)\s{0,3}=\s{0,3}\S"),
    ("read-secret", r"(?i)\b(?:cat|type|more|less|head|tail|get-content|gc)\b[^|;&\n]{0,120}?(?:^|[\s/\\])(?:\.env(?:\.(?!example|sample|template|dist|defaults)\w{1,20})?|id_(?:rsa|ed25519|ecdsa|dsa)|[\w.-]{1,60}\.pem)(?=\s|$|[;&|\"'])"),
    ("dd-device", r"(?i)\b(?:dd\b[^|;&\n]{0,120}?\bof=/dev/(?:sd|hd|nvme|disk|rdisk)|mkfs\S{0,10}\s|format\s{1,3}[a-z]:)"),
]
_PANIC_RX: List[Tuple[str, Any]] = []


def panic_check(command: str) -> List[Finding]:
    """Six short linear rules on the raw text. The handler runs them first in their own try block and keeps
    their block when the rich analysis fails. (The rich analysis is the judge otherwise: it knows quotes.)"""
    if not isinstance(command, str):
        return []
    if not _PANIC_RX:
        for rid, src in _PANIC:
            _PANIC_RX.append((rid, re.compile(src)))
    text = command[:MAX_COMMAND_CHARS * 5]
    out = []
    for rid, rx in _PANIC_RX:
        if rx.search(text):
            out.append(F(rid, "found by the short safety list", BLOCK))
    return out


# --------------------------------------------------------------------------- public API: files

_LOCK_SKIP = re.compile(r"(?i)(?:^|/)(?:package-lock\.json|yarn\.lock|pnpm-lock\.yaml|npm-shrinkwrap\.json|cargo\.lock|poetry\.lock|"
                        r"go\.sum|gemfile\.lock|composer\.lock|uv\.lock|pdm\.lock|pipfile\.lock)$|\.min\.(?:js|css)$|\.map$")
_SCRIPT_EXT = re.compile(r"(?i)\.(?:sh|bash|ps1|bat|cmd)$")


def scan_script_text(path: str, text: str, cwd: str = "") -> List[Finding]:
    """The commands inside a script the model is writing (*.sh *.ps1 *.bat *.cmd, a Makefile, package.json scripts)."""
    base = _norm(path).rsplit("/", 1)[-1].lower()
    ctx = Ctx(SH, cwd, mode="script")
    ctx.hidden = False
    ctx.sender_parent = False
    lines: List[Tuple[str, str]] = []
    text = text[:SCRIPT_MAX_BYTES * 2]
    try:
        if base == "package.json":
            data = None
            try:
                data = json.loads(text)
            except ValueError:
                data = None
            if isinstance(data, dict) and isinstance(data.get("scripts"), dict):
                lines = [(SH, str(v)) for v in data["scripts"].values() if isinstance(v, str)]
            else:                                   # an Edit fragment: "name": "command" pairs
                for m in re.finditer(r'"([\w:.@/-]{1,60})"\s{0,3}:\s{0,3}"((?:[^"\\\n]|\\.){1,400})"', text):
                    if _DANGER_WORDS.search(m.group(2)):
                        lines.append((SH, m.group(2).replace('\\"', '"').replace("\\\\", "\\")))
        elif base in ("makefile", "gnumakefile") or base.endswith(".mk"):
            lines = [(SH, ln.strip().lstrip("@-+").strip()) for ln in text.split("\n") if ln.startswith("\t")]
        elif _SCRIPT_EXT.search(base):
            ext = base.rsplit(".", 1)[-1]
            lines = [(PS if ext == "ps1" else CMD if ext in ("bat", "cmd") else SH, text)]
        found: List[str] = []
        for kind, body in lines[:200]:
            if not body.strip() or not _DANGER_WORDS.search(body):
                continue
            ch = Ctx(kind, cwd, ctx.shared, 1, "script")
            ch.hidden = False
            ch.sender_parent = False
            run_text(ch, body)
            found.extend(f["rule_id"] for f in ch.out if f["tier"] != WARN)
    except BudgetExceeded:
        return [F("script-with-danger", "the script is too long to check", ASK)]
    except Exception:  # noqa: BLE001
        return []
    if found:
        return [F("script-with-danger", short_text(base, 30) + ": " + ", ".join(sorted(set(found))[:4]))]
    return []


def analyze_file_op(tool: str, path: str, content: str, cwd: str = "", scratchpad_dir: str = "") -> List[Finding]:
    """Findings for a Write, Edit or NotebookEdit call: path rules first, then what is written."""
    out: List[Finding] = []
    p = str(path or "")
    if not p:
        return out
    tags = path_tags(p, cwd, scratchpad_dir)
    if "never" in tags:
        return out
    text = content if isinstance(content, str) else ""
    shown = short_text(_shown_path(p, cwd), 60)
    norm = _norm(p)
    base = norm.rsplit("/", 1)[-1].lower()

    def add(rule: str, detail: str, tier: Optional[str] = None) -> None:
        if not any(f["rule_id"] == rule for f in out):
            out.append(F(rule, detail, tier))

    if "hook-only" in tags:
        add("hook-only-path", shown)
    elif "config" in tags:
        add("config-write", shown)
    if "config" in tags or re.match(r"(?i)^(?:settings(?:\.local)?|\.claude|\.mcp|managed-settings)\.json$", base):
        if text and _GUARD_OFF_KEYS.search(text):
            add("guard-off", "text that switches hooks or permissions off")
    if "hook-only" not in tags and "config" not in tags and _secrets.is_secret_filename(norm):
        add("secret-file-write", shown)
    if text and not _LOCK_SKIP.search(norm):
        try:
            hits = _secrets.scan_text(text, max_bytes=len(text))     # the whole text: a key after 256 KB is found too
            strong = [h for h in hits if getattr(h, "strong", True)]
            if strong:
                add("secret-in-file", ", ".join(sorted(set(str(h.kind) for h in strong))[:3]))
            elif getattr(hits, "error", "") or getattr(hits, "truncated", False):
                add("secret-scan-incomplete", "the secret check did not finish")
        except Exception:  # noqa: BLE001
            add("secret-scan-incomplete", "the secret check failed")
    if "outside" in tags:
        add("write-outside-project", shown)
    if text and (base in ("package.json", "makefile", "gnumakefile") or _SCRIPT_EXT.search(base) or base.endswith(".mk")):
        for f in scan_script_text(norm, text, cwd):
            add(f["rule_id"], f["detail"], f["tier"])
    return _sorted(out)


# --------------------------------------------------------------------------- the decision

def _entry(rule_id: str, key: str = "") -> Dict[str, str]:
    e = messages().get(key or rule_id)
    if isinstance(e, dict):
        return {k: str(e.get(k, "")) for k in ("short", "why", "safe", "lesson")}
    return {"short": "this needs a closer look", "why": "", "safe": "ask the user before running it, and explain what it does", "lesson": ""}


def _sentence(text: str) -> str:
    text = " ".join(str(text).split()).strip()
    return text.rstrip(".") + "." if text else ""


PREFIX = "Stopped on purpose by the tutor safety guard (%s). This is a safety stop, not a setup error. "
SUFFIX = (" In your next message tell the user in two plain sentences what you were about to do, why it is risky and the "
          "safe alternative; do not retry the same goal with a reworded command.")


def reason_text(findings: List[Any], seen: Optional[Dict[str, Any]] = None, cannot_ask: bool = False) -> str:
    """The deny/ask text (SPEC 4.3): prefix, short, [why on the first hit], safe way, other findings, suffix."""
    top = findings[0]
    rid = _field(top, "rule_id")
    e = _entry(rid, _field(top, "message_key") or rid)
    first = not (seen or {}).get(rid)
    detail = _field(top, "detail")
    body = " ".join(e["short"].split()).rstrip(".")
    if detail:
        body += " (seen: " + short_text(detail, 90).rstrip(".") + ")"
    body += "."
    if first and e["why"]:
        body += " " + _sentence(e["why"])
    body += " Safe way: " + _sentence(e["safe"])
    others = []
    for f in findings[1:3]:
        oid = _field(f, "rule_id")
        if oid != rid:
            others.append("%s (%s)" % (oid, _sentence(_entry(oid, _field(f, "message_key") or oid)["short"]).rstrip(".")))
    if others:
        body += " Also noticed: " + "; ".join(others) + "."
    if cannot_ask:
        body += " This permission mode cannot ask the user, so the command was stopped; the user can run it themselves or change the mode."
    return PREFIX % rid + body + SUFFIX


def decide(findings: Sequence[Any], permission_mode: str = "", seen: Optional[Dict[str, Any]] = None) -> Tuple[str, str]:
    """(decision, text). decision: 'deny', 'ask', 'warn' or 'none'. An ask becomes a deny in dontAsk and
    bypassPermissions mode (nobody can answer). `seen` maps rule_id to how often the learner has met it
    (first hit: the long text; later: short)."""
    fs = [f for f in findings if f]
    if not fs:
        return "none", ""
    ordered = sorted(fs, key=lambda f: -_RANK.get(_field(f, "tier"), 0))
    top_tier = _field(ordered[0], "tier")
    if top_tier == BLOCK:
        return "deny", reason_text(ordered, seen)
    if top_tier == ASK:
        if (permission_mode or "") in ("dontAsk", "bypassPermissions"):
            return "deny", reason_text(ordered, seen, cannot_ask=True)
        return "ask", reason_text(ordered, seen)
    rid = _field(ordered[0], "rule_id")
    e = _entry(rid, _field(ordered[0], "message_key") or rid)
    text = "Heads-up from the safety guard (%s): %s Safe way: %s Mention it to the user in one plain sentence." % (
        rid, _sentence(e["short"]), _sentence(e["safe"]))
    return "warn", text


# --------------------------------------------------------------------------- looking only

_OBSERVE = frozenset(
    "ls dir pwd cat type head tail wc echo printf grep egrep fgrep rg find which where whoami hostname date uname tree stat "
    "file du df ps sort uniq cut tr diff cmp basename dirname realpath readlink id groups tput clear cd chdir pushd popd "
    "get-childitem get-content get-location get-date get-command get-process select-string sls measure-object where-object "
    "select-object sort-object format-table format-list write-output write-host test-path resolve-path split-path "
    "set-location get-item get-itemproperty get-help help man history sleep start-sleep true false test [ ".split())
_GIT_OBSERVE = frozenset("status diff log show blame shortlog describe rev-parse ls-files ls-tree cat-file reflog grep "
                         "check-ignore whatchanged count-objects for-each-ref show-ref tag branch remote config stash".split())


def is_observe_only(command: str, shell: str = "bash") -> bool:
    """True when the command only looks (lists, prints, reads status); nothing is written, deleted, installed or sent."""
    try:
        if not isinstance(command, str) or not command.strip() or len(command) > 4000:
            return False
        kind = _kind_of(shell)
        parsed = parse_command(command, kind, time.monotonic() + 0.5)
        count = 0
        for pipe in parsed.pipelines:
            for seg in pipe:
                count += 1
                if count > 40 or seg.heredocs:
                    return False
                for op, t in seg.redirs:
                    if op in ("<",) or t.v in ("/dev/null", "nul", "NUL", "$null"):
                        continue
                    return False
                for k2, text in seg.nested:
                    if not is_observe_only(text, "powershell" if k2 == PS else "bash"):
                        return False
                c = resolve(seg, seg.kind)
                if c.unresolved or c.envs and not c.prog:
                    return False
                if c.assign:
                    continue
                prog = c.prog
                if not prog:
                    continue
                if c.wrappers - {"time", "command", "builtin", "nohup"}:
                    return False
                vals = c.vals()
                if prog == "git":
                    sub, sa, cfgs = git_parse(vals)
                    short, long_, tg = split_flags(sa)
                    if cfgs or sub not in _GIT_OBSERVE:
                        return False
                    if sub == "branch" and (short & set("dDmMcCfu") or long_ & {"delete", "move", "force", "copy"} or (tg and not (short & {"l"}) and "list" not in long_)):
                        return False
                    if sub == "remote" and tg and tg[0] not in ("-v", "show", "get-url"):
                        return False
                    if sub == "config" and not (long_ & {"get", "list", "get-all", "get-regexp"} or "l" in short):
                        return False
                    if sub == "stash" and tg[:1] != ["list"] and tg[:1] != ["show"]:
                        return False
                    if sub == "tag" and tg and not (short & {"l"} or "list" in long_):
                        return False
                    continue
                if prog in ("npm", "pnpm", "yarn") and vals[:1] and vals[0] in ("ls", "list", "view", "info", "outdated", "-v", "--version", "root", "bin"):
                    continue
                if prog in ("pip", "pip3") and vals[:1] and vals[0] in ("list", "show", "freeze", "check", "--version", "-V"):
                    continue
                if prog in ("python", "python3", "py", "node", "ruby", "java", "go", "cargo", "dotnet", "npm", "docker") and \
                        vals[:1] and vals[0] in ("--version", "-V", "-v", "version"):
                    continue
                if prog == "find" and any(v in ("-delete", "-exec", "-execdir", "-ok", "-okdir", "-fprint", "-fprintf", "-fls") for v in vals):
                    return False
                if prog in ("sort", "tee") and any(v == "-o" for v in vals):
                    return False
                if prog in _OBSERVE and prog != "tee":
                    if prog in ("cat", "type", "head", "tail", "get-content", "grep", "egrep", "fgrep", "rg", "select-string", "sls"):
                        if any(_secret_token(v) for v in vals):
                            return False
                    continue
                return False
        return count > 0
    except Exception:  # noqa: BLE001
        return False
