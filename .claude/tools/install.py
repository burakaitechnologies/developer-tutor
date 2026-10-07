"""install.py - put the tutor's .claude folder into a project, update it, or remove it (for people who use a terminal).

What: python install.py <project-folder> [--dry-run] [--update] [--uninstall] [--interpreter NAME]
[--enable-hooks] [--accept-existing] [--yes-this-is-my-project] [--skip-selftest].
  first install  copies the kit files that are missing (never overwrites), merges settings.json last,
                 repairs .claude/.gitignore, then runs the quick self-test on a temporary copy.
  --update       replaces a kit file only if it is still exactly what the OLD version shipped (or is gone);
                 a file you edited stays, and the new version is saved next to it as <file>.new.
  --uninstall    removes only kit files that are unchanged, keeps your notes (agent-memory), keeps settings.json
                 and only takes the tutor's hook entries out of it.
  --dry-run      prints exactly what would happen and writes nothing.
Why: the README's main path needs no terminal. This is the careful route for people who want a repeatable install.
How it fails safely: it refuses the home folder, a drive root, ~/.claude, the kit's own folder, system folders,
a folder that does not exist yet (it never creates one), a folder that is neither empty nor has a project marker
(an empty folder, or one with only .git, README, LICENSE or .gitignore, is a new project), and a .claude that is a link (exit 2). It lists everything in the project that
can run code before it copies, and stops unless you add --accept-existing. It never writes outside
<project>/.claude, never touches agent-memory/ or settings.local.json, never edits the project's root .gitignore
or CLAUDE.md, never follows links in the kit, checks every copy byte for byte, and writes a backup before it
changes settings.json. Exit codes: 0 done, 1 done with warnings or a failed self-test (or a bad command line), 2 refused.
Who calls it: people; tools/selftest_tools.py. It loads tools/doctor.py with runpy for the audit, the settings
helpers and the manifest reader, so those rules live in one place. Python 3.9, standard library only.
"""
from __future__ import annotations

import copy
import fnmatch
import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)                    # the kit's .claude folder
TEMPLATE_ROOT = os.path.dirname(SRC)           # the folder that holds the kit's .claude
MARKERS = (".git", "package.json", "pyproject.toml", "requirements.txt", "Cargo.toml", "go.mod", "*.sln", "index.html", "README*")
NEW_PROJECT_NAMES = (".git", "README*", "LICENSE*", ".gitignore", ".claude")   # .claude: an earlier install into an empty folder
USAGE = """install.py - put the tutor's .claude folder into a project.
Usage: python install.py <project-folder> [options]
  The folder must already exist (create it first). An empty folder is a new project and needs no flag.
  --dry-run               show what would happen; write nothing
  --update                update kit files (your edited files stay; new versions are saved as <file>.new)
  --uninstall             remove the kit files that are unchanged; your notes stay
  --enable-hooks          also turn the helper scripts (hooks) on (needs a working Python)
  --interpreter NAME      the Python name for the hooks: python3, python, py, or a full path
  --accept-existing       go on although the project already has files that can run code
  --yes-this-is-my-project   go on although the folder has no project file (package.json, .git, README, ...)
  --skip-selftest         do not run the quick self-test after copying
Exit codes: 0 done, 1 done with warnings, 2 refused."""


class Usage(Exception):
    pass


STATE: Dict[str, Any] = {"capture": None}     # tests set capture to [] to collect the output lines


def out(text: str = "") -> None:
    if STATE["capture"] is not None:
        STATE["capture"].append(text)
        return
    data = (text + "\n").encode("utf-8", errors="replace")
    try:
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
    except (AttributeError, OSError, ValueError):
        try:
            sys.stdout.write(text + "\n")
        except Exception:
            pass


def load_doctor() -> Dict[str, Any]:
    doc = runpy.run_path(os.path.join(HERE, "doctor.py"), run_name="doctor_module")
    doc["STATE"]["libs"] = False          # the installer needs only the pure helpers; never import the target's hook modules
    return doc


# --------------------------------------------------------------------------- refusing a target

def real(path: str) -> str:
    try:
        return os.path.normcase(os.path.realpath(path))
    except (OSError, ValueError):
        return os.path.normcase(os.path.abspath(path))


def inside(path: str, folder: str, allow_equal: bool = True) -> bool:
    a, b = real(path), real(folder)
    if a == b:
        return allow_equal
    return a.startswith(b.rstrip("\\/") + os.sep)


def system_folders() -> Tuple[List[str], List[str]]:
    """(folders that are refused with everything below them, folders refused only as themselves)."""
    below: List[str] = []
    exact: List[str] = []
    if os.name == "nt":
        for var in ("SystemRoot", "windir", "ProgramFiles", "ProgramFiles(x86)", "ProgramW6432"):
            if os.environ.get(var):
                below.append(os.environ[var])
        below += ["C:\\Windows", "C:\\Program Files", "C:\\Program Files (x86)"]
    else:
        below += ["/etc", "/usr", "/bin", "/sbin", "/lib", "/lib64", "/boot", "/dev", "/proc", "/sys", "/System", "/Library", "/private/etc"]
        exact += ["/var"]
    return below, exact


def home_folder() -> str:
    return os.path.expanduser("~")


def refusal_for(target: str, home: str, template_root: str, src_claude: str) -> str:
    """A plain sentence when this folder must not get the tutor, else an empty string."""
    tgt = real(target)
    if os.path.dirname(tgt) == tgt:
        return "This is the top of a drive. The tutor needs a folder for one project."
    if tgt == real(home):
        return "This is your home folder. Make a new folder for one project, and install there."
    home_claude = os.path.join(home, ".claude")
    if inside(target, home_claude):
        return "This is the .claude folder in your home folder. It holds Claude Code's own settings."
    template_is_broad = real(template_root) == real(home) or os.path.dirname(real(template_root)) == real(template_root)
    if tgt == real(template_root) or inside(target, src_claude) or (not template_is_broad and inside(target, template_root)):
        return "This folder is the tutor kit itself, or inside it. Install into your own project folder instead."
    below, exact = system_folders()
    for folder in below:
        if inside(target, folder):
            return "This is a system folder. Programs and the system live here, not projects."
    for folder in exact:
        if tgt == real(folder):
            return "This is a system folder. Programs and the system live here, not projects."
    return ""


def has_marker(target: str) -> bool:
    try:
        names = os.listdir(target)
    except OSError:
        return False
    for name in names:
        for pattern in MARKERS:
            if fnmatch.fnmatchcase(name.lower(), pattern.lower()):
                return True
    return False


def is_new_project(target: str) -> bool:
    """True for an empty folder, or one whose only names are a .git folder, README, LICENSE or .gitignore:
    a new project that needs no flag. Any other file or folder leaves it to the project-file check."""
    try:
        names = os.listdir(target)
    except OSError:
        return False
    return all(any(fnmatch.fnmatchcase(name.lower(), pattern.lower()) for pattern in NEW_PROJECT_NAMES) for name in names)


def wide_folder_warning(target: str, home: str) -> str:
    tgt = real(target)
    for name in ("Desktop", "Documents", "Downloads"):
        if tgt == real(os.path.join(home, name)):
            return "This is your %s folder. The tutor works best in a folder made for one project." % name
    if tgt in (real(os.path.dirname(home)),):
        return "This folder holds all user accounts. The tutor works best in a folder made for one project."
    return ""


def synced_warning(target: str) -> str:
    low = target.lower()
    for name in ("onedrive", "icloud", "dropbox", "google drive"):
        if name in low:
            return "This folder is synced by %s. A sync service can damage the .git folder. Git history is not a backup." % name
    return ""


# --------------------------------------------------------------------------- plan

class Plan(object):
    def __init__(self) -> None:
        self.actions: List[Tuple[str, str, str]] = []      # (kind, relative path, note)
        self.warnings: List[str] = []
        self.notes: List[str] = []

    def add(self, kind: str, rel: str, note: str = "") -> None:
        self.actions.append((kind, rel, note))

    def of(self, kind: str) -> List[str]:
        return [rel for k, rel, _ in self.actions if k == kind]


def safe_rel(rel: str) -> bool:
    parts = rel.split("/")
    if not rel or rel.startswith("/") or "\\" in rel or ":" in rel:
        return False
    return all(p not in ("", ".", "..") for p in parts)


def dest_ok(doctor: Dict[str, Any], tclaude: str, rel: str) -> bool:
    """False when a folder on the way to the destination is a link (nothing may be written through a link)."""
    cur = tclaude
    for part in rel.split("/")[:-1]:
        cur = os.path.join(cur, part)
        if os.path.lexists(cur) and doctor["is_link"](cur):
            return False
    return True


def source_files(doctor: Dict[str, Any], plan: Plan) -> Tuple[List[str], Dict[str, str]]:
    """The relative paths this kit ships, and their hashes (empty when there is no manifest).
    The copy list is every file the manifest names PLUS every shipped file it does not name, so a stale MANIFEST.txt
    can never drop the docs or the README from an install; the stale manifest is reported as a warning instead."""
    version, files, bad = doctor["read_manifest"](os.path.join(SRC, "MANIFEST.txt"))
    if version is not None and files:
        check = doctor["compare_manifest"](SRC, files)
        problems = len(check["modified"]) + len(check["missing"])
        if problems:
            plan.warnings.append("The kit's own files do not match its MANIFEST.txt (%d file(s) differ or are missing). "
                                 "Use the released copy if you can." % problems)
        if check["extra"]:
            plan.warnings.append("The kit has %d file(s) that its MANIFEST.txt does not list. I copied them anyway; "
                                 "the released copy needs a new MANIFEST.txt." % len(check["extra"]))
        names = set(files) | set(check["extra"])
        rels = [r for r in sorted(names) if safe_rel(r)]
        skipped = len(names) - len(rels)
        if skipped:
            plan.warnings.append("%d manifest path(s) looked unsafe and were skipped." % skipped)
        # the files the manifest does not name are the kit's own too: their hashes let the audit recognise them
        known = dict(files)
        for rel in check["extra"]:
            digest = doctor["sha256_file"](os.path.join(SRC, *rel.split("/")))
            if digest:
                known[rel] = digest
        return [r for r in rels if os.path.isfile(os.path.join(SRC, *r.split("/"))) and not doctor["has_link_between"](os.path.join(SRC, *r.split("/")), SRC)], known
    plan.notes.append("The kit has no MANIFEST.txt (a development copy), so I copy every file in it.")
    return doctor["list_shipped_files"](SRC), {}


def build_plan(doctor: Dict[str, Any], tclaude: str, rels: List[str], update: bool, plan: Plan) -> None:
    _, old, _ = doctor["read_manifest"](os.path.join(tclaude, "MANIFEST.txt"))
    for rel in rels:
        if rel in ("settings.json", "MANIFEST.txt") or doctor["is_excluded"](rel):
            continue
        s = os.path.join(SRC, *rel.split("/"))
        d = os.path.join(tclaude, *rel.split("/"))
        if rel == ".gitignore":
            plan.add("gitignore", rel)
            continue
        if not dest_ok(doctor, tclaude, rel) or (os.path.lexists(d) and doctor["is_link"](d)):
            plan.add("link", rel)
            plan.warnings.append("%s is, or sits inside, a link. I did not write it." % rel)
            continue
        if not os.path.lexists(d):
            plan.add("copy", rel)
        elif not os.path.isfile(d):
            plan.add("skip", rel, "not a plain file")
            plan.warnings.append("%s exists but is not a plain file. I left it." % rel)
        else:
            cur, new = doctor["sha256_file"](d), doctor["sha256_file"](s)
            if cur == new:
                plan.add("same", rel)
            elif update:
                if old.get(rel) and cur == old.get(rel):
                    plan.add("update", rel)
                else:
                    plan.add("new", rel)
                    plan.warnings.append("%s was changed by you. I kept it and saved the new version as %s.new" % (rel, rel))
            else:
                plan.add("skip", rel, "differs")
                plan.warnings.append("%s already exists and differs from the kit's copy. I left it (use --update to see the new version)." % rel)
    if update and old:
        keep = set(rels) | {"settings.json", "MANIFEST.txt", ".gitignore"}
        for rel in sorted(old):
            if rel in keep or not safe_rel(rel) or doctor["is_excluded"](rel):
                continue
            d = os.path.join(tclaude, *rel.split("/"))
            if not os.path.isfile(d) or doctor["is_link"](d) or not dest_ok(doctor, tclaude, rel):
                continue
            if doctor["sha256_file"](d) == old[rel]:
                plan.add("delete", rel)
            else:
                plan.add("keep-removed", rel)
                plan.warnings.append("%s was removed from the kit but you changed it, so it stays." % rel)


# --------------------------------------------------------------------------- copying

def copy_verified(doctor: Dict[str, Any], src: str, dst: str) -> bool:
    """Copy with shutil.copy2 to a .part file, compare the bytes, then rename. False when anything went wrong."""
    tmp = dst + ".part"
    try:
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.copy2(src, tmp)
        with open(src, "rb") as a, open(tmp, "rb") as b:
            if a.read() != b.read():
                raise OSError("bytes differ after copy")
        os.replace(tmp, dst)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def prune_empty_dirs(doctor: Dict[str, Any], tclaude: str) -> None:
    """Remove empty folders below tclaude (never agent-memory, never a link or anything below one), then tclaude itself if empty."""
    def walk(folder: str, top: bool) -> None:
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return
        for name in names:
            sub = os.path.join(folder, name)
            if top and name == "agent-memory":
                continue
            if os.path.isdir(sub) and not doctor["is_link"](sub):
                walk(sub, False)
                try:
                    if not os.listdir(sub):
                        os.rmdir(sub)
                except OSError:
                    pass

    if os.path.isdir(tclaude) and not doctor["is_link"](tclaude):
        walk(tclaude, True)
        try:
            if not os.listdir(tclaude):
                os.rmdir(tclaude)
        except OSError:
            pass


# --------------------------------------------------------------------------- settings.json

def merge_settings(target: Dict[str, Any], kit: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str], List[str]]:
    """Merge the kit's settings into the project's. Never replaces: objects are merged, arrays are joined in order
    without repeats, a value that exists stays (a different kit value is reported). The kit's 'hooks' are not merged here.
    Returns (merged, what was added, what was kept although the kit says otherwise)."""
    merged = copy.deepcopy(target)
    changes: List[str] = []
    conflicts: List[str] = []

    def blend(dst: Dict[str, Any], src: Dict[str, Any], prefix: str) -> None:
        for key, value in src.items():
            if prefix == "" and key == "hooks":
                continue
            path = prefix + key
            if key not in dst:
                dst[key] = copy.deepcopy(value)
                changes.append(path)
                continue
            current = dst[key]
            if isinstance(current, dict) and isinstance(value, dict):
                blend(current, value, path + ".")
            elif isinstance(current, list) and isinstance(value, list):
                added = [x for x in value if x not in current]
                if added:
                    current.extend(copy.deepcopy(added))
                    changes.append("%s (+%d)" % (path, len(added)))
            elif current != value:
                conflicts.append(path)

    blend(merged, kit, "")
    return merged, changes, conflicts


def plan_settings(doctor: Dict[str, Any], tclaude: str, plan: Plan, want_hooks: bool, interpreter: Optional[str]) -> Optional[Dict[str, Any]]:
    """Work out the merged settings.json. Returns {'new': dict, 'changed': bool} or None when nothing can be merged."""
    kit_path = os.path.join(SRC, "settings.json")
    kit, why = doctor["load_settings"](kit_path)
    target_path = os.path.join(tclaude, "settings.json")
    target, twhy = doctor["load_settings"](target_path)
    if kit is None:
        if why == "missing":
            plan.notes.append("The kit has no settings.json yet, so there is nothing to merge.")
        else:
            plan.warnings.append("The kit's settings.json could not be read (%s). I did not merge settings." % why)
            return None
    if target is None and twhy not in ("missing",):
        plan.warnings.append("The project's settings.json is not valid JSON (%s). I did not touch it; fix it and run again." % twhy)
        return None
    base = target if target is not None else {}
    merged, changes, conflicts = merge_settings(base, kit or {})
    for key in conflicts:
        plan.warnings.append("settings.json: your value for '%s' stays; the tutor expects a different one." % key)
    hook_note = ""
    if want_hooks:
        spec, problem = doctor["read_hooks_spec"](os.path.join(SRC, "tools", "hooks.json"))
        if spec is None:
            plan.warnings.append("Hooks were not turned on: " + problem)
        else:
            if interpreter:
                command, extra, bad = doctor["check_interpreter_name"](interpreter)
                ok, ver, why2 = (False, "", bad) if bad else doctor["probe_interpreter"](command, extra)
            else:
                command, extra, ver = doctor["find_working_interpreter"]()
                ok, why2 = bool(command), "I found no working Python (tried python3, python, py -3)."
            if not ok:
                plan.warnings.append("Hooks were not turned on. " + why2)
            else:
                merged = doctor["merge_hooks"](merged, spec, command, extra)
                hook_note = "hooks on with %s (Python %s)" % (doctor["display_name"](command, extra), ver)
    elif interpreter:
        plan.notes.append("--interpreter is only used together with --enable-hooks, so I ignored it.")
    changed = merged != base
    if changed:
        what = ", ".join(changes[:6]) + (" and more" if len(changes) > 6 else "")
        if hook_note:
            what = (what + "; " if what else "") + hook_note
        plan.add("settings", "settings.json", what or "no new keys")
    elif kit is not None:
        plan.add("settings-same", "settings.json")
    return {"new": merged, "changed": changed, "existed": target is not None}


# --------------------------------------------------------------------------- self-test

def run_selftest(tclaude: str) -> Tuple[Optional[bool], List[str]]:
    """Run tools/selftest.py --quick on a temporary copy of the installed .claude. (None, note) when it cannot run."""
    script = os.path.join(tclaude, "tools", "selftest.py")
    if not os.path.isfile(script):
        return None, ["The quick self-test was skipped: tools/selftest.py is not in the kit yet."]
    tmp = tempfile.mkdtemp(prefix="tutor-install-")
    try:
        proj = os.path.join(tmp, "project")
        os.makedirs(proj)
        shutil.copytree(tclaude, os.path.join(proj, ".claude"), symlinks=True,
                        ignore=shutil.ignore_patterns("agent-memory", "__pycache__", "*.pyc", "*.tutor-backup", "*.new", "settings.local.json"))
        env = dict(os.environ)
        env["CLAUDE_PROJECT_DIR"] = proj
        env["TUTOR_IN_INSTALL_SELFTEST"] = "1"
        try:
            proc = subprocess.run([sys.executable, "-B", os.path.join(proj, ".claude", "tools", "selftest.py"), "--quick"],
                                  cwd=proj, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=240)
        except subprocess.TimeoutExpired:
            return False, ["The quick self-test took longer than 4 minutes and was stopped."]
        except OSError as exc:
            return False, ["The quick self-test could not start (%s)." % type(exc).__name__]
        text = proc.stdout.decode("utf-8", "replace")
        lines = [ln for ln in text.split("\n") if ln.strip()]
        keep = [ln for ln in lines if ln.startswith(("FAIL", "        -", "selftest:"))][:12]
        return proc.returncode == 0, keep or lines[-3:]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- reporting

NEXT_STEPS = (
    "1. Open the project folder in Claude Code (the Desktop app, or run claude in a terminal inside the folder).",
    "2. Claude Code asks whether you trust the folder. Read the question, then say yes if you trust it.",
    "3. Say hello. The tutor asks what you want to make, and helps you build it.",
    "4. The tutor explains new words and asks short questions. It keeps private notes in .claude/agent-memory on your computer.",
    "5. The helper scripts (hooks) are off at first. To turn them on later, tell the tutor \"turn on helper scripts\", or run: py -3 .claude/tools/doctor.py enable-hooks (Windows) or python3 .claude/tools/doctor.py enable-hooks (macOS and Linux). If that command is not found, try python.",
)


def print_plan(plan: Plan, dry: bool) -> None:
    verbs = {"copy": ("would copy", "Copied"), "update": ("would update", "Updated"), "new": ("would save the new version next to", "Saved a .new file for"),
             "delete": ("would delete (removed from the kit, unchanged)", "Deleted"), "keep-removed": ("would keep (removed from the kit, but you edited it)", "Kept"),
             "skip": ("would skip (already there)", "Skipped"), "same": ("already identical", "Already identical"), "link": ("would not write (link)", "Not written (link)")}
    if dry:
        for kind in ("copy", "update", "new", "delete", "keep-removed", "skip", "link"):
            for rel in plan.of(kind):
                out("  %s .claude/%s" % (verbs[kind][0], rel))
        for kind, rel, note in plan.actions:
            if kind == "settings":
                out("  would merge .claude/settings.json (%s)" % note)
            elif kind == "settings-same":
                out("  .claude/settings.json already has everything the kit needs")
            elif kind == "gitignore":
                out("  would create or repair .claude/.gitignore")
        out("  (%d file(s) already identical)" % len(plan.of("same")))
        return
    out("Result:")
    for kind in ("copy", "update", "new", "delete", "keep-removed", "skip", "same", "link"):
        n = len(plan.of(kind))
        if n:
            out("  %s %d file(s)" % (verbs[kind][1], n))


def parse_args(argv: List[str]) -> Dict[str, Any]:
    opts: Dict[str, Any] = {"project": None, "dry": False, "update": False, "uninstall": False, "interpreter": None,
                            "hooks": False, "accept": False, "mine": False, "skip_selftest": False}
    flags = {"--dry-run": "dry", "--update": "update", "--uninstall": "uninstall", "--enable-hooks": "hooks",
             "--accept-existing": "accept", "--yes-this-is-my-project": "mine", "--skip-selftest": "skip_selftest"}
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in flags:
            opts[flags[arg]] = True
        elif arg == "--interpreter":
            if i + 1 >= len(argv):
                raise Usage("--interpreter needs a name")
            opts["interpreter"] = argv[i + 1]
            i += 1
        elif arg.startswith("--interpreter="):
            opts["interpreter"] = arg.split("=", 1)[1]
        elif arg in ("-h", "--help"):
            raise Usage("")
        elif arg.startswith("-"):
            raise Usage("unknown option %s" % arg[:40])
        elif opts["project"] is None:
            opts["project"] = arg
        else:
            raise Usage("only one project folder can be given (nothing was written). If the folder name has a space, put the whole path in quotes")
        i += 1
    if opts["project"] is None:
        raise Usage("")
    if opts["update"] and opts["uninstall"]:
        raise Usage("--update and --uninstall cannot be used together")
    return opts


# --------------------------------------------------------------------------- uninstall

def uninstall(doctor: Dict[str, Any], target: str, tclaude: str, dry: bool) -> int:
    version, files, bad = doctor["read_manifest"](os.path.join(tclaude, "MANIFEST.txt"))
    if version is None or not files:
        out("There is no MANIFEST.txt in %s, so I cannot tell which files are the tutor's." % os.path.join(target, ".claude"))
        out("Nothing was removed.")
        return 1
    warnings = 0
    removed: List[str] = []
    edited: List[str] = []
    keep_gitignore = os.path.isdir(os.path.join(tclaude, "agent-memory"))
    for rel in sorted(files):
        if not safe_rel(rel) or rel == "settings.json" or doctor["is_excluded"](rel):
            continue
        path = os.path.join(tclaude, *rel.split("/"))
        if not os.path.lexists(path):
            continue
        if doctor["is_link"](path) or not dest_ok(doctor, tclaude, rel):
            out("  kept .claude/%s (it is a link)" % rel)
            warnings += 1
            continue
        if rel == ".gitignore" and keep_gitignore:
            out("  kept .claude/.gitignore (it keeps your notes out of Git)")
            continue
        if doctor["sha256_file"](path) == files[rel]:
            removed.append(rel)
        else:
            edited.append(rel)
    for rel in removed:
        out("  %s .claude/%s" % ("would delete" if dry else "deleting", rel))
        if not dry:
            try:
                os.remove(os.path.join(tclaude, *rel.split("/")))
            except OSError:
                out("    could not delete it")
                warnings += 1
    for rel in edited:
        out("  kept .claude/%s (you changed it)" % rel)
    if edited:
        warnings += 1
    # settings.json: only the tutor's hook entries go; the file stays
    path = os.path.join(tclaude, "settings.json")
    settings, why = doctor["load_settings"](path)
    if settings is not None and isinstance(settings.get("hooks"), dict):
        cleaned, count = doctor["remove_our_hooks"](settings["hooks"])
        if count:
            out("  %s %d tutor hook entr%s from .claude/settings.json (the file stays)" % ("would remove" if dry else "removing", count, "y" if count == 1 else "ies"))
            if not dry:
                new = copy.deepcopy(settings)
                if cleaned:
                    new["hooks"] = cleaned
                else:
                    del new["hooks"]
                if doctor["backup_settings"](path) and doctor["write_text_file"](path, doctor["dump_settings"](new)):
                    out("  A copy of the old file is in .claude/settings.json.tutor-backup")
                else:
                    out("  could not update settings.json")
                    warnings += 1
    elif settings is None and why not in ("missing",):
        out("  settings.json is not valid JSON (%s), so I did not touch it." % why)
        warnings += 1
    out("  .claude/settings.json is kept. Remove the tutor's other lines by hand if you want them gone.")
    if not dry:
        if not edited:
            try:
                os.remove(os.path.join(tclaude, "MANIFEST.txt"))
            except OSError:
                pass
        prune_empty_dirs(doctor, tclaude)
    out("Your notes in .claude/agent-memory were not touched." if os.path.isdir(os.path.join(tclaude, "agent-memory")) else "Done.")
    return 1 if warnings else 0


# --------------------------------------------------------------------------- main

def main(argv: Optional[List[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        opts = parse_args(args)
    except Usage as exc:
        if str(exc):
            out("I did not understand the command line: %s." % exc)
        out(USAGE)
        return 0 if (not str(exc) and args and args[0] in ("-h", "--help")) else 1
    try:
        doctor = load_doctor()
    except Exception as exc:
        out("tools/doctor.py is missing or broken (%s). The kit is incomplete; copy it again." % type(exc).__name__)
        return 1
    home = home_folder()
    target = os.path.abspath(os.path.expanduser(opts["project"]))
    why = refusal_for(target, home, TEMPLATE_ROOT, SRC)
    if why:
        out("Refused: %s" % why)
        out("Folder: %s" % target)
        return 2
    if os.path.lexists(target) and not os.path.isdir(target):
        out("Refused: %s is a file, not a folder. Give the folder of your project." % target)
        return 2
    if not os.path.isdir(target):
        # never create a folder silently: the learner names it and runs again
        out("The folder %s does not exist yet. Create it first (give it a name), then run this command again." % target)
        return 2
    tclaude = os.path.join(target, ".claude")
    if os.path.lexists(tclaude) and (doctor["is_link"](tclaude) or not os.path.isdir(tclaude)):
        out("Refused: %s is a link or not a folder. I never write through links." % tclaude)
        return 2
    if not opts["mine"] and not has_marker(target) and not is_new_project(target) and not opts["uninstall"]:
        out("Refused: this folder has no project file (like .git, package.json, README or index.html).")
        out("If this is the right folder, run again with --yes-this-is-my-project.")
        return 2
    warnings: List[str] = []
    for text in (wide_folder_warning(target, home), synced_warning(target)):
        if text:
            warnings.append(text)
    out("Tutor kit %s -> %s" % ((doctor["read_text"](os.path.join(SRC, "VERSION"), 100) or "").strip() or "unknown", target))
    if opts["dry"]:
        out("Dry run: nothing will be written.")
    if opts["uninstall"]:
        return uninstall(doctor, target, tclaude, opts["dry"])

    # 1. what can already run code in this project?
    plan = Plan()
    plan.warnings.extend(warnings)
    rels, src_manifest = source_files(doctor, plan)
    longest = max([len(r) for r in rels] or [0])
    if len(tclaude) + 1 + longest > 240:
        plan.warnings.append("The path of this folder is long (%d characters). Some kit files would have paths over 240 characters, "
                             "which Windows may refuse. Use a shorter folder path." % len(target))
    audit = doctor["audit_scan"](target, SRC, src_manifest)
    items = audit["items"]
    if items:
        out("Audit: %d thing(s) in this project can run code or change safety rules. They are not from the tutor kit." % len(items))
    else:
        out("Audit: nothing in this project can run code by itself, apart from the tutor kit.")
    for item in items[:40]:
        out("  - %s: %s" % (doctor["safe_text"](item["path"], 100), item["reason"]))
    if len(items) > 40:
        out("  ... and %d more." % (len(items) - 40))
    for note in audit["notes"]:
        out("  note: " + doctor["safe_text"](note, 160))
    if items and not opts["accept"]:
        out("Refused: these items are not from the tutor. Look at them first.")
        out("If you know them and want to go on, run again with --accept-existing.")
        return 2

    # 2. plan
    build_plan(doctor, tclaude, rels, opts["update"], plan)
    settings_plan = plan_settings(doctor, tclaude, plan, opts["hooks"], opts["interpreter"])
    for note in plan.notes:
        out("Note: " + note)
    if opts["dry"]:
        print_plan(plan, True)
        for text in plan.warnings:
            out("Warning: " + text)
        out("Dry run finished. Nothing was written.")
        return 1 if plan.warnings else 0

    # 3. copy (everything except settings.json and MANIFEST.txt first)
    failed = 0
    for kind, rel, _ in list(plan.actions):
        if kind in ("copy", "update", "new"):
            s = os.path.join(SRC, *rel.split("/"))
            d = os.path.join(tclaude, *rel.split("/")) + (".new" if kind == "new" else "")
            if not copy_verified(doctor, s, d):
                failed += 1
                plan.warnings.append("Could not copy %s correctly." % rel)
        elif kind == "delete":
            try:
                os.remove(os.path.join(tclaude, *rel.split("/")))
            except OSError:
                plan.warnings.append("Could not delete %s." % rel)
    prune_empty_dirs(doctor, tclaude)
    # 4. .claude/.gitignore
    os.makedirs(tclaude, exist_ok=True)
    status, notes = doctor["repair_gitignore"](os.path.join(tclaude, ".gitignore"), os.path.join(SRC, ".gitignore"))
    if status == "failed":
        plan.warnings.append(".claude/.gitignore could not be written. Private notes may not be protected.")
    elif status in ("created", "repaired"):
        out("  .claude/.gitignore: %s" % "; ".join(notes))
    # 5. settings.json last
    if settings_plan is not None and settings_plan["changed"]:
        spath = os.path.join(tclaude, "settings.json")
        ok = doctor["backup_settings"](spath) and doctor["write_text_file"](spath, doctor["dump_settings"](settings_plan["new"]))
        again, _ = doctor["load_settings"](spath)
        if ok and again == settings_plan["new"]:
            out("  .claude/settings.json merged%s." % (" (the old file is in settings.json.tutor-backup)" if settings_plan["existed"] else ""))
        else:
            plan.warnings.append("settings.json could not be written correctly.")
    # 6. manifest last
    sm = os.path.join(SRC, "MANIFEST.txt")
    dm = os.path.join(tclaude, "MANIFEST.txt")
    if os.path.isfile(sm) and (not os.path.lexists(dm) or opts["update"]):
        if not copy_verified(doctor, sm, dm):
            plan.warnings.append("Could not copy MANIFEST.txt.")
    print_plan(plan, False)
    # 7. self-test
    selftest_ok: Optional[bool] = None
    if opts["skip_selftest"]:
        out("The quick self-test was skipped (--skip-selftest).")
    else:
        selftest_ok, lines = run_selftest(tclaude)
        for ln in lines:
            out("  " + doctor["safe_text"](ln, 160))
        if selftest_ok is False:
            plan.warnings.append("The quick self-test failed. The files are copied, but check the lines above.")
    for text in plan.warnings:
        out("Warning: " + text)
    out("")
    out("Next steps:")
    for line in NEXT_STEPS:
        out("  " + line)
    code = 1 if (plan.warnings or failed) else 0
    out("Finished with %d warning(s)." % len(plan.warnings) if code else "Finished.")
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        out("Stopped.")
        sys.exit(1)
