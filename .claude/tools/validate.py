"""validate.py - checks that the tutor files are well-formed, consistent and inside the context budget.

What: one command that reads every shipped file and prints ERROR and WARN lines in plain words, then
"RESULT: N errors, M warnings". It checks the skills, agents, rules and output style (with a real
front-matter reader that follows the rules Claude Code applies), the fixed-context budget, the knowledge
files, pointers between files, label strings, the docs, text hygiene, the concept index and MANIFEST.txt.
Why: Claude Code drops a skill or agent with broken front matter without a message, and a fixed-context
file that grows too large costs every learner money and attention. A script finds these mistakes, not a reader.
Usage: python validate.py [--root DIR] [--quick] [--release] [--no-runtime-data]
                          [--write-index] [--write-manifest] [--write-commands]
  --quick            skips the documentation link walk (everything else still runs)
  --release          also needs docs, MANIFEST.txt, settings.json and every file of the layout; no runtime data;
                     no 'TO FILL AT RELEASE:' text in the README files, CHANGELOG.md or docs
  --no-runtime-data  ERROR if agent-memory/, caches, settings.local.json, *.tutor-backup or *.new exist
  --write-index      regenerates knowledge/concepts-index.txt
  --write-manifest   regenerates MANIFEST.txt (sha256 of every shipped file); run it last
  --write-commands   regenerates the skill table inside docs/commands.md
Exit code: 0 when there is no ERROR line (WARN lines never fail), 1 on any ERROR, 2 on a bad command line.
How it fails safely: a check that crashes is reported as one ERROR line (a bug in this script), never as a
crash; a missing folder is a finding. It writes only the three generated files above, only when asked.
No network, standard library only, Python 3.9 syntax. Who calls it: people, selftest.py (module "validate"),
selftest_files.py, doctor.py verify, CI, the release steps of the main agent.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import re
import runpy
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ROOT = os.path.dirname(HERE)

# --------------------------------------------------------------------------- constants

SKILL_NAMES = ("tutor", "tutor-setup", "learn", "progress", "explain", "think-first", "new-project", "fix-it",
               "save-point", "before-push", "git-rescue")
AGENT_NAMES = ("architecture-reviewer", "code-reviewer")
RULE_NAMES = ("clear-writing", "checking-facts", "safety", "design-gate", "keeping-memory", "tidy-project")
HANDLER_NAMES = ("session_start", "user_prompt", "pre_tool", "post_tool", "stop", "subagent_start")
LIB_NAMES = ("paths", "clock", "fsio", "hookio", "config", "text", "untrusted", "secrets", "guardrules", "archrules",
             "chatlog", "learner", "knowledge", "ledger", "activity", "tree", "gitq")
TEMPLATE_NAMES = ("now", "journal-entry", "decision-record", "learner-profile", "claude-md")
DOC_NAMES = ("getting-started", "commands", "how-it-works", "customize", "troubleshooting", "faq")

SKILL_FIELDS = ("name", "description", "when_to_use", "argument-hint", "allowed-tools")
AGENT_FIELDS = ("name", "description", "tools", "model", "maxTurns")
STYLE_FIELDS = ("name", "description", "keep-coding-instructions")
SKILL_DESC_MAX = 210
SKILL_DESC_TOTAL_MAX = 2300
AGENT_DESC_MAX = 250
SKILL_LINES_MAX = 300
SKILL_KEY_LINES = 80
RULE_WORDS_MAX = 360
RULES_TOTAL_WORDS_MAX = 1800
STYLE_WORDS_MAX = 1420
CLAUDE_MD_WORDS_MAX = 780
CLAUDE_MD_LINES_MAX = 55
MILESTONES_LINES_MAX = 120
TOKENS_PER_WORD = 1.35
CAPSULE_ALLOWANCE_TOKENS = 300
TOKEN_ERROR_ABOVE = 7000
TOKEN_WARN_ABOVE = 6300
PATH_RELATIVE_MAX = 120       # ".claude/" + path inside the product; leaves room for the project folder
PATH_ABSOLUTE_MAX = 239       # the whole path must stay under 240 characters (Windows limit)
INDEX_LINE_MAX_BYTES = 399    # "under 400 characters per line"
COMMANDS_SENTENCE_MAX = 140

FORBIDDEN_PHRASES_ANY_CASE = ("without asking", "always allowed", "pre-approved")
FORBIDDEN_PHRASES_EXACT = ("CRITICAL", "YOU MUST", "IMPORTANT:")

CONCEPT_KEYS = ["id", "title", "domain", "tier", "needs", "terms", "signals", "plain", "check", "check_type", "rubric",
                "try", "pitfall", "volatile", "src", "verified"]
CHECK_TYPES = ("explain", "predict", "do", "debug", "review")
DOMAIN_TARGETS = {"term": 10, "files": 6, "git": 16, "gh": 10, "cc": 18, "prog": 14, "web": 6, "data": 4, "test": 8,
                  "sec": 8, "arch": 10, "proj": 6, "ai": 4}
GLOSSARY_KEYS = ["term", "aliases", "plain", "domain", "jargon"]
PROBE_KEYS = ["id", "question", "options", "misconceptions", "correct"]
CONCEPT_PLAIN_MAX_WORDS = 35
GLOSSARY_PLAIN_MAX_WORDS = 25
YESNO_START = re.compile(r"^\s*(do|does|did|is|are|was|were|can|could|will|would|should|have|has)\s+(you|it|this|that|they)\b", re.I)
ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)+$")

GITIGNORE_LINES = ("agent-memory/tutor-data/", "settings.local.json", "*.tutor-backup", "__pycache__/", "*.pyc")

BINARY_EXT = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".gz", ".pdf", ".woff", ".woff2", ".ttf")

# Backticked words that look like a concept id but are not one (pointer check). One reason per entry.
ID_LOOKALIKES = {
    "git-rescue": "name of a skill, not a concept card",
}
# Product folders: a backticked path that starts with one of these must exist (pointer check).
# Paths that start with anything else (src/, css/, tests/) are examples about the learner's project.
PRODUCT_NAMESPACES = ("skills", "rules", "agents", "hooks", "knowledge", "templates", "tools", "docs", "output-styles",
                      "references", "handlers", "lib")
# Paths that exist only on the learner's computer at run time (the pointer check does not look for them).
# One reason per entry.
RUNTIME_NAMESPACES = {
    "agent-memory": "the folder where notes and learner data are created at run time",
    "tutor-data": "the data folder inside agent-memory",
    "learner": "profile.md, notes.md and progress.jsonl inside the data folder",
    "journal": "the dated journal files inside the data folder",
    "inbox": "the inbox files the model writes and the hook consumes",
    "state": "ledger, activity and state files written by the hooks",
    "chat": "the optional chat copy written by the hooks",
}
RUNTIME_FILES = {
    "settings.local.json": "a file of the learner's computer only; git ignores it",
    "settings.json.tutor-backup": "the backup that doctor.py enable-hooks writes",
}
PROJECT_RUNTIME_PREFIXES = {
    "docs/decisions": "the learner's own decision records (outside .claude)",
}
POINTER_EXTENSIONS = (".md", ".json", ".jsonl", ".py", ".txt")

REQUIRED_ROOT_FILES = ("README.md", "CLAUDE.md", "VERSION", "CHANGELOG.md", "MANIFEST.txt", ".gitignore", "settings.json",
                       "settings.json.explained.md")
EXPECTED_DIAGRAMS = (("a", "files and paths"), ("b", "memory and disk"), ("c", "git's four places"),
                     ("d", "request and response"), ("e", "claude code loop"))
LABEL_LANGUAGES = (("English", "en"), ("Turkish", "tr"), ("Spanish", "es"), ("German", "de"), ("French", "fr"))
OFFER_LABEL = "Next I can teach:"
PLACEHOLDER = "TO FILL AT RELEASE:"        # the release gap marker; it may not reach the learner's pages

BROAD_TOOL_WORDS = ("Bash", "PowerShell", "Write", "Edit", "NotebookEdit")      # MultiEdit is not a Claude Code tool
MUTATING_GIT = ("add", "commit", "push", "reset", "clean", "rm", "mv", "checkout", "switch", "restore", "rebase", "merge",
                "tag", "init", "pull", "fetch", "cherry-pick", "revert", "apply")
READ_TOOLS = ("Read", "Grep", "Glob")
WEB_TOOLS = ("WebFetch", "WebSearch")
WRITE_TOOLS = ("Write", "Edit", "Bash", "PowerShell", "NotebookEdit", "Agent", "Task")


# --------------------------------------------------------------------------- output

def say(text: str = "") -> None:
    """Print one line as UTF-8 bytes (a Windows console with cp1252 must not crash on non-ASCII)."""
    data = (text + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except (AttributeError, ValueError, OSError):
        try:
            sys.stdout.write(data.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 - printing must never raise
            pass


class Report(object):
    """Collects ERROR and WARN lines and informational notes."""

    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.notes: List[str] = []

    def error(self, where: str, message: str) -> None:
        line = "ERROR %s: %s" % (where, message)
        if line not in self.errors:
            self.errors.append(line)

    def warn(self, where: str, message: str) -> None:
        line = "WARN %s: %s" % (where, message)
        if line not in self.warnings:
            self.warnings.append(line)

    def note(self, line: str) -> None:
        self.notes.append(line)


# --------------------------------------------------------------------------- the product folder

def _is_link(path: str) -> bool:
    """True for a symbolic link or a Windows junction (not for a OneDrive placeholder, which also has a reparse point)."""
    try:
        if os.path.islink(path):
            return True
        st = os.lstat(path)
        if not getattr(st, "st_file_attributes", 0) & 0x400:        # FILE_ATTRIBUTE_REPARSE_POINT
            return False
        tag = getattr(st, "st_reparse_tag", None)
        if tag is not None:
            return tag in (0xA000000C, 0xA0000003)                  # symbolic link, mount point (junction)
        return os.path.normcase(os.path.realpath(path)) != os.path.normcase(os.path.abspath(path))
    except OSError:
        return False


def _is_runtime_file(name: str) -> bool:
    return name == "settings.local.json" or name.endswith((".pyc", ".tutor-backup", ".new"))


class Product(object):
    """The files of one .claude folder (shipped files only; runtime artefacts are listed apart)."""

    def __init__(self, root: str, only: Optional[Set[str]] = None) -> None:
        self.root = os.path.abspath(root)
        self.files: List[str] = []         # shipped files, forward slashes, sorted
        self.runtime: List[str] = []       # runtime artefacts that should not ship
        self.links: List[str] = []         # symlinks and junctions
        self.only = only                   # when given, only these paths count as ours (an installed copy)
        self._raw: Dict[str, Optional[bytes]] = {}
        self._text: Dict[str, Optional[str]] = {}
        self.exists = os.path.isdir(self.root)
        if self.exists:
            self._scan()
            if only is not None:
                self.files = [f for f in self.files if f in only]
                self.runtime = []
                self.links = [l for l in self.links if l.rstrip("/") in only]

    def _scan(self) -> None:
        for dirpath, dirnames, filenames in os.walk(self.root, topdown=True, followlinks=False):
            rel_dir = os.path.relpath(dirpath, self.root).replace("\\", "/")
            rel_dir = "" if rel_dir == "." else rel_dir
            keep = []
            for name in sorted(dirnames):
                full = os.path.join(dirpath, name)
                rel = (rel_dir + "/" + name) if rel_dir else name
                if name in ("agent-memory", "__pycache__"):
                    self.runtime.append(rel + "/")
                    continue
                if _is_link(full):
                    self.links.append(rel + "/")
                    continue
                keep.append(name)
            dirnames[:] = keep
            for name in sorted(filenames):
                rel = (rel_dir + "/" + name) if rel_dir else name
                full = os.path.join(dirpath, name)
                if _is_link(full):
                    self.links.append(rel)
                    continue
                if _is_runtime_file(name):
                    self.runtime.append(rel)
                    continue
                self.files.append(rel)
        self.files.sort()

    def join(self, rel: str) -> str:
        return os.path.join(self.root, *rel.split("/"))

    def has(self, rel: str) -> bool:
        return rel in self._file_set()

    def _file_set(self) -> Set[str]:
        cached = getattr(self, "_set", None)
        if cached is None:
            cached = set(self.files)
            self._set = cached
        return cached

    def raw(self, rel: str) -> Optional[bytes]:
        if rel not in self._raw:
            try:
                with open(self.join(rel), "rb") as handle:
                    self._raw[rel] = handle.read()
            except OSError:
                self._raw[rel] = None
        return self._raw[rel]

    def text(self, rel: str) -> Optional[str]:
        """The file as text (a leading BOM is dropped, line endings are kept); None when unreadable."""
        if rel not in self._text:
            data = self.raw(rel)
            value = None
            if data is not None:
                try:
                    value = data.decode("utf-8")
                    if value.startswith("\ufeff"):
                        value = value[1:]
                except UnicodeDecodeError:
                    value = None
            self._text[rel] = value
        return self._text[rel]

    def files_under(self, prefix: str, suffix: str = "") -> List[str]:
        return [f for f in self.files if f.startswith(prefix) and f.endswith(suffix)]


def installed_mode() -> bool:
    """True when install.py runs the quick self-test on a copy inside a learner's project (it sets this variable).

    In that copy settings.json is merged with the learner's own settings and the folder may hold files of their
    own, so only the files listed in MANIFEST.txt are checked, and the exact-content rules are relaxed."""
    return os.environ.get("TUTOR_IN_INSTALL_SELFTEST") == "1"


def manifest_paths(root: str) -> Optional[Set[str]]:
    """The paths listed in MANIFEST.txt, or None when there is no readable manifest."""
    try:
        with open(os.path.join(root, "MANIFEST.txt"), "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    found = set()
    for line in text.split("\n"):
        match = re.match(r"^[0-9a-f]{64}  (\S.*)$", line)
        if match:
            found.add(match.group(1))
    return found or None


def open_product(root: str) -> "Product":
    """The Product for `root`; in installed mode limited to the files the manifest lists."""
    if installed_mode():
        paths = manifest_paths(root)
        if paths:
            return Product(root, only=paths | {"MANIFEST.txt"})
    return Product(root)


def words(text: str) -> int:
    return len(text.split())


def tokens_for(word_count: int) -> int:
    return int(math.ceil(TOKENS_PER_WORD * word_count))


# --------------------------------------------------------------------------- front-matter reader

class FrontMatter(object):
    """Result of reading the --- block at the top of a Markdown file."""

    def __init__(self) -> None:
        self.present = False
        self.data: Dict[str, Any] = {}      # key -> str or list of str
        self.style: Dict[str, str] = {}     # key -> plain single double folded literal flow list empty
        self.indicator: Dict[str, str] = {}  # key -> ">-" and so on for block scalars
        self.errors: List[Tuple[int, str]] = []
        self.end_line = 0
        self.body = ""
        self.body_first_line = 1


_KEY_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_.-]*)[ \t]*:(?:[ \t]+(.*))?$")
_BLOCK_RE = re.compile(r"^([>|])([+-]?)([1-9]?)([+-]?)[ \t]*(?:#.*)?$")
_ESC_SIMPLE = {"0": "\0", "a": "\a", "b": "\b", "t": "\t", "\t": "\t", "n": "\n", "v": "\v", "f": "\f", "r": "\r",
               "e": "\x1b", " ": " ", '"': '"', "/": "/", "\\": "\\", "N": "\x85", "_": "\xa0", "L": "\u2028",
               "P": "\u2029"}
_HEX = {"x": 2, "u": 4, "U": 8}


def parse_front_matter(text: str) -> FrontMatter:
    """Read the front matter the way Claude Code does (a YAML subset). Problems go to .errors as (line, message)."""
    fm = FrontMatter()
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n")
    lines = text.split("\n")
    if not lines or lines[0].rstrip() != "---":
        fm.errors.append((1, "front matter must start on line 1 with a line that holds only ---"))
        fm.body = text
        return fm
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].rstrip() == "---":
            end = idx
            break
    if end is None:
        fm.errors.append((1, "front matter is not closed by a line that holds only ---"))
        fm.body = text
        return fm
    fm.present = True
    fm.end_line = end + 1
    fm.body = "\n".join(lines[end + 1:])
    fm.body_first_line = end + 2
    block = lines[1:end]
    for offset, line in enumerate(block):
        # Claude Code ends the block at the FIRST "---" it finds, even in the middle of a line.
        if "---" in line:
            fm.errors.append((offset + 2, "the text --- inside front matter can end the block early; reword it"))
    _parse_block(block, 2, fm)
    return fm


def _parse_block(lines: List[str], base: int, fm: FrontMatter) -> None:
    i, n = 0, len(lines)
    while i < n:
        raw = lines[i]
        ln = base + i
        if not raw.strip() or raw.lstrip().startswith("#"):
            i += 1
            continue
        if raw[0] in " \t":
            fm.errors.append((ln, "this line is indented but belongs to no key"))
            i += 1
            continue
        match = _KEY_RE.match(raw.rstrip())
        if not match:
            fm.errors.append((ln, "cannot read this line as 'key: value'"))
            i += 1
            continue
        key, val = match.group(1), match.group(2) or ""
        if key in fm.data:
            fm.errors.append((ln, "the key '%s' appears twice" % key))
        i = _parse_value(lines, i, base, key, val.strip(), fm)


def _parse_value(lines: List[str], i: int, base: int, key: str, val: str, fm: FrontMatter) -> int:
    n = len(lines)
    ln = base + i
    if val == "" or val.startswith("#"):
        return _parse_empty_or_list(lines, i, base, key, fm)
    block = _BLOCK_RE.match(val)
    if block:
        return _parse_block_scalar(lines, i, base, key, val, block, fm)
    if val[0] in "\"'":
        text, rest, last = _read_quoted(val, lines, i, base, fm)
        rest_s = rest.strip()
        if rest_s and not (rest_s.startswith("#") and rest[:1] in " \t"):
            if val[0] == '"':
                fm.errors.append((base + last, "text follows the closing double quote of '%s'; write an inner quote as \\\" "
                                  "or use a folded block (%s: >-)" % (key, key)))
            else:
                fm.errors.append((base + last, "text follows the closing single quote of '%s'; write an inner quote as ''" % key))
        fm.data[key] = text
        fm.style[key] = "double" if val[0] == '"' else "single"
        return last + 1
    if val[0] == "[":
        items, last = _read_flow_seq(val, lines, i, base, fm)
        fm.data[key] = items
        fm.style[key] = "flow"
        return last + 1
    if val[0] == "{":
        fm.errors.append((ln, "'%s' is a flow mapping { }; this kit does not use them" % key))
        fm.data[key] = val
        fm.style[key] = "flow"
        return i + 1
    # plain scalar, possibly continued on indented lines
    parts = [_plain_scalar(val, ln, key, fm)]
    j = i + 1
    while j < n:
        nxt = lines[j]
        if nxt.strip() == "":
            k = j
            while k < n and lines[k].strip() == "":
                k += 1
            if k < n and lines[k][0] in " \t" and not lines[k].lstrip().startswith("#"):
                j = k
                continue
            break
        if nxt[0] not in " \t":
            break
        if nxt.lstrip().startswith("#"):
            j += 1
            continue
        parts.append(_plain_scalar(nxt.strip(), base + j, key, fm, continuation=True))
        j += 1
    fm.data[key] = " ".join(p for p in parts if p)
    fm.style[key] = "plain"
    return j


def _plain_scalar(text: str, ln: int, key: str, fm: FrontMatter, continuation: bool = False) -> str:
    cut = text.find(" #")
    if cut >= 0:
        text = text[:cut]
    text = text.strip()
    if not text:
        return ""
    first = text[0]
    if not continuation:
        if first in "]},&*!%@`>|":
            fm.errors.append((ln, "a plain value for '%s' cannot start with %s; put it in quotes or use a folded block" % (key, first)))
        elif text[:2] in ("- ", "? ") or text == "-":
            fm.errors.append((ln, "a plain value for '%s' cannot start with '%s'" % (key, text[:1])))
    if re.search(r":(?:\s|$)", text):
        fm.errors.append((ln, "the plain value for '%s' contains ': ' and Claude Code reads it as a new key; "
                          "put it in quotes or use a folded block (%s: >-)" % (key, key)))
    return text


def _parse_empty_or_list(lines: List[str], i: int, base: int, key: str, fm: FrontMatter) -> int:
    n = len(lines)
    j = i + 1
    items: List[str] = []
    saw_item = False
    while j < n:
        line = lines[j]
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            j += 1
            continue
        if stripped.startswith("- ") or stripped == "-":
            saw_item = True
            item = stripped[1:].strip()
            if item[:1] in ("'", '"'):
                text, rest, _ = _read_quoted(item, [item], 0, base + j, fm)
                items.append(text)
            else:
                if re.match(r"^[A-Za-z_][\w-]*:(?:\s|$)", item):
                    fm.errors.append((base + j, "a list item of '%s' holds a mapping; this kit does not use them" % key))
                items.append(_plain_scalar(item, base + j, key, fm, continuation=True))
            j += 1
            continue
        if line[0] in " \t":
            if not saw_item:
                fm.errors.append((base + j, "'%s' holds a nested mapping; this kit does not use them" % key))
            j += 1
            continue
        break
    if saw_item:
        fm.data[key] = items
        fm.style[key] = "list"
    else:
        fm.data[key] = ""
        fm.style[key] = "empty"
    return j


def _parse_block_scalar(lines: List[str], i: int, base: int, key: str, val: str, match: Any, fm: FrontMatter) -> int:
    n = len(lines)
    kind = match.group(1)
    chomp = "-" if "-" in (match.group(2) + match.group(4)) else ("+" if "+" in (match.group(2) + match.group(4)) else "")
    j = i + 1
    chunk: List[str] = []
    while j < n:
        line = lines[j]
        if line.strip() == "":
            chunk.append("")
            j += 1
            continue
        if line[0] in " \t":
            if line[0] == "\t":
                fm.errors.append((base + j, "a tab is used as indentation; YAML allows only spaces"))
            chunk.append(line)
            j += 1
            continue
        break
    while chunk and chunk[-1] == "":
        chunk.pop()
    indent = min([len(c) - len(c.lstrip(" \t")) for c in chunk if c.strip()] or [0])
    body = [c[indent:] if c.strip() else "" for c in chunk]
    if not any(body):
        fm.errors.append((base + i, "the block value of '%s' is empty" % key))
    if kind == ">":
        paragraphs: List[str] = []
        current: List[str] = []
        for text in body:
            if text == "":
                if current:
                    paragraphs.append(" ".join(current))
                    current = []
            else:
                current.append(text.strip())
        if current:
            paragraphs.append(" ".join(current))
        value = "\n".join(paragraphs)
        style = "folded"
    else:
        value = "\n".join(body)
        style = "literal"
    if chomp != "-" and value:
        value += "\n"
    fm.data[key] = value
    fm.style[key] = style
    fm.indicator[key] = kind + chomp
    return j


def _read_quoted(first: str, lines: List[str], i: int, base: int, fm: FrontMatter) -> Tuple[str, str, int]:
    """Read a quoted scalar that starts with first[0]. Returns (value, text after the closing quote, last line index)."""
    quote = first[0]
    line = first[1:]
    buf: List[str] = []
    cur = i
    pos = 0
    while True:
        while pos < len(line):
            ch = line[pos]
            if quote == '"' and ch == "\\":
                nxt = line[pos + 1:pos + 2]
                if nxt == "":
                    pos += 1       # backslash at the end of a line joins the next line
                    continue
                if nxt in _ESC_SIMPLE:
                    buf.append(_ESC_SIMPLE[nxt])
                    pos += 2
                    continue
                if nxt in _HEX:
                    digits = line[pos + 2:pos + 2 + _HEX[nxt]]
                    if len(digits) == _HEX[nxt] and re.match(r"^[0-9a-fA-F]+$", digits):
                        try:
                            buf.append(chr(int(digits, 16)))
                        except (ValueError, OverflowError):
                            fm.errors.append((base + cur, "the escape \\%s%s is not a valid character" % (nxt, digits)))
                        pos += 2 + _HEX[nxt]
                        continue
                fm.errors.append((base + cur, "the escape \\%s is not valid inside double quotes (write \\\\ for a backslash)" % nxt))
                pos += 2
                continue
            if quote == '"' and ch == '"':
                return "".join(buf), line[pos + 1:], cur
            if quote == "'" and ch == "'":
                if line[pos + 1:pos + 2] == "'":
                    buf.append("'")
                    pos += 2
                    continue
                return "".join(buf), line[pos + 1:], cur
            buf.append(ch)
            pos += 1
        cur += 1
        if cur >= len(lines) or (lines[cur] and lines[cur][0] not in " \t") or not lines[cur].strip():
            fm.errors.append((base + i, "a quoted value is not closed on the same or an indented next line"))
            return "".join(buf), "", min(cur, len(lines)) - 1 if cur > i else i
        if not (buf and buf[-1] == ""):
            buf.append(" ")
        line = lines[cur].strip()
        pos = 0


def _read_flow_seq(first: str, lines: List[str], i: int, base: int, fm: FrontMatter) -> Tuple[List[str], int]:
    buf = first
    cur = i
    while True:
        end = _matching_bracket(buf)
        if end >= 0:
            break
        cur += 1
        if cur >= len(lines) or not lines[cur].strip() or lines[cur][0] not in " \t":
            fm.errors.append((base + i, "a [ ] list is not closed"))
            return [], max(i, cur - 1)
        buf += " " + lines[cur].strip()
    rest = buf[end + 1:]
    if rest.strip() and not rest.lstrip().startswith("#"):
        fm.errors.append((base + cur, "text follows the closing ] of a list"))
    inner = buf[1:end]
    items: List[str] = []
    for piece in _split_flow(inner):
        piece = piece.strip()
        if not piece:
            continue
        if piece[0] in "\"'":
            text, after, _ = _read_quoted(piece, [piece], 0, base + i, fm)
            if after.strip():
                fm.errors.append((base + i, "text follows a quoted item inside a [ ] list"))
            items.append(text)
        else:
            if re.search(r":(?:\s|$)", piece):
                fm.errors.append((base + i, "a list item contains ': ' and is read as a mapping"))
            items.append(piece)
    return items, cur


def _matching_bracket(text: str) -> int:
    depth = 0
    quote = ""
    pos = 0
    while pos < len(text):
        ch = text[pos]
        if quote:
            if quote == '"' and ch == "\\":
                pos += 2
                continue
            if ch == quote:
                if quote == "'" and text[pos + 1:pos + 2] == "'":
                    pos += 2
                    continue
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    return -1


def _split_flow(text: str) -> List[str]:
    out: List[str] = []
    depth = 0
    quote = ""
    current: List[str] = []
    pos = 0
    while pos < len(text):
        ch = text[pos]
        if quote:
            current.append(ch)
            if quote == '"' and ch == "\\" and pos + 1 < len(text):
                current.append(text[pos + 1])
                pos += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            current.append(ch)
        elif ch in "[{":
            depth += 1
            current.append(ch)
        elif ch in "]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(current))
            current = []
        else:
            current.append(ch)
        pos += 1
    out.append("".join(current))
    return out


def as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, str):
        if value.strip().lower() in ("true", "yes", "on"):
            return True
        if value.strip().lower() in ("false", "no", "off"):
            return False
    return None


def as_list(value: Any) -> List[str]:
    """A tools-style value as a list: a YAML list, or a string split on commas and white space."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [p for p in re.split(r"[,\s]+", value) if p]
    return []


def split_rule_tokens(text: str) -> List[str]:
    """Split an allowed-tools string such as 'Bash(git status *) Bash(git log *)' at spaces outside parentheses."""
    out, depth, cur = [], 0, []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if ch.isspace() and depth == 0:
            if cur:
                out.append("".join(cur))
                cur = []
        else:
            cur.append(ch)
    if cur:
        out.append("".join(cur))
    return out


# --------------------------------------------------------------------------- shared context

class Ctx(object):
    """Everything the checks share."""

    def __init__(self, prod: Product, rep: Report, quick: bool, release: bool, no_runtime: bool) -> None:
        self.prod = prod
        self.rep = rep
        self.quick = quick
        self.release = release
        self.no_runtime = no_runtime
        self.skills: Dict[str, Dict[str, Any]] = {}
        self.agents: Dict[str, Dict[str, Any]] = {}
        self.concept_ids: Set[str] = set()
        self.concepts: List[Tuple[str, int, Dict[str, Any]]] = []     # (file name, line, object)
        self.budget_rows: List[Tuple[str, int, int]] = []


def read_jsonl(prod: Product, rel: str, rep: Report) -> List[Tuple[int, Any]]:
    """[(line number, parsed object)] for every non-blank line; JSON problems become ERROR lines."""
    text = prod.text(rel)
    if text is None:
        rep.error(rel, "cannot read the file as UTF-8 text")
        return []
    rows: List[Tuple[int, Any]] = []
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
        if not line.strip():
            continue
        try:
            rows.append((number, json.loads(line)))
        except ValueError as exc:
            rep.error("%s line %d" % (rel, number), "is not valid JSON (%s)" % str(exc)[:80])
    return rows


# --------------------------------------------------------------------------- check: inventory and hygiene

def check_inventory(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    if not prod.exists:
        rep.error(prod.root, "the folder does not exist")
        return
    for link in prod.links:
        rep.error(link, "is a symbolic link or junction; the product must not contain links")
    if not prod.files:
        rep.error(prod.root, "the folder holds no files")


def check_hygiene(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    for rel in prod.files:
        full = prod.join(rel)
        if len(full) > PATH_ABSOLUTE_MAX:
            rep.error(rel, "the full path is %d characters; paths must stay under 240 (Windows limit)" % len(full))
        if len(".claude/" + rel) > PATH_RELATIVE_MAX:
            rep.error(rel, "the path inside a project is %d characters; keep it under %d so a normal project folder fits"
                      % (len(".claude/" + rel), PATH_RELATIVE_MAX))
        if rel.lower().endswith(BINARY_EXT):
            continue
        data = prod.raw(rel)
        if data is None:
            rep.error(rel, "cannot read the file")
            continue
        if data.startswith(b"\xef\xbb\xbf"):
            rep.error(rel, "starts with a byte order mark (BOM); save the file as UTF-8 without BOM")
        if b"\r" in data:
            rep.error(rel, "uses Windows line endings (CR); the product uses LF only")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            rep.error(rel, "is not valid UTF-8 text")
            continue
        if "\x00" in text:
            rep.error(rel, "contains a NUL character")
        if data and not data.endswith(b"\n"):
            rep.warn(rel, "does not end with a line break")
        in_fence = False
        fence_char = ""
        tab_lines: List[int] = []
        space_lines: List[int] = []
        is_md = rel.endswith(".md")
        for number, line in enumerate(text.replace("\r", "").split("\n"), 1):
            stripped = line.lstrip()
            if is_md and (stripped.startswith("```") or stripped.startswith("~~~")):
                marker = stripped[0]
                if not in_fence:
                    in_fence, fence_char = True, marker
                elif marker == fence_char:
                    in_fence = False
            if is_md and "\t" in line and not in_fence:
                tab_lines.append(number)
            if len(line) - len(line.rstrip(" ")) > 2:
                space_lines.append(number)
        if tab_lines:
            rep.error(rel, "uses a tab character outside code on line(s) %s" % _first(tab_lines))
        if space_lines:
            rep.error(rel, "has more than two trailing spaces on line(s) %s" % _first(space_lines))


def _first(numbers: Sequence[int], limit: int = 5) -> str:
    text = ", ".join(str(n) for n in numbers[:limit])
    if len(numbers) > limit:
        text += " and %d more" % (len(numbers) - limit)
    return text


# --------------------------------------------------------------------------- check: skills, agents, style, rules

def _frontmatter(ctx: Ctx, rel: str) -> Optional[FrontMatter]:
    text = ctx.prod.text(rel)
    if text is None:
        ctx.rep.error(rel, "cannot read the file as UTF-8 text")
        return None
    fm = parse_front_matter(text)
    for line, message in fm.errors:
        ctx.rep.error("%s line %d" % (rel, line), message)
    return fm


def _common_prose_checks(ctx: Ctx, rel: str, text: str, comments_allowed: bool = False) -> None:
    rep = ctx.rep
    if not comments_allowed and "<!--" in text:
        rep.error(rel, "contains an HTML comment; Claude Code does not strip it here and it costs tokens")
    lower = text.lower()
    for phrase in FORBIDDEN_PHRASES_ANY_CASE:
        if phrase in lower:
            rep.error(rel, "contains the phrase '%s' (it trips the automatic-mode safety check)" % phrase)
    for phrase in FORBIDDEN_PHRASES_EXACT:
        if phrase in text:
            rep.error(rel, "contains the shouting phrase '%s'; use a calm sentence" % phrase)


def check_skills(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    folders = sorted(set(f.split("/")[1] for f in prod.files if f.startswith("skills/") and f.count("/") >= 2))
    for name in SKILL_NAMES:
        if name not in folders:
            rep.error("skills/" + name, "this skill is missing (the kit has exactly 11 skills)")
    for name in folders:
        if name not in SKILL_NAMES:
            rep.warn("skills/" + name, "is not one of the 11 skills of the kit")
    total = 0
    for name in folders:
        rel = "skills/%s/SKILL.md" % name
        if not prod.has(rel):
            rep.error("skills/" + name, "has no SKILL.md")
            continue
        fm = _frontmatter(ctx, rel)
        text = prod.text(rel) or ""
        if fm is None:
            continue
        for key in fm.data:
            if key not in SKILL_FIELDS:
                rep.error(rel, "front-matter field '%s' is not allowed (allowed: %s)" % (key, ", ".join(SKILL_FIELDS)))
        if str(fm.data.get("name", "")) != name:
            rep.error(rel, "name '%s' must equal the folder name '%s'" % (fm.data.get("name", ""), name))
        if not re.match(r"^[a-z0-9][a-z0-9-]{0,63}$", name):
            rep.error(rel, "the folder name must be lower-case letters, digits and hyphens (up to 64 characters)")
        desc = fm.data.get("description", "")
        when = fm.data.get("when_to_use", "")
        if not isinstance(desc, str) or not desc.strip():
            rep.error(rel, "description is missing or empty")
            desc = ""
        else:
            if fm.style.get("description") != "folded" or fm.indicator.get("description") != ">-":
                rep.error(rel, "description must be a folded block scalar ('description: >-' with the text on indented "
                          "lines); a quoted or plain value can silently blank the description")
            if "\n" in desc.strip():
                rep.warn(rel, "description holds more than one paragraph")
        if isinstance(when, str) and when:
            desc_len = len(desc.strip()) + len(when.strip())
        else:
            desc_len = len(desc.strip())
        if desc_len > SKILL_DESC_MAX:
            rep.error(rel, "description is %d characters (maximum %d)" % (desc_len, SKILL_DESC_MAX))
        total += desc_len
        if "argument-hint" in fm.data and fm.style.get("argument-hint") not in ("double", "single"):
            rep.error(rel, "argument-hint must be quoted; an unquoted [ ] value is read as a list")
        _check_allowed_tools(ctx, rel, fm)
        lines = text.splitlines()
        if len(lines) > SKILL_LINES_MAX:
            rep.error(rel, "has %d lines (maximum %d)" % (len(lines), SKILL_LINES_MAX))
        step_line = next((n for n, l in enumerate(lines, 1) if re.match(r"^\s*1[.)]\s", l)), 0)
        if step_line == 0 or step_line > SKILL_KEY_LINES:
            rep.warn(rel, "the first numbered step is %s; key instructions should be inside the first %d lines"
                     % ("missing" if step_line == 0 else "on line %d" % step_line, SKILL_KEY_LINES))
        if "disable-model-invocation" in text:
            rep.error(rel, "uses disable-model-invocation; every skill must stay model-invocable")
        for number, line in enumerate(fm.body.split("\n"), fm.body_first_line):
            if re.search(r"(^|[\s(])!`", line) or line.strip().startswith("```!"):
                rep.error("%s line %d" % (rel, number), "uses the ! command-injection form, which runs a command when the skill loads")
        _common_prose_checks(ctx, rel, text)
        ctx.skills[name] = {"desc": desc.strip(), "when": when.strip() if isinstance(when, str) else "", "fm": fm, "rel": rel}
    for rel in prod.files_under("skills/", ".md"):
        parts = rel.split("/")
        if len(parts) >= 3 and parts[2] != "SKILL.md":
            text = prod.text(rel) or ""
            _common_prose_checks(ctx, rel, text)
            if parts[2] != "references":
                rep.warn(rel, "sits outside the skill's references/ folder")
    for rel in prod.files:
        parts = rel.split("/")
        if parts[0] == "skills" and len(parts) >= 3 and not rel.endswith(".md"):
            rep.warn(rel, "is not a Markdown file; skills hold only SKILL.md and references/*.md")
    if total > SKILL_DESC_TOTAL_MAX:
        rep.error("skills", "the descriptions together are %d characters (maximum %d)" % (total, SKILL_DESC_TOTAL_MAX))
    rep.note("skills: %d, description characters %d (maximum %d)" % (len(ctx.skills), total, SKILL_DESC_TOTAL_MAX))


def _check_allowed_tools(ctx: Ctx, rel: str, fm: FrontMatter) -> None:
    rep = ctx.rep
    if "allowed-tools" not in fm.data:
        return
    value = fm.data["allowed-tools"]
    tokens = value if isinstance(value, list) else split_rule_tokens(str(value))
    for token in tokens:
        match = re.match(r"^([A-Za-z][A-Za-z0-9_]*)(?:\((.*)\))?$", token, re.S)
        if not match:
            rep.error(rel, "allowed-tools entry '%s' is not written as Tool or Tool(pattern)" % token[:60])
            continue
        tool, pattern = match.group(1), match.group(2)
        if tool in ("Write", "Edit", "NotebookEdit"):
            rep.error(rel, "allowed-tools lets '%s' run without a prompt; only read-only actions may be listed" % tool)
        elif tool in BROAD_TOOL_WORDS and (pattern is None or pattern.strip() in ("", "*", "**")):
            rep.error(rel, "allowed-tools entry '%s' approves every %s command" % (token[:40], tool))
        elif tool in ("Bash", "PowerShell") and pattern:
            words_ = pattern.split()
            if words_[:1] == ["git"] and len(words_) > 1 and words_[1] in MUTATING_GIT:
                rep.warn(rel, "allowed-tools lets 'git %s' run without a prompt; is that read-only?" % words_[1])
            if words_[:1] in (["rm"], ["del"], ["Remove-Item"]):
                rep.warn(rel, "allowed-tools lets a delete command run without a prompt")


def check_agents(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    found = sorted(f for f in prod.files if f.startswith("agents/") and f.count("/") == 1 and f.endswith(".md"))
    for name in AGENT_NAMES:
        if "agents/%s.md" % name not in found:
            rep.error("agents/%s.md" % name, "this agent is missing (the kit has exactly 2 agents)")
    for rel in found:
        stem = rel[len("agents/"):-3]
        if stem not in AGENT_NAMES:
            rep.warn(rel, "is not one of the 2 agents of the kit")
        fm = _frontmatter(ctx, rel)
        text = prod.text(rel) or ""
        if fm is None:
            continue
        for key in fm.data:
            if key not in AGENT_FIELDS:
                rep.error(rel, "front-matter field '%s' is not allowed for agents (allowed: %s)" % (key, ", ".join(AGENT_FIELDS)))
        if str(fm.data.get("name", "")) != stem:
            rep.error(rel, "name '%s' must equal the file name '%s'" % (fm.data.get("name", ""), stem))
        desc = fm.data.get("description", "")
        if not isinstance(desc, str) or not desc.strip():
            rep.error(rel, "description is missing or empty")
            desc = ""
        else:
            if fm.style.get("description") != "folded" or fm.indicator.get("description") != ">-":
                rep.error(rel, "description must be a folded block scalar ('description: >-')")
            if len(desc.strip()) > AGENT_DESC_MAX:
                rep.error(rel, "description is %d characters (maximum %d)" % (len(desc.strip()), AGENT_DESC_MAX))
        if "tools" not in fm.data:
            rep.error(rel, "tools is missing; an agent without a tools list can use every tool")
        tools = as_list(fm.data.get("tools", ""))
        if not tools:
            rep.error(rel, "tools list is empty or unreadable")
        if set(tools) & set(READ_TOOLS) and set(tools) & set(WEB_TOOLS):
            rep.error(rel, "combines a read tool and a web tool; that lets file content flow to the web")
        bad = sorted(set(tools) & set(WRITE_TOOLS))
        if bad:
            rep.error(rel, "agents must be read-only; remove %s from tools" % ", ".join(bad))
        if str(fm.data.get("model", "inherit")) != "inherit":
            rep.warn(rel, "model is '%s'; the kit uses 'inherit'" % fm.data.get("model"))
        turns = str(fm.data.get("maxTurns", "")).strip()
        if turns and not (turns.isdigit() and 1 <= int(turns) <= 50):
            rep.warn(rel, "maxTurns '%s' should be a whole number from 1 to 50" % turns)
        _common_prose_checks(ctx, rel, text)
        if "clear-writing" not in text:
            rep.warn(rel, "does not point to rules/clear-writing.md (the reader is a beginner)")
        if "UNVERIFIED" not in text:
            rep.warn(rel, "does not tell the agent to mark unchecked statements UNVERIFIED")
        ctx.agents[stem] = {"desc": desc.strip(), "fm": fm}


def check_style(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "output-styles/tutor.md"
    if not prod.has(rel):
        rep.error(rel, "the output style file is missing")
        return
    fm = _frontmatter(ctx, rel)
    text = prod.text(rel) or ""
    if fm is None:
        return
    for key in fm.data:
        if key not in STYLE_FIELDS:
            rep.error(rel, "front-matter field '%s' is not allowed (allowed: %s)" % (key, ", ".join(STYLE_FIELDS)))
    if str(fm.data.get("name", "")) != "tutor":
        rep.error(rel, "name must be 'tutor' (settings.json outputStyle must match it)")
    if as_bool(fm.data.get("keep-coding-instructions")) is not True:
        rep.error(rel, "keep-coding-instructions must be true")
    count = words(text)
    if count > STYLE_WORDS_MAX:
        rep.error(rel, "has %d words (maximum %d)" % (count, STYLE_WORDS_MAX))
    _common_prose_checks(ctx, rel, text)


def check_rules(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    found = sorted(f for f in prod.files if f.startswith("rules/") and f.count("/") == 1 and f.endswith(".md"))
    for name in RULE_NAMES:
        if "rules/%s.md" % name not in found:
            rep.error("rules/%s.md" % name, "this rule file is missing (the kit has exactly 6 rules)")
    total = 0
    for rel in found:
        text = prod.text(rel) or ""
        count = words(text)
        total += count
        if rel[len("rules/"):-3] not in RULE_NAMES:
            rep.warn(rel, "is not one of the 6 rules of the kit; every rule is loaded in every session")
        if count > RULE_WORDS_MAX:
            rep.error(rel, "has %d words (maximum %d)" % (count, RULE_WORDS_MAX))
        if not text.lstrip().startswith("# "):
            rep.error(rel, "must start with a '# ' heading (rules are plain Markdown without front matter)")
        if "For:" not in text[:200]:
            rep.warn(rel, "should say 'For: ...' near the top so a reader knows who it is for")
        _common_prose_checks(ctx, rel, text)
    if total > RULES_TOTAL_WORDS_MAX:
        rep.error("rules", "the rules together have %d words (maximum %d)" % (total, RULES_TOTAL_WORDS_MAX))


def check_claude_md(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "CLAUDE.md"
    if not prod.has(rel):
        rep.error(rel, "the file is missing")
        return
    text = prod.text(rel) or ""
    count = words(text)
    lines = len(text.splitlines())
    if count > CLAUDE_MD_WORDS_MAX:
        rep.error(rel, "has %d words (maximum %d)" % (count, CLAUDE_MD_WORDS_MAX))
    if lines > CLAUDE_MD_LINES_MAX:
        rep.error(rel, "has %d lines (maximum %d)" % (lines, CLAUDE_MD_LINES_MAX))
    _common_prose_checks(ctx, rel, text, comments_allowed=True)
    # the skill menu: every skill name appears in the section about skills
    section = _section(text, r"skill")
    menu = section if section is not None else text
    if section is None:
        rep.error(rel, "has no section about which skill to start (a heading that contains the word 'skill')")
    for name in SKILL_NAMES:
        if not re.search(r"(?<![\w-])%s(?![\w-])" % re.escape(name), menu):
            rep.error(rel, "the skill menu does not mention the skill '%s'" % name)


def _section(text: str, heading_pattern: str) -> Optional[str]:
    """Text under the first '## ' heading that matches heading_pattern, up to the next '## ' heading."""
    lines = text.split("\n")
    start = None
    for idx, line in enumerate(lines):
        if line.startswith("## ") and re.search(heading_pattern, line, re.I):
            start = idx
            break
    if start is None:
        return None
    end = len(lines)
    for idx in range(start + 1, len(lines)):
        if lines[idx].startswith("## "):
            end = idx
            break
    return "\n".join(lines[start:end])


# --------------------------------------------------------------------------- check: budget

def check_budget(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rows: List[Tuple[str, int, int]] = []

    def add(label: str, text: str) -> None:
        count = words(text)
        rows.append((label, count, tokens_for(count)))

    add("CLAUDE.md", prod.text("CLAUDE.md") or "")
    rule_text = " ".join((prod.text(f) or "") for f in prod.files if f.startswith("rules/") and f.count("/") == 1 and f.endswith(".md"))
    add("rules (%d files)" % len([f for f in prod.files if f.startswith("rules/") and f.count("/") == 1 and f.endswith(".md")]), rule_text)
    add("output style", prod.text("output-styles/tutor.md") or "")
    listing = " ".join("%s: %s %s" % (name, info["desc"], info["when"]) for name, info in sorted(ctx.skills.items()))
    add("skill listing (%d lines)" % len(ctx.skills), listing)
    rows.append(("state capsule (allowance)", 0, CAPSULE_ALLOWANCE_TOKENS))
    total = sum(r[2] for r in rows)
    ctx.budget_rows = rows
    rep.note("Fixed-context budget (words x %.2f = tokens):" % TOKENS_PER_WORD)
    for label, count, tok in rows:
        rep.note("  %-28s %6d words %6d tokens" % (label, count, tok))
    rep.note("  %-28s %6s       %6d tokens (error above %d, warning above %d)" % ("TOTAL", "", total, TOKEN_ERROR_ABOVE, TOKEN_WARN_ABOVE))
    if total > TOKEN_ERROR_ABOVE:
        rep.error("budget", "the files every session loads cost about %d tokens (maximum %d); shorten CLAUDE.md, a rule, the style or a description"
                  % (total, TOKEN_ERROR_ABOVE))
    elif total > TOKEN_WARN_ABOVE:
        rep.warn("budget", "the files every session loads cost about %d tokens; the warning level is %d, the maximum %d"
                 % (total, TOKEN_WARN_ABOVE, TOKEN_ERROR_ABOVE))


# --------------------------------------------------------------------------- check: knowledge

def _concept_files(prod: Product) -> List[str]:
    return sorted(f for f in prod.files if f.startswith("knowledge/concepts/") and f.endswith(".jsonl") and f.count("/") == 2)


def _norm_term(term: str) -> str:
    return re.sub(r"\s+", " ", str(term)).strip().casefold()


def check_knowledge(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    files = _concept_files(prod)
    if not files:
        rep.error("knowledge/concepts", "no concept files (concepts/<domain>.jsonl) found")
    rows: Dict[str, Tuple[str, int, Dict[str, Any]]] = {}
    per_domain: Dict[str, List[Dict[str, Any]]] = {}
    for rel in files:
        name = rel.split("/")[-1]
        domain = name[:-6].split("-")[0]
        if domain not in DOMAIN_TARGETS:
            rep.error(rel, "the file name starts with '%s', which is not a known domain" % domain)
        for number, row in read_jsonl(prod, rel, rep):
            where = "%s line %d" % (rel, number)
            if not isinstance(row, dict):
                rep.error(where, "the line is not a JSON object")
                continue
            ctx.concepts.append((name, number, row))
            keys = list(row.keys())
            if keys != CONCEPT_KEYS:
                missing = [k for k in CONCEPT_KEYS if k not in row]
                extra = [k for k in keys if k not in CONCEPT_KEYS]
                if missing or extra:
                    rep.error(where, "keys are wrong (missing: %s; not allowed: %s)" % (", ".join(missing) or "none", ", ".join(extra) or "none"))
                else:
                    rep.warn(where, "keys are not in the fixed order of the schema")
            _check_concept_row(ctx, where, name, domain, row, rows)
            per_domain.setdefault(domain, []).append(row)
    ctx.concept_ids = set(rows.keys())
    # references, cycles, depth
    for cid, (rel, number, row) in rows.items():
        for ref in _list(row.get("needs")):
            if ref not in rows:
                rep.error("%s line %d" % (rel, number), "%s needs '%s', which is not a concept id" % (cid, ref))
    _check_cycles_and_depth(ctx, rows)
    for domain in sorted(per_domain):
        cards = per_domain[domain]
        explain = sum(1 for r in cards if r.get("check_type") == "explain")
        if cards and explain / float(len(cards)) > 0.35:
            rep.warn("knowledge/concepts", "domain %s: %d%% of the checks are 'explain' (maximum 35%%)" % (domain, int(100 * explain / len(cards))))
    rep.note("concepts: %d cards in %d files; per domain: %s" % (
        len(rows), len(files), ", ".join("%s %d/%d" % (d, len(per_domain.get(d, [])), DOMAIN_TARGETS[d]) for d in DOMAIN_TARGETS)))
    glossary_terms = _check_glossary(ctx, rows)
    _check_term_overlap(ctx, glossary_terms)
    _check_probes(ctx)
    _check_milestones(ctx)
    _check_diagrams(ctx)
    _check_stacks(ctx)


def _list(value: Any) -> List[str]:
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def _check_concept_row(ctx: Ctx, where: str, filename: str, domain: str, row: Dict[str, Any],
                       rows: Dict[str, Tuple[str, int, Dict[str, Any]]]) -> None:
    rep = ctx.rep
    cid = row.get("id")
    number = int(where.rsplit(" ", 1)[1])
    rel = where.rsplit(" line ", 1)[0]
    if not isinstance(cid, str) or not ID_RE.match(cid):
        rep.error(where, "the id %r is not written like domain-words (lower case, hyphens)" % (cid,))
        return
    if cid in rows:
        rep.error(where, "the id '%s' is already used at %s line %d" % (cid, rows[cid][0], rows[cid][1]))
    else:
        rows[cid] = (rel, number, row)
    if row.get("domain") != domain:
        rep.error(where, "domain '%s' does not match the file name (%s)" % (row.get("domain"), filename))
    if not cid.startswith(domain + "-"):
        rep.error(where, "the id '%s' must start with '%s-'" % (cid, domain))
    for key in ("title", "plain", "check", "try", "pitfall"):
        if not isinstance(row.get(key), str) or not row.get(key, "").strip():
            rep.error(where, "%s must be a non-empty text" % key)
    tier = row.get("tier")
    if isinstance(tier, bool) or tier not in (1, 2):
        rep.error(where, "tier must be 1 or 2 in version 1")
    needs = row.get("needs")
    if not isinstance(needs, list) or any(not isinstance(v, str) for v in needs):
        rep.error(where, "needs must be a list of concept ids")
    elif len(needs) > 3:
        rep.error(where, "needs lists %d prerequisites (maximum 3)" % len(needs))
    elif cid in needs:
        rep.error(where, "needs lists the concept itself")
    terms = row.get("terms")
    if not isinstance(terms, list) or not terms or any(not isinstance(v, str) or not v.strip() for v in terms):
        rep.error(where, "terms must be a non-empty list of words (the first is the main term)")
    signals = row.get("signals")
    if not isinstance(signals, list) or any(not isinstance(v, str) for v in signals):
        rep.error(where, "signals must be a list of text")
    else:
        for sig in signals:
            if len(sig) < 4 or sig != sig.lower():
                rep.error(where, "signal %r must be lower case and at least 4 characters" % sig)
    plain = row.get("plain")
    if isinstance(plain, str) and words(plain) > CONCEPT_PLAIN_MAX_WORDS:
        rep.error(where, "plain has %d words (maximum %d)" % (words(plain), CONCEPT_PLAIN_MAX_WORDS))
    check = row.get("check")
    if isinstance(check, str) and check.strip() and (not check.strip().endswith("?") or YESNO_START.match(check)):
        rep.error(where, "check must be one question that is not answered with yes or no")
    if row.get("check_type") not in CHECK_TYPES:
        rep.error(where, "check_type must be one of %s" % ", ".join(CHECK_TYPES))
    rubric = row.get("rubric")
    if not isinstance(rubric, list) or not (2 <= len(rubric) <= 3) or any(not isinstance(v, str) or not v.strip() for v in rubric):
        rep.error(where, "rubric needs 2 or 3 text bullets")
    volatile = row.get("volatile")
    if not isinstance(volatile, bool):
        rep.error(where, "volatile must be true or false")
    verified = row.get("verified")
    date_ok = isinstance(verified, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}$", verified))
    if date_ok:
        try:
            datetime.date.fromisoformat(verified)
        except ValueError:
            date_ok = False
    if verified not in ("", None) and not date_ok:
        rep.error(where, "verified must be a real date like 2026-01-31")
    if volatile is True:
        if not (isinstance(row.get("src"), str) and row["src"].startswith("http")):
            rep.error(where, "a volatile card needs src (a link to the primary document)")
        if not date_ok:
            rep.error(where, "a volatile card needs verified (the date the facts were checked)")


def _check_cycles_and_depth(ctx: Ctx, rows: Dict[str, Tuple[str, int, Dict[str, Any]]]) -> None:
    rep = ctx.rep
    state: Dict[str, int] = {}
    depth: Dict[str, int] = {}
    reported: Set[str] = set()

    def visit(cid: str, trail: List[str]) -> int:
        if state.get(cid) == 2:
            return depth[cid]
        if state.get(cid) == 1:
            key = " -> ".join(trail + [cid])
            if key not in reported:
                reported.add(key)
                rep.error("knowledge/concepts", "prerequisite cycle: %s" % key)
            return 0
        state[cid] = 1
        best = 0
        for ref in _list(rows[cid][2].get("needs")):
            if ref in rows:
                best = max(best, 1 + visit(ref, trail + [cid]))
        state[cid] = 2
        depth[cid] = best
        return best

    for cid in sorted(rows):
        visit(cid, [])
    for cid, (rel, number, row) in sorted(rows.items()):
        if row.get("tier") == 1 and depth.get(cid, 0) > 2:
            rep.error("%s line %d" % (rel, number), "tier-1 concept %s needs a chain of %d prerequisites (maximum 2)" % (cid, depth[cid]))


def _check_glossary(ctx: Ctx, rows: Dict[str, Tuple[str, int, Dict[str, Any]]]) -> Dict[str, Tuple[int, Dict[str, Any]]]:
    prod, rep = ctx.prod, ctx.rep
    rel = "knowledge/glossary.jsonl"
    out: Dict[str, Tuple[int, Dict[str, Any]]] = {}
    if not prod.has(rel):
        rep.error(rel, "the glossary file is missing")
        return out
    for number, row in read_jsonl(prod, rel, rep):
        where = "%s line %d" % (rel, number)
        if not isinstance(row, dict):
            rep.error(where, "the line is not a JSON object")
            continue
        keys = list(row.keys())
        if sorted(keys) != sorted(GLOSSARY_KEYS):
            rep.error(where, "keys are wrong (needed: %s)" % ", ".join(GLOSSARY_KEYS))
        term = row.get("term")
        if not isinstance(term, str) or not term.strip():
            rep.error(where, "term must be non-empty text")
            continue
        norm = _norm_term(term)
        if norm in out:
            rep.error(where, "the term '%s' is already in the glossary at line %d" % (term, out[norm][0]))
        out[norm] = (number, row)
        if not isinstance(row.get("aliases"), list) or any(not isinstance(a, str) for a in row.get("aliases", [])):
            rep.error(where, "aliases must be a list of text")
        plain = row.get("plain")
        if not isinstance(plain, str) or not plain.strip() or words(plain) > GLOSSARY_PLAIN_MAX_WORDS:
            rep.error(where, "plain must have 1 to %d words (now %d)" % (GLOSSARY_PLAIN_MAX_WORDS, words(plain) if isinstance(plain, str) else 0))
        if row.get("domain") not in DOMAIN_TARGETS:
            rep.error(where, "domain %r is not a known domain" % (row.get("domain"),))
        if row.get("jargon") is not True:
            rep.error(where, "jargon must be true (the glossary holds only jargon terms)")
    rep.note("glossary: %d terms" % len(out))
    return out


def _check_term_overlap(ctx: Ctx, glossary: Dict[str, Tuple[int, Dict[str, Any]]]) -> None:
    """A term lives in a concept OR in the glossary, never both."""
    rep = ctx.rep
    concept_terms: Dict[str, str] = {}
    for filename, number, row in ctx.concepts:
        cid = row.get("id", "?")
        for term in _list(row.get("terms")):
            norm = _norm_term(term)
            if norm in concept_terms and concept_terms[norm] != cid:
                rep.warn("knowledge/concepts/%s line %d" % (filename, number),
                         "the term '%s' is also a term of the concept %s" % (term, concept_terms[norm]))
            concept_terms.setdefault(norm, cid)
    for norm, (number, row) in sorted(glossary.items(), key=lambda kv: kv[1][0]):
        names = [row.get("term", "")] + _list(row.get("aliases"))
        for name in names:
            owner = concept_terms.get(_norm_term(name))
            if owner:
                rep.error("knowledge/glossary.jsonl line %d" % number,
                          "'%s' is also a term of the concept %s; keep it in one place only (the concept)" % (name, owner))


def _check_probes(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "knowledge/probes.jsonl"
    if not prod.has(rel):
        rep.error(rel, "the probes file is missing")
        return
    seen: Set[str] = set()
    count = 0
    for number, row in read_jsonl(prod, rel, rep):
        count += 1
        where = "%s line %d" % (rel, number)
        if not isinstance(row, dict) or sorted(row.keys()) != sorted(PROBE_KEYS):
            rep.error(where, "keys must be exactly: %s" % ", ".join(PROBE_KEYS))
            continue
        pid = row.get("id")
        if pid not in ctx.concept_ids:
            rep.error(where, "id '%s' is not a concept id" % (pid,))
        if pid in seen:
            rep.error(where, "id '%s' appears twice" % (pid,))
        seen.add(str(pid))
        options = row.get("options")
        correct = row.get("correct")
        if not isinstance(options, list) or not (3 <= len(options) <= 5) or any(not isinstance(o, str) for o in options):
            rep.error(where, "options must be 3 to 5 texts")
            continue
        if correct not in options:
            rep.error(where, "correct is not one of the options")
        misc = row.get("misconceptions")
        if not isinstance(misc, dict) or not misc:
            rep.error(where, "misconceptions must map wrong options to the belief behind them")
        else:
            for option, belief in misc.items():
                if option not in options:
                    rep.error(where, "a misconception key is not one of the options")
                if option == correct:
                    rep.error(where, "the correct option is listed as a misconception")
                if not isinstance(belief, str) or not belief.strip():
                    rep.error(where, "a misconception text is empty")
        if not isinstance(row.get("question"), str) or not row["question"].strip().endswith("?"):
            rep.warn(where, "the question does not end with a question mark")
    if count < 24 or count > 28:
        rep.warn(rel, "has %d probes; the plan is 24 to 28" % count)


def _check_milestones(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "knowledge/milestones.md"
    if not prod.has(rel):
        rep.error(rel, "the milestones file is missing")
        return
    text = prod.text(rel) or ""
    lines = text.splitlines()
    if len(lines) > MILESTONES_LINES_MAX:
        rep.error(rel, "has %d lines (maximum %d)" % (len(lines), MILESTONES_LINES_MAX))
    heads = re.findall(r"^## M(\d+)\b", text, re.M)
    expected = [str(n) for n in range(1, 13)]
    if heads != expected:
        rep.error(rel, "needs the 12 headings '## M1' to '## M12' in order (found: %s)" % (", ".join("M" + h for h in heads) or "none"))
    for number, line in enumerate(lines, 1):
        if line.startswith("Concepts:"):
            for cid in re.findall(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)+", line[len("Concepts:"):]):
                if cid not in ctx.concept_ids:
                    rep.error("%s line %d" % (rel, number), "'%s' is not a concept id" % cid)
    if len(re.findall(r"^Alone when:", text, re.M)) < len(heads):
        rep.warn(rel, "not every milestone has an 'Alone when:' line")


def _check_diagrams(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "knowledge/diagrams.md"
    if not prod.has(rel):
        rep.error(rel, "the diagrams file is missing")
        return
    text = _norm_quotes(prod.text(rel) or "")
    heads = [(m.group(1), m.group(2).strip().lower()) for m in re.finditer(r"^## ([a-z])\. (.+)$", text, re.M)]
    letters = [h[0] for h in heads]
    if letters != [e[0] for e in EXPECTED_DIAGRAMS]:
        rep.error(rel, "needs the five headings '## a.' to '## e.' in order (found: %s)" % (", ".join(letters) or "none"))
    for letter, needle in EXPECTED_DIAGRAMS:
        title = next((h[1] for h in heads if h[0] == letter), None)
        if title is not None and needle not in title:
            rep.error(rel, "heading %s. should be about '%s' (found '%s')" % (letter, needle, title))


def _check_stacks(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "knowledge/stacks.md"
    if not prod.has(rel):
        rep.error(rel, "the stacks file is missing")
        return
    text = prod.text(rel) or ""
    heads = re.findall(r"^## (\d+)\. ", text, re.M)
    if heads != [str(n) for n in range(1, 9)]:
        rep.error(rel, "needs the 8 project-type sections '## 1.' to '## 8.' (found: %s)" % (", ".join(heads) or "none"))
    hits = []
    in_fence = False
    for number, line in enumerate(text.split("\n"), 1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        if not in_fence and re.search(r"(?<![\w.])\d+\.\d+(?:\.\d+)?(?![\w.])", line) and "http" not in line:
            hits.append(number)
    if hits:
        rep.warn(rel, "looks like it holds version numbers on line(s) %s; the file must stay free of them" % _first(hits))


def _norm_quotes(text: str) -> str:
    return text.replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')


# --------------------------------------------------------------------------- check: pointers

_ID_PREFIXES = "|".join(DOMAIN_TARGETS)
_ID_TOKEN = re.compile(r"^(?:%s)-[a-z0-9]+(?:-[a-z0-9]+)*$" % _ID_PREFIXES)
_SPAN = re.compile(r"`([^`\n]+)`")


def _blank_fences(text: str) -> List[str]:
    """Lines of a Markdown file with the content of code fences blanked (line numbers stay the same)."""
    out: List[str] = []
    in_fence = False
    marker = ""
    for line in text.replace("\r", "").split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            if not in_fence:
                in_fence, marker = True, stripped[0]
            elif stripped[0] == marker:
                in_fence = False
            out.append("")
            continue
        out.append("" if in_fence else line)
    return out


def check_pointers(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    diagram_heads = [h.group(1).strip().lower() for h in re.finditer(r"^## (?:[a-z]\. )?(.+)$", _norm_quotes(prod.text("knowledge/diagrams.md") or ""), re.M)]
    gate_defs: Dict[str, Set[str]] = {}
    for rule in prod.files_under("rules/", ".md"):
        gate_defs[rule] = set(re.findall(r"\bG([1-9])\b", prod.text(rule) or ""))
    for rel in prod.files:
        if not rel.endswith(".md"):
            continue
        text = prod.text(rel)
        if text is None:
            continue
        for number, line in enumerate(_blank_fences(text), 1):
            if not line:
                continue
            where = "%s line %d" % (rel, number)
            for span in _SPAN.finditer(line):
                _check_span(ctx, rel, where, span.group(1))
            _check_gates(ctx, where, line, gate_defs)
            _check_diagram_quotes(ctx, where, line, diagram_heads)


def _check_span(ctx: Ctx, rel: str, where: str, span: str) -> None:
    rep, prod = ctx.rep, ctx.prod
    token = span.strip()
    if ctx.concept_ids and _ID_TOKEN.match(token) and token not in ID_LOOKALIKES and token not in ctx.concept_ids:
        rep.error(where, "`%s` looks like a concept id, but no concept card has that id" % token)
        return
    for word in token.split():
        word = word.strip(",;:)(\"'")
        word = word.rstrip(".")
        if "/" not in word or not word.endswith(POINTER_EXTENSIONS):
            continue
        if re.search(r"[<>*{}$%|~]|://|\.\.\.", word):
            continue
        path = word[2:] if word.startswith("./") else word
        explicit = path.startswith(".claude/")
        if explicit:
            path = path[len(".claude/"):]
        first = path.split("/")[0]
        if first in RUNTIME_NAMESPACES or path in RUNTIME_FILES:
            continue
        if any(path == p or path.startswith(p + "/") for p in PROJECT_RUNTIME_PREFIXES):
            continue
        if not explicit and first not in PRODUCT_NAMESPACES:
            continue
        if not _resolve_pointer(prod, rel, path):
            rep.error(where, "`%s` points to a file that does not exist" % word)


def _resolve_pointer(prod: Product, rel: str, path: str) -> bool:
    candidates = [path]
    folder = rel.rsplit("/", 1)[0] if "/" in rel else ""
    if folder:
        candidates.append(folder + "/" + path)
    parts = rel.split("/")
    if len(parts) >= 3 and parts[0] == "skills":
        candidates.append("/".join(parts[:2]) + "/" + path)
    if path.startswith(("handlers/", "lib/")):
        candidates.append("hooks/" + path)
    for cand in candidates:
        norm = os.path.normpath(cand).replace("\\", "/")
        if prod.has(norm):
            return True
    full = os.path.normpath(os.path.join(prod.root, path))
    if os.path.exists(full) or os.path.exists(os.path.normpath(os.path.join(os.path.dirname(prod.root), path))):
        return True      # settings.json, a docs/ folder next to .claude, and other files outside the manifest
    return False


def _check_gates(ctx: Ctx, where: str, line: str, gate_defs: Dict[str, Set[str]]) -> None:
    rules = [(m.start(), m.group(0)) for m in re.finditer(r"rules/[a-z-]+\.md", line)]
    if not rules:
        return
    for gate in re.finditer(r"\bG(\d)\b", line):
        near = min(rules, key=lambda r: abs(r[0] - gate.start()))
        if abs(near[0] - gate.start()) > 100:
            continue
        defined = gate_defs.get(near[1])
        if defined is not None and gate.group(1) not in defined:
            ctx.rep.error(where, "gate G%s is named next to %s, but that rule does not define it" % (gate.group(1), near[1]))


def _check_diagram_quotes(ctx: Ctx, where: str, line: str, heads: List[str]) -> None:
    if "diagrams.md" not in line or not heads:
        return
    norm = _norm_quotes(line)
    pos = norm.find("diagrams.md")
    after = norm[pos:pos + 160]
    quotes = [m.group(1) for m in re.finditer(r'"([^"]{3,60})"', after)]
    before = norm[max(0, pos - 80):pos]
    for m in re.finditer(r'(?:picture|heading|section|diagram)\s+"([^"]{3,60})"', before):
        quotes.append(m.group(1))
    for quote in quotes:
        if not any(quote.strip().lower() in head for head in heads):
            ctx.rep.error(where, "the heading \"%s\" does not exist in knowledge/diagrams.md" % quote)


# --------------------------------------------------------------------------- check: labels

def _load_labels(prod: Product, rep: Report) -> Optional[Dict[str, Any]]:
    rel = "hooks/lib/config.py"
    if not prod.has(rel):
        rep.error(rel, "the file is missing, so the label strings cannot be checked")
        return None
    try:
        namespace = runpy.run_path(prod.join(rel), run_name="tutor_config_for_validate")
        labels = namespace["LABELS"]
        if not isinstance(labels, dict):
            raise TypeError("LABELS is not a dict")
        return labels
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        rep.error(rel, "cannot load LABELS (%s: %s)" % (type(exc).__name__, str(exc)[:80]))
        return None


def check_labels(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    labels = _load_labels(prod, rep)
    if labels is not None:
        style = prod.text("output-styles/tutor.md") or ""
        en = labels.get("en", {})
        wanted = list(en.get("check", [])) + [en.get("offer", "")] + list(en.get("card", []))
        for label in wanted:
            if label and label not in style:
                rep.error("output-styles/tutor.md", "does not contain the English label '%s' that hooks/lib/config.py looks for" % label)
        if en.get("offer") != OFFER_LABEL:
            rep.error("hooks/lib/config.py", "the English offer label must be exactly '%s'" % OFFER_LABEL)
        _check_label_table(ctx, labels)
    # the offer label is spelled the same everywhere
    for rel in prod.files:
        if rel.lower().endswith(BINARY_EXT) or rel.startswith("tools/validate.py"):
            continue
        text = prod.text(rel)
        if not text:
            continue
        for match in re.finditer(r"next\s+i\s+can\s+teach(:?)", text, re.I):
            found = match.group(0)
            if found != OFFER_LABEL:
                # a Python file may mention the words in program text (a docstring, a comment) without the colon:
                # that is not the label itself, so it is not reported
                if rel.endswith(".py") and not found.endswith(":"):
                    continue
                line = text.count("\n", 0, match.start()) + 1
                rep.error("%s line %d" % (rel, line), "the offer label is written '%s'; it must be exactly '%s'" % (found, OFFER_LABEL))


def _check_label_table(ctx: Ctx, labels: Dict[str, Any]) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "skills/tutor/references/settings.md"
    text = prod.text(rel)
    if text is None:
        rep.error(rel, "the file is missing, so the table 'Labels by language' cannot be checked")
        return
    section = None
    lines = text.split("\n")
    for idx, line in enumerate(lines):
        if re.match(r"^#+\s+Labels by language\s*$", line):
            section = idx
            break
    if section is None:
        rep.error(rel, "has no heading 'Labels by language'")
        return
    table: Dict[str, Tuple[List[str], List[str]]] = {}
    for line in lines[section + 1:]:
        if re.match(r"^#+\s", line):
            break
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 3:
            continue
        table[cells[0]] = (re.findall(r"`([^`]+)`", cells[1]), re.findall(r"`([^`]+)`", cells[2]))
    for name, code in LABEL_LANGUAGES:
        if name not in table:
            rep.error(rel, "the table 'Labels by language' has no row for %s" % name)
            continue
        want = labels.get(code, {})
        checks, offers = table[name]
        if checks != list(want.get("check", [])):
            rep.error(rel, "%s check labels %s differ from hooks/lib/config.py %s" % (name, checks, list(want.get("check", []))))
        if offers != [want.get("offer", "")]:
            rep.error(rel, "%s offer label %s differs from hooks/lib/config.py %s" % (name, offers, [want.get("offer", "")]))


# --------------------------------------------------------------------------- check: Claude variables

def check_claude_vars(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    pattern = re.compile(r"\$\{?CLAUDE_")
    for rel in prod.files:
        if rel.lower().endswith(BINARY_EXT) or rel.endswith(".py"):
            continue
        if re.match(r"^skills/[^/]+/SKILL\.md$", rel):
            continue
        text = prod.text(rel)
        if text and pattern.search(text):
            line = text.count("\n", 0, pattern.search(text).start()) + 1
            rep.error("%s line %d" % (rel, line), "uses ${CLAUDE_...}; these variables work only inside SKILL.md "
                      "(elsewhere write a path from the project root)")


# --------------------------------------------------------------------------- check: text that hooks print

def check_hook_text(ctx: Ctx) -> None:
    """The guard messages carry no phrase that trips the automatic-mode check; the capsule menu names real skills."""
    prod, rep = ctx.prod, ctx.rep
    rel = "hooks/guard-messages.json"
    if prod.has(rel):
        text = (prod.text(rel) or "").lower()
        for phrase in FORBIDDEN_PHRASES_ANY_CASE:
            if phrase in text:
                rep.error(rel, "contains the phrase '%s' (it trips the automatic-mode safety check)" % phrase)
    menu_file = "hooks/handlers/session_start.py"
    source = prod.text(menu_file) if prod.has(menu_file) else None
    if source is None:
        return
    match = re.search(r'^MENU\s*=\s*"([^"\n]*)"', source, re.M)
    if not match:
        rep.warn(menu_file, "has no MENU line, so the capsule menu cannot be checked against the skills")
        return
    for command in re.findall(r"(?<![\w/])/([a-z][a-z-]*)", match.group(1)):
        if command not in SKILL_NAMES:
            rep.error(menu_file, "the capsule menu line names /%s, which is not one of the 11 skills" % command)


# --------------------------------------------------------------------------- check: small files

def check_small_files(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    version = (prod.text("VERSION") or "").strip()
    if prod.has("VERSION") and not re.match(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$", version):
        rep.error("VERSION", "must hold one version such as 1.0.0 (found %r)" % version[:30])
    if prod.has(".gitignore"):
        lines = [l.strip() for l in (prod.text(".gitignore") or "").split("\n") if l.strip() and not l.strip().startswith("#")]
        missing = [l for l in GITIGNORE_LINES if l not in lines]
        if installed_mode():
            if missing:
                rep.error(".gitignore", "must hold these rules: %s" % ", ".join(missing))
        elif sorted(lines) != sorted(GITIGNORE_LINES):
            rep.error(".gitignore", "must hold exactly these rules (comments allowed): %s" % ", ".join(GITIGNORE_LINES))
    if prod.has("CHANGELOG.md") and version and version not in (prod.text("CHANGELOG.md") or ""):
        rep.warn("CHANGELOG.md", "does not mention the version %s" % version)
    for name in TEMPLATE_NAMES:
        if ctx.release and not prod.has("templates/%s.md" % name):
            rep.error("templates/%s.md" % name, "this template is missing")


# --------------------------------------------------------------------------- check: docs

def what_it_does(description: str, limit: int = COMMANDS_SENTENCE_MAX) -> str:
    """The sentence of a skill description that says what the skill does, cut to `limit` characters.

    SPEC 10 puts the trigger phrases FIRST in every description, so the plain 'first sentence' would list what
    the learner can say, not what the skill does. Rule: when the first sentence is a trigger list (it holds a
    double quote or at least 3 commas), skip it; then take the first sentence without a double quote. If no
    such sentence exists, the first sentence is used. Change the rule here and nowhere else."""
    sentences = _sentences(" ".join(description.split()))
    if not sentences:
        return ""
    start = 1 if ('"' in sentences[0] or sentences[0].count(",") >= 3) else 0
    chosen = next((s for s in sentences[start:] if '"' not in s), sentences[0])
    if len(chosen) > limit:
        chosen = chosen[:limit - 3].rstrip() + "..."
    return chosen


def _sentences(text: str) -> List[str]:
    out: List[str] = []
    buf: List[str] = []
    in_quote = False
    for pos, ch in enumerate(text):
        buf.append(ch)
        if ch == '"':
            in_quote = not in_quote
        elif ch in ".!?" and not in_quote:
            nxt = text[pos + 1:pos + 2]
            if nxt == "" or nxt.isspace():
                out.append("".join(buf).strip())
                buf = []
    rest = "".join(buf).strip()
    if rest:
        out.append(rest)
    return [s for s in out if s]


COMMANDS_START = "<!-- skills:start -->"
COMMANDS_END = "<!-- skills:end -->"


def commands_table(skills: Dict[str, Dict[str, Any]]) -> str:
    rows = ["| Command | What it does |", "|---|---|"]
    for name in sorted(skills):
        what = what_it_does(skills[name]["desc"]).replace("|", "\\|")
        rows.append("| `/%s` | %s |" % (name, what))
    return "\n".join(rows)


def check_docs(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    docs = prod.files_under("docs/", ".md")
    if not docs and not ctx.release:
        return
    rel = "docs/commands.md"
    if prod.has(rel):
        text = prod.text(rel) or ""
        start, end = text.find(COMMANDS_START), text.find(COMMANDS_END)
        if start < 0 or end < start:
            rep.error(rel, "needs the lines %s and %s around the skill table" % (COMMANDS_START, COMMANDS_END))
        else:
            current = text[start + len(COMMANDS_START):end].strip("\n")
            wanted = commands_table(ctx.skills)
            if current != wanted:
                rep.error(rel, "the skill table does not match the skill descriptions; run: python tools/validate.py --write-commands")
    if ctx.quick:
        return
    _check_links(ctx)


_LINK = re.compile(r"(?<!\!)\[[^\]\n]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")


def _slug(heading: str) -> str:
    heading = re.sub(r"[`*_]", "", heading.strip().lower())
    heading = re.sub(r"[^\w\s-]", "", heading, flags=re.U)
    return re.sub(r"\s", "-", heading)


def _check_links(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    for rel in prod.files:
        if not rel.endswith(".md") or rel.startswith("templates/"):
            continue
        text = prod.text(rel)
        if not text:
            continue
        for number, line in enumerate(_blank_fences(text), 1):
            for match in _LINK.finditer(line):
                target = match.group(1)
                if re.match(r"^(?:[a-z]+:|#|<)", target, re.I):
                    continue
                path, _, anchor = target.partition("#")
                if not path:
                    continue
                full = os.path.normpath(os.path.join(os.path.dirname(prod.join(rel)), path.replace("/", os.sep)))
                where = "%s line %d" % (rel, number)
                if not os.path.exists(full):
                    rep.error(where, "the link '%s' points to a file that does not exist" % target)
                elif anchor and full.endswith(".md") and os.path.isfile(full):
                    try:
                        with open(full, "rb") as handle:
                            body = handle.read().decode("utf-8", errors="replace")
                    except OSError:
                        continue
                    slugs = set(_slug(h) for h in re.findall(r"^#+\s+(.+?)\s*$", body, re.M))
                    if anchor.lower() not in slugs:
                        rep.warn(where, "the link '%s' points to a heading that does not exist" % target)


def write_commands(prod: Product, skills: Dict[str, Dict[str, Any]]) -> bool:
    """Rewrite the block between the markers in docs/commands.md. Returns True when the file changed."""
    path = prod.join("docs/commands.md")
    table = commands_table(skills)
    block = "%s\n%s\n%s" % (COMMANDS_START, table, COMMANDS_END)
    old = prod.text("docs/commands.md") if prod.has("docs/commands.md") else None
    if old is None:
        new = "# Commands\n\nThese are the skills of the tutor. Say what you want in plain words or type the command.\n\n%s\n" % block
    else:
        start, end = old.find(COMMANDS_START), old.find(COMMANDS_END)
        if start >= 0 and end > start:
            new = old[:start] + block + old[end + len(COMMANDS_END):]
        else:
            new = old.rstrip("\n") + "\n\n" + block + "\n"
    if new == old:
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(new.encode("utf-8"))
    return True


# --------------------------------------------------------------------------- check: layout, runtime data

def release_layout() -> List[str]:
    """Every file the layout of the product lists (SPEC section 2)."""
    out = list(REQUIRED_ROOT_FILES)
    out.append("output-styles/tutor.md")
    out += ["rules/%s.md" % n for n in RULE_NAMES]
    out += ["skills/%s/SKILL.md" % n for n in SKILL_NAMES]
    out += ["agents/%s.md" % n for n in AGENT_NAMES]
    out += ["hooks/dispatch.py", "hooks/guard-messages.json"]
    out += ["hooks/handlers/%s.py" % n for n in HANDLER_NAMES]
    out += ["hooks/lib/%s.py" % n for n in LIB_NAMES]
    out += ["knowledge/glossary.jsonl", "knowledge/probes.jsonl", "knowledge/milestones.md", "knowledge/stacks.md",
            "knowledge/diagrams.md", "knowledge/concepts-index.txt"]
    out += ["templates/%s.md" % n for n in TEMPLATE_NAMES]
    out += ["tools/hooks.json", "tools/install.py", "tools/doctor.py", "tools/selftest.py", "tools/validate.py"]
    out += ["docs/%s.md" % n for n in DOC_NAMES]
    return out


def check_layout(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    if not ctx.release:
        return
    for rel in release_layout():
        if rel in ("MANIFEST.txt", "knowledge/concepts-index.txt"):
            continue         # the manifest and index checks give a more useful message
        if not prod.has(rel):
            rep.error(rel, "is missing (the layout of the product lists it)")
    if not _concept_files(prod):
        rep.error("knowledge/concepts", "has no concept files")


def check_placeholders(ctx: Ctx) -> None:
    """A release has no 'TO FILL AT RELEASE:' text left in the pages a learner reads: the product's README files,
    CHANGELOG.md and docs, plus the repo-root README.md when it sits next to the product. The builder's test report
    (repo/docs/test-report.md) is outside the product and is not read here."""
    prod, rep = ctx.prod, ctx.rep
    if not ctx.release:
        return
    pages = [(rel, prod.text(rel)) for rel in prod.files
             if rel == "CHANGELOG.md" or rel == "README.md" or rel.endswith("/README.md") or (rel.startswith("docs/") and rel.endswith(".md"))]
    repo_readme = os.path.join(os.path.dirname(prod.root), "README.md")
    if os.path.isfile(repo_readme):
        try:
            with open(repo_readme, "rb") as handle:
                pages.append(("repo README.md", handle.read().decode("utf-8", errors="replace")))
        except OSError:
            pass
    for rel, text in pages:
        if not text:
            continue
        for match in re.finditer(re.escape(PLACEHOLDER), text):
            line = text.count("\n", 0, match.start()) + 1
            rep.error("%s line %d" % (rel, line), "still has the text '%s'; fill it in before the release" % PLACEHOLDER)


def check_runtime(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    if not (ctx.no_runtime or ctx.release):
        return
    for rel in prod.runtime:
        rep.error(rel, "is runtime data or a cache and must not ship; delete it before release")


# --------------------------------------------------------------------------- generated files: index and manifest

def build_index(prod: Product, rep: Optional[Report] = None) -> List[str]:
    """One line per concept card, each under 400 bytes (signals are cut first, then terms, then the title)."""
    entries: List[Tuple[str, int, str]] = []
    scratch = rep if rep is not None else Report()
    # A probe row is also a long line that Grep hides, so a card that has a probe ends with "| probe:<line>".
    probe_lines: Dict[str, int] = {}
    probe_text = prod.text("knowledge/probes.jsonl")
    if probe_text:
        for number, line in enumerate(probe_text.replace("\r\n", "\n").split("\n"), 1):
            if not line.strip():
                continue
            try:
                probe = json.loads(line)
            except ValueError:
                continue
            if isinstance(probe, dict) and isinstance(probe.get("id"), str):
                probe_lines.setdefault(probe["id"], number)
    for rel in _concept_files(prod):
        name = rel.split("/")[-1]
        text = prod.text(rel)
        if text is None:
            continue
        for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or not isinstance(row.get("id"), str):
                continue
            pointer = "%s:%d" % (name, number)
            if row["id"] in probe_lines:
                pointer += " | probe:%d" % probe_lines[row["id"]]
            entries.append((name, number, _index_line(row, pointer, scratch)))
    entries.sort(key=lambda e: (e[0], e[1]))
    return [e[2] for e in entries]


def _index_line(row: Dict[str, Any], pointer: str, rep: Report) -> str:
    needs = _list(row.get("needs"))
    terms = [t.replace("|", "/") for t in _list(row.get("terms"))][:4]
    signals = [s.replace("|", "/") for s in _list(row.get("signals"))][:8]
    title = str(row.get("title", "")).replace("|", "/")

    def make(sig: List[str], trm: List[str], ttl: str) -> str:
        return "%s | %s | %s | t%s | needs: %s | terms: %s | signals: %s | %s" % (
            row.get("id"), ttl, row.get("domain", ""), row.get("tier", ""), ", ".join(needs) or "-",
            ", ".join(trm) or "-", ", ".join(sig) or "-", pointer)

    line = make(signals, terms, title)
    while len(line.encode("utf-8")) > INDEX_LINE_MAX_BYTES and signals:
        signals = signals[:-1]
        line = make(signals, terms, title)
    while len(line.encode("utf-8")) > INDEX_LINE_MAX_BYTES and len(terms) > 1:
        terms = terms[:-1]
        line = make(signals, terms, title)
    while len(line.encode("utf-8")) > INDEX_LINE_MAX_BYTES and len(title) > 20:
        title = title[:-5].rstrip() + "..."
        line = make(signals, terms, title)
    return line


def index_text(prod: Product) -> str:
    lines = build_index(prod)
    return "\n".join(lines) + ("\n" if lines else "")


def index_problem(prod: Product) -> Optional[str]:
    """None when knowledge/concepts-index.txt is current, else a plain sentence that says why not."""
    rel = "knowledge/concepts-index.txt"
    if not prod.has(rel):
        return "the file is missing; run: python tools/validate.py --write-index"
    if prod.text(rel) != index_text(prod):
        return "is out of date with the concept files; run: python tools/validate.py --write-index"
    return None


def write_index(prod: Product) -> int:
    path = prod.join("knowledge/concepts-index.txt")
    text = index_text(prod)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    return text.count("\n")


def check_index(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    if not _concept_files(prod):
        return
    problem = index_problem(prod)
    if problem is None:
        long_lines = [l for l in (prod.text("knowledge/concepts-index.txt") or "").split("\n") if len(l.encode("utf-8")) > INDEX_LINE_MAX_BYTES]
        if long_lines:
            rep.error("knowledge/concepts-index.txt", "has a line over 399 bytes")
        return
    if not prod.has("knowledge/concepts-index.txt") and not ctx.release:
        rep.warn("knowledge/concepts-index.txt", problem)
    else:
        rep.error("knowledge/concepts-index.txt", problem)


MANIFEST_EXCLUDED = ("MANIFEST.txt",)


def manifest_entries(prod: Product) -> List[Tuple[str, str]]:
    """[(sha256, path)] of every shipped file except the manifest itself, sorted by path."""
    out = []
    for rel in prod.files:
        if rel in MANIFEST_EXCLUDED:
            continue
        data = prod.raw(rel)
        if data is None:
            continue
        out.append((hashlib.sha256(data).hexdigest(), rel))
    out.sort(key=lambda e: e[1])
    return out


def manifest_text(prod: Product) -> str:
    version = (prod.text("VERSION") or "").strip()
    lines = ["# developer-tutor MANIFEST", "# version %s" % version]
    lines += ["%s  %s" % (digest, rel) for digest, rel in manifest_entries(prod)]
    return "\n".join(lines) + "\n"


def write_manifest(prod: Product) -> int:
    path = prod.join("MANIFEST.txt")
    text = manifest_text(prod)
    with open(path, "wb") as handle:
        handle.write(text.encode("utf-8"))
    return text.count("\n") - 2


def check_manifest(ctx: Ctx) -> None:
    prod, rep = ctx.prod, ctx.rep
    rel = "MANIFEST.txt"
    if not prod.has(rel):
        if ctx.release:
            rep.error(rel, "is missing; run: python tools/validate.py --write-manifest")
        else:
            rep.warn(rel, "is missing (it is written at release time with --write-manifest)")
        return
    report = rep.error if ctx.release else rep.warn
    text = prod.text(rel) or ""
    lines = text.split("\n")
    version = (prod.text("VERSION") or "").strip()
    if lines[:2] != ["# developer-tutor MANIFEST", "# version %s" % version]:
        report(rel, "the first two lines must be '# developer-tutor MANIFEST' and '# version %s'" % version)
    listed: Dict[str, str] = {}
    for number, line in enumerate(lines[2:], 3):
        if not line.strip():
            continue
        match = re.match(r"^([0-9a-f]{64})  (\S.*)$", line)
        if not match:
            report("%s line %d" % (rel, number), "is not '<sha256>  <path>'")
            continue
        listed[match.group(2)] = match.group(1)
    actual = dict((path, digest) for digest, path in manifest_entries(prod))
    stale = sorted(p for p in listed if p in actual and actual[p] != listed[p])
    gone = sorted(p for p in listed if p not in actual)
    extra = sorted(p for p in actual if p not in listed)
    if stale:
        report(rel, "does not match %d file(s) on disk, for example %s; run: python tools/validate.py --write-manifest" % (len(stale), stale[0]))
    if gone:
        report(rel, "lists %d file(s) that no longer exist, for example %s" % (len(gone), gone[0]))
    if extra:
        report(rel, "does not list %d shipped file(s), for example %s" % (len(extra), extra[0]))


# --------------------------------------------------------------------------- driver

CHECKS = (
    ("inventory", check_inventory),
    ("hygiene", check_hygiene),
    ("skills", check_skills),
    ("agents", check_agents),
    ("output style", check_style),
    ("rules", check_rules),
    ("CLAUDE.md", check_claude_md),
    ("budget", check_budget),
    ("knowledge", check_knowledge),
    ("pointers", check_pointers),
    ("labels", check_labels),
    ("claude variables", check_claude_vars),
    ("hook text", check_hook_text),
    ("small files", check_small_files),
    ("docs", check_docs),
    ("layout", check_layout),
    ("release placeholders", check_placeholders),
    ("runtime data", check_runtime),
    ("concept index", check_index),
    ("manifest", check_manifest),
)


def validate(root: Optional[str] = None, quick: bool = False, release: bool = False, no_runtime_data: bool = False) -> Report:
    """Run every check on the folder `root` (default: the .claude folder of this script)."""
    rep = Report()
    prod = open_product(root or DEFAULT_ROOT)
    ctx = Ctx(prod, rep, quick, release, no_runtime_data)
    for name, func in CHECKS:
        try:
            func(ctx)
        except Exception as exc:  # noqa: BLE001 - a bug in one check must not hide the others
            rep.error("validate.py", "the check '%s' stopped with %s: %s (this is a bug in validate.py)"
                      % (name, type(exc).__name__, str(exc)[:100]))
    return rep


def run(root: Optional[str] = None, quick: bool = False, release: bool = False, no_runtime_data: bool = False) -> List[str]:
    """For selftest.py: the ERROR lines only (an empty list means pass)."""
    return validate(root, quick, release, no_runtime_data).errors


def _usage() -> str:
    return ("usage: python validate.py [--root DIR] [--quick] [--release] [--no-runtime-data] "
            "[--write-index] [--write-manifest] [--write-commands]")


def main(argv: List[str]) -> int:
    root = DEFAULT_ROOT
    flags: Set[str] = set()
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--root" and i + 1 < len(argv):
            root = argv[i + 1]
            i += 2
            continue
        if arg.startswith("--root="):
            root = arg[len("--root="):]
        elif arg in ("--quick", "--release", "--no-runtime-data", "--write-index", "--write-manifest", "--write-commands"):
            flags.add(arg)
        elif arg in ("-h", "--help"):
            say(_usage())
            return 0
        else:
            say("Unknown option: %s" % arg)
            say(_usage())
            return 2
        i += 1
    if not os.path.isdir(root):
        say("The folder does not exist: %s" % root)
        return 2
    # Generated files first, so the checks below see the final bytes. The manifest goes last.
    if flags & {"--write-commands", "--write-index", "--write-manifest"}:
        pre = Report()
        probe_ctx = Ctx(Product(root), pre, True, False, False)
        try:
            check_skills(probe_ctx)
        except Exception:  # noqa: BLE001
            pass
        if "--write-commands" in flags:
            changed = write_commands(probe_ctx.prod, probe_ctx.skills)
            say("docs/commands.md: %s" % ("table rewritten" if changed else "table already current"))
        if "--write-index" in flags:
            say("knowledge/concepts-index.txt: %d lines written" % write_index(Product(root)))
        if "--write-manifest" in flags:
            say("MANIFEST.txt: %d files listed" % write_manifest(Product(root)))
    rep = validate(root, quick="--quick" in flags, release="--release" in flags, no_runtime_data="--no-runtime-data" in flags)
    for line in rep.notes:
        say(line)
    for line in rep.errors:
        say(line)
    for line in rep.warnings:
        say(line)
    say("RESULT: %d errors, %d warnings" % (len(rep.errors), len(rep.warnings)))
    return 1 if rep.errors else 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        say("validate.py stopped with %s: %s" % (type(exc).__name__, str(exc)[:100]))
        code = 1
    sys.exit(code)
