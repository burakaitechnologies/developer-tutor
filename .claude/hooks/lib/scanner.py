"""scanner.py - the commit and push scanner of the PreToolUse guard (SPEC 7.6).

What it is: scan_staged(cwd, command) reads a shell command, finds the git
steps that put files into history (git add, git commit, git push, gh repo
create --push, gh pr create) and checks what those steps would send:
  (a) git add: asks Git which files it WOULD stage (git add --dry-run, with the
      same arguments), checks every name and reads every file;
  (b) git commit -a, -am, --all, or with paths: scans git diff HEAD -U0 and the
      staged diff;
  (c) plain git commit: scans git diff --cached -U0;
  (d) git push: scans the commits that would leave (git log -p -U0, at most 200
      commits and 2 MB) and lists their file names;
  (e) any error, timeout or cap hit becomes an ask: "I could not check for
      secrets: <reason>". The caller turns an ask into a deny in bypass or
      dontAsk mode (guardrules.decide).
It also blocks git add, commit and push of the private tutor notes
(.claude/agent-memory) and .claude/settings.local.json.

Why it exists: the guard runs BEFORE the command. In "git add . && git commit"
nothing is staged yet, and a push sends commits, not the staged diff. So the
scanner looks at what the command is about to do, not at the index.

How it fails safely: scan_staged never raises. A command without git or gh
returns [] at once. A command it cannot read, a path it cannot open, a diff that
is too big, a time limit: all return one ask finding. A finding never contains
any part of a secret. All Git calls go through gitq (hardened
as in SPEC 4.3: no pager, no hooks of the repository's choosing, 5 s timeout).

What it reads from the command: quotes, escapes, here-documents, redirects,
command substitutions, `cd` and `git -C`, git aliases, and what a nested shell
(bash -c, cmd /c, powershell -Command, wsl, eval, iex, find -exec) will run.
A file list built at run time ($files, $(...), xargs) cannot be checked: ask.
Content is not read for lockfiles, images, minified files, build and vendor
folders, and the tutor's own folders under .claude (hooks, tools, knowledge,
skills, agents, rules, output-styles, templates, docs). The names are still checked.

Known gaps (docs/how-it-works.md): a file that an earlier step of the SAME command
creates; git run from a script, make or an IDE; commit messages and tags are not
read; secrets split over two lines; a change that exists only inside a merge commit.

Who calls it: handlers/pre_tool.py, for every Bash or PowerShell command that
mentions git or gh. The caller passes the folder the command starts in as cwd and
the seconds left in its own budget as limit_s.

A finding is a dict: rule_id, tier (block or ask), message_key (== rule_id),
detail (plain text, file names neutralised; a secret is named by file, line and kind only, never by its value).
The five rule ids
are in RULE_IDS; SUGGESTED_MESSAGES holds the texts for hooks/guard-messages.json.
"""
from __future__ import annotations

import base64
import os
import re
import stat
import time
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

try:
    from . import gitq as _gitq
except ImportError:  # loaded as a flat module (tests, scripts)
    try:
        import gitq as _gitq  # type: ignore
    except ImportError:
        _gitq = None  # type: ignore
try:
    from . import secrets as _secrets
except ImportError:
    try:
        import secrets as _secrets  # type: ignore
    except ImportError:
        _secrets = None  # type: ignore
try:
    from . import untrusted as _untrusted
except ImportError:
    try:
        import untrusted as _untrusted  # type: ignore
    except ImportError:
        _untrusted = None  # type: ignore

# ---------------------------------------------------------------- limits

TOTAL_SECONDS = 5.0            # whole scan
MAX_FILE_BYTES = 200 * 1024    # content scan reads at most this much of one file
MAX_FILES = 200                # files whose content is read in one command
MAX_DIFF_BYTES = 2 * 1024 * 1024
MAX_COMMITS = 200
MAX_COMMAND_CHARS = 20000
MAX_CALLS = 24                 # add, commit, push and gh steps examined in one command
MAX_STEPS = 200                # git and gh steps of any kind found while reading a command
MAX_SEGMENTS = 400             # parts of one command (work bound)
MAX_NESTING = 4

RULE_SECRET_FILE = "scan-secret-file"
RULE_SECRET_CONTENT = "scan-secret-content"
RULE_NOTES_ADD = "scan-private-notes-add"
RULE_NOTES_PUSH = "scan-private-notes-push"
RULE_INCOMPLETE = "scan-incomplete"
RULE_IDS = (RULE_SECRET_FILE, RULE_SECRET_CONTENT, RULE_NOTES_ADD, RULE_NOTES_PUSH, RULE_INCOMPLETE)

# Texts for hooks/guard-messages.json. The guard builder owns that file; these
# are the entries the scanner needs (message_key == rule_id).
SUGGESTED_MESSAGES: Dict[str, Dict[str, str]] = {
    RULE_SECRET_FILE: {
        "short": "A file with a secret-looking name would go into Git.",
        "why": "Git keeps every version for good, and a push copies it to GitHub, where bots find keys within minutes.",
        "safe": "Leave it out: put its name in .gitignore and add your other files by name. If a key was already shared, make a new key first.",
        "lesson": "sec-secrets",
    },
    RULE_SECRET_CONTENT: {
        "short": "The changes contain something that looks like a secret.",
        "why": "A key in a commit stays in the history even if you delete it later.",
        "safe": "Move the value into .env (Git ignores it), read it from the environment, and commit again. If it already left this computer, revoke the key and make a new one.",
        "lesson": "sec-rotate-leaked-key",
    },
    RULE_NOTES_ADD: {
        "short": "Private tutor notes or local settings would go into Git.",
        "why": "They hold your own words and choices, and they are meant to stay on this computer.",
        "safe": "Leave .claude/agent-memory and .claude/settings.local.json out of the command and add your project files by name.",
        "lesson": "sec-personal-data",
    },
    RULE_NOTES_PUSH: {
        "short": "Git already tracks private tutor notes, and a push would publish them.",
        "why": "Once pushed, anyone who can see the repository can read your notes.",
        "safe": "Stop tracking them first: run git rm --cached -r .claude/agent-memory yourself, commit that, then push.",
        "lesson": "sec-personal-data",
    },
    RULE_INCOMPLETE: {
        "short": "I could not check for secrets.",
        "why": "The check failed or ran out of time, so nobody can say this commit is clean.",
        "safe": "Look at git status and git diff yourself, or run the command in smaller steps.",
        "lesson": "sec-secrets",
    },
}

_GIT_ENV = re.compile(r"(?i)(?<![\w])GIT_(?:DIR|WORK_TREE|INDEX_FILE)[ \t]{0,3}=")
_GIT_KNOWN = frozenset((
    "add", "am", "apply", "archive", "bisect", "blame", "branch", "bundle", "cat-file", "check-ignore", "checkout",
    "cherry-pick", "clean", "clone", "commit", "config", "describe", "diff", "difftool", "fetch", "for-each-ref",
    "format-patch", "fsck", "gc", "grep", "help", "init", "log", "ls-files", "ls-tree", "maintenance", "merge",
    "mergetool", "mv", "notes", "pull", "push", "rebase", "reflog", "remote", "reset", "restore", "rev-list",
    "rev-parse", "revert", "rm", "shortlog", "show", "show-ref", "sparse-checkout", "stash", "status", "submodule",
    "switch", "symbolic-ref", "tag", "update-ref", "version", "worktree", "lfs",
))
_TRIGGER = re.compile(r"(?i)\bgit(?:\.exe)?\b|\bgh(?:\.exe)?\b")
_REMOTE_NAME = re.compile(r"^[A-Za-z0-9._-]{1,60}$")
_REV_NAME = re.compile(r"^[A-Za-z0-9._/@{}~^+:-]{1,120}$")

# content we never read: names that hold no hand-written text
_LOCKFILES = frozenset((
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "npm-shrinkwrap.json", "cargo.lock", "poetry.lock",
    "go.sum", "gemfile.lock", "composer.lock", "uv.lock", "pdm.lock", "pipfile.lock", "bun.lockb",
))
_SKIP_DIRS = ("node_modules", "dist", "build", "vendor", ".git", "__pycache__", "site-packages")
_PRODUCT_DIRS = ("hooks", "tools", "knowledge", "skills", "agents", "rules", "output-styles", "templates", "docs")
_BINARY_EXT = frozenset((
    "png", "jpg", "jpeg", "gif", "webp", "bmp", "ico", "icns", "tif", "tiff", "svg", "pdf", "zip", "gz", "tgz", "bz2",
    "xz", "7z", "rar", "jar", "war", "woff", "woff2", "ttf", "otf", "eot", "mp3", "mp4", "mov", "avi", "mkv", "wav",
    "ogg", "webm", "exe", "dll", "so", "dylib", "bin", "class", "pyc", "pyo", "o", "a", "lib", "sqlite", "sqlite3",
    "db", "map", "psd", "ai",
))


# ---------------------------------------------------------------- small helpers


def _clean(text: Any, n: int = 80) -> str:
    """File names come from Git and from the command: neutralise them before they reach the model."""
    try:
        if _untrusted is not None:
            return str(_untrusted.neutralize(str(text), n))
    except Exception:
        pass
    out = "".join(ch if ch.isprintable() and ch not in "<>`" else " " for ch in str(text))
    return " ".join(out.split())[:n]


def _norm(path: str) -> str:
    return str(path).replace("\\", "/")


def _base_prog(word: str) -> str:
    p = _norm(word).rsplit("/", 1)[-1].lower()
    for suffix in (".exe", ".cmd", ".bat", ".com"):
        if p.endswith(suffix):
            return p[:-len(suffix)]
    return p


def _join_limited(items: Sequence[str], limit: int, sep: str = "; ") -> str:
    shown = list(items[:limit])
    text = sep.join(shown)
    if len(items) > limit:
        text += " (and %d more)" % (len(items) - limit)
    return text


def _hit_field(hit: Any, name: str, default: Any = None) -> Any:
    try:
        if isinstance(hit, dict):
            return hit.get(name, default)
        return getattr(hit, name, default)
    except Exception:
        return default


def _kind_of(hit: Any) -> str:
    """The kind of a secret (say 'Anthropic API key'). The guard text names the file, the line and this kind,
    never any character of the value: not even a prefix."""
    return _clean(str(_hit_field(hit, "kind", "secret") or "secret"), 40)


# ---------------------------------------------------------------- reading a shell command


class _ParseError(Exception):
    pass


_PARSE_REASONS = {
    "quote": "a quote is not closed", "backtick": "a backtick is not closed", "paren": "a bracket is not closed",
    "nesting": "it is nested too deeply", "here-string": "a here-string is not closed",
    "too many steps": "it has too many git steps", "too many parts": "it has too many parts",
    "encoded command": "an encoded command could not be decoded",
}


def _looks_windows(text: str) -> bool:
    """True when backslashes look like path separators (C:\\x\\y), not shell escapes."""
    return "\\" in text and re.search(r"\\[ \t\"'$`\\;&|<>()#\n]", text) is None


def _grab_paren(text: str, i: int) -> Tuple[int, str]:
    """text[i] == '('. Return (index after the matching ')', inner text).

    Quotes are respected, and so are here-documents: the usual commit message
    $(cat <<'EOF' ... EOF) may hold an apostrophe that is not a quote.
    """
    depth = 0
    j = i
    n = len(text)
    pending: List[Tuple[str, bool]] = []
    while j < n:
        c = text[j]
        if c == "\n" and pending:
            j = _skip_heredocs(text, j + 1, pending)
            pending = []
            continue
        if c == "<" and text[j + 1:j + 2] == "<" and text[j + 2:j + 3] != "<":
            k = j + 2
            strip = text[k:k + 1] == "-"
            if strip:
                k += 1
            k, delim = _read_word(text, k)
            if delim:
                pending.append((delim, strip))
            j = k
            continue
        if c == "'":
            k = text.find("'", j + 1)
            if k < 0:
                raise _ParseError("quote")
            j = k
        elif c == '"':
            j += 1
            while j < n and text[j] != '"':
                if text[j] == "\\" and j + 1 < n:
                    j += 1
                j += 1
            if j >= n:
                raise _ParseError("quote")
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                return j + 1, text[i + 1:j]
        j += 1
    raise _ParseError("paren")


def _read_word(text: str, i: int) -> Tuple[int, str]:
    """Skip blanks, then read one word (quotes removed). Used for redirect targets and here-doc markers."""
    n = len(text)
    while i < n and text[i] in " \t":
        i += 1
    out: List[str] = []
    while i < n and text[i] not in " \t\r\n;|&<>()":
        c = text[i]
        if c in "'\"":
            j = text.find(c, i + 1)
            if j < 0:
                raise _ParseError("quote")
            out.append(text[i + 1:j])
            i = j + 1
            continue
        out.append(c)
        i += 1
    return i, "".join(out)


def _skip_heredocs(text: str, i: int, pending: List[Tuple[str, bool]]) -> int:
    n = len(text)
    for delim, strip_tabs in pending:
        while i < n:
            j = text.find("\n", i)
            line = text[i:] if j < 0 else text[i:j]
            i = n if j < 0 else j + 1
            line = line.rstrip("\r")
            if strip_tabs:
                line = line.lstrip("\t")
            if line == delim:
                break
    return i


Token = Tuple[str, bool]   # (word, dynamic: built by the shell from a variable or a command)
_HERE_START = re.compile(r"@(['\"])[ \t]*\r?\n")   # PowerShell here-string opener


def _lex(text: str, win: bool) -> Tuple[List[List[Token]], List[str]]:
    """Split a command into segments of tokens. Returns (segments, nested command strings).

    Quotes, escapes, here-documents, redirects and command substitutions are handled. A token is
    dynamic when the shell would fill it in at run time ($VAR, $(...), backticks).
    """
    segs: List[List[Token]] = []
    seg: List[Token] = []
    nested: List[str] = []
    tok: List[str] = []
    state = {"has": False, "dyn": False}
    heredocs: List[Tuple[str, bool]] = []
    i, n = 0, len(text)

    def end_tok() -> None:
        if state["has"] or tok:
            seg.append(("".join(tok), bool(state["dyn"])))
        del tok[:]
        state["has"] = False
        state["dyn"] = False

    def end_seg() -> None:
        end_tok()
        if seg:
            segs.append(list(seg))
        del seg[:]

    while i < n:
        c = text[i]
        if c in " \t\r":
            end_tok()
            i += 1
        elif c == "\n":
            end_seg()
            i += 1
            if heredocs:
                i = _skip_heredocs(text, i, heredocs)
                heredocs = []
        elif c == "#" and not state["has"] and not tok:
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif c == "@" and _HERE_START.match(text, i) is not None:
            m = _HERE_START.match(text, i)
            quote = m.group(1)
            end = text.find("\n" + quote + "@", m.end() - 1)
            if end < 0:
                raise _ParseError("here-string")
            tok.append(text[m.end():end])
            state["has"] = True
            state["dyn"] = state["dyn"] or quote == '"'
            i = end + 3
        elif c == "'":
            j = text.find("'", i + 1)
            if j < 0:
                raise _ParseError("quote")
            tok.append(text[i + 1:j])
            state["has"] = True
            i = j + 1
        elif c == '"':
            state["has"] = True
            i += 1
            while True:
                if i >= n:
                    raise _ParseError("quote")
                d = text[i]
                nxt = text[i + 1] if i + 1 < n else ""
                if d == '"':
                    if win and nxt == '"':
                        tok.append('"')
                        i += 2
                        continue
                    i += 1
                    break
                if d == "\\" and not win and nxt in ('"', "\\", "$", "`"):
                    tok.append(nxt)
                    i += 2
                elif d == "\\" and not win and nxt == "\n":
                    i += 2
                elif d == "`" and win and nxt:
                    tok.append(nxt)
                    i += 2
                elif d == "$" and nxt == "(":
                    j, inner = _grab_paren(text, i + 1)
                    nested.append(inner)
                    state["dyn"] = True
                    tok.append("$(...)")
                    i = j
                elif d == "`" and not win:
                    j = text.find("`", i + 1)
                    if j < 0:
                        raise _ParseError("backtick")
                    nested.append(text[i + 1:j])
                    state["dyn"] = True
                    tok.append("`...`")
                    i = j + 1
                elif d == "$" and nxt and (nxt.isalpha() or nxt in "_{"):
                    state["dyn"] = True
                    tok.append(d)
                    i += 1
                else:
                    tok.append(d)
                    i += 1
        elif c == "$" and text[i + 1:i + 2] == "(":
            j, inner = _grab_paren(text, i + 1)
            nested.append(inner)
            state["has"] = True
            state["dyn"] = True
            tok.append("$(...)")
            i = j
        elif c == "$" and text[i + 1:i + 2] and (text[i + 1].isalpha() or text[i + 1] in "_{"):
            state["has"] = True
            state["dyn"] = True
            tok.append(c)
            i += 1
        elif c == "`":
            if win:
                if i + 1 < n:
                    tok.append(text[i + 1])
                    state["has"] = True
                i += 2
            else:
                j = text.find("`", i + 1)
                if j < 0:
                    raise _ParseError("backtick")
                nested.append(text[i + 1:j])
                state["has"] = True
                state["dyn"] = True
                tok.append("`...`")
                i = j + 1
        elif c == "\\" and not win:
            if text[i + 1:i + 2] == "\n":
                i += 2
            elif i + 1 < n:
                tok.append(text[i + 1])
                state["has"] = True
                i += 2
            else:
                i += 1
        elif c in ";|":
            end_seg()
            i += 2 if text[i + 1:i + 2] in ("|", "&") and c == "|" else 1
            if c == ";" and text[i:i + 1] == ";":
                i += 1
        elif c == "&":
            nxt = text[i + 1:i + 2]
            if nxt == ">":
                end_tok()
                i += 2
                if text[i:i + 1] == ">":
                    i += 1
                i, _target = _read_word(text, i)
            else:
                end_seg()
                i += 2 if nxt == "&" else 1
        elif c in "<>":
            if tok and "".join(tok).isdigit():          # a file number such as 2 in 2>&1
                del tok[:]
                state["has"] = False
                state["dyn"] = False
            else:
                end_tok()
            i += 1
            if c == "<" and text[i:i + 1] == "<":
                if text[i + 1:i + 2] == "<":
                    i, _word = _read_word(text, i + 2)
                else:
                    i += 1
                    strip = text[i:i + 1] == "-"
                    if strip:
                        i += 1
                    i, delim = _read_word(text, i)
                    if delim:
                        heredocs.append((delim, strip))
                continue
            if text[i:i + 1] == "(":
                j, inner = _grab_paren(text, i)
                nested.append(inner)
                tok.append("<(...)")
                state["has"] = True
                state["dyn"] = True
                i = j
                continue
            if c == ">" and text[i:i + 1] == ">":
                i += 1
            if text[i:i + 1] == "&":
                i += 1
            elif c == ">" and text[i:i + 1] == "|":
                i += 1
            i, _target = _read_word(text, i)
        elif c == "(" and seg and not tok:
            # PowerShell (...) in the middle of a command is an argument built at run time
            j, inner = _grab_paren(text, i)
            nested.append(inner)
            tok.append("(...)")
            state["has"] = True
            state["dyn"] = True
            i = j
        elif c in "()":
            end_seg()
            i += 1
        else:
            tok.append(c)
            state["has"] = True
            i += 1
    end_seg()
    return segs, nested


_SHELLS = frozenset(("bash", "sh", "zsh", "dash", "ksh", "ash", "fish"))
_PS_SHELLS = frozenset(("powershell", "pwsh"))
_CONTROL = frozenset((
    "if", "then", "else", "elif", "do", "while", "until", "!", "{", "}", "command", "builtin", "exec",
    "nohup", "time", "call", "&", ".",
))
_GIT_GLOBAL_WITH_VALUE = frozenset((
    "--namespace", "--exec-path", "--super-prefix", "--config-env", "--attr-source",
))


class _Call(object):
    """One git or gh step found in a command."""

    def __init__(self, prog: str, sub: str, args: List[str], dyn: List[bool], cwd: Optional[str],
                 xargs: bool, redirected_git_dir: bool, cwds: Optional[List[str]] = None) -> None:
        self.prog = prog
        self.cwds = cwds or ([cwd] if cwd else [])      # every folder the step may run in
        self.sub = sub
        self.args = args
        self.dyn = dyn
        self.cwd = cwd                      # None = cannot be known
        self.xargs = xargs
        self.redirected_git_dir = redirected_git_dir


def _resolve(tokens: List[Token]) -> Tuple[str, List[str], List[bool], bool]:
    """(program, args, dynamic flags of args, runs-under-xargs) after wrappers and assignments."""
    i = 0
    n = len(tokens)
    xargs = False
    while i < n:
        word, _dyn = tokens[i]
        low = _base_prog(word)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", word) or low in _CONTROL or word == "(...)":
            i += 1
        elif low in ("sudo", "doas", "gsudo", "runas"):
            i += 1
            while i < n and tokens[i][0].startswith("-"):
                i += 2 if tokens[i][0] in ("-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D") else 1
        elif low == "env":
            i += 1
            while i < n and (tokens[i][0].startswith("-") or "=" in tokens[i][0]):
                i += 2 if tokens[i][0] in ("-u", "-C", "-S") else 1
        elif low in ("xargs", "watch"):
            xargs = xargs or low == "xargs"
            i += 1
            while i < n and tokens[i][0].startswith("-"):
                i += 1
        elif low in ("timeout", "nice", "ionice", "stdbuf", "setsid"):
            i += 1
            while i < n and (tokens[i][0].startswith("-") or re.match(r"^[0-9.]+[smhd]?$", tokens[i][0])):
                i += 1
        else:
            break
    if i >= n:
        return "", [], [], xargs
    prog = _base_prog(tokens[i][0])
    rest = tokens[i + 1:]
    while rest and rest[-1][0] == "}":          # the end of a { ... } block written without a semicolon
        rest = rest[:-1]
    return prog, [t[0] for t in rest], [t[1] for t in rest], xargs


def _nested_from(prog: str, args: List[str]) -> List[str]:
    """Command strings that a shell, cmd, PowerShell, wsl, eval or iex will run."""
    out: List[str] = []
    if prog in _SHELLS:
        for k, a in enumerate(args):
            if re.match(r"^-[a-zA-Z]*c[a-zA-Z]*$", a) and k + 1 < len(args):
                out.append(args[k + 1])
                break
    elif prog in _PS_SHELLS:
        for k, a in enumerate(args):
            low = a.lower()
            if re.match(r"^-(?:c|co|com|comm|comma|comman|command)$", low) and k + 1 < len(args):
                out.append(" ".join(args[k + 1:]))
                break
            if re.match(r"^-e(?:c|nc|nco|ncod|ncode|ncoded|ncodedc\w*)?$", low) and k + 1 < len(args):
                try:
                    out.append(base64.b64decode(args[k + 1]).decode("utf-16-le", "replace"))
                except Exception:
                    raise _ParseError("encoded command")
                break
    elif prog == "cmd":
        for k, a in enumerate(args):
            if a.lower() in ("/c", "/k", "/r") and k + 1 < len(args):
                out.append(" ".join(args[k + 1:]))
                break
    elif prog == "wsl":
        rest = []
        skip = False
        for a in args:
            if skip:
                skip = False
            elif a in ("-d", "--distribution", "-u", "--user", "--cd"):
                skip = True
            elif a not in ("-e", "--exec", "--"):
                rest.append(a)
        if rest:
            out.append(" ".join(rest))
    elif prog == "find":
        for k, a in enumerate(args):
            if a in ("-exec", "-execdir", "-ok", "-okdir"):
                words = []
                for b in args[k + 1:]:
                    if b in (";", "+") or b == "\\;":
                        break
                    words.append("$FOUND" if b == "{}" else b)
                if words:
                    out.append(" ".join(words))      # {} is a file name that find fills in: dynamic
    elif prog in ("eval", "iex", "invoke-expression"):
        if args:
            out.append(" ".join(args))
    elif prog == "start-process":
        low = [a.lower() for a in args]
        pieces = [a for a in args if not a.startswith("-")][:1]
        for k, a in enumerate(low):
            if a in ("-argumentlist", "-args") and k + 1 < len(args):
                pieces.append(args[k + 1])
        if len(pieces) > 1:
            out.append(" ".join(pieces))
    return out


def _git_parts(args: List[str], dyn: List[bool]) -> Tuple[List[Tuple[str, bool]], bool, str, List[str], List[bool]]:
    """Split git's own global options from the sub-command. Returns (-C dirs, git-dir override, sub, args, dyn)."""
    i = 0
    n = len(args)
    cdirs: List[Tuple[str, bool]] = []
    override = False
    while i < n:
        a = args[i]
        if a == "-C" and i + 1 < n:
            cdirs.append((args[i + 1], dyn[i + 1]))
            i += 2
        elif a == "-c" and i + 1 < n:
            i += 2
        elif a in ("--git-dir", "--work-tree") and i + 1 < n:
            override = True
            i += 2
        elif a.startswith(("--git-dir=", "--work-tree=")):
            override = True
            i += 1
        elif a in _GIT_GLOBAL_WITH_VALUE and i + 1 < n:
            i += 2
        elif a.startswith("-"):
            i += 1
        else:
            break
    sub = args[i] if i < n else ""
    return cdirs, override, sub, args[i + 1:], dyn[i + 1:]


def _resolve_dir(base: Optional[str], arg: str, is_dynamic: bool) -> Optional[str]:
    """New working folder, '' when the folder does not exist, None when it cannot be known."""
    if is_dynamic or base is None or not arg or arg in ("-", "~") or arg.startswith(("~", "$", "%")):
        return None
    path = os.path.normpath(os.path.join(base, arg))
    return path if os.path.isdir(path) else ""


def _collect_calls(text: str, cwd: Optional[str], depth: int, out: List[_Call], visited: List[str]) -> Optional[str]:
    """Walk one command string; append git and gh steps to `out`. Returns the cwd after the string.

    `visited` lists every folder a cd has moved to so far. A step is checked in all of them,
    because a cd inside ( ... ) or inside a nested shell may or may not apply to what follows.
    """
    if depth > MAX_NESTING:
        raise _ParseError("nesting")
    segs, nested = _lex(text, _looks_windows(text))
    if len(segs) > MAX_SEGMENTS:
        raise _ParseError("too many parts")
    for seg in segs:
        prog, args, dyn, xargs = _resolve(seg)
        if not prog:
            continue
        if prog in ("cd", "chdir", "pushd", "set-location", "sl"):
            values = [(a, d) for a, d in zip(args, dyn)
                      if a.lower() not in ("-path", "-literalpath", "/d", "--") and (not a.startswith("-") or a == "-")]
            if values:
                new = _resolve_dir(cwd, values[0][0], values[0][1])
                cwd = new if new != "" else cwd
                if new and new not in visited:
                    visited.append(new)
            else:
                cwd = None
            continue
        if prog == "popd":
            cwd = None
            continue
        for inner in _nested_from(prog, args):
            _collect_calls(inner, cwd, depth + 1, out, visited)
        if prog == "git":
            cdirs, override, sub, sargs, sdyn = _git_parts(args, dyn)
            call = _Call("git", sub.lower(), sargs, sdyn, _apply_cdirs(cwd, cdirs), xargs, override)
            call.cwds = _candidates(visited, cdirs, call.cwd)
            out.append(call)
        elif prog == "gh":
            words = [a for a in args if not a.startswith("-")]
            sub = " ".join(words[:2]).lower()
            call = _Call("gh", sub, args, dyn, cwd, xargs, False)
            call.cwds = _candidates(visited, [], cwd)
            out.append(call)
        if len(out) > MAX_STEPS:
            raise _ParseError("too many steps")
    for inner in nested:
        _collect_calls(inner, cwd, depth + 1, out, visited)
    return cwd


def _apply_cdirs(cwd: Optional[str], cdirs: List[Tuple[str, bool]]) -> Optional[str]:
    """The folder after git's own -C options. None = unknown, '' = a folder that does not exist."""
    current = cwd
    for d, is_dyn in cdirs:
        current = _resolve_dir(current, d, is_dyn)
        if not current:
            break
    return current


def _candidates(visited: List[str], cdirs: List[Tuple[str, bool]], current: Optional[str]) -> List[str]:
    """Folders worth checking for one step: the current one and every earlier cd target."""
    if not current:
        return []
    found = [current]
    for folder in visited:
        folded = _apply_cdirs(folder, cdirs)
        if folded and folded not in found:
            found.append(folded)
    return found


def parse_calls(command: str, cwd: str) -> List[_Call]:
    """The git and gh steps of a command, with the folder each one runs in. Raises _ParseError."""
    out: List[_Call] = []
    start = os.path.abspath(cwd) if cwd else None
    _collect_calls(command, start, 0, out, [start] if start else [])
    return out


# ---------------------------------------------------------------- file classes


def _notes_class(path: str) -> str:
    """'private' (never goes into Git), 'shareable' (allowed once share-notes is on) or ''."""
    parts = _norm(path).lower().split("/")
    if len(parts) >= 2 and parts[-1] == "settings.local.json" and parts[-2] == ".claude":
        return "private"
    for i in range(len(parts) - 1):
        if parts[i] == ".claude" and parts[i + 1] == "agent-memory":
            rest = parts[i + 2:]
            if len(rest) >= 2 and rest[0] == "tutor-data":
                sub = rest[1:]
                if sub == ["now.md"] or sub == ["learner", "profile.md"] or (sub[0] == "journal" and len(sub) >= 2):
                    return "shareable"
            return "private"
    return ""


def _skip_content(rel: str) -> bool:
    """Files whose text is never read for secrets: lockfiles, images and other binaries, build and
    vendor folders, and the tutor's own shipped folders under .claude (their text is checked by the
    MANIFEST, and they hold test patterns that look like keys)."""
    low = _norm(rel).lower()
    base = low.rsplit("/", 1)[-1]
    if base in _LOCKFILES or ".min." in base:
        return True
    if "." in base and base.rsplit(".", 1)[-1] in _BINARY_EXT:
        return True
    folders = low.split("/")[:-1]
    if any(part in _SKIP_DIRS for part in folders):
        return True
    for i, part in enumerate(folders[:-1]):
        if part == ".claude" and folders[i + 1] in _PRODUCT_DIRS:
            return True
    return False


def _decode(data: bytes) -> Optional[str]:
    """Text of a file, or None for binary data. Reads UTF-8, and UTF-16 with or without a BOM."""
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", "replace")
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16", "replace")
    if b"\x00" in data[:4096]:
        sample = data[:4096]
        if len(sample) >= 8 and sample[1::2].count(0) > len(sample) // 4:
            return data.decode("utf-16-le", "replace")
        if len(sample) >= 8 and sample[0::2].count(0) > len(sample) // 4:
            return data.decode("utf-16-be", "replace")
        return None
    return data.decode("utf-8", "replace")


# ---------------------------------------------------------------- the scan


class _Ctx(object):
    """State of one scan_staged call."""

    def __init__(self, cwd: str, limit_s: float) -> None:
        self.cwd = cwd
        self.current = cwd                  # the folder of the step being scanned
        self.limit = max(0.5, float(limit_s))
        self.deadline = time.monotonic() + self.limit
        self.secret_files: List[str] = []
        self.notes_add: List[str] = []
        self.notes_push: List[str] = []
        self.hits: List[Tuple[str, int, str, str]] = []          # (file, line, kind, where)
        self.incomplete: List[str] = []
        self.files_read = 0
        self.top_cache: Dict[str, Optional[str]] = {}
        self.done: Set[Tuple[Any, ...]] = set()

    def left(self) -> float:
        return self.deadline - time.monotonic()

    def fail(self, reason: str) -> None:
        if reason not in self.incomplete:
            self.incomplete.append(reason)


def _git(ctx: _Ctx, cwd: str, argv: List[str], max_bytes: int = MAX_DIFF_BYTES) -> Optional[Any]:
    """gitq.run_git with the time that is left. None = failed, timed out or not allowed."""
    if _gitq is None:
        return None
    remaining = ctx.left()
    if remaining <= 0.05:
        ctx.fail("the time limit of %.0f seconds ran out" % ctx.limit)
        return None
    return _gitq.run_git(cwd, argv, timeout=min(5.0, remaining), max_bytes=max_bytes)


def _toplevel(ctx: _Ctx, cwd: str) -> Optional[str]:
    """The folder that holds .git, found by walking up (no process is started)."""
    if cwd in ctx.top_cache:
        return ctx.top_cache[cwd]
    top: Optional[str] = None
    cur = os.path.abspath(cwd)
    for _ in range(40):
        if os.path.exists(os.path.join(cur, ".git")):
            top = cur
            break
        parent = os.path.dirname(cur)
        if parent == cur:
            break
        cur = parent
    ctx.top_cache[cwd] = top
    return top


def _ignored(ctx: _Ctx, cwd: str, path: str) -> bool:
    """True when the ignore rules cover this path (also for tracked files)."""
    out = _git(ctx, cwd, ["check-ignore", "-q", "--no-index", "--", path], max_bytes=1000)
    return out is not None


def _record_notes(ctx: _Ctx, top: str, path: str, bucket: List[str]) -> None:
    klass = _notes_class(path)
    if not klass:
        return
    if klass == "shareable" and not _ignored(ctx, top, path):
        return          # the learner turned share-notes on: these three kinds may be committed
    if _clean(path) not in bucket:
        bucket.append(_clean(path))


def _scan_text(ctx: _Ctx, text: str, label: str, where: str, line_of: Optional[List[Tuple[int, int]]] = None) -> None:
    """Find secrets in text and record hits (file, line, kind only). line_of maps text offsets to file line numbers."""
    scan = getattr(_secrets, "scan_text", None) if _secrets is not None else None
    if scan is None:
        scan = getattr(_secrets, "find_secrets", None) if _secrets is not None else None
    if scan is None:
        ctx.fail("the secret checker is not available")
        return
    try:
        # guard mode: only hits that are almost certainly real, documentation keys ignored
        hits = scan(text, max_bytes=max(len(text), 1)) if scan is getattr(_secrets, "scan_text", None) else scan(text)
    except Exception:
        ctx.fail("the secret checker failed")
        return
    if getattr(hits, "truncated", False) or getattr(hits, "error", ""):
        ctx.fail("the secret checker did not read all of %s" % _clean(label, 60))
    for hit in list(hits)[:20]:
        kind = _kind_of(hit)
        start = _hit_field(hit, "start", 0)
        if line_of:
            line = line_of[0][1]
            for off, ln in line_of:
                if off <= (start if isinstance(start, int) else 0):
                    line = ln
                else:
                    break
        else:
            line = text.count("\n", 0, start) + 1 if isinstance(start, int) else 0
        entry = (_clean(label, 60), line, kind, where)
        if entry not in ctx.hits:
            ctx.hits.append(entry)


def _scan_file(ctx: _Ctx, abs_path: str, rel: str, where: str) -> None:
    """Read one file that will be committed and look for secrets."""
    if _skip_content(rel):
        return
    try:
        st = os.lstat(abs_path)
    except OSError:
        return
    if stat.S_ISLNK(st.st_mode) or not stat.S_ISREG(st.st_mode):
        return
    if ctx.files_read >= MAX_FILES:
        ctx.fail("more than %d files would be added" % MAX_FILES)
        return
    if ctx.left() <= 0.05:
        ctx.fail("the time limit of %.0f seconds ran out" % ctx.limit)
        return
    ctx.files_read += 1
    try:
        with open(abs_path, "rb") as handle:
            data = handle.read(MAX_FILE_BYTES + 1)
    except OSError:
        ctx.fail("a file could not be opened (%s)" % _clean(rel, 60))
        return
    partial = len(data) > MAX_FILE_BYTES
    text = _decode(data[:MAX_FILE_BYTES])
    if text is None:
        return
    before = len(ctx.hits)
    _scan_text(ctx, text, rel, where)
    if partial and len(ctx.hits) == before:
        ctx.fail("%s is larger than 200 KB and I read only its first 200 KB" % _clean(rel, 60))


def _scan_listed_paths(ctx: _Ctx, cwd: str, paths: Sequence[str], where: str) -> None:
    """Names and contents of files that git add would stage."""
    top = _toplevel(ctx, cwd) or cwd
    for path in paths:
        rel = _norm(path)
        abs_path = os.path.join(top, rel)
        if not os.path.lexists(abs_path):
            continue           # a removal: nothing new goes into history
        if _notes_class(rel):
            _record_notes(ctx, top, rel, ctx.notes_add)
        if _is_secret_name(rel) and _clean(rel) not in ctx.secret_files:
            ctx.secret_files.append(_clean(rel))
        _scan_file(ctx, abs_path, rel, where)


def _is_secret_name(path: str) -> bool:
    if _secrets is None or not hasattr(_secrets, "is_secret_filename"):
        return False
    try:
        return bool(_secrets.is_secret_filename(path))
    except Exception:
        return False


_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _scan_diff(ctx: _Ctx, diff: Any, where: str) -> None:
    """Scan the added lines of a patch (git diff -U0 or git log -p -U0) and check the file names."""
    if getattr(diff, "truncated", False):
        ctx.fail("the changes are bigger than %d MB" % (MAX_DIFF_BYTES // (1024 * 1024)))
    text = str(diff)
    lines = text.split("\n")
    current = ""
    deleted = False
    added: List[str] = []
    offsets: List[Tuple[int, int]] = []
    size = 0
    files_seen: Set[str] = set()

    def flush() -> None:
        nonlocal added, offsets, size
        if added and not (current and _skip_content(current)):
            _scan_text(ctx, "\n".join(added), current or "(unknown file)", where, offsets)
        added = []
        offsets = []
        size = 0

    i = 0
    total = len(lines)
    while i < total:
        line = lines[i]
        if line.startswith("diff --git "):
            flush()
            deleted = False
            current = _header_path(line)
            i += 1
            continue
        if line.startswith("deleted file mode"):
            deleted = True
        elif line.startswith("+++ b/") and not current:
            current = line[6:].split("\t", 1)[0]
        elif line.startswith("@@ "):
            m = _HUNK.match(line)
            if m is not None:
                old_n = int(m.group(2)) if m.group(2) is not None else 1
                new_start = int(m.group(3))
                new_n = int(m.group(4)) if m.group(4) is not None else 1
                i += 1
                taken = 0
                skipped = 0
                while i < total and (taken < new_n or skipped < old_n):
                    row = lines[i]
                    if row.startswith("\\"):
                        i += 1
                        continue
                    if row.startswith("-") and skipped < old_n:
                        skipped += 1
                    elif row.startswith("+") and taken < new_n:
                        if size < MAX_DIFF_BYTES:
                            offsets.append((size, new_start + taken))
                            added.append(row[1:])
                            size += len(row)
                        taken += 1
                    else:
                        break
                    i += 1
                continue
        i += 1
        if current and not deleted and current not in files_seen:
            files_seen.add(current)
            if _is_secret_name(current) and _clean(current) not in ctx.secret_files:
                ctx.secret_files.append(_clean(current))
            if _notes_class(current):
                top = _toplevel(ctx, ctx.current) or ctx.current
                _record_notes(ctx, top, current, ctx.notes_add)
    flush()


def _header_path(line: str) -> str:
    """File name from 'diff --git a/x b/x'. Handles names with spaces and quoted names."""
    rest = line[len("diff --git "):]
    if rest.startswith('"'):
        m = re.match(r'^"a/((?:[^"\\]|\\.)*)"', rest)
        return m.group(1) if m else ""
    if not rest.startswith("a/"):
        return ""
    idx = 0
    best = ""
    while True:
        idx = rest.find(" b/", idx + 1)
        if idx < 0:
            break
        left, right = rest[2:idx], rest[idx + 3:]
        if left == right:
            return left
        best = right
    return best


# ---------------------------------------------------------------- git add


def _literal_pathspecs(args: List[str]) -> List[str]:
    out: List[str] = []
    after = False
    for a in args:
        if a == "--" and not after:
            after = True
            continue
        if (a.startswith("-") and not after) or a.startswith(":") or any(ch in a for ch in "*?["):
            continue
        out.append(a)
    return out


_ADD_LINE = re.compile(r"^(?:add|remove) '(.*)'$")


def _dry_run_list(ctx: _Ctx, cwd: str, args: List[str]) -> Optional[List[str]]:
    """Paths `git add <args>` would stage (nothing is staged). None = could not find out.

    When some explicit paths are ignored, Git stages the others, prints a hint and exits with 1.
    gitq.add_dry_run returns [] then, which would hide the others, so the lines are read here.
    """
    if _gitq is None:
        return None
    run = getattr(_gitq, "_run", None)
    if run is None:
        return _gitq.add_dry_run(cwd, args)
    remaining = ctx.left()
    if remaining <= 0.05:
        ctx.fail("the time limit of %.0f seconds ran out" % ctx.limit)
        return None
    res = run(cwd, ["add", "--dry-run"] + [a for a in args if a != "--dry-run"], min(5.0, remaining), MAX_DIFF_BYTES)
    if res is None:
        return None
    code, out, err = res
    if code != 0 and "ignored by one of your .gitignore" not in err:
        return None
    if getattr(out, "truncated", False):
        ctx.fail("the list of files that git add would stage is longer than %d MB" % (MAX_DIFF_BYTES // (1024 * 1024)))
    found: List[str] = []
    for line in str(out).split("\n"):
        m = _ADD_LINE.match(line.strip())
        if m is not None:
            found.append(m.group(1))
    return found


def _plan_add(ctx: _Ctx, call: _Call, cwd: str) -> None:
    if call.xargs:
        ctx.fail("git add gets its file list from another command")
        return
    if any(call.dyn):
        ctx.fail("the file list of git add is built by the shell, so I cannot see it")
        return
    if any(a in ("-n", "--dry-run") for a in call.args):
        return
    if any(a in ("-i", "--interactive", "-p", "--patch", "-e", "--edit") for a in call.args):
        # answers can be piped in (yes | git add -p), so this can stage files without a terminal
        ctx.fail("git add is interactive and I cannot see what it will stage")
        return
    key = ("add", cwd, tuple(call.args))
    if key in ctx.done:
        return
    ctx.done.add(key)
    listed = _dry_run_list(ctx, cwd, call.args)
    if listed is None:
        missing = [p for p in _literal_pathspecs(call.args) if not os.path.lexists(os.path.join(cwd, p))]
        if missing:
            return          # git add would fail on a path that does not exist: nothing is staged
        ctx.fail("Git could not list what git add would stage")
        return
    _scan_listed_paths(ctx, cwd, listed, "in files that git add would stage")


# ---------------------------------------------------------------- git commit

_COMMIT_VALUE_OPTS = frozenset((
    "-m", "-F", "-C", "-c", "-t", "--author", "--date", "--message", "--file", "--reuse-message",
    "--reedit-message", "--fixup", "--squash", "--template", "--cleanup", "--trailer", "--pathspec-from-file",
))


def _parse_commit(args: List[str], dyn: List[bool]) -> Tuple[bool, List[str], bool, bool]:
    """(all flag, paths, dynamic path, dry run)."""
    all_flag = False
    paths: List[str] = []
    dyn_path = False
    dry = False
    after_dd = False
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if after_dd:
            paths.append(a)
            dyn_path = dyn_path or dyn[i]
        elif a == "--":
            after_dd = True
        elif a in _COMMIT_VALUE_OPTS:
            i += 1
        elif a.startswith("--"):
            if a == "--all":
                all_flag = True
            elif a == "--dry-run":
                dry = True
        elif a.startswith("-") and len(a) > 1:
            cluster = a[1:]
            for k, ch in enumerate(cluster):
                if ch == "a":
                    all_flag = True
                elif ch in "mFCct":
                    if k == len(cluster) - 1:
                        i += 1
                    break
                elif ch in "Su":
                    break
        else:
            paths.append(a)
            dyn_path = dyn_path or dyn[i]
        i += 1
    return all_flag, paths, dyn_path, dry


def _has_head(ctx: _Ctx, cwd: str) -> bool:
    return _git(ctx, cwd, ["rev-parse", "--verify", "-q", "HEAD"], max_bytes=1000) is not None


def _diff(ctx: _Ctx, cwd: str, argv: List[str], what: str) -> Optional[Any]:
    out = _git(ctx, cwd, argv)
    if out is None:
        ctx.fail("Git could not show %s" % what)
    return out


def _plan_commit(ctx: _Ctx, call: _Call, cwd: str) -> None:
    all_flag, paths, dyn_path, dry = _parse_commit(call.args, call.dyn)
    if dry:
        return
    if dyn_path:
        ctx.fail("the file list of git commit is built by the shell, so I cannot see it")
        return
    key = ("commit", cwd, all_flag, tuple(paths))
    if key in ctx.done:
        return
    ctx.done.add(key)
    base = ["-U0", "--no-renames"]
    tail = ["--"] + paths if paths else []
    if all_flag or paths:
        if _has_head(ctx, cwd):
            out = _diff(ctx, cwd, ["diff", "HEAD"] + base + tail, "the changes git commit would include")
            if out is not None:
                _scan_diff(ctx, out, "in the changes git commit would include")
        else:
            for argv in (["diff", "--cached"] + base + tail, ["diff"] + base + tail):
                out = _diff(ctx, cwd, argv, "the changes git commit would include")
                if out is not None:
                    _scan_diff(ctx, out, "in the changes git commit would include")
    out = _diff(ctx, cwd, ["diff", "--cached"] + base, "the staged changes")
    if out is not None:
        _scan_diff(ctx, out, "in the staged changes")


# ---------------------------------------------------------------- git push, gh

_PUSH_VALUE_OPTS = frozenset(("-o", "--push-option", "--repo", "--receive-pack", "--exec"))


def _check_tracked_notes(ctx: _Ctx, cwd: str) -> None:
    top = _toplevel(ctx, cwd) or cwd
    if _gitq is None:
        return
    tracked = _gitq.ls_files(top, ":(glob)**/.claude/agent-memory/**", ":(glob)**/.claude/settings.local.json")
    if tracked is None:
        ctx.fail("Git could not list the tracked files")
        return
    for path in tracked:
        _record_notes(ctx, top, path, ctx.notes_push)


def _plan_push(ctx: _Ctx, args: List[str], dyn: List[bool], cwd: str, via_gh: str = "") -> None:
    key = ("push", cwd, tuple(args), via_gh)
    if key in ctx.done:
        return
    ctx.done.add(key)
    positional: List[str] = []
    flags: Set[str] = set()
    skip = False
    for a in args:
        if skip:
            skip = False
            continue
        if a in _PUSH_VALUE_OPTS:
            skip = True
        elif a.startswith("-"):
            flags.add(a.split("=", 1)[0])
        else:
            positional.append(a)
    if via_gh == "":
        if flags & {"--dry-run", "-n", "--delete", "-d"}:
            return
        if any(dyn):
            ctx.fail("the arguments of git push are built by the shell, so I cannot see them")
            return
    _check_tracked_notes(ctx, cwd)
    revs: List[str] = []
    notpart: List[str] = []
    if via_gh == "repo create":
        revs = ["HEAD"]                     # a brand-new remote: everything goes out
    elif via_gh == "pr create":
        revs = ["HEAD"]
        notpart = ["--not", "--remotes"]
    else:
        remote = positional[0] if positional else ""
        refspecs = positional[1:]
        if remote and _REMOTE_NAME.match(remote):
            scope = ["--not", "--remotes=%s" % remote]
        elif remote:
            scope = []                      # an address, not a configured remote: scan everything
        else:
            scope = None                    # decided below from the upstream
        sources: List[str] = []
        for spec in refspecs:
            src = spec.lstrip("+").split(":", 1)[0]
            if not src:
                continue                    # ":branch" deletes a remote branch
            if src.startswith("-") or not _REV_NAME.match(src):
                ctx.fail("I cannot read the branch name in the push command")
                return
            sources.append(src)
        if sources:
            revs.extend(sources)
        else:
            revs.append("HEAD")             # a plain push, or --tags alone: scan the current branch too
        if flags & {"--all", "--mirror"}:
            revs.append("--branches")
        if flags & {"--tags", "--mirror"}:
            revs.append("--tags")
        if scope is None:
            up = _gitq.upstream(cwd) if _gitq is not None else None
            if up and revs == ["HEAD"]:
                revs = ["%s..HEAD" % up]
                scope = []
            else:
                scope = ["--not", "--remotes"]
        notpart = scope
    argv = ["log", "-p", "-U0", "--no-renames", "--max-count=%d" % MAX_COMMITS, "--format=commit %H"] + revs + notpart + ["--"]
    out = _git(ctx, cwd, argv)
    if out is None:
        if not _has_head(ctx, cwd):
            return          # no commit yet: there is nothing to push
        ctx.fail("Git could not list the commits that would be pushed")
        return
    _scan_diff(ctx, out, "in commits that would be pushed")
    commits = len(re.findall(r"(?m)^commit [0-9a-f]{7,64}$", str(out)))
    if commits >= MAX_COMMITS:
        count = _git(ctx, cwd, ["log", "--format=%H", "--max-count=%d" % (MAX_COMMITS + 1)] + revs + notpart + ["--"],
                     max_bytes=64 * 1024)
        if count is None or len([ln for ln in str(count).split("\n") if ln.strip()]) > MAX_COMMITS:
            ctx.fail("more than %d commits would be pushed" % MAX_COMMITS)


# ---------------------------------------------------------------- entry point


def _finding(rule_id: str, tier: str, detail: str) -> Dict[str, str]:
    return {"rule_id": rule_id, "tier": tier, "message_key": rule_id, "detail": detail}


def _collect_findings(ctx: _Ctx) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    if ctx.secret_files:
        out.append(_finding(RULE_SECRET_FILE, "block", "Files: %s." % _join_limited(ctx.secret_files, 8, ", ")))
    if ctx.hits:
        # the most useful words come first: the guard shows only the first 90 characters of a detail
        items = ["%s line %d: %s" % (h[0], h[1], h[2]) for h in ctx.hits]
        places = sorted(set(h[3] for h in ctx.hits))
        tail = " (%s)" % places[0] if len(places) == 1 else ""
        out.append(_finding(RULE_SECRET_CONTENT, "block", _join_limited(items, 5) + tail + "."))
    if ctx.notes_add:
        out.append(_finding(RULE_NOTES_ADD, "block", "Files: %s." % _join_limited(ctx.notes_add, 6, ", ")))
    if ctx.notes_push:
        out.append(_finding(RULE_NOTES_PUSH, "block", "Tracked: %s." % _join_limited(ctx.notes_push, 6, ", ")))
    if ctx.incomplete:
        out.append(_finding(RULE_INCOMPLETE, "ask", "I could not check for secrets: %s." % _join_limited(ctx.incomplete, 3)))
    return out


def scan_staged(cwd: str, command: str, limit_s: float = TOTAL_SECONDS) -> List[Dict[str, str]]:
    """Findings for the git and gh steps in `command`. [] when there is nothing to report.

    cwd      the project folder (the folder the command starts in)
    command  the shell command text of the tool call
    limit_s  seconds for the whole scan (the caller may pass less than 5 when its own budget is short)
    """
    try:
        return _scan(cwd, command, limit_s)
    except Exception as exc:                      # never raise into the hook
        return [_finding(RULE_INCOMPLETE, "ask", "I could not check for secrets: the scanner failed (%s)." % type(exc).__name__)]


def _read_aliases(ctx: _Ctx, folder: str) -> Dict[str, str]:
    out = _git(ctx, folder, ["config", "--get-regexp", "^alias[.]"], max_bytes=64 * 1024)
    aliases: Dict[str, str] = {}
    if out is None:
        return aliases
    for line in str(out).split("\n"):
        key, _sep, value = line.partition(" ")
        if key.lower().startswith("alias."):
            aliases[key[6:].lower()] = value.strip()
    return aliases


def _expand_aliases(ctx: _Ctx, calls: List[_Call]) -> None:
    """Replace a git alias (git ci -m x) by the command it stands for, so add, commit and push are still seen."""
    cache: Dict[str, Dict[str, str]] = {}
    for call in calls:
        for _ in range(3):
            if call.prog != "git" or not call.sub or call.sub in _GIT_KNOWN or not call.cwds or call.redirected_git_dir:
                break
            folder = call.cwds[0]
            if not os.path.isdir(folder) or not _gitq.is_repo(folder):
                break
            if folder not in cache:
                cache[folder] = _read_aliases(ctx, folder)
            value = cache[folder].get(call.sub)
            if value is None:
                break
            if value.startswith("!"):
                if re.search(r"(?i)\bgit\b|\bgh\b", value):
                    ctx.fail("the Git alias %s runs a shell command" % _clean(call.sub, 20))
                break
            try:
                segs, _nested = _lex(value, False)
            except _ParseError:
                ctx.fail("the Git alias %s could not be read" % _clean(call.sub, 20))
                break
            words = [w for seg in segs for (w, _d) in seg]
            if not words:
                break
            call.args = words[1:] + call.args
            call.dyn = [False] * (len(words) - 1) + call.dyn
            call.sub = words[0].lower()


def _scan(cwd: str, command: str, limit_s: float) -> List[Dict[str, str]]:
    if not isinstance(command, str) or not command.strip() or _TRIGGER.search(command) is None:
        return []
    ctx = _Ctx(cwd, limit_s)
    if len(command) > MAX_COMMAND_CHARS:
        ctx.fail("the command is longer than %d characters" % MAX_COMMAND_CHARS)
        return _collect_findings(ctx)
    try:
        calls = parse_calls(command, cwd)
    except _ParseError as exc:
        # The trigger regex is broad (any "git" word), so this ask can also hit a command that only
        # mentions git; a command that does not close its quotes would fail in the shell as well.
        ctx.fail("the command could not be read (%s)" % _PARSE_REASONS.get(str(exc), "it has an unusual shape"))
        return _collect_findings(ctx)
    if _gitq is not None and limit_s >= 0.3:
        _expand_aliases(ctx, calls)
    relevant = [c for c in calls if (c.prog == "git" and c.sub in ("add", "commit", "push")) or
                (c.prog == "gh" and (c.sub == "repo create" or c.sub == "pr create"))]
    if not relevant:
        return _collect_findings(ctx)
    if _gitq is None or _secrets is None or not (hasattr(_secrets, "scan_text") or hasattr(_secrets, "find_secrets")):
        ctx.fail("a part of the checker is missing")
        return _collect_findings(ctx)
    if _GIT_ENV.search(command) is not None:
        ctx.fail("GIT_DIR or GIT_WORK_TREE points git at another folder")
    if limit_s < 0.3:
        ctx.fail("the hook had no time left for the check")
        return _collect_findings(ctx)
    if len(relevant) > MAX_CALLS:
        ctx.fail("the command has more than %d git steps" % MAX_CALLS)
        relevant = relevant[:MAX_CALLS]
    for call in relevant:
        if call.redirected_git_dir:
            ctx.fail("git is pointed at another folder with --git-dir or --work-tree")
            continue
        if call.cwd is None:
            ctx.fail("I cannot tell which folder the git command runs in")
            continue
        for folder in call.cwds:
            if not os.path.isdir(folder) or not _gitq.is_repo(folder):
                continue                          # no folder or not a repository: git fails by itself
            ctx.current = folder
            if call.prog == "git" and call.sub == "add":
                _plan_add(ctx, call, folder)
            elif call.prog == "git" and call.sub == "commit":
                _plan_commit(ctx, call, folder)
            elif call.prog == "git" and call.sub == "push":
                _plan_push(ctx, call.args, call.dyn, folder)
            elif call.prog == "gh" and call.sub == "repo create":
                if "--push" in call.args:
                    _plan_push(ctx, [], [], folder, via_gh="repo create")
            elif call.prog == "gh" and call.sub == "pr create":
                _plan_push(ctx, [], [], folder, via_gh="pr create")
    return _collect_findings(ctx)


def all_regexes() -> List["re.Pattern[str]"]:
    """Every compiled expression of this module (the selftest fuzzes each one)."""
    return [v for v in list(globals().values()) if isinstance(v, re.Pattern)]
