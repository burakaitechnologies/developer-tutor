"""selftest_files.py - checks the shape of the shipped files: settings, hook launcher, personal data, Python 3.9 rules.

What: run() returns a list of failure messages (empty = pass). Each check is a small function that takes the
product folder, so the same checks can run on a broken copy to prove that they fire.
  1 settings.json shape (SPEC 4.2)            5 size caps of dispatch.py and the handlers
  2 tools/hooks.json shape and launcher       6 byte-code rule of the hook library
  3 personal data in every shipped file       7 no symbolic links or junctions
  4 Python 3.9 syntax and module headers      8 the concept index is current
  9 JSON files parse                         10 validate.py really finds broken files (on a temp copy)
Why: Claude Code ignores a settings.json with one wrong value and silently drops a skill with bad front matter;
a hook that uses Python 3.10 syntax fails on a learner's older Python; a stray name or path in a shipped file
is a privacy leak. A test finds these before a learner does.
How it fails safely: it only reads the product and writes into a temp folder it removes; a check that crashes
becomes one failure message; no network; standard library only.
Who calls it: tools/selftest.py (module "files"). Run alone: python selftest_files.py [product-folder]
"""
from __future__ import annotations

import ast
import getpass
import json
import os
import re
import shutil
import sys
import tempfile
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# --------------------------------------------------------------------------- shared helpers


def _import_validate() -> Any:
    import validate
    return validate


def shipped_files(root: str) -> List[str]:
    """Shipped files of a product folder (forward-slash paths relative to it)."""
    return list(_import_validate().open_product(root).files)


def read_text(root: str, rel: str) -> str:
    try:
        with open(os.path.join(root, *rel.split("/")), "rb") as handle:
            return handle.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def python_files(root: str) -> List[str]:
    return [rel for rel in shipped_files(root) if rel.endswith(".py")]


# --------------------------------------------------------------------------- 1 settings.json

SKILL_NAMES = ("tutor", "tutor-setup", "learn", "progress", "explain", "think-first", "new-project", "fix-it",
               "save-point", "before-push", "git-rescue")
SETTINGS_TOP_KEYS = {"$schema", "outputStyle", "permissions"}
PERMISSION_KEYS = {"defaultMode", "deny", "ask", "allow"}
FORBIDDEN_SETTINGS_WORDS = ("hooks", "env", "statusLine", "apiKeyHelper", "enableAllProjectMcpServers", "disableAllHooks",
                            "skipDangerousModePermissionPrompt")
RULE_GRAMMAR = re.compile(r"^(?:Bash|PowerShell|Read|Edit|Write|Glob|Grep|WebFetch|WebSearch|NotebookEdit|Skill|Agent|Task|"
                          r"mcp__[A-Za-z0-9_-]+)(?:\(.+\))?$", re.S)
FORCE_PUSH_PATTERNS = ("git push --force *", "git push -f *", "git push * --force", "git push * --force *",
                       "git push * -f", "git push * -f *", "git push +*", "git push * +*")
REMOVED_ASK_SHAPES = (
    r"(?:npm|pnpm|yarn|bun)\s+(?:install|i|add)\b(?!.*(?:-g\b|--global))", r"pip3?\s+install", r"python3?\s+-m\s+pip",
    r"uv\s+add", r"poetry\s+add", r"cargo\s+add", r"(?:npx|bunx|uvx)\b", r"pnpm\s+dlx", r"git\s+rm\b", r"git\s+restore\b",
    r"(?:ssh|scp|rsync)\b")
READ_DENY_NEEDS = (".env", ".pem", "id_rsa", "id_ed25519", "~/.ssh", "~/.aws", "~/.config/gh")


def check_settings(root: str) -> List[str]:
    """settings.json: strict JSON, only known keys, the 11 Skill entries, twin rules, the 8 force-push shapes."""
    path = os.path.join(root, "settings.json")
    if not os.path.isfile(path):
        return ["settings.json is missing"]
    fails: List[str] = []
    try:
        with open(path, "rb") as handle:
            raw = handle.read()
    except OSError:
        return ["settings.json cannot be read"]
    if _is_merged_copy(root, raw):
        return check_settings_merged(raw)
    if raw.startswith(b"\xef\xbb\xbf"):
        fails.append("settings.json starts with a BOM")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return fails + ["settings.json is not UTF-8"]
    duplicates: List[str] = []

    def pairs(items: List[Tuple[str, Any]]) -> Dict[str, Any]:
        seen: Dict[str, Any] = {}
        for key, value in items:
            if key in seen:
                duplicates.append(key)
            seen[key] = value
        return seen

    try:
        data = json.loads(text, object_pairs_hook=pairs)
    except ValueError as exc:
        return fails + ["settings.json is not strict JSON (%s)" % str(exc)[:80]]
    if duplicates:
        fails.append("settings.json repeats the key(s): %s" % ", ".join(sorted(set(duplicates))))
    if not isinstance(data, dict):
        return fails + ["settings.json must hold one JSON object"]
    extra = sorted(set(data) - SETTINGS_TOP_KEYS)
    if extra:
        fails.append("settings.json has top-level key(s) that are not allowed: %s (allowed: $schema, outputStyle, permissions)" % ", ".join(extra))
    for word in FORBIDDEN_SETTINGS_WORDS:
        if re.search(r'"%s"' % re.escape(word), text):
            fails.append('settings.json contains the key "%s"; the kit never ships it' % word)
    if "bypass" in text.lower():
        fails.append("settings.json mentions bypass; the kit never ships a bypass setting")
    style_name = _style_name(root)
    if data.get("outputStyle") != style_name:
        fails.append("settings.json outputStyle %r must equal the output style name %r" % (data.get("outputStyle"), style_name))
    perms = data.get("permissions")
    if not isinstance(perms, dict):
        return fails + ["settings.json needs a permissions object"]
    extra = sorted(set(perms) - PERMISSION_KEYS)
    if extra:
        fails.append("permissions has key(s) that are not allowed: %s (allowed: defaultMode, deny, ask, allow)" % ", ".join(extra))
    if perms.get("defaultMode") != "acceptEdits":
        fails.append("permissions.defaultMode must be acceptEdits (found %r)" % (perms.get("defaultMode"),))
    lists: Dict[str, List[str]] = {}
    for name in ("deny", "ask", "allow"):
        value = perms.get(name)
        if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
            fails.append("permissions.%s must be a list of non-empty text" % name)
            value = []
        lists[name] = value
    expected_allow = sorted("Skill(%s)" % n for n in SKILL_NAMES)
    if sorted(lists["allow"]) != expected_allow:
        fails.append("permissions.allow must hold exactly the 11 entries Skill(<name>) and nothing else (found %d entries)" % len(lists["allow"]))
    for name in ("deny", "ask", "allow"):
        for rule in lists[name]:
            if not RULE_GRAMMAR.match(rule) or rule.count("(") != rule.count(")"):
                fails.append("permissions.%s rule %r does not match Tool or Tool(pattern)" % (name, rule[:60]))
            if rule.startswith("Write(") or rule.startswith("Edit("):
                fails.append("permissions.%s rule %r is a path rule for Write or Edit; Claude Code does not use those" % (name, rule[:60]))
    for name in ("deny", "ask"):
        have = set(lists[name])
        for rule in lists[name]:
            if rule.startswith("Bash(") and rule.endswith(")"):
                twin = "PowerShell(" + rule[len("Bash("):]
                if twin not in have:
                    fails.append("permissions.%s has %r but no PowerShell twin %r" % (name, rule[:60], twin[:60]))
            if rule == "Bash" and "PowerShell" not in have:
                fails.append("permissions.%s has Bash but no PowerShell twin" % name)
    deny = set(lists["deny"])
    for pattern in FORCE_PUSH_PATTERNS:
        for tool in ("Bash", "PowerShell"):
            if "%s(%s)" % (tool, pattern) not in deny:
                fails.append("permissions.deny is missing the force-push rule %s(%s)" % (tool, pattern))
    for rule in lists["deny"]:
        body = rule.split("(", 1)[-1]
        if body.startswith("git push") and ("force-with-lease" in body or re.match(r"^git push( \*)?\)?$", body)):
            fails.append("permissions.deny blocks %r, but force-with-lease and a plain push must stay possible" % rule[:60])
    for needle in READ_DENY_NEEDS:
        if not any(r.startswith("Read(") and needle in r for r in lists["deny"]):
            fails.append("permissions.deny has no Read rule for %s" % needle)
    if not any(r.startswith("Bash(git push") for r in lists["ask"]):
        fails.append("permissions.ask has no rule that asks before git push")
    for needle in ("git reset --hard", "git clean -f", "git branch -D"):
        if not any(needle in r for r in lists["ask"]):
            fails.append("permissions.ask has no rule for '%s'" % needle)
    for rule in lists["ask"] + lists["deny"]:
        for shape in REMOVED_ASK_SHAPES:
            if re.match(r"^(?:Bash|PowerShell)\(%s" % shape, rule):
                fails.append("permissions rule %r should not exist; the hook decides this case with context" % rule[:60])
    return fails


def _is_merged_copy(root: str, raw: bytes) -> bool:
    """True when this is an installed copy whose settings.json differs from the shipped one (install.py merged it)."""
    validate = _import_validate()
    if not validate.installed_mode():
        return False
    import hashlib
    try:
        with open(os.path.join(root, "MANIFEST.txt"), "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return False
    match = re.search(r"^([0-9a-f]{64})  settings\.json$", text, re.M)
    return bool(match) and match.group(1) != hashlib.sha256(raw).hexdigest()


def check_settings_merged(raw: bytes) -> List[str]:
    """A learner's own settings are merged into ours: only check that the file is JSON and keeps our safety rules."""
    try:
        data = json.loads(raw.decode("utf-8-sig"))
    except (ValueError, UnicodeDecodeError):
        return ["settings.json is not valid JSON, so Claude Code would ignore all of it"]
    perms = data.get("permissions") if isinstance(data, dict) else None
    deny = perms.get("deny") if isinstance(perms, dict) else None
    if not isinstance(deny, list):
        return ["settings.json has lost the deny rules of the kit"]
    fails = []
    for pattern in FORCE_PUSH_PATTERNS:
        for tool in ("Bash", "PowerShell"):
            if "%s(%s)" % (tool, pattern) not in deny:
                fails.append("settings.json is missing the force-push rule %s(%s)" % (tool, pattern))
    return fails


def _style_name(root: str) -> str:
    match = re.search(r"^name:\s*(\S+)\s*$", read_text(root, "output-styles/tutor.md"), re.M)
    return match.group(1) if match else ""


# --------------------------------------------------------------------------- 2 hooks.json

LAUNCHER = ("import os,sys,runpy; (sys.version_info>=(3,9) or sys.exit('tutor hooks need Python 3.9 or newer')); "
            "p=os.path.join(os.environ.get('CLAUDE_PROJECT_DIR','.'),'.claude','hooks','dispatch.py'); "
            "(os.path.isfile(p) or sys.exit(0)); sys.argv=[p]+sys.argv[1:]; runpy.run_path(p,run_name='__main__')")
HOOK_EVENTS = {
    "SessionStart": ("startup|resume|clear|compact|fork", 15, "session-start"),
    "UserPromptSubmit": (None, 10, "user-prompt"),
    "PreToolUse": ("Bash|PowerShell|Write|Edit|NotebookEdit", 8, "pre-tool"),
    "PostToolUse": ("Bash|PowerShell|Write|Edit|NotebookEdit", 10, "post-tool"),
    "Stop": (None, 15, "stop"),
    "SubagentStart": (None, 5, "subagent-start"),
}


def check_hooks_json(root: str) -> List[str]:
    path = os.path.join(root, "tools", "hooks.json")
    if not os.path.isfile(path):
        return ["tools/hooks.json is missing"]
    try:
        with open(path, "rb") as handle:
            data = json.loads(handle.read().decode("utf-8"))
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        return ["tools/hooks.json cannot be read as JSON (%s)" % type(exc).__name__]
    fails: List[str] = []
    if not isinstance(data, dict) or set(data) != {"hooks"} or not isinstance(data.get("hooks"), dict):
        return ["tools/hooks.json must be one object with the single key hooks"]
    hooks = data["hooks"]
    if set(hooks) != set(HOOK_EVENTS):
        fails.append("tools/hooks.json must hold exactly these events: %s (found %s)" % (", ".join(sorted(HOOK_EVENTS)), ", ".join(sorted(hooks))))
    launchers: Set[str] = set()
    for event, (matcher, timeout, mode) in HOOK_EVENTS.items():
        groups = hooks.get(event)
        if not isinstance(groups, list) or len(groups) != 1 or not isinstance(groups[0], dict):
            fails.append("%s must have exactly one matcher group" % event)
            continue
        group = groups[0]
        if group.get("matcher") != matcher:
            fails.append("%s matcher must be %r (found %r)" % (event, matcher, group.get("matcher")))
        if set(group) - {"matcher", "hooks"}:
            fails.append("%s group has unexpected keys: %s" % (event, ", ".join(sorted(set(group) - {"matcher", "hooks"}))))
        handlers = group.get("hooks")
        if not isinstance(handlers, list) or len(handlers) != 1 or not isinstance(handlers[0], dict):
            fails.append("%s must have exactly one hook" % event)
            continue
        hook = handlers[0]
        if set(hook) != {"type", "command", "timeout", "args"}:
            fails.append("%s hook must have exactly the keys type, command, timeout, args" % event)
        if hook.get("type") != "command":
            fails.append("%s hook type must be command" % event)
        if hook.get("command") != "python3":
            fails.append("%s hook command must be python3 (found %r)" % (event, hook.get("command")))
        if hook.get("timeout") != timeout:
            fails.append("%s timeout must be %d (found %r)" % (event, timeout, hook.get("timeout")))
        args = hook.get("args")
        if not isinstance(args, list) or len(args) != 7 or any(not isinstance(a, str) for a in args):
            fails.append("%s args must be 7 texts: -I -B -X utf8 -c <launcher> <mode>" % event)
            continue
        if args[:5] != ["-I", "-B", "-X", "utf8", "-c"]:
            fails.append("%s args must start with -I -B -X utf8 -c" % event)
        if args[6] != mode:
            fails.append("%s last argument must be the mode %r (found %r)" % (event, mode, args[6]))
        launchers.add(args[5])
    if len(launchers) > 1:
        fails.append("the launcher text differs between events; it must be identical except for the mode")
    for launcher in launchers:
        if launcher != LAUNCHER:
            fails.append("the launcher text is not the one of SPEC 4.1")
        for bad in ("&&", "||", "|", "`", "$(", ">>", "2>"):
            if bad in launcher:
                fails.append("the launcher contains the shell operator %r" % bad)
        for needed in ("dispatch.py", "CLAUDE_PROJECT_DIR", "runpy.run_path"):
            if needed not in launcher:
                fails.append("the launcher does not mention %s" % needed)
    return fails


# --------------------------------------------------------------------------- 3 personal data

PLACEHOLDER_NAMES = {"ada", "you", "user", "username", "yourname", "your-name", "your_name", "name", "me", "someone", "example",
                     "public", "default", "all users", "admin", "administrator", "test", "learner", "student", "alice", "bob",
                     "runner", "ubuntu", "foo", "x", "home", "project", "app", "dev"}
COMMON_USER_NAMES = {"user", "admin", "root", "runner", "test", "guest", "default", "public", "ubuntu", "vagrant", "docker",
                     "builder", "build", "jenkins", "github", "azure", "system", "owner", "student", "learner", "tutor",
                     "claude", "administrator", "pi", "ec2-user"}
EMAIL_OK_LOCAL = {"you", "name", "your-name", "yourname", "user", "someone", "me", "ada", "alice", "bob", "jane", "email",
                  "address", "username", "noreply", "no-reply", "git", "x", "a", "foo", "test", "jane.doe", "first.last"}
EMAIL_OK_DOMAIN_SUFFIX = ("example.com", "example.org", "example.net", ".example", "noreply.github.com", ".invalid", ".test",
                          ".localhost", ".local")
_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s\"'`<>|*?:;,)]+)", re.I)
_UNIX_HOME = re.compile(r"(?<![\w.~])/(?:Users|home)/([A-Za-z0-9_.-]+)/")
_EMAIL = re.compile(r"(?<![\w.+\\-])([\w.+-]+)@([A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+)")
_PHONE = re.compile(r"(?<![\w.])(?:\+\d{1,3}[ .-]?)?(?:\(\d{3}\)[ .-]?|\d{3}[ .-])\d{3}[ .-]\d{4}(?![\w.])")
_PHONE_INTL = re.compile(r"(?<![\w.])\+\d{2}[ -]?\d{3}[ -]?\d{3}[ -]?\d{2}[ -]?\d{2}(?![\w.])")
_IPV4 = re.compile(r"(?<![\w.])(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})(?!\w)(?!\.\d)")
GENERIC_IPS = ("10.0.0.0", "10.0.0.1", "192.168.0.1", "192.168.1.1", "172.16.0.1", "169.254.169.254", "255.255.255.255", "8.8.8.8")
_OWNER_WORDS = ("business" + "-" + "project",)


def os_user_names() -> List[str]:
    names = []
    for candidate in (os.environ.get("USERNAME"), os.environ.get("USER"), _safe_getuser()):
        if candidate and candidate.lower() not in COMMON_USER_NAMES and len(candidate) >= 4 and candidate.lower() not in names:
            names.append(candidate.lower())
    return names


def _safe_getuser() -> str:
    try:
        return getpass.getuser()
    except Exception:  # noqa: BLE001 - some CI machines have no user name
        return ""


def personal_findings(text: str, users: Sequence[str]) -> List[Tuple[int, str]]:
    """[(line number, kind)] of things in `text` that look like personal data."""
    out: List[Tuple[int, str]] = []
    for number, line in enumerate(text.split("\n"), 1):
        for match in _DRIVE_PATH.finditer(line):
            name = match.group(1)
            if len(name) == 1 or name.lower() in PLACEHOLDER_NAMES or name.startswith(("%", "$", "{", "[", "~")):
                continue
            out.append((number, "a Windows user folder path (C:\\Users\\%s)" % name))
        for match in _UNIX_HOME.finditer(line):
            name = match.group(1)
            if len(name) == 1 or name.lower() in PLACEHOLDER_NAMES or name.startswith(("%", "$", "{", "[", "~")):
                continue
            out.append((number, "a home folder path (/%s/)" % name))
        for match in _EMAIL.finditer(line):
            local, domain = match.group(1), match.group(2).lower()
            if not re.search(r"[A-Za-z]{2,}$", domain):
                continue
            if local.lower() in EMAIL_OK_LOCAL or domain.endswith(EMAIL_OK_DOMAIN_SUFFIX):
                continue
            if re.search(r"://[^\s/@]*$", line[max(0, match.start() - 120):match.start()]):
                continue      # user:password@host inside a URL is a secret-shaped test string, not an address
            out.append((number, "an e-mail address (%s@%s)" % (local[:2] + "...", domain)))
        for match in list(_PHONE.finditer(line)) + list(_PHONE_INTL.finditer(line)):
            digits = re.sub(r"\D", "", match.group(0))
            if "555" in (digits[-10:-7], digits[-7:-4]):
                continue
            out.append((number, "a phone-like number"))
        for match in _IPV4.finditer(line):
            parts = [int(g) for g in match.groups()]
            if any(p > 255 for p in parts):
                continue
            text_ip = ".".join(str(p) for p in parts)
            if text_ip in ("127.0.0.1", "0.0.0.0") or text_ip in GENERIC_IPS or text_ip.startswith(("192.0.2.", "198.51.100.", "203.0.113.")):
                continue
            out.append((number, "an IP address (%s)" % text_ip))
        lower = line.lower()
        for word in _OWNER_WORDS:
            if word in lower:
                out.append((number, "the private project name %r" % word))
        for name in users:
            if name in lower:
                out.append((number, "the user name of the computer running this test"))
    return out


def check_personal_data(root: str) -> List[str]:
    fails: List[str] = []
    users = os_user_names()
    for rel in shipped_files(root):
        if rel.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".ico", ".zip", ".pdf")):
            continue
        text = read_text(root, rel)
        for number, kind in personal_findings(text, users)[:5]:
            fails.append("%s line %d holds %s" % (rel, number, kind))
    return fails


# --------------------------------------------------------------------------- 4 Python 3.9 lint

TYPE_NAMES = {"str", "int", "float", "bool", "bytes", "list", "dict", "set", "frozenset", "tuple", "type", "object", "complex",
              "bytearray", "Any", "List", "Dict", "Set", "Tuple", "Optional", "Callable", "Iterable", "Sequence", "Mapping",
              "FrozenSet", "Type", "Union", "Path", "Iterator", "Generator"}
BANNED_MODULE_ATTRS = {
    ("datetime", "UTC"), ("itertools", "pairwise"), ("itertools", "batched"), ("typing", "Self"), ("typing", "TypeAlias"),
    ("typing", "ParamSpec"), ("typing", "TypeGuard"), ("typing", "LiteralString"), ("typing", "Never"), ("typing", "assert_never"),
    ("typing", "override"), ("typing", "Required"), ("typing", "NotRequired"), ("typing", "Unpack"), ("typing", "TypeVarTuple"),
    ("typing", "reveal_type"), ("typing", "assert_type"), ("contextlib", "chdir"), ("enum", "StrEnum"), ("asyncio", "TaskGroup"),
    ("asyncio", "timeout"), ("math", "cbrt"), ("math", "exp2"), ("hashlib", "file_digest"), ("inspect", "get_annotations"),
    ("sys", "orig_argv"), ("sys", "exception"), ("types", "NoneType"), ("types", "UnionType"), ("types", "EllipsisType"),
}
BANNED_ANY_ATTRS = {"bit_count", "is_junction", "isjunction", "hardlink_to"}
BANNED_BUILTINS = {"aiter", "anext", "ExceptionGroup", "BaseExceptionGroup"}
BANNED_KEYWORDS = {"process_group", "delete_on_close", "onexc", "kw_only", "slots"}
WALK_OK_MODULES = {"os", "ast"}


def _line_starts(source: str) -> List[int]:
    starts = [0]
    for index, ch in enumerate(source):
        if ch == "\n":
            starts.append(index + 1)
    return starts


def _offset(source: str, starts: List[int], lineno: int, col: int) -> int:
    """Character offset of an AST position (col_offset counts UTF-8 bytes)."""
    start = starts[lineno - 1]
    line_end = source.find("\n", start)
    line = source[start:] if line_end < 0 else source[start:line_end]
    return start + len(line.encode("utf-8")[:col].decode("utf-8", errors="ignore"))


def _group_end(text: str, start: int) -> int:
    """Index of the parenthesis that closes the one at text[start]; -1 when none."""
    depth, quote, pos = 0, "", start
    while pos < len(text):
        ch = text[pos]
        if quote:
            if ch == "\\":
                pos += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "#":
            newline = text.find("\n", pos)
            pos = len(text) if newline < 0 else newline
            continue
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
            if depth == 0:
                return pos
        pos += 1
    return -1


def _is_parenthesised_with(source: str, starts: List[int], node: Any) -> bool:
    """True for `with (a as x, b as y):` (valid only from Python 3.10)."""
    begin = _offset(source, starts, node.lineno, node.col_offset)
    end = _offset(source, starts, node.body[0].lineno, node.body[0].col_offset)
    header = source[begin:end]
    match = re.match(r"\s*(?:async\s+)?with\s*\(", header)
    if not match:
        return False
    open_at = match.end() - 1
    close_at = _group_end(header, open_at)
    if close_at < 0 or not header[close_at + 1:].lstrip().startswith(":"):
        return False
    top = _top_level(header[open_at + 1:close_at])
    return "," in top or re.search(r"\sas\s", " " + top + " ") is not None


def _top_level(text: str) -> str:
    """The text with everything inside brackets and quotes blanked out."""
    out, depth, quote = [], 0, ""
    for ch in text:
        if quote:
            out.append(" ")
            if ch == quote:
                quote = ""
            continue
        if ch in "\"'":
            quote = ch
            out.append(" ")
        elif ch in "([{":
            depth += 1
            out.append(" ")
        elif ch in ")]}":
            depth -= 1
            out.append(" ")
        else:
            out.append(ch if depth == 0 else " ")
    return "".join(out)


def _typeish(node: Any) -> bool:
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Name):
        return node.id in TYPE_NAMES
    if isinstance(node, ast.Attribute):
        return isinstance(node.value, ast.Name) and node.value.id in ("typing", "typing_extensions") and node.attr in TYPE_NAMES
    if isinstance(node, ast.Subscript):
        return _typeish(node.value)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        return _typeish(node.left) or _typeish(node.right)
    return False


def lint_source(source: str, name: str, need_header: bool = True, need_future: bool = True) -> List[str]:
    """Findings (as text) for a Python source; an empty list means it fits the kit's Python 3.9 rules."""
    fails: List[str] = []
    try:
        tree = ast.parse(source, filename=name, feature_version=(3, 9))
    except SyntaxError as exc:
        return ["%s line %s: does not parse as Python 3.9 (%s)" % (name, exc.lineno, str(exc.msg)[:80])]
    except ValueError:
        try:
            tree = ast.parse(source, filename=name)
        except SyntaxError as exc:
            return ["%s line %s: syntax error (%s)" % (name, exc.lineno, str(exc.msg)[:80])]
    if need_header and not (ast.get_docstring(tree) or "").strip():
        fails.append("%s: the module must start with a docstring header" % name)
    has_future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names)
                     for n in tree.body)
    if need_future and not has_future:
        fails.append("%s: the module must contain 'from __future__ import annotations'" % name)
    aliases: Dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                aliases[(alias.asname or alias.name).split(".")[0]] = alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                aliases[alias.asname or alias.name] = node.module.split(".")[0] + "." + alias.name
    annotation_ids: Set[int] = set()
    if has_future:
        for node in ast.walk(tree):
            notes = []
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = node.args
                for arg in list(args.args) + list(args.kwonlyargs) + list(getattr(args, "posonlyargs", [])) + [args.vararg, args.kwarg]:
                    if arg is not None and arg.annotation is not None:
                        notes.append(arg.annotation)
                if node.returns is not None:
                    notes.append(node.returns)
            elif isinstance(node, ast.AnnAssign):
                notes.append(node.annotation)
            for note in notes:
                for sub in ast.walk(note):
                    annotation_ids.add(id(sub))
    starts = _line_starts(source)
    guarded: Set[int] = set()       # run-time API uses inside `if sys.version_info ...` or `try ... except ImportError`
    for node in ast.walk(tree):
        parts: List[Any] = []
        if isinstance(node, ast.If) and "version_info" in ast.dump(node.test):
            parts = list(node.body) + list(node.orelse)
        elif isinstance(node, ast.Try) and any(
                h.type is None or any(isinstance(n, ast.Name) and n.id in ("ImportError", "AttributeError", "ModuleNotFoundError", "Exception")
                                      for n in ast.walk(h.type)) for h in node.handlers):
            parts = list(node.body)
        for part in parts:
            for sub in ast.walk(part):
                guarded.add(id(sub))
    match_class = getattr(ast, "Match", None)
    star_class = getattr(ast, "TryStar", None)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        where = "%s line %d" % (name, line)
        if match_class is not None and isinstance(node, match_class):
            fails.append("%s: a match statement needs Python 3.10" % where)
        elif star_class is not None and isinstance(node, star_class):
            fails.append("%s: except* needs Python 3.11" % where)
        elif isinstance(node, ast.Import) and id(node) not in guarded:
            for alias in node.names:
                if alias.name.split(".")[0] == "tomllib":
                    fails.append("%s: tomllib needs Python 3.11" % where)
        elif isinstance(node, ast.ImportFrom) and id(node) not in guarded:
            module = node.module or ""
            if module.split(".")[0] == "tomllib":
                fails.append("%s: tomllib needs Python 3.11" % where)
            for alias in node.names:
                if (module, alias.name) in BANNED_MODULE_ATTRS:
                    fails.append("%s: %s.%s needs a newer Python than 3.9" % (where, module, alias.name))
        elif isinstance(node, ast.Attribute) and id(node) not in guarded:
            receiver = node.value
            module = aliases.get(receiver.id, receiver.id) if isinstance(receiver, ast.Name) else ""
            if (module.split(".")[0], node.attr) in BANNED_MODULE_ATTRS:
                fails.append("%s: %s.%s needs a newer Python than 3.9" % (where, module.split(".")[0], node.attr))
            elif node.attr in BANNED_ANY_ATTRS:
                fails.append("%s: .%s needs a newer Python than 3.9" % (where, node.attr))
            elif node.attr == "walk" and module.split(".")[0] not in WALK_OK_MODULES:
                fails.append("%s: .walk() on a path needs Python 3.12 (use os.walk)" % where)
        elif isinstance(node, ast.Call) and id(node) not in guarded:
            func = node.func
            if isinstance(func, ast.Name) and func.id == "zip" and any(k.arg == "strict" for k in node.keywords):
                fails.append("%s: zip(strict=...) needs Python 3.10" % where)
            if isinstance(func, ast.Name) and func.id in BANNED_BUILTINS:
                fails.append("%s: %s() needs a newer Python than 3.9" % (where, func.id))
            for keyword in node.keywords:
                if keyword.arg in BANNED_KEYWORDS:
                    fails.append("%s: the argument %s= needs a newer Python than 3.9" % (where, keyword.arg))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) and id(node) not in annotation_ids:
            left, right = node.left, node.right
            none_side = any(isinstance(s, ast.Constant) and s.value is None for s in (left, right))
            if none_side or (_typeish(left) and _typeish(right)):
                fails.append("%s: a type written with | is evaluated at run time; use Optional[...] or Union[...] (needs Python 3.10)" % where)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            if _is_parenthesised_with(source, starts, node):
                fails.append("%s: a parenthesised with-statement is not supported before Python 3.10" % where)
        elif type(node).__name__ == "TypeAlias":
            fails.append("%s: the 'type' statement needs Python 3.12" % where)
        if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and getattr(node, "type_params", None):
            fails.append("%s: type parameters in square brackets need Python 3.12" % where)
    fails += _fstring_findings(tree, source, name)
    unique: List[str] = []
    for item in fails:
        if item not in unique:
            unique.append(item)
    return unique


def _fstring_findings(tree: Any, source: str, name: str) -> List[str]:
    """f-strings that only Python 3.12 can read: the same quote inside the braces, or a backslash inside the braces.

    Before 3.12 these do not parse at all, so this matters only when the test runs on 3.12 or newer."""
    if sys.version_info < (3, 12):
        return []
    parents: Dict[int, Any] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    found: List[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.JoinedStr):
            continue
        holder = parents.get(id(node))
        if isinstance(holder, ast.FormattedValue) and holder.format_spec is node:
            continue
        outer = (ast.get_source_segment(source, node) or "").lstrip("rRbBfFuU")[:1]
        for value in [n for n in node.values if isinstance(n, ast.FormattedValue)]:
            segment = ast.get_source_segment(source, value.value) or ""
            if "\\" in segment:
                found.append("%s line %d: a backslash inside the braces of an f-string needs Python 3.12" % (name, node.lineno))
            for inner in ast.walk(value.value):
                if isinstance(inner, ast.Constant) and isinstance(inner.value, str):
                    text = (ast.get_source_segment(source, inner) or "").lstrip("rRbBfFuU")[:1]
                    if text and text == outer:
                        found.append("%s line %d: an f-string uses its own quote inside the braces; that needs Python 3.12" % (name, node.lineno))
    return found


def check_python_syntax(root: str, extra_dirs: Sequence[str] = ()) -> List[str]:
    fails: List[str] = []
    for rel in python_files(root):
        base = os.path.basename(rel)
        text = read_text(root, rel)
        fails += lint_source(text, rel, need_header=True, need_future=base not in ("dispatch.py", "__init__.py"))
    for folder in extra_dirs:
        for dirpath, dirnames, filenames in os.walk(folder):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for name in sorted(filenames):
                if name.endswith(".py"):
                    full = os.path.join(dirpath, name)
                    try:
                        with open(full, "rb") as handle:
                            text = handle.read().decode("utf-8", errors="replace")
                    except OSError:
                        continue
                    label = os.path.relpath(full, os.path.dirname(root)).replace("\\", "/")
                    fails += lint_source(text, label, need_header=True, need_future=name not in ("__init__.py",))
    return fails


def repo_test_dirs(root: str) -> List[str]:
    """repo/tests next to the product folder, when it exists."""
    candidate = os.path.join(os.path.dirname(os.path.abspath(root)), "repo", "tests")
    return [candidate] if os.path.isdir(candidate) else []


# --------------------------------------------------------------------------- 5 to 9 small structural checks

def check_size_caps(root: str) -> List[str]:
    fails: List[str] = []
    for rel in python_files(root):
        count = len(read_text(root, rel).splitlines())
        if rel == "hooks/dispatch.py" and count > 40:
            fails.append("hooks/dispatch.py has %d lines (maximum 40)" % count)
        if rel.startswith("hooks/handlers/") and count > 250:
            fails.append("%s has %d lines (maximum 250)" % (rel, count))
    return fails


def check_bytecode_rule(root: str) -> List[str]:
    """Every hook library module sets sys.dont_write_bytecode, or the launcher runs with -B."""
    launcher_has_b = False
    try:
        with open(os.path.join(root, "tools", "hooks.json"), "rb") as handle:
            hooks = json.loads(handle.read().decode("utf-8"))["hooks"]
        launcher_has_b = all("-B" in h["args"] for groups in hooks.values() for g in groups for h in g["hooks"])
    except (OSError, ValueError, KeyError, TypeError):
        launcher_has_b = False
    fails: List[str] = []
    if not launcher_has_b:
        fails.append("tools/hooks.json: every launcher must run python with -B (no byte-code files in a learner's project)")
    for rel in python_files(root):
        if not rel.startswith("hooks/lib/") or rel.endswith("__init__.py"):
            continue
        try:
            tree = ast.parse(read_text(root, rel))
        except SyntaxError:
            continue
        sets_flag = any(isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr == "dont_write_bytecode" for t in n.targets)
                        for n in ast.walk(tree))
        if not sets_flag and not launcher_has_b:
            fails.append("%s does not set sys.dont_write_bytecode and the launcher has no -B" % rel)
    return fails


def check_no_links(root: str) -> List[str]:
    return ["%s is a symbolic link or junction; the product must contain none" % link for link in _import_validate().open_product(root).links]


def check_index_current(root: str) -> List[str]:
    validate = _import_validate()
    problem = validate.index_problem(validate.open_product(root))
    return ["knowledge/concepts-index.txt %s" % problem] if problem else []


def check_json_files(root: str) -> List[str]:
    fails: List[str] = []
    for rel in shipped_files(root):
        if not rel.endswith(".json"):
            continue
        raw = read_text(root, rel)
        try:
            json.loads(raw)
        except ValueError as exc:
            fails.append("%s is not valid JSON (%s)" % (rel, str(exc)[:60]))
    return fails


# --------------------------------------------------------------------------- 10 validate.py fires on broken input

def _copy_for_validation(root: str, dest: str) -> None:
    """A small copy of the product that holds everything validate.py reads."""
    skip_dirs = {"tools", "__pycache__", "agent-memory"}
    for entry in os.listdir(root):
        src = os.path.join(root, entry)
        dst = os.path.join(dest, entry)
        if os.path.isdir(src):
            if entry in skip_dirs:
                continue
            if entry == "hooks":
                os.makedirs(os.path.join(dst, "lib"), exist_ok=True)
                shutil.copy2(os.path.join(src, "lib", "config.py"), os.path.join(dst, "lib", "config.py"))
                continue
            shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        elif os.path.isfile(src):
            shutil.copy2(src, dst)


def _edit(path: str, func: Any, binary: bool = False) -> None:
    with open(path, "rb") as handle:
        raw = handle.read()
    if binary:
        new = func(raw)
    else:
        new = func(raw.decode("utf-8")).encode("utf-8")
    with open(path, "wb") as handle:
        handle.write(new)


def _must_find(lines: Sequence[str], where: str, phrase: str, label: str, fails: List[str]) -> None:
    if not any(where in line and phrase in line for line in lines):
        fails.append("validate.py did not report '%s' for %s (%s)" % (phrase, where, label))


def check_validator_fires(root: str) -> List[str]:
    """Break a temp copy in many ways and prove that validate.py reports each break."""
    validate = _import_validate()
    fails: List[str] = []
    base = tempfile.mkdtemp(prefix="tutor-files-")
    try:
        copy = os.path.join(base, "proj \u015f1", ".claude")
        os.makedirs(copy)
        _copy_for_validation(root, copy)
        # make the generated files current, so that only our breaks show up
        prod = validate.Product(copy)
        validate.write_index(prod)
        validate.write_manifest(validate.Product(copy))
        before = validate.validate(copy)
        before_lines = set(before.errors) | set(before.warnings)

        def p(rel: str) -> str:
            return os.path.join(copy, *rel.split("/"))

        # a: double-quoted description with an inner quote
        def inner_quote(text: str) -> str:
            return re.sub(r"description: >-\n(?:  .*\n)+", 'description: "He said "hello" to me"\n', text, count=1)
        _edit(p("skills/explain/SKILL.md"), inner_quote)
        # b: BOM, c: CRLF
        _edit(p("skills/fix-it/SKILL.md"), lambda b: b"\xef\xbb\xbf" + b, binary=True)
        _edit(p("skills/progress/SKILL.md"), lambda b: b.replace(b"\n", b"\r\n"), binary=True)
        # d: a card with a missing key; e: a dangling concept id
        def drop_pitfall(text: str) -> str:
            first, rest = text.split("\n", 1)
            row = json.loads(first)
            del row["pitfall"]
            return json.dumps(row, ensure_ascii=False) + "\n" + rest
        _edit(p("knowledge/concepts/git.jsonl"), drop_pitfall)

        def dangle(text: str) -> str:
            lines = text.split("\n")
            row = json.loads(lines[2])
            row["needs"] = ["ai-does-not-exist"]
            lines[2] = json.dumps(row, ensure_ascii=False)
            return "\n".join(lines)
        _edit(p("knowledge/concepts/ai.jsonl"), dangle)
        # f: an oversized rule
        _edit(p("rules/safety.md"), lambda t: t + ("filler words for the size test " * 80) + "\n")
        # g: an agent that reads files and the web
        _edit(p("agents/code-reviewer.md"), lambda t: t.replace("tools: Read, Grep, Glob", "tools: Read, Grep, Glob, WebFetch", 1))
        # h: a forbidden field and an HTML comment in skills
        _edit(p("skills/learn/SKILL.md"), lambda t: t.replace("\n---\n", "\ndisable-model-invocation: true\n---\n", 1))
        _edit(p("skills/save-point/SKILL.md"), lambda t: t + "\n<!-- a hidden note -->\n")
        # i: a Claude variable outside SKILL.md
        _edit(p("rules/tidy-project.md"), lambda t: t + "\nUse ${CLAUDE_PROJECT_DIR} here.\n")
        # j: a label that differs from config.py in the settings table
        _edit(p("skills/tutor/references/settings.md"), lambda t: t.replace("`Kontrol:`", "`Kontrolle:`", 1))
        # k: the output style loses an English label
        _edit(p("output-styles/tutor.md"), lambda t: t.replace("Your move:", "Your turn:"))
        # l: a glossary row that is also a concept term; m: a probe with an unknown id
        first_term = json.loads(read_text(copy, "knowledge/concepts/git.jsonl").split("\n")[1])["terms"][0]

        def overlap(text: str) -> str:
            row = {"term": first_term, "aliases": [], "plain": "A test row.", "domain": "git", "jargon": True}
            return text.rstrip("\n") + "\n" + json.dumps(row) + "\n"
        _edit(p("knowledge/glossary.jsonl"), overlap)
        _edit(p("knowledge/probes.jsonl"), lambda t: t.rstrip("\n") + "\n" + json.dumps(
            {"id": "git-not-a-card", "question": "Q?", "options": ["a", "b", "not sure"], "misconceptions": {"a": "x"}, "correct": "b"}) + "\n")
        # n: pointers (concept id, file, gate, diagram heading), trailing spaces, a tab
        _edit(p("skills/learn/references/playbook.md"), lambda t: t.rstrip("\n") + (
            "\n\nSee `git-no-such-card`, `.claude/knowledge/no-such-file.md` and rules/safety.md G7."
            "\nThe picture is in `.claude/knowledge/diagrams.md`: Grep for \"No such picture\".   \n\tTabbed line.\n"))
        # o: docs: a wrong skill table and a broken link
        os.makedirs(p("docs"), exist_ok=True)
        with open(p("docs/commands.md"), "wb") as handle:
            handle.write(("# Commands\n\n%s\n| Command | What it does |\n|---|---|\n| `/x` | y |\n%s\n\nSee [missing](nowhere.md).\n"
                          % (validate.COMMANDS_START, validate.COMMANDS_END)).encode("utf-8"))
        # p: runtime data
        os.makedirs(p("agent-memory/tutor-data"), exist_ok=True)
        os.makedirs(p("hooks/lib/__pycache__"), exist_ok=True)
        with open(p("settings.local.json"), "wb") as handle:
            handle.write(b"{}\n")
        _apply_more_breaks(copy, p)
        report = validate.validate(copy, quick=False, release=False, no_runtime_data=True)
        errors = [e for e in report.errors if e not in before_lines]
        warns = [w for w in report.warnings if w not in before_lines]
        _must_find(errors, "skills/explain/SKILL.md", "closing double quote", "inner quote in a double-quoted description", fails)
        _must_find(errors, "skills/explain/SKILL.md", "folded block scalar", "description is not a folded block", fails)
        _must_find(errors, "skills/fix-it/SKILL.md", "byte order mark", "BOM", fails)
        _must_find(errors, "skills/progress/SKILL.md", "line endings", "CRLF", fails)
        _must_find(errors, "knowledge/concepts/git.jsonl line 1", "keys are wrong", "card with a missing key", fails)
        _must_find(errors, "knowledge/concepts/ai.jsonl", "ai-does-not-exist", "dangling concept id", fails)
        _must_find(errors, "rules/safety.md", "maximum 360", "oversized rule", fails)
        _must_find(errors, "agents/code-reviewer.md", "read tool and a web tool", "read plus web tools", fails)
        _must_find(errors, "skills/learn/SKILL.md", "disable-model-invocation", "forbidden field", fails)
        _must_find(errors, "skills/save-point/SKILL.md", "HTML comment", "HTML comment in a skill", fails)
        _must_find(errors, "rules/tidy-project.md", "${CLAUDE_", "variable outside SKILL.md", fails)
        _must_find(errors, "skills/tutor/references/settings.md", "Kontrol", "label table differs from config.py", fails)
        _must_find(errors, "output-styles/tutor.md", "Your move:", "English label missing from the style", fails)
        _must_find(errors, "knowledge/glossary.jsonl", "keep it in one place", "term in concept and glossary", fails)
        _must_find(errors, "knowledge/probes.jsonl", "git-not-a-card", "probe with unknown id", fails)
        _must_find(errors, "skills/learn/references/playbook.md", "git-no-such-card", "unknown concept id in a pointer", fails)
        _must_find(errors, "skills/learn/references/playbook.md", "no-such-file.md", "missing file in a pointer", fails)
        _must_find(errors, "skills/learn/references/playbook.md", "G7", "unknown gate", fails)
        _must_find(errors, "skills/learn/references/playbook.md", "No such picture", "unknown diagram heading", fails)
        _must_find(errors, "skills/learn/references/playbook.md", "trailing spaces", "trailing spaces", fails)
        _must_find(errors, "skills/learn/references/playbook.md", "tab character", "tab in Markdown", fails)
        _must_find(errors, "docs/commands.md", "does not match the skill descriptions", "wrong skill table", fails)
        _must_find(errors, "docs/commands.md", "nowhere.md", "broken Markdown link", fails)
        _must_find(errors, "knowledge/concepts-index.txt", "out of date", "stale concept index", fails)
        _must_find(errors, "agent-memory", "runtime data", "agent-memory in the product", fails)
        _must_find(errors, "settings.local.json", "runtime data", "settings.local.json in the product", fails)
        _must_find(warns, "MANIFEST.txt", "does not match", "stale manifest", fails)
        _assert_more_breaks(errors, warns, fails)
        # repair what the generators can repair, then the matching complaints must go away
        shutil.rmtree(p("agent-memory"), ignore_errors=True)
        shutil.rmtree(p("hooks/lib/__pycache__"), ignore_errors=True)
        os.remove(p("settings.local.json"))
        validate.write_index(validate.Product(copy))
        prod = validate.Product(copy)
        validate.write_commands(prod, _skills_of(validate, copy))
        validate.write_manifest(validate.Product(copy))
        again = validate.validate(copy, quick=True, release=False, no_runtime_data=True)
        for line in again.errors + again.warnings:
            if any(k in line for k in ("concepts-index.txt", "MANIFEST.txt", "skill table")):
                fails.append("validate.py still complains after the generators ran: %s" % line[:120])
        # release mode: a missing layout file and a manifest that lists a file that is gone must be errors
        os.remove(p("templates/now.md"))
        # the document must be missing in the copy before the release run (the copy still has it from the product)
        os.remove(p("docs/getting-started.md"))
        # a placeholder left in a learner-facing page, and an offer label mentioned in Python program text (not an error)
        _edit(p("README.md"), lambda t: t + "\nTO FILL AT RELEASE: the date of the live check.\n")
        _edit(p("hooks/lib/config.py"), lambda t: t + "\n# Next I can teach, in a comment of program text\n")
        released = validate.validate(copy, quick=True, release=True)
        _must_find(released.errors, "templates/now.md", "is missing", "release: missing template", fails)
        _must_find(released.errors, "docs/getting-started.md", "is missing", "release: missing doc", fails)
        _must_find(released.errors, "MANIFEST.txt", "no longer exist", "release: manifest lists a deleted file", fails)
        _must_find(released.errors, "README.md line", "TO FILL AT RELEASE:", "release: placeholder text in a README", fails)
        if any("hooks/lib/config.py" in line and "offer label" in line for line in released.errors + released.warnings):
            fails.append("validate.py reports the offer label in Python program text (hooks/lib/config.py); it must not")
        plain = validate.validate(copy, quick=True, release=False)
        if any("TO FILL AT RELEASE" in line for line in plain.errors + plain.warnings):
            fails.append("validate.py checks the release placeholder outside --release mode")
    except Exception as exc:  # noqa: BLE001 - a crash is one failure message
        fails.append("the validator test stopped with %s: %s" % (type(exc).__name__, str(exc)[:100]))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return fails


def _card_edit(path: str, line_index: int, change: Any) -> None:
    """Change one JSON card (0-based line index) of a concept file."""
    def apply(text: str) -> str:
        lines = text.split("\n")
        row = json.loads(lines[line_index])
        change(row)
        lines[line_index] = json.dumps(row, ensure_ascii=False)
        return "\n".join(lines)
    _edit(path, apply)


def _apply_more_breaks(copy: str, p: Any) -> None:
    """More deliberate breaks, each in a file of its own, for the second half of the validator test."""
    # CLAUDE.md too long; a skill with a long description, an unquoted argument-hint, a bare Bash entry, too many lines
    _edit(p("CLAUDE.md"), lambda t: t + "short line\n" * 60)
    _edit(p("skills/think-first/SKILL.md"),
          lambda t: re.sub(r"description: >-\n(?:  .*\n)+", "description: >-\n  " + ("word " * 90).strip() + "\n", t, count=1))
    _edit(p("skills/new-project/SKILL.md"), lambda t: re.sub(r'argument-hint: "(.*)"', r"argument-hint: \1", t, count=1))
    _edit(p("skills/before-push/SKILL.md"), lambda t: t.replace("allowed-tools: >-\n", "allowed-tools: >-\n  Bash\n", 1))
    _edit(p("skills/tutor-setup/SKILL.md"), lambda t: t + "- filler\n" * 310)
    _edit(p("agents/architecture-reviewer.md"), lambda t: t.replace("tools: Read, Grep, Glob", "tools: Read, Grep, Glob, Write", 1))
    # the style: false switch and too many words; a rule without a heading
    _edit(p("output-styles/tutor.md"), lambda t: t.replace("keep-coding-instructions: true", "keep-coding-instructions: false") + ("word " * 700) + "\n")
    _edit(p("rules/design-gate.md"), lambda t: "Introduction line\n\n" + t)
    # knowledge cards
    _card_edit(p("knowledge/concepts/data.jsonl"), 0, lambda r: r.update({"plain": " ".join(["word"] * 40)}))
    _card_edit(p("knowledge/concepts/data.jsonl"), 1, lambda r: r.update({"signals": ["AB", "fine signal"]}))
    _card_edit(p("knowledge/concepts/data.jsonl"), 2, lambda r: r.update({"tier": 3}))
    _card_edit(p("knowledge/concepts/data.jsonl"), 3, lambda r: r.update({"volatile": True, "src": ""}))
    rows = [json.loads(l) for l in read_text(copy, "knowledge/concepts/proj.jsonl").split("\n") if l.strip()]
    _card_edit(p("knowledge/concepts/proj.jsonl"), 0, lambda r: r.update({"needs": [rows[1]["id"]]}))
    _card_edit(p("knowledge/concepts/proj.jsonl"), 1, lambda r: r.update({"needs": [rows[0]["id"]]}))
    _card_edit(p("knowledge/concepts/proj.jsonl"), 2, lambda r: r.update({"id": rows[3]["id"]}))
    chain = [json.loads(l) for l in read_text(copy, "knowledge/concepts/test.jsonl").split("\n") if l.strip()]
    for index in range(4):
        needs = [chain[index + 1]["id"]] if index < 3 else []
        _card_edit(p("knowledge/concepts/test.jsonl"), index, lambda r, n=needs: r.update({"needs": n, "tier": 1}))
    _card_edit(p("knowledge/concepts/web.jsonl"), 0, lambda r: r.update({"check": "Tell me about it."}))
    _edit(p("knowledge/milestones.md"), lambda t: t.replace("term-terminal", "term-bogus-id", 1))
    _edit(p("knowledge/diagrams.md"), lambda t: t.replace("## c. Git's four places", "## c. Git stuff", 1))
    _edit(p("knowledge/stacks.md"), lambda t: t.replace("## 8. ", "## 9. ", 1))
    # small files, a stray offer label, hook text
    _edit(p(".gitignore"), lambda t: t + "extra-rule/\n")
    _edit(p("VERSION"), lambda t: "version one\n")
    _edit(p("skills/learn/references/probes.md"), lambda t: t.rstrip("\n") + "\nnext i can" + " teach: x\n")
    os.makedirs(p("hooks/handlers"), exist_ok=True)
    with open(p("hooks/handlers/session_start.py"), "wb") as handle:
        handle.write(b'MENU = "Say: save | /bogus-skill"\n')
    with open(p("hooks/guard-messages.json"), "wb") as handle:
        handle.write(json.dumps({"x": {"short": "Do it " + "without" + " asking"}}).encode("utf-8"))


def _assert_more_breaks(errors: Sequence[str], warns: Sequence[str], fails: List[str]) -> None:
    expectations = [
        ("CLAUDE.md", "lines (maximum 55)", "CLAUDE.md too many lines"),
        ("CLAUDE.md", "words (maximum 780)", "CLAUDE.md too many words"),
        ("skills/think-first/SKILL.md", "characters (maximum 210)", "long skill description"),
        ("skills/new-project/SKILL.md", "argument-hint must be quoted", "unquoted argument-hint"),
        ("skills/before-push/SKILL.md", "approves every Bash", "bare Bash in allowed-tools"),
        ("skills/tutor-setup/SKILL.md", "lines (maximum 300)", "skill with too many lines"),
        ("agents/architecture-reviewer.md", "read-only", "agent with Write"),
        ("output-styles/tutor.md", "keep-coding-instructions must be true", "style without keep-coding-instructions"),
        ("output-styles/tutor.md", "(maximum 1420)", "style with too many words"),
        ("rules/design-gate.md", "must start with a '# ' heading", "rule without a heading"),
        ("rules", "the rules together", "rules together over the limit"),
        ("budget", "tokens (maximum 7000)", "token budget over the limit"),
        ("knowledge/concepts/data.jsonl line 1", "plain has 40 words", "plain too long"),
        ("knowledge/concepts/data.jsonl line 2", "signal 'AB'", "short upper-case signal"),
        ("knowledge/concepts/data.jsonl line 3", "tier must be 1 or 2", "tier 3"),
        ("knowledge/concepts/data.jsonl line 4", "a volatile card needs src", "volatile without src"),
        ("knowledge/concepts", "prerequisite cycle", "prerequisite cycle"),
        ("knowledge/concepts/proj.jsonl line 3", "is already used", "duplicate id"),
        ("knowledge/concepts/test.jsonl line 1", "chain of 3 prerequisites", "prerequisite chain over 2"),
        ("knowledge/concepts/web.jsonl line 1", "check must be one question", "check that is not a question"),
        ("knowledge/milestones.md", "term-bogus-id", "milestone with an unknown concept id"),
        ("knowledge/diagrams.md", "heading c. should be about", "diagram heading renamed"),
        ("knowledge/stacks.md", "8 project-type sections", "stack section missing"),
        (".gitignore", "must hold exactly", "changed .gitignore"),
        ("VERSION", "must hold one version", "bad VERSION"),
        ("skills/learn/references/probes.md", "offer label is written", "wrong offer label"),
        ("hooks/handlers/session_start.py", "/bogus-skill", "capsule menu names a missing skill"),
        ("hooks/guard-messages.json", "automatic-mode", "forbidden phrase in the guard messages"),
    ]
    for where, phrase, label in expectations:
        _must_find(errors, where, phrase, label, fails)


def _skills_of(validate: Any, copy: str) -> Dict[str, Dict[str, Any]]:
    report = validate.Report()
    ctx = validate.Ctx(validate.Product(copy), report, True, False, False)
    validate.check_skills(ctx)
    return ctx.skills


def check_link_detection() -> List[str]:
    """validate.py must report a symbolic link or junction. Skipped when this computer does not allow creating one."""
    validate = _import_validate()
    base = tempfile.mkdtemp(prefix="tutor-files-")
    link = os.path.join(base, "product", "linked")
    try:
        os.makedirs(os.path.join(base, "product"))
        os.makedirs(os.path.join(base, "elsewhere"))
        with open(os.path.join(base, "product", "VERSION"), "wb") as handle:
            handle.write(b"1.0.0\n")
        made = False
        try:
            os.symlink(os.path.join(base, "elsewhere"), link, target_is_directory=True)
            made = True
        except (OSError, NotImplementedError):
            if os.name == "nt":
                try:
                    import subprocess
                    made = subprocess.run(["cmd", "/c", "mklink", "/J", link, os.path.join(base, "elsewhere")],
                                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20).returncode == 0
                except (OSError, ValueError):
                    made = False
        if not made:
            return []
        found = validate.Product(os.path.join(base, "product")).links
        result = [] if "linked/" in found else ["validate.py did not report a link or junction inside the product folder"]
        try:
            os.rmdir(link)        # removes the link itself, never the target
        except OSError:
            try:
                os.remove(link)
            except OSError:
                pass
        return result
    finally:
        shutil.rmtree(base, ignore_errors=True)


def check_runner() -> List[str]:
    """selftest.py must pass good modules and report failing, crashing, silent, hanging and run-less ones."""
    import subprocess
    fails: List[str] = []
    outer = tempfile.mkdtemp(prefix="tutor-files-")
    base = os.path.join(outer, "tools")       # selftest.py sweeps its parent folder for __pycache__, so keep that small
    os.makedirs(base)
    try:
        shutil.copy2(os.path.join(HERE, "selftest.py"), os.path.join(base, "selftest.py"))
        modules = {
            "okmod": "def run():\n    return []\n",
            "failmod": "def run():\n    return ['first problem', 'second problem']\n",
            "crashmod": "def run():\n    raise ValueError('boom')\n",
            "exitmod": "import os\ndef run():\n    os._exit(3)\n",
            "hangmod": "import time\ndef run():\n    time.sleep(30)\n    return []\n",
            "norun": "x = 1\n",
            "quickmod": "import os\ndef run():\n    return ['quick is on'] if os.environ.get('TUTOR_SELFTEST_QUICK') == '1' else []\n",
            "warnmod": "WARNINGS = ['be careful']\ndef run():\n    return []\n",
        }
        quick = os.environ.get("TUTOR_SELFTEST_QUICK") == "1"
        if quick:
            del modules["hangmod"]            # the hang test waits for the time-out; quick runs skip it
        for name, body in modules.items():
            with open(os.path.join(base, "selftest_%s.py" % name), "wb") as handle:
                handle.write(body.encode("utf-8"))
        env = dict(os.environ)
        env["TUTOR_SELFTEST_TIMEOUT"] = "3"
        env.pop("TUTOR_SELFTEST_QUICK", None)

        def go(*args: str) -> Tuple[int, str]:
            proc = subprocess.run([sys.executable, "-I", "-B", "-X", "utf8", os.path.join(base, "selftest.py")] + list(args),
                                  stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, timeout=90)
            return proc.returncode, proc.stdout.decode("utf-8", errors="replace")

        code, text = go()
        expect = ["OK okmod", "FAIL failmod: first problem", "FAIL failmod: second problem", "FAIL crashmod: crashed with ValueError",
                  "FAIL exitmod: the test process ended with exit code 3",
                  "FAIL norun: the module has no run() function", "OK warnmod", "OK quickmod"]
        if not quick:
            expect.append("FAIL hangmod: timed out after 3 seconds")
        for needle in expect:
            if needle not in text:
                fails.append("selftest.py output lacks '%s'" % needle)
        want_result = "RESULT: 7 modules, 5 failures" if quick else "RESULT: 8 modules, 6 failures"
        if want_result not in text:
            last = text.strip().splitlines()[-1][:100] if text.strip() else "nothing"
            fails.append("selftest.py RESULT line is wrong (last line: %s)" % last)
        if code != 1:
            fails.append("selftest.py must exit 1 when a module fails (exit code %d)" % code)
        if "be careful" in text:
            fails.append("selftest.py shows warnings without --verbose")
        code, text = go("--verbose", "--only", "warnmod")
        if "WARN warnmod: be careful" not in text or code != 0:
            fails.append("selftest.py --verbose must show the warning and exit 0")
        code, text = go("--quick", "--only", "quickmod")
        if "FAIL quickmod: quick is on" not in text:
            fails.append("selftest.py --quick must set TUTOR_SELFTEST_QUICK=1 for the modules")
        code, text = go("--only", "okmod,warnmod")
        if code != 0 or "RESULT: 2 modules, 0 failures" not in text:
            fails.append("selftest.py --only with two good modules must exit 0")
        code, text = go("--only", "nosuch")
        if code != 2:
            fails.append("selftest.py with an unknown module name must exit 2 (exit code %d)" % code)
        code, text = go("--bogus")
        if code != 2:
            fails.append("selftest.py with an unknown option must exit 2 (exit code %d)" % code)
        code, text = go("--list")
        if code != 0 or "okmod" not in text.split():
            fails.append("selftest.py --list must print the module names")
        if "__pycache__" in os.listdir(base):
            fails.append("selftest.py left a __pycache__ folder behind")
    finally:
        shutil.rmtree(outer, ignore_errors=True)
    return fails


def _model_hooks() -> Dict[str, Any]:
    hooks: Dict[str, Any] = {}
    for event, (matcher, timeout, mode) in HOOK_EVENTS.items():
        group: Dict[str, Any] = {"hooks": [{"type": "command", "command": "python3", "timeout": timeout,
                                             "args": ["-I", "-B", "-X", "utf8", "-c", LAUNCHER, mode]}]}
        if matcher:
            group["matcher"] = matcher
        hooks[event] = [group]
    return {"hooks": hooks}


def check_structure_selfcheck() -> List[str]:
    """The hooks.json, size-cap, personal-data and bytecode checks must fire on a deliberately broken temp product."""
    fails: List[str] = []
    base = tempfile.mkdtemp(prefix="tutor-files-")
    try:
        root = os.path.join(base, "product")
        for sub in ("tools", "hooks/handlers", "hooks/lib", "output-styles"):
            os.makedirs(os.path.join(root, *sub.split("/")))
        good_hooks = _model_hooks()
        write_json_file(os.path.join(root, "tools", "hooks.json"), good_hooks)
        if check_hooks_json(root):
            fails.append("check_hooks_json rejects a model hooks.json: %s" % check_hooks_json(root)[0][:120])
        breaks = {
            "a wrong timeout": lambda d: d["hooks"]["Stop"][0]["hooks"][0].update({"timeout": 99}),
            "a wrong matcher": lambda d: d["hooks"]["PreToolUse"][0].update({"matcher": "Bash"}),
            "a missing event": lambda d: d["hooks"].pop("SubagentStart"),
            "an extra event": lambda d: d["hooks"].update({"SessionEnd": []}),
            "a different launcher": lambda d: d["hooks"]["Stop"][0]["hooks"][0]["args"].__setitem__(5, LAUNCHER + "; pass"),
            "a shell operator": lambda d: d["hooks"]["Stop"][0]["hooks"][0]["args"].__setitem__(5, LAUNCHER + " && echo"),
            "no -B flag": lambda d: d["hooks"]["Stop"][0]["hooks"][0]["args"].__setitem__(1, "-S"),
            "a wrong command": lambda d: d["hooks"]["Stop"][0]["hooks"][0].update({"command": "python"}),
            "a wrong mode": lambda d: d["hooks"]["Stop"][0]["hooks"][0]["args"].__setitem__(6, "stopp"),
        }
        for label, mutate in breaks.items():
            data = json.loads(json.dumps(good_hooks))
            mutate(data)
            write_json_file(os.path.join(root, "tools", "hooks.json"), data)
            if not check_hooks_json(root):
                fails.append("check_hooks_json did not flag: %s" % label)
        write_json_file(os.path.join(root, "tools", "hooks.json"), good_hooks)
        header = '"""Header."""\nfrom __future__ import annotations\n'
        with open(os.path.join(root, "hooks", "dispatch.py"), "wb") as handle:
            handle.write((header + "x = 1\n" * 60).encode("utf-8"))
        with open(os.path.join(root, "hooks", "handlers", "big.py"), "wb") as handle:
            handle.write((header + "x = 1\n" * 300).encode("utf-8"))
        with open(os.path.join(root, "hooks", "lib", "nobyte.py"), "wb") as handle:
            handle.write((header + "x = 1\n").encode("utf-8"))
        if len(check_size_caps(root)) != 2:
            fails.append("check_size_caps must flag a 60-line dispatch.py and a 300-line handler")
        if check_bytecode_rule(root):
            fails.append("check_bytecode_rule must accept modules when the launcher has -B")
        data = json.loads(json.dumps(good_hooks))
        for groups in data["hooks"].values():
            groups[0]["hooks"][0]["args"][1] = "-S"
        write_json_file(os.path.join(root, "tools", "hooks.json"), data)
        if not check_bytecode_rule(root):
            fails.append("check_bytecode_rule must flag a launcher without -B")
        with open(os.path.join(root, "notes.md"), "wb") as handle:
            handle.write(("Contact: " + "zed" + "@" + "mail-example.io\n").encode("utf-8"))
        if not check_personal_data(root):
            fails.append("check_personal_data must flag an e-mail address in a shipped file")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return fails


# --------------------------------------------------------------------------- synthetic checks of the checks themselves

def check_lint_selfcheck() -> List[str]:
    """The Python 3.9 lint must flag each forbidden construct and accept the allowed ones."""
    fails: List[str] = []
    head = '"""Test module."""\nfrom __future__ import annotations\n\n'
    bad = {
        "match statement": head + "def f(x):\n    match x:\n        case 1:\n            return 1\n",
        "zip strict": head + "z = list(zip([1], [2], strict=True))\n",
        "datetime.UTC": head + "import datetime\nz = datetime.UTC\n",
        "from datetime import UTC": head + "from datetime import UTC\n",
        "itertools.pairwise": head + "import itertools\nz = itertools.pairwise([1, 2])\n",
        "tomllib": head + "import tomllib\n",
        "typing.Self": head + "import typing\nz = typing.Self\n",
        "Path.walk": head + "def f(p):\n    return list(p.walk())\n",
        "bit_count": head + "z = (5).bit_count()\n",
        "contextlib.chdir": head + "import contextlib\nwith contextlib.chdir('.'):\n    pass\n",
        "runtime union": head + "z = int | None\n",
        "isinstance union": head + "def f(x):\n    return isinstance(x, str | int)\n",
        "union without future import": '"""Doc."""\ndef f(a: str | None = None):\n    return a\n',
        "parenthesised with": head + "def f():\n    with (open('a') as f1, open('b') as f2):\n        pass\n",
        "except star": head + "def f():\n    try:\n        pass\n    except* ValueError:\n        pass\n",
        "f-string with its own quote inside": head + "d = {'a': 1}\nz = f\"{d[\"a\"]}\"\n",
        "no docstring": "from __future__ import annotations\nz = 1\n",
        "no future import": '"""Doc."""\nz = 1\n',
    }
    for label, source in bad.items():
        if not lint_source(source, "synthetic.py"):
            fails.append("the Python 3.9 lint did not flag: %s" % label)
    good = {
        "annotation union": head + "def f(a: str | None = None) -> int | None:\n    x: int | None = None\n    return x\n",
        "os.walk and ast.walk": head + "import os, ast\nz = list(os.walk('.'))\ny = list(ast.walk(ast.parse('1')))\n",
        "int or": head + "z = 1 | 2\ny = {1} | {2}\n",
        "plain with": head + "def f():\n    with open('a') as f1, open('b') as f2:\n        pass\n    with (open('c')) as f3:\n        pass\n",
        "f-string with other quotes": head + "d = {'a': 1}\nz = f\"{d['a']}\"\n",
        "plain zip": head + "z = list(zip([1], [2]))\n",
        "optional": head + "from typing import Optional\ndef f(a: Optional[str] = None):\n    return a\n",
        "os.chdir": head + "import os\nos.chdir('.')\n",
        "version-guarded argument": head + "import shutil, sys\nif sys.version_info >= (3, 12):\n    shutil.rmtree('x', onexc=print)\nelse:\n    shutil.rmtree('x', onerror=print)\n",
        "import guarded by try": head + "try:\n    import tomllib\nexcept ImportError:\n    tomllib = None\n",
    }
    for label, source in good.items():
        found = lint_source(source, "synthetic.py")
        if found:
            fails.append("the Python 3.9 lint wrongly flagged '%s': %s" % (label, found[0][:100]))
    return fails


def check_personal_selfcheck() -> List[str]:
    """The personal-data scan must catch real-looking data and let neutral examples pass."""
    fails: List[str] = []
    drive = "C" + ":" + "\\" + "Users" + "\\"
    bad = {
        "windows user path": "see " + drive + "bobby" + "\\Desktop\\x",
        "unix home path": "open /" + "home" + "/zed/project/file",
        "mac home path": "open /" + "Users" + "/zed/project/file",
        "e-mail": "write to zed" + "@" + "mail-example" + ".io for help",
        "phone": "call " + "415" + "-867-" + "5309" + " now",
        "ip": "server at " + "10.20" + ".30.40" + " today",
        "project word": "the " + "business" + "-" + "project folder",
        "user name": "hello zedname1 there",
    }
    users = ["zedname1"]
    for label, line in bad.items():
        if not personal_findings(line, users):
            fails.append("the personal-data scan did not flag: %s" % label)
    good = {
        "placeholder path": "see " + drive + "Ada" + "\\Desktop and " + drive + "<name>" + "\\x and %USERPROFILE%",
        "example e-mail": "write to you@example.com or noreply@users.noreply.github.com or git@github.com:o/r.git",
        "documentation ip": "127.0.0.1 and 0.0.0.0 and 192.0.2.7",
        "version": "Claude Code 2.1.288 and python 3.9.1 and 2026-10-07",
        "fiction phone": "call 555-123-4567",
        "package version": "pkg@1.2.3 and name@latest",
    }
    for label, line in good.items():
        found = personal_findings(line, users)
        if found:
            fails.append("the personal-data scan wrongly flagged '%s': %s" % (label, found[0][1]))
    return fails


def check_settings_selfcheck() -> List[str]:
    """check_settings must accept a model file and reject each kind of break."""
    fails: List[str] = []
    base = tempfile.mkdtemp(prefix="tutor-files-")
    try:
        os.makedirs(os.path.join(base, "output-styles"))
        with open(os.path.join(base, "output-styles", "tutor.md"), "wb") as handle:
            handle.write(b"---\nname: tutor\n---\n# Tutor\n")
        good = model_settings()
        write_json_file(os.path.join(base, "settings.json"), good)
        found = check_settings(base)
        if found:
            fails.append("check_settings rejects a model settings.json: %s" % found[0][:120])
        breaks = {
            "a hooks key": lambda d: d.update({"hooks": {}}),
            "an env key": lambda d: d["permissions"].update({"env": {}}),
            "wrong output style": lambda d: d.update({"outputStyle": "default"}),
            "missing skill entry": lambda d: d["permissions"]["allow"].pop(),
            "extra allow entry": lambda d: d["permissions"]["allow"].append("Bash(*)"),
            "missing PowerShell twin": lambda d: d["permissions"]["ask"].append("Bash(git tag -d *)"),
            "missing force-push rule": lambda d: d["permissions"]["deny"].remove("Bash(git push -f *)"),
            "plain push denied": lambda d: d["permissions"]["deny"].extend(["Bash(git push *)", "PowerShell(git push *)"]),
            "a Write path rule": lambda d: d["permissions"]["deny"].append("Write(.env)"),
            "bad rule grammar": lambda d: d["permissions"]["deny"].append("Bash(unclosed"),
            "a removed ask rule": lambda d: d["permissions"]["ask"].extend(["Bash(npm install *)", "PowerShell(npm install *)"]),
            "bypass word": lambda d: d.update({"$schema": "https://example.com/bypassPermissions.json"}),
        }
        for label, mutate in breaks.items():
            data = json.loads(json.dumps(good))
            mutate(data)
            write_json_file(os.path.join(base, "settings.json"), data)
            if not check_settings(base):
                fails.append("check_settings did not flag: %s" % label)
        os.remove(os.path.join(base, "settings.json"))
        if check_settings(base) != ["settings.json is missing"]:
            fails.append("a missing settings.json must give exactly the failure 'settings.json is missing'")
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return fails


def model_settings() -> Dict[str, Any]:
    deny = ["Read(.env)", "Read(.env.*)", "Read(*.pem)", "Read(id_rsa)", "Read(id_ed25519)", "Read(~/.ssh/**)", "Read(~/.aws/**)",
            "Read(~/.config/gh/**)"]
    shell_deny = ["git push %s" % s[len("git push "):] for s in FORCE_PUSH_PATTERNS]
    ask = ["git push *", "git reset --hard*", "git clean -f *", "git branch -D *"]
    return {
        "$schema": "https://json.schemastore.org/claude-code-settings.json",
        "outputStyle": "tutor",
        "permissions": {
            "defaultMode": "acceptEdits",
            "deny": deny + ["Bash(%s)" % s for s in shell_deny] + ["PowerShell(%s)" % s for s in shell_deny],
            "ask": ["Bash(%s)" % s for s in ask] + ["PowerShell(%s)" % s for s in ask],
            "allow": ["Skill(%s)" % n for n in SKILL_NAMES],
        },
    }


def write_json_file(path: str, data: Any) -> None:
    with open(path, "wb") as handle:
        handle.write((json.dumps(data, indent=2) + "\n").encode("utf-8"))


# --------------------------------------------------------------------------- entry points

def checks_for(root: str) -> List[Tuple[str, Any]]:
    return [
        ("settings.json", lambda: check_settings(root)),
        ("hooks.json", lambda: check_hooks_json(root)),
        ("personal data", lambda: check_personal_data(root)),
        ("python 3.9", lambda: check_python_syntax(root, repo_test_dirs(root))),
        ("size caps", lambda: check_size_caps(root)),
        ("byte code", lambda: check_bytecode_rule(root)),
        ("links", lambda: check_no_links(root)),
        ("index", lambda: check_index_current(root)),
        ("json files", lambda: check_json_files(root)),
    ]


def run_on(root: str) -> List[str]:
    fails: List[str] = []
    for label, func in checks_for(root):
        try:
            fails += func()
        except Exception as exc:  # noqa: BLE001 - one broken check must not hide the others
            fails.append("the check '%s' stopped with %s: %s" % (label, type(exc).__name__, str(exc)[:100]))
    return fails


def run() -> List[str]:
    fails = run_on(PRODUCT)
    # the self-checks build their own temp products and must not see the installed-copy mode of install.py
    saved = os.environ.pop("TUTOR_IN_INSTALL_SELFTEST", None)
    try:
        fails += run_selfchecks()
    finally:
        if saved is not None:
            os.environ["TUTOR_IN_INSTALL_SELFTEST"] = saved
    return fails


def check_installed_mode() -> List[str]:
    """In a learner's project (install.py sets TUTOR_IN_INSTALL_SELFTEST) the merged settings.json and the
    learner's own files must not fail the quick self-test; the same differences must fail in the kit's own folder."""
    validate = _import_validate()
    fails: List[str] = []
    base = tempfile.mkdtemp(prefix="tutor-files-")
    saved = os.environ.pop("TUTOR_IN_INSTALL_SELFTEST", None)
    try:
        copy = os.path.join(base, "project", ".claude")
        os.makedirs(copy)
        _copy_for_validation(PRODUCT, copy)
        write_json_file(os.path.join(copy, "settings.json"), model_settings())
        validate.write_manifest(validate.Product(copy))
        if check_settings(copy):
            fails.append("a model settings.json with a matching manifest must pass: %s" % check_settings(copy)[0][:100])
        merged = model_settings()
        merged["env"] = {"MY_SETTING": "1"}
        merged["permissions"]["allow"].append("Bash(npm test)")
        write_json_file(os.path.join(copy, "settings.json"), merged)
        os.makedirs(os.path.join(copy, "skills", "mine"))
        with open(os.path.join(copy, "skills", "mine", "SKILL.md"), "wb") as handle:
            handle.write(b"---\r\nname: wrong\r\n---\r\nDo it without asking.  \r\n")
        with open(os.path.join(copy, "notes.md"), "wb") as handle:
            handle.write(("Mail " + "zed" + "@" + "mail-example.io\r\n").encode("utf-8"))
        normal_settings = check_settings(copy)
        normal_validate = validate.run(copy, quick=True)
        os.environ["TUTOR_IN_INSTALL_SELFTEST"] = "1"
        installed_settings = check_settings(copy)
        installed_validate = validate.run(copy, quick=True)
        installed_personal = check_personal_data(copy)
        if not normal_settings:
            fails.append("a merged settings.json must fail the strict check in the kit's own folder")
        if installed_settings:
            fails.append("a merged settings.json must pass in an installed copy: %s" % installed_settings[0][:100])
        if not any("skills/mine" in e for e in normal_validate):
            fails.append("validate.py must check a user file in the kit's own folder")
        if any("skills/mine" in e or "notes.md" in e for e in installed_validate):
            fails.append("validate.py must ignore the learner's own files in an installed copy")
        if installed_personal:
            fails.append("the personal-data check must ignore the learner's own files in an installed copy: %s" % installed_personal[0][:100])
        broken = merged
        broken["permissions"]["deny"].remove("Bash(git push -f *)")
        write_json_file(os.path.join(copy, "settings.json"), broken)
        if not check_settings(copy):
            fails.append("an installed copy that lost a force-push rule must fail")
    finally:
        os.environ.pop("TUTOR_IN_INSTALL_SELFTEST", None)
        if saved is not None:
            os.environ["TUTOR_IN_INSTALL_SELFTEST"] = saved
        shutil.rmtree(base, ignore_errors=True)
    return fails


def run_selfchecks() -> List[str]:
    fails: List[str] = []
    for label, func in (("lint self-check", check_lint_selfcheck), ("personal-data self-check", check_personal_selfcheck),
                        ("settings self-check", check_settings_selfcheck), ("installed-copy mode", check_installed_mode),
                        ("validator test", lambda: check_validator_fires(PRODUCT)), ("link detection", check_link_detection),
                        ("structure self-check", check_structure_selfcheck), ("runner test", check_runner)):
        try:
            fails += func()
        except Exception as exc:  # noqa: BLE001
            fails.append("the check '%s' stopped with %s: %s" % (label, type(exc).__name__, str(exc)[:100]))
    return fails


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    problems = run_on(os.path.abspath(target)) if target else run()
    for item in problems:
        sys.stdout.buffer.write(("FAIL files: %s\n" % item).encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(("%d failure(s)\n" % len(problems)).encode("utf-8"))
    sys.exit(1 if problems else 0)
