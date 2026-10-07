"""selftest.py - runs every offline check of the tutor with one command.

What: finds the files selftest_*.py next to this one and runs each in its OWN Python process, so a hang
or a crash in one test cannot hide the others. It also runs validate.py (as the module "validate").
Usage: python selftest.py [--quick] [--security] [--only NAME[,NAME]] [--list] [--verbose] [--jobs N]
  --quick     sets TUTOR_SELFTEST_QUICK=1 so modules shrink their loops (install.py and CI smoke runs)
  --security  runs only selftest_security.py (a plain run includes it anyway)
  --only      runs the named modules (names without the selftest_ prefix; "validate" is allowed)
  --list      prints the module names and stops
  --verbose   shows warnings and every failure line (otherwise at most 30 lines per module)
  --jobs N    runs up to N modules at the same time (default: half the processors, at most 4; 1 = one by one)
Environment: TUTOR_SELFTEST_TIMEOUT sets the seconds a module may run (default 120).
Each module offers run() -> list of failure messages (empty = pass) and may offer WARNINGS (a list of text).
Output: "OK <module> (x.x s)" per passing module, "FAIL <module>: <message>" per failure, and
"RESULT: N modules, F failures, T s". Exit code 0 = all passed, 1 = a failure, 2 = a bad command line.
How it fails safely: a module that raises, exits, times out (120 s) or prints junk counts as a failure with a
plain reason; the runner writes only into temp folders (through the modules) and removes any __pycache__
folder that appeared during the run; no network; standard library only.
Who calls it: people, install.py (--quick), doctor.py verify, CI.
Internal: "python -I -B -X utf8 selftest.py --module NAME" is how the runner starts one module.
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional, Set, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCT = os.path.dirname(HERE)


def _timeout_seconds() -> int:
    """120 seconds per module; TUTOR_SELFTEST_TIMEOUT (1 to 600) lets the runner's own test use a short limit."""
    try:
        value = int(os.environ.get("TUTOR_SELFTEST_TIMEOUT", "120"))
    except ValueError:
        return 120
    return value if 1 <= value <= 600 else 120


MODULE_TIMEOUT_SECONDS = _timeout_seconds()
FAILURE_LINES_SHOWN = 30
# Timing tests must not compete with other modules for the processor, so they run alone at the end.
SERIAL_LAST = ("perf", "secrets", "guard")
USAGE = "usage: python selftest.py [--quick] [--security] [--only NAME[,NAME]] [--list] [--verbose] [--jobs N]"


def out(text: str = "") -> None:
    data = (text + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except (AttributeError, ValueError, OSError):
        try:
            sys.stdout.write(data.decode("utf-8", errors="replace"))
        except Exception:  # noqa: BLE001 - printing must never raise
            pass


def discover() -> List[str]:
    """Module names (without the selftest_ prefix) of the test files in this folder, plus 'validate'."""
    names = []
    for entry in sorted(os.listdir(HERE)):
        if entry.startswith("selftest_") and entry.endswith(".py"):
            names.append(entry[len("selftest_"):-3])
    if os.path.isfile(os.path.join(HERE, "validate.py")):
        names.append("validate")
    return names


def one_line(message: object) -> str:
    return " / ".join(part.strip() for part in str(message).splitlines() if part.strip())[:600]


# --------------------------------------------------------------------------- child side

def run_child(name: str) -> int:
    """Run one module inside this process and print FAIL / WARN lines."""
    sys.path.insert(0, HERE)
    import importlib
    try:
        module = importlib.import_module("selftest_" + name)
    except BaseException as exc:  # noqa: BLE001 - report, never crash silently
        out("FAIL %s: could not load the module (%s: %s)" % (name, type(exc).__name__, one_line(exc)[:200]))
        return 1
    func = getattr(module, "run", None)
    if not callable(func):
        out("FAIL %s: the module has no run() function" % name)
        return 1
    try:
        result = func()
    except SystemExit as stop:
        out("FAIL %s: the module called sys.exit(%r)" % (name, stop.code))
        return 1
    except BaseException as exc:  # noqa: BLE001
        frames = traceback.extract_tb(exc.__traceback__)
        where = "%s line %d" % (os.path.basename(frames[-1].filename), frames[-1].lineno) if frames else "?"
        out("FAIL %s: crashed with %s in %s: %s" % (name, type(exc).__name__, where, one_line(exc)[:200]))
        return 1
    failures = [one_line(item) for item in (result or [])]
    for text in getattr(module, "WARNINGS", None) or []:
        out("WARN %s: %s" % (name, one_line(text)))
    for text in failures:
        out("FAIL %s: %s" % (name, text))
    return 1 if failures else 0


# --------------------------------------------------------------------------- parent side

def run_validate(quick: bool) -> Tuple[List[str], List[str]]:
    """Run validate.py in this process. Returns (failure messages, warning lines)."""
    sys.path.insert(0, HERE)
    try:
        import validate
        report = validate.validate(quick=quick)
        return [line[len("ERROR "):] if line.startswith("ERROR ") else line for line in report.errors], report.warnings
    except BaseException as exc:  # noqa: BLE001
        return ["validate.py could not run (%s: %s)" % (type(exc).__name__, one_line(exc)[:200])], []
    finally:
        try:
            sys.path.remove(HERE)
        except ValueError:
            pass


def run_module_process(name: str, quick: bool) -> Tuple[List[str], List[str], float, str]:
    """(failure messages, warning lines, seconds, raw output) for one module run in its own process."""
    env = dict(os.environ)
    if quick:
        env["TUTOR_SELFTEST_QUICK"] = "1"
    argv = [sys.executable, "-I", "-B", "-X", "utf8", os.path.join(HERE, "selftest.py"), "--module", name]
    started = time.perf_counter()
    try:
        proc = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env,
                              cwd=HERE, timeout=MODULE_TIMEOUT_SECONDS)
        code, raw_out, raw_err = proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return ["timed out after %d seconds" % MODULE_TIMEOUT_SECONDS], [], time.perf_counter() - started, ""
    except OSError as exc:
        return ["could not start Python (%s)" % type(exc).__name__], [], time.perf_counter() - started, ""
    seconds = time.perf_counter() - started
    text = raw_out.decode("utf-8", errors="replace")
    err = raw_err.decode("utf-8", errors="replace")
    prefix_fail, prefix_warn = "FAIL %s: " % name, "WARN %s: " % name
    failures = [l[len(prefix_fail):] for l in text.splitlines() if l.startswith(prefix_fail)]
    warnings = [l[len(prefix_warn):] for l in text.splitlines() if l.startswith(prefix_warn)]
    if code != 0 and not failures:
        tail = [l for l in err.splitlines() if l.strip()]
        failures = ["the test process ended with exit code %d and no failure message%s" % (code, ": " + tail[-1][:200] if tail else "")]
    elif code == 0 and failures:
        failures.append("the test process reported failures but exited with 0")
    return failures, warnings, seconds, text + err


def find_caches() -> Set[str]:
    found: Set[str] = set()
    for dirpath, dirnames, _files in os.walk(PRODUCT):
        if "agent-memory" in dirnames:
            dirnames.remove("agent-memory")
        if "__pycache__" in dirnames:
            found.add(os.path.join(dirpath, "__pycache__"))
            dirnames.remove("__pycache__")
    return found


def remove_new_caches(before: Set[str]) -> None:
    import shutil
    for path in find_caches() - before:
        shutil.rmtree(path, ignore_errors=True)


def parse_args(argv: List[str]) -> Optional[Dict[str, object]]:
    options: Dict[str, object] = {"quick": False, "security": False, "only": [], "list": False, "verbose": False, "module": "", "jobs": 0}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in ("--quick", "--security", "--list", "--verbose"):
            options[arg[2:]] = True
        elif arg == "--only" and i + 1 < len(argv):
            options["only"] = [n.strip() for n in argv[i + 1].split(",") if n.strip()]
            i += 1
        elif arg.startswith("--only="):
            options["only"] = [n.strip() for n in arg[len("--only="):].split(",") if n.strip()]
        elif arg == "--module" and i + 1 < len(argv):
            options["module"] = argv[i + 1]
            i += 1
        elif arg == "--jobs" and i + 1 < len(argv) and argv[i + 1].isdigit() and int(argv[i + 1]) >= 1:
            options["jobs"] = int(argv[i + 1])
            i += 1
        else:
            return None
        i += 1
    return options


def main(argv: List[str]) -> int:
    options = parse_args(argv)
    if options is None:
        out("Unknown or incomplete option.")
        out(USAGE)
        return 2
    if options["module"]:
        return run_child(str(options["module"]))
    names = discover()
    if options["list"]:
        for name in names:
            out(name)
        return 0
    wanted: List[str] = list(options["only"])  # type: ignore[arg-type]
    if options["security"]:
        wanted = ["security"]
    if wanted:
        unknown = [n for n in wanted if n not in names]
        if unknown:
            out("No test module named: %s (known: %s)" % (", ".join(unknown), ", ".join(names)))
            return 2
        names = [n for n in names if n in wanted]
    quick = bool(options["quick"])
    verbose = bool(options["verbose"])
    caches_before = find_caches()
    out("selftest: Python %s, %d module(s)%s" % (sys.version.split()[0], len(names), ", quick mode" if quick else ""))
    total_failures = 0
    started = time.perf_counter()
    jobs = int(options["jobs"]) or max(1, min(4, (os.cpu_count() or 2) // 2))
    results: Dict[str, Tuple[List[str], List[str], float]] = {}

    def work(name: str) -> Tuple[List[str], List[str], float]:
        if name == "validate":
            begin = time.perf_counter()
            failures, warnings = run_validate(quick)
            return failures, warnings, time.perf_counter() - begin
        failures, warnings, seconds, _raw = run_module_process(name, quick)
        return failures, warnings, seconds

    parallel_names = [n for n in names if n not in SERIAL_LAST and n != "validate"]
    serial_names = [n for n in names if n in SERIAL_LAST or n == "validate"]
    if jobs > 1 and len(parallel_names) > 1:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = {n: pool.submit(work, n) for n in parallel_names}
            for name in parallel_names:
                results[name] = futures[name].result()
    else:
        for name in parallel_names:
            results[name] = work(name)
    for name in serial_names:
        results[name] = work(name)
    for name in names:
        failures, warnings, seconds = results[name]
        if verbose:
            for line in warnings:
                out("WARN %s: %s" % (name, line))
        if failures:
            shown = failures if verbose else failures[:FAILURE_LINES_SHOWN]
            for message in shown:
                out("FAIL %s: %s" % (name, message))
            if len(shown) < len(failures):
                out("FAIL %s: ... and %d more (use --verbose)" % (name, len(failures) - len(shown)))
            total_failures += len(failures)
        else:
            out("OK %s (%.1f s)" % (name, seconds))
    remove_new_caches(caches_before)
    out("RESULT: %d modules, %d failures, %.1f s" % (len(names), total_failures, time.perf_counter() - started))
    return 1 if total_failures else 0


if __name__ == "__main__":
    try:
        code = main(sys.argv[1:])
    except Exception as exc:  # noqa: BLE001
        out("selftest runner stopped with %s: %s" % (type(exc).__name__, one_line(exc)[:200]))
        code = 1
    sys.exit(code)
