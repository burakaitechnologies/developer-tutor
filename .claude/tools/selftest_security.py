"""selftest_security.py - reads the Python code of hooks/ and tools/ and fails on risky constructs (SPEC 13, 7).

What: run() returns a list of failure messages (empty = pass). The scan never runs the code; it parses each
file into a syntax tree and looks for: imports that reach the network or load code (socket, ssl, urllib, http,
ftplib, smtplib, xmlrpc, telnetlib, webbrowser, requests, ctypes, pickle, marshal, importlib), calls that run text
as code (os.system, os.popen, eval, exec, compile, __import__ and the getattr tricks that hide them), subprocess
calls that are not a safe list command (hooks: only subprocess.run or Popen with a list that starts with git),
shell=True anywhere, file writes outside the file helpers, reads of environment variables outside an allow-list,
absolute user paths, and silent `except Exception: pass` blocks.
Why: the tutor's scripts run on a learner's computer with the learner's rights. The promise "no network, no
hidden code" is only worth something if a test keeps it.
How a hook subprocess call is recognised as safe: the first argument is a list (or a name, or a sum of lists)
whose first element is the text "git", or a module constant that is bound to the text "git" (GIT = "git"), or a
module list that starts with "git" (gitq.py: _BASE = ["git", ...]; Popen(_BASE + argv)). Anything else is an error.
How it fails safely: it only reads files; a file that does not parse is a failure message, not a crash; WARNINGS
holds findings that do not fail the run. The scanner is tested with small synthetic sources built at run time.
Who calls it: tools/selftest.py (module "security", also alone with --security). Run alone:
python selftest_security.py [product-folder]
"""
from __future__ import annotations

import ast
import os
import re
import sys
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)

WARNINGS: List[str] = []

FORBIDDEN_IMPORTS = ("socket", "ssl", "urllib", "http", "ftplib", "smtplib", "xmlrpc", "telnetlib", "webbrowser", "requests",
                     "ctypes", "pickle", "marshal", "importlib",
                     "socketserver", "imaplib", "poplib", "nntplib", "urllib3", "httpx", "aiohttp", "websocket", "websockets",
                     "paramiko", "_socket", "_ssl", "cffi")
IMPORTLIB_ALLOWED = ("tools/validate.py", "tools/selftest.py")
FORBIDDEN_BARE_CALLS = ("eval", "exec", "compile", "__import__")
FORBIDDEN_NAMES_AS_TEXT = ("system", "popen", "eval", "exec", "compile", "__import__", "startfile")
SUBPROCESS_FUNCS = ("run", "Popen", "call", "check_call", "check_output", "getoutput", "getstatusoutput")
HOOK_SUBPROCESS_FUNCS = ("run", "Popen")
ENV_ALLOW = ("CLAUDE_PROJECT_DIR", "CLAUDE_CODE_ENTRYPOINT", "TUTOR_FAKE_NOW", "TUTOR_SELFTEST_QUICK", "TEMP", "TMP", "HOME",
             "USERPROFILE", "LOCALAPPDATA", "APPDATA", "PATH", "PATHEXT", "SYSTEMROOT", "COMSPEC", "OS", "USERNAME", "USER", "LANG",
             "TMPDIR")      # TMPDIR: the macOS and Linux name for the temp folder (SPEC lists TEMP and TMP only; see the TV report)
WRITE_HELPER_FILES = ("hooks/lib/fsio.py", "hooks/lib/paths.py")
SWALLOW_ALLOWED_FILES = ("hooks/lib/fsio.py", "hooks/lib/hookio.py")
SWALLOW_ALLOWED_FUNCTIONS = re.compile(r"log|note|swallow|quiet", re.I)
PLACEHOLDER_NAMES = ("ada", "you", "user", "username", "yourname", "name", "me", "someone", "example", "public", "default",
                     "admin", "administrator", "test", "learner", "student", "alice", "bob", "runner", "ubuntu", "foo", "x",
                     "home", "project", "app", "dev")
_DRIVE_PATH = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]+Users[\\/]+([^\\/\s\"'`<>|*?:;,)]+)", re.I)
_UNIX_HOME = re.compile(r"(?<![\w.~])/(?:Users|home)/([A-Za-z0-9_.-]+)/")
MODE_TEXT = re.compile(r"^[rwxabtU+]{1,4}$")


def _dotted(node: Any) -> str:
    """'a.b.c' for a chain of attributes ending in a name; '' otherwise."""
    parts: List[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return ""


class Scanner(ast.NodeVisitor):
    """Walks one parsed file and collects errors and warnings."""

    def __init__(self, tree: ast.AST, rel: str, scope: str) -> None:
        self.rel = rel
        self.scope = scope                       # "hooks" or "tools"
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.aliases: Dict[str, str] = {}        # local name -> dotted module path it stands for
        self.module_lists: Dict[str, Any] = {}   # module-level name -> assigned value node
        self.function_stack: List[ast.AST] = []
        self.parents: Dict[int, ast.AST] = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                self.parents[id(child)] = parent
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self.aliases[(alias.asname or alias.name).split(".")[0]] = alias.name if alias.asname else alias.name.split(".")[0]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                for alias in node.names:
                    self.aliases[alias.asname or alias.name] = node.module + "." + alias.name
        for node in getattr(tree, "body", []):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        self.module_lists[target.id] = node.value
        self.visit(tree)

    # ---- helpers
    def err(self, node: Any, message: str) -> None:
        self.errors.append("%s line %d: %s" % (self.rel, getattr(node, "lineno", 0), message))

    def warn(self, node: Any, message: str) -> None:
        self.warnings.append("%s line %d: %s" % (self.rel, getattr(node, "lineno", 0), message))

    def resolve(self, node: Any) -> str:
        """The dotted real name of a Name or Attribute chain ('os.system', 'subprocess.run'), '' when unknown."""
        dotted = _dotted(node)
        if not dotted:
            return ""
        head, _, tail = dotted.partition(".")
        base = self.aliases.get(head, head)
        return base + ("." + tail if tail else "")

    def enclosing_function(self, node: Any) -> str:
        current = self.parents.get(id(node))
        while current is not None:
            if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return current.name
            current = self.parents.get(id(current))
        return ""

    # ---- imports
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.check_import(node, alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module and node.level == 0:
            self.check_import(node, node.module)
            if node.module == "os":
                for alias in node.names:
                    if alias.name in ("system", "popen") or alias.name.startswith(("exec", "spawn")) or alias.name == "startfile":
                        self.err(node, "imports os.%s, which runs a command through the shell or replaces the process" % alias.name)
            if node.module == "subprocess":
                for alias in node.names:
                    if alias.name in ("getoutput", "getstatusoutput"):
                        self.err(node, "imports subprocess.%s, which always uses a shell" % alias.name)
        self.generic_visit(node)

    def check_import(self, node: Any, module: str) -> None:
        root = module.split(".")[0]
        if root not in FORBIDDEN_IMPORTS:
            return
        if root == "importlib" and self.rel in IMPORTLIB_ALLOWED:
            return
        self.err(node, "imports '%s', which can reach the network or load code that nobody reviewed" % module)

    # ---- calls
    def visit_Call(self, node: ast.Call) -> None:
        func = node.func
        real = self.resolve(func)
        if isinstance(func, ast.Name) and func.id in FORBIDDEN_BARE_CALLS and func.id not in self.aliases:
            self.err(node, "calls %s(), which runs text as code" % func.id)
        elif real in ("builtins.eval", "builtins.exec", "builtins.compile", "builtins.__import__"):
            self.err(node, "calls %s, which runs text as code" % real)
        elif real in ("os.system", "os.popen", "os.startfile") or re.match(r"^os\.(?:exec|spawn)\w*$", real):
            self.err(node, "calls %s, which runs a command through the shell or replaces the process" % real)
        elif real in ("subprocess.getoutput", "subprocess.getstatusoutput"):
            self.err(node, "calls %s, which always uses a shell" % real)
        if isinstance(func, ast.Name) and func.id == "getattr" and len(node.args) >= 2:
            name = node.args[1]
            if isinstance(name, ast.Constant) and isinstance(name.value, str) and name.value in FORBIDDEN_NAMES_AS_TEXT:
                self.err(node, "looks up the name '%s' with getattr, which hides a forbidden call" % name.value)
        if real.startswith("subprocess.") and real.split(".")[-1] in SUBPROCESS_FUNCS:
            self.check_subprocess(node, real.split(".")[-1])
        self.check_open(node, real)
        self.check_environ_call(node, real)
        self.generic_visit(node)

    def check_subprocess(self, node: ast.Call, func: str) -> None:
        for keyword in node.keywords:
            if keyword.arg == "shell" and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is False):
                self.err(node, "uses subprocess with shell=%s; commands must be lists without a shell" % (
                    keyword.value.value if isinstance(keyword.value, ast.Constant) else "something"))
        first: Optional[ast.AST] = node.args[0] if node.args else None
        for keyword in node.keywords:
            if keyword.arg == "args":
                first = keyword.value
        if first is None:
            self.err(node, "calls subprocess.%s without a command list" % func)
            return
        if self.is_text_command(first):
            self.err(node, "gives subprocess.%s a text command; use a list so no shell reads it" % func)
            return
        if self.scope == "hooks":
            if func not in HOOK_SUBPROCESS_FUNCS:
                self.err(node, "hooks may use only subprocess.run or subprocess.Popen (found subprocess.%s)" % func)
            elif not self.is_git_list(first, node):
                self.err(node, "a hook runs subprocess.%s with a command that does not start with the text 'git'" % func)

    def is_text_command(self, node: Any) -> bool:
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return True
        if isinstance(node, ast.JoinedStr):
            return True
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mod) and isinstance(node.left, ast.Constant) \
                and isinstance(node.left.value, str):
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format" \
                and isinstance(node.func.value, ast.Constant):
            return True
        return False

    def is_git_list(self, node: Any, at: Any, depth: int = 0) -> bool:
        """True when the command list starts with the text 'git' (directly, by constant, or by a module list)."""
        if depth > 4:
            return False
        if isinstance(node, (ast.List, ast.Tuple)):
            if not node.elts:
                return False
            return self.is_git_text(node.elts[0], depth)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return self.is_git_list(node.left, at, depth + 1)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in ("list", "tuple") and node.args:
            return self.is_git_list(node.args[0], at, depth + 1)
        if isinstance(node, ast.Name):
            values = self.local_values(node.id, at)
            if values:
                return all(self.is_git_list(v, at, depth + 1) for v in values)
            module_value = self.module_lists.get(node.id)
            return module_value is not None and self.is_git_list(module_value, at, depth + 1)
        return False

    def is_git_text(self, node: Any, depth: int) -> bool:
        if isinstance(node, ast.Constant):
            return node.value == "git"
        if isinstance(node, ast.Name):
            value = self.module_lists.get(node.id)
            return isinstance(value, ast.Constant) and value.value == "git"
        if isinstance(node, ast.Starred):
            return self.is_git_list(node.value, node, depth + 1)
        return False

    def local_values(self, name: str, at: Any) -> List[Any]:
        """Values assigned to `name` inside the function that holds `at`."""
        current = self.parents.get(id(at))
        while current is not None and not isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            current = self.parents.get(id(current))
        if current is None:
            return []
        out = []
        for sub in ast.walk(current):
            if isinstance(sub, ast.Assign):
                for target in sub.targets:
                    if isinstance(target, ast.Name) and target.id == name:
                        out.append(sub.value)
        return out

    # ---- file writes
    def check_open(self, node: ast.Call, real: str) -> None:
        """open(path, mode) and Path methods that write. A mode is a short text such as 'w', 'ab' or 'r+'."""
        func = node.func
        is_open = (isinstance(func, ast.Name) and func.id == "open" and "open" not in self.aliases) or real in ("io.open", "codecs.open")
        method = func.attr if isinstance(func, ast.Attribute) else ""
        if method in ("write_text", "write_bytes"):
            if not real.startswith(("lib.", "fsio.", "paths.")):     # fsio.write_text(...) is the helper itself
                self.report_write(node, "writes a file with .%s()" % method)
            return
        is_path_open = method == "open" and not real.startswith(("os.", "webbrowser.", "zipfile.", "tarfile.", "gzip.", "bz2.", "lzma."))
        if not (is_open or is_path_open):
            return
        mode_node: Optional[ast.AST] = None
        if is_open and len(node.args) >= 2:
            mode_node = node.args[1]
        elif is_path_open and node.args:
            mode_node = node.args[0]
        for keyword in node.keywords:
            if keyword.arg == "mode":
                mode_node = keyword.value
        if mode_node is None:
            return
        if isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str):
            if MODE_TEXT.match(mode_node.value) and any(ch in mode_node.value for ch in "wax+"):
                self.report_write(node, "opens a file for writing (mode %r)" % mode_node.value)
        elif is_open:
            self.warn(node, "opens a file with a mode that is not a plain text; cannot tell whether it writes")

    def report_write(self, node: Any, what: str) -> None:
        if self.scope == "hooks":
            if self.rel not in WRITE_HELPER_FILES:
                self.err(node, "%s; hook files are written only through the helpers in fsio.py or paths.py" % what)
        else:
            self.warn(node, what)

    # ---- environment
    def is_environ(self, node: Any) -> bool:
        return self.resolve(node) == "os.environ"

    def check_environ_call(self, node: ast.Call, real: str) -> None:
        if self.scope != "hooks":
            return
        func = node.func
        key: Optional[ast.AST] = None
        if real == "os.getenv":
            key = node.args[0] if node.args else None
        elif isinstance(func, ast.Attribute) and self.is_environ(func.value) and func.attr in ("get", "pop", "setdefault"):
            key = node.args[0] if node.args else None
        elif isinstance(func, ast.Attribute) and self.is_environ(func.value) and func.attr in ("items", "keys", "values"):
            self.warn(node, "goes through every environment variable (.%s())" % func.attr)
            return
        else:
            return
        self.check_env_key(node, key)

    def check_env_key(self, node: Any, key: Optional[ast.AST]) -> None:
        if isinstance(key, ast.Constant) and isinstance(key.value, str):
            if key.value not in ENV_ALLOW:
                self.err(node, "reads the environment variable %s, which is not on the allow-list" % key.value)
        else:
            self.warn(node, "reads an environment variable whose name is not a plain text")

    def visit_Subscript(self, node: ast.Subscript) -> None:
        if self.scope == "hooks" and self.is_environ(node.value) and isinstance(node.ctx, ast.Load):
            slice_node = node.slice
            self.check_env_key(node, slice_node)
        if isinstance(node.slice, ast.Constant) and node.slice.value in FORBIDDEN_NAMES_AS_TEXT:
            holder = node.value
            hides = (isinstance(holder, ast.Call) and isinstance(holder.func, ast.Name) and holder.func.id in ("globals", "vars", "locals")) \
                or (isinstance(holder, ast.Name) and holder.id == "__builtins__") \
                or (isinstance(holder, ast.Attribute) and holder.attr == "__dict__")
            if hides:
                self.err(node, "looks up the name '%s' in a namespace dictionary, which hides a forbidden call" % node.slice.value)
        self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> None:
        if self.scope == "hooks":
            for op, comparator in zip(node.ops, node.comparators):
                if isinstance(op, (ast.In, ast.NotIn)) and self.is_environ(comparator):
                    self.check_env_key(node, node.left)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        if self.scope == "hooks" and self.is_environ(node.iter):
            self.warn(node, "goes through every environment variable")
        self.generic_visit(node)

    # ---- text constants and swallowed errors
    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            for regex in (_DRIVE_PATH, _UNIX_HOME):
                for match in regex.finditer(node.value):
                    name = match.group(1)
                    if len(name) == 1 or name.lower() in PLACEHOLDER_NAMES or name.startswith(("%", "$", "{", "[", "~")):
                        continue
                    self.err(node, "holds an absolute user path (.../%s/...)" % name)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if self.scope == "hooks" and self.swallows_everything(node):
            function = self.enclosing_function(node)
            if self.rel not in SWALLOW_ALLOWED_FILES and not SWALLOW_ALLOWED_FUNCTIONS.search(function):
                self.warn(node, "'except Exception: pass' hides a failure (function %s)" % (function or "module level"))
        self.generic_visit(node)

    @staticmethod
    def swallows_everything(node: ast.ExceptHandler) -> bool:
        broad = node.type is None
        kinds = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
        for kind in kinds:
            if isinstance(kind, ast.Name) and kind.id in ("Exception", "BaseException"):
                broad = True
        only_pass = all(isinstance(s, ast.Pass) or (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant)) for s in node.body)
        return broad and only_pass


def scan_source(source: str, rel: str, scope: str) -> Tuple[List[str], List[str]]:
    """(errors, warnings) for one Python source. `rel` is its path in the product, `scope` is 'hooks' or 'tools'."""
    try:
        tree = ast.parse(source, filename=rel)
    except SyntaxError as exc:
        return ["%s line %s: does not parse (%s)" % (rel, exc.lineno, str(exc.msg)[:60])], []
    scanner = Scanner(tree, rel, scope)
    return scanner.errors, scanner.warnings


def manifest_paths(root: str) -> Optional[Set[str]]:
    """Paths listed in MANIFEST.txt; used only in an installed copy, where files of the learner must not be scanned."""
    if os.environ.get("TUTOR_IN_INSTALL_SELFTEST") != "1":
        return None
    try:
        with open(os.path.join(root, "MANIFEST.txt"), "rb") as handle:
            text = handle.read().decode("utf-8", errors="replace")
    except OSError:
        return None
    found = set(m.group(1) for m in re.finditer(r"^[0-9a-f]{64}  (\S.*)$", text, re.M))
    return found or None


def scan_product(root: str) -> Tuple[List[str], List[str]]:
    errors: List[str] = []
    warnings: List[str] = []
    only = manifest_paths(root)
    for folder, scope in (("hooks", "hooks"), ("tools", "tools")):
        base = os.path.join(root, folder)
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
            for name in sorted(filenames):
                if not name.endswith(".py"):
                    continue
                full = os.path.join(dirpath, name)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if only is not None and rel not in only:
                    continue
                try:
                    with open(full, "rb") as handle:
                        source = handle.read().decode("utf-8", errors="replace")
                except OSError:
                    errors.append("%s cannot be read" % rel)
                    continue
                found_errors, found_warnings = scan_source(source, rel, scope)
                errors += found_errors
                warnings += found_warnings
    return errors, warnings


# --------------------------------------------------------------------------- tests of the scanner itself

def _hit(source: str, rel: str, scope: str, want_error: bool = True, want_warning: bool = False) -> bool:
    errors, warnings = scan_source(source, rel, scope)
    if want_warning:
        return bool(warnings) and not errors
    return bool(errors) if want_error else not errors


def selfcheck() -> List[str]:
    """Feed the scanner small sources: each forbidden construct must be flagged, each allowed one accepted."""
    fails: List[str] = []
    hook = "hooks/lib/example.py"
    tool = "tools/doctor.py"
    flagged: List[Tuple[str, str, str]] = []
    for name in FORBIDDEN_IMPORTS:
        flagged.append(("import " + name, "import %s\n" % name, hook))
        flagged.append(("from-import " + name, "from %s import thing\n" % name, tool))
    flagged += [
        ("importlib in a tool that may not use it", "import importlib\n", "tools/doctor.py"),
        ("dotted forbidden import", "import urllib.request\n", hook),
        ("os.system", "import os\nos.system('x')\n", tool),
        ("os.popen", "import os\nos.popen('x')\n", hook),
        ("aliased os.system", "import os as o\no.system('x')\n", hook),
        ("from os import system", "from os import system\n", hook),
        ("eval", "x = eval('1')\n", hook),
        ("exec", "exec('x = 1')\n", tool),
        ("compile", "c = compile('1', 'f', 'eval')\n", hook),
        ("__import__", "m = __import__('os')\n", hook),
        ("getattr os.system", "import os\nf = getattr(os, 'sys' + 'tem') if 0 else getattr(os, 'system')\n", hook),
        ("builtins.eval", "import builtins\nbuiltins.eval('1')\n", hook),
        ("globals eval", "f = globals()['eval']\n", hook),
        ("shell=True in a tool", "import subprocess\nsubprocess.run(['ls'], shell=True)\n", tool),
        ("text command in a tool", "import subprocess\nsubprocess.run('ls -l')\n", tool),
        ("f-string command", "import subprocess\nname = 'x'\nsubprocess.run(f'ls {name}')\n", tool),
        ("hook subprocess without git", "import subprocess\nsubprocess.run(['ls'])\n", hook),
        ("hook subprocess with a variable", "import subprocess\ndef f(cmd):\n    return subprocess.run(cmd)\n", hook),
        ("hook subprocess.check_output", "import subprocess\nsubprocess.check_output(['git', 'status'])\n", hook),
        ("hook sys.executable", "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])\n", hook),
        ("hook shell=True with git", "import subprocess\nsubprocess.run(['git', 'x'], shell=True)\n", hook),
        ("hook write outside helpers", "with open('f', 'w') as h:\n    h.write('x')\n", hook),
        ("hook append", "open('f', 'ab').close()\n", hook),
        ("hook write_text", "from pathlib import Path\nPath('f').write_text('x')\n", hook),
        ("hook reads a secret variable", "import os\nk = os.environ.get('MY_SECRET_THING')\n", hook),
        ("hook subscript env", "import os\nk = os.environ['HOMEDRIVE_X']\n", hook),
        ("hook getenv", "import os\nk = os.getenv('AWS_KEY_X')\n", hook),
        ("hook env membership", "import os\nk = 'FOO_X' in os.environ\n", hook),
        ("absolute user path (Windows)", "p = '%s'\n" % ("C" + ":" + "\\\\" + "Users" + "\\\\" + "bobby" + "\\\\" + "x"), tool),
        ("absolute user path (Unix)", "p = '/%s/zed/work'\n" % "home", hook),
    ]
    for label, source, rel in flagged:
        scope = "hooks" if rel.startswith("hooks/") else "tools"
        if not _hit(source, rel, scope):
            fails.append("the security scan did not flag: %s" % label)
    accepted: List[Tuple[str, str, str]] = [
        ("importlib in validate.py", "import importlib\n", "tools/validate.py"),
        ("importlib in selftest.py", "import importlib\n", "tools/selftest.py"),
        ("re.compile", "import re\nr = re.compile('x')\n", hook),
        ("os.path and os.environ.get of an allowed name", "import os\nv = os.environ.get('CLAUDE_PROJECT_DIR')\n", hook),
        ("getenv of an allowed name", "import os\nv = os.getenv('USERNAME')\n", hook),
        ("env membership allowed name", "import os\nv = 'LANG' in os.environ\n", hook),
        ("copying the environment", "import os\nenv = dict(os.environ)\nenv2 = os.environ.copy()\n", hook),
        ("git list literal", "import subprocess\nsubprocess.run(['git', 'status'], cwd='.')\n", hook),
        ("git constant", "import subprocess\nGIT = 'git'\nsubprocess.run([GIT, 'status'])\n", hook),
        ("module list plus arguments", "import subprocess\n_BASE = ['git', '--no-pager']\ndef f(a):\n    return subprocess.Popen(_BASE + a)\n", hook),
        ("local list that starts with git", "import subprocess\ndef f(a):\n    cmd = ['git'] + list(a)\n    return subprocess.run(cmd)\n", hook),
        ("sys.executable in a tool", "import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'pass'])\n", tool),
        ("a variable command list in a tool", "import subprocess\ndef f(cmd):\n    return subprocess.run(cmd)\n", tool),
        ("check_output list in a tool", "import subprocess\nsubprocess.check_output(['git', 'status'])\n", tool),
        ("shell=False", "import subprocess\nsubprocess.run(['git', 'x'], shell=False)\n", hook),
        ("reading a file", "with open('f', 'rb') as h:\n    h.read()\nopen('g')\n", hook),
        ("writing through fsio", "with open('f', 'wb') as h:\n    h.write(b'x')\n", "hooks/lib/fsio.py"),
        ("neutral example path", "p = '%s'\n" % ("C" + ":" + "\\\\" + "Users" + "\\\\" + "Ada" + "\\\\" + "x"), tool),
        ("swallow inside fsio", "def f():\n    try:\n        pass\n    except Exception:\n        pass\n", "hooks/lib/fsio.py"),
    ]
    for label, source, rel in accepted:
        scope = "hooks" if rel.startswith("hooks/") else "tools"
        errors, _warnings = scan_source(source, rel, scope)
        if errors:
            fails.append("the security scan wrongly flagged '%s': %s" % (label, errors[0][:120]))
    warned: List[Tuple[str, str, str]] = [
        ("hook swallowing errors", "def f():\n    try:\n        pass\n    except Exception:\n        pass\n", hook),
        ("tool writing a file", "with open('f', 'w') as h:\n    h.write('x')\n", tool),
        ("hook looping over the environment", "import os\nfor k in os.environ:\n    pass\n", hook),
    ]
    for label, source, rel in warned:
        scope = "hooks" if rel.startswith("hooks/") else "tools"
        if not _hit(source, rel, scope, want_warning=True):
            fails.append("the security scan should only warn about: %s" % label)
    errors, warnings = scan_source("def f(:\n", hook, "hooks")
    if not errors:
        fails.append("the security scan must report a file that does not parse")
    return fails


def installed_selfcheck() -> List[str]:
    """In an installed copy (TUTOR_IN_INSTALL_SELFTEST) only the files of the manifest are scanned, not the learner's own."""
    import shutil
    import tempfile
    fails: List[str] = []
    base = tempfile.mkdtemp(prefix="tutor-sec-")
    saved = os.environ.pop("TUTOR_IN_INSTALL_SELFTEST", None)
    try:
        os.makedirs(os.path.join(base, "hooks", "lib"))
        header = '"""Header."""\nfrom __future__ import annotations\n'
        with open(os.path.join(base, "hooks", "lib", "ours.py"), "wb") as handle:
            handle.write((header + "x = 1\n").encode("utf-8"))
        with open(os.path.join(base, "hooks", "lib", "mine.py"), "wb") as handle:
            handle.write((header + "import socket\n").encode("utf-8"))
        with open(os.path.join(base, "MANIFEST.txt"), "wb") as handle:
            handle.write(("# developer-tutor MANIFEST\n# version 1.0.0\n%s  hooks/lib/ours.py\n" % ("0" * 64)).encode("utf-8"))
        if not scan_product(base)[0]:
            fails.append("the scan must flag a file with a forbidden import in the kit's own folder")
        os.environ["TUTOR_IN_INSTALL_SELFTEST"] = "1"
        if scan_product(base)[0]:
            fails.append("the scan must skip files that are not in the manifest of an installed copy")
    finally:
        os.environ.pop("TUTOR_IN_INSTALL_SELFTEST", None)
        if saved is not None:
            os.environ["TUTOR_IN_INSTALL_SELFTEST"] = saved
        shutil.rmtree(base, ignore_errors=True)
    return fails


# --------------------------------------------------------------------------- entry points

def run_on(root: str) -> List[str]:
    del WARNINGS[:]
    errors, warnings = scan_product(root)
    WARNINGS.extend(warnings)
    return errors


def run() -> List[str]:
    fails = selfcheck()
    fails += installed_selfcheck()
    fails += run_on(PRODUCT)
    return fails


def run_security() -> List[str]:
    return run()


if __name__ == "__main__":
    target = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else None
    problems = run_on(target) if target else run()
    for item in problems:
        sys.stdout.buffer.write(("FAIL security: %s\n" % item).encode("utf-8", errors="replace"))
    for item in WARNINGS:
        sys.stdout.buffer.write(("WARN security: %s\n" % item).encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(("%d failure(s), %d warning(s)\n" % (len(problems), len(WARNINGS))).encode("utf-8"))
    sys.exit(1 if problems else 0)
