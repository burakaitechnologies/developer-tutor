"""lint_py39.py - find Python 3.10+ syntax and library use in files that must run on Python 3.9 (SPEC P13).

What: parses each .py file with the running Python and reports: match statements, except*, `X | Y` outside
annotations, zip(strict=), datetime.UTC, itertools.pairwise, tomllib, typing.Self / TypeAlias / ParamSpec,
Path.walk, int.bit_count, contextlib.chdir, ExceptionGroup, StrEnum, dataclass(slots=...), and a missing
`from __future__ import annotations`.
Why: the product must run on 3.9, while the build machines have newer Pythons that accept all of this silently.
Real 3.9 runs happen in CI; this lint catches the common slips early.
How it fails safely: read-only; a file that does not parse is reported, not fatal. Exit code 1 when anything is found.
Use:  python lint_py39.py [PATH ...]      (default: the folder of this file; folders are searched recursively)
"""
from __future__ import annotations

import ast
import os
import sys
from typing import Iterator, List, Optional, Set, Tuple

sys.dont_write_bytecode = True

TYPE_NAMES = {"None", "str", "int", "float", "bool", "bytes", "list", "dict", "set", "tuple", "Any", "object"}
BAD_IMPORTS = {"tomllib": "tomllib is 3.11+", "zoneinfo_future": ""}
BAD_FROM = {("typing", "Self"): "typing.Self is 3.11+", ("typing", "TypeAlias"): "typing.TypeAlias is 3.10+",
            ("typing", "ParamSpec"): "typing.ParamSpec is 3.10+", ("typing", "TypeGuard"): "typing.TypeGuard is 3.10+",
            ("typing", "override"): "typing.override is 3.12+", ("enum", "StrEnum"): "enum.StrEnum is 3.11+",
            ("itertools", "pairwise"): "itertools.pairwise is 3.10+", ("contextlib", "chdir"): "contextlib.chdir is 3.11+",
            ("datetime", "UTC"): "datetime.UTC is 3.11+", ("asyncio", "TaskGroup"): "asyncio.TaskGroup is 3.11+"}
BAD_ATTRS = {"pairwise": "itertools.pairwise is 3.10+", "bit_count": "int.bit_count is 3.10+", "UTC": "datetime.UTC is 3.11+",
             "chdir": "contextlib.chdir is 3.11+", "StrEnum": "enum.StrEnum is 3.11+", "Self": "typing.Self is 3.11+"}
BAD_NAMES = {"ExceptionGroup": "ExceptionGroup is 3.11+", "BaseExceptionGroup": "BaseExceptionGroup is 3.11+", "aiter": "aiter is 3.10+", "anext": "anext is 3.10+"}


def annotation_nodes(tree: ast.AST) -> Set[int]:
    """ids of every node inside an annotation (these are strings at run time thanks to the __future__ import)."""
    inside: Set[int] = set()

    def mark(node: Optional[ast.AST]) -> None:
        if node is not None:
            for sub in ast.walk(node):
                inside.add(id(sub))

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            mark(node.returns)
            for arg in node.args.args + node.args.kwonlyargs + node.args.posonlyargs:
                mark(arg.annotation)
            mark(node.args.vararg.annotation if node.args.vararg else None)
            mark(node.args.kwarg.annotation if node.args.kwarg else None)
        elif isinstance(node, ast.AnnAssign):
            mark(node.annotation)
    return inside


def looks_like_type(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant) and node.value is None:
        return True
    if isinstance(node, ast.Name) and node.id in TYPE_NAMES:
        return True
    if isinstance(node, ast.Subscript):
        return looks_like_type(node.value)
    return False


def check(path: str) -> List[Tuple[int, str]]:
    try:
        with open(path, encoding="utf-8-sig") as f:
            source = f.read()
        tree = ast.parse(source, filename=path)
    except (OSError, SyntaxError, ValueError) as exc:
        return [(0, "cannot parse: %s" % exc)]
    found: List[Tuple[int, str]] = []
    has_future = any(isinstance(n, ast.ImportFrom) and n.module == "__future__" and any(a.name == "annotations" for a in n.names) for n in tree.body)
    if not has_future and source.strip():
        found.append((1, "missing 'from __future__ import annotations'"))
    inside = annotation_nodes(tree)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.Match):
            found.append((line, "match statement is 3.10+"))
        elif type(node).__name__ == "TryStar":
            found.append((line, "except* is 3.11+"))
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr) and id(node) not in inside:
            if looks_like_type(node.left) or looks_like_type(node.right):
                found.append((line, "X | Y type union outside an annotation is 3.10+"))
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "zip" and any(k.arg == "strict" for k in node.keywords):
                found.append((line, "zip(strict=) is 3.10+"))
            if isinstance(func, ast.Name) and func.id == "isinstance" and len(node.args) == 2 and isinstance(node.args[1], ast.BinOp):
                found.append((line, "isinstance with X | Y is 3.10+"))
            if isinstance(func, ast.Attribute) and func.attr == "walk" and isinstance(func.value, ast.Call):
                inner = func.value.func
                if isinstance(inner, ast.Name) and inner.id in ("Path", "PurePath"):
                    found.append((line, "Path.walk is 3.12+"))
            if isinstance(func, (ast.Name, ast.Attribute)):
                name = func.id if isinstance(func, ast.Name) else func.attr
                if name == "dataclass" and any(k.arg in ("slots", "kw_only", "match_args") for k in node.keywords):
                    found.append((line, "dataclass(slots=/kw_only=) is 3.10+"))
        elif isinstance(node, ast.Attribute) and node.attr in BAD_ATTRS:
            found.append((line, BAD_ATTRS[node.attr]))
        elif isinstance(node, ast.Name) and node.id in BAD_NAMES:
            found.append((line, BAD_NAMES[node.id]))
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name in BAD_IMPORTS and BAD_IMPORTS[alias.name]:
                    found.append((line, BAD_IMPORTS[alias.name]))
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                note = BAD_FROM.get((node.module or "", alias.name))
                if note:
                    found.append((line, note))
            if node.module == "tomllib":
                found.append((line, "tomllib is 3.11+"))
    return found


def python_files(paths: List[str]) -> Iterator[str]:
    for path in paths:
        if os.path.isfile(path):
            yield path
        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(root, name)


def main(argv: List[str]) -> int:
    paths = argv or [os.path.dirname(os.path.abspath(__file__))]
    total = 0
    count = 0
    for path in python_files(paths):
        count += 1
        for line, message in sorted(set(check(path))):
            total += 1
            sys.stdout.buffer.write(("%s:%d: %s\n" % (path, line, message)).encode("utf-8", errors="replace"))
    sys.stdout.buffer.write(("lint_py39: %d file(s), %d finding(s)\n" % (count, total)).encode("ascii"))
    return 1 if total else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
