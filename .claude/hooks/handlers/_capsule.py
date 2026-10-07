"""_capsule.py - the pieces of the SessionStart capsule (not a hook itself).

What: one small function per line or block of the state capsule: Python, surface, settings, Git, notes
excerpt, decision titles, profile, skills. Why: keeps session_start.py short and each piece testable.
Safety: text that came from files, Git or the profile is neutralized and fenced here.
How it fails safely: the caller wraps each piece; a missing file gives None or an empty string.
Who calls it: session_start.
"""
from __future__ import annotations

import os
import sys

from lib import clock, config, fsio, gitq, paths, untrusted

sys.dont_write_bytecode = True

SKILLS = ("tutor", "tutor-setup", "learn", "progress", "explain", "think-first", "new-project", "fix-it",
          "save-point", "before-push", "git-rescue")


def python_line():
    name = os.path.basename(sys.executable or "python3").lower()
    if name.endswith(".exe"):
        name = name[:-4]
    cmd = "python3" if name.startswith("python3") else ("python" if name.startswith("python") else "python3")
    v = sys.version_info
    return "Python: %s %d.%d.%d" % (cmd, v[0], v[1], v[2])


def surface_line():
    name, kind = config.surface(os.environ.get("CLAUDE_CODE_ENTRYPOINT"))
    extra = {"desktop": " (say mode selector and terminal pane; never Shift+Tab or `!`)",
             "unknown": " (ask once, only when a how-to depends on it)"}.get(kind, "")
    return "Surface: %s%s" % (name, extra)


def settings_line():
    path = os.path.join(paths.claude_dir(), "settings.json")
    if not os.path.isfile(path):
        return "Settings: .claude/settings.json is missing"
    data = fsio.read_json(path, None)
    if not isinstance(data, dict):
        return "Settings: .claude/settings.json is not valid JSON (Claude Code ignores the whole file)"
    if data.get("outputStyle") != "tutor":
        return "Settings: outputStyle is not tutor, so the tutor style is not active"
    if not os.path.isfile(os.path.join(paths.product_dir(), "output-styles", "tutor.md")):
        return "Settings: the tutor output style file is missing"
    return "Settings: ok"


def error_count():
    text = fsio.read_text(paths.sub("state", "hook-errors.log"), "", 220000)
    cutoff = clock.add_days(clock.today(), -7) or ""
    return sum(1 for ln in text.split("\n") if len(ln) > 10 and ln[:10] >= cutoff) if text else 0


def git_facts(root, want_ignored):
    if not gitq.is_repo(root):
        return None
    jobs = {"status": lambda: gitq.status_summary(root), "push": lambda: gitq.days_since_push(root),
            "ignore": lambda: gitq.secrets_ignored(root)}
    if want_ignored:
        jobs["ignored"] = lambda: gitq.ignored_top_level(root)
    return gitq.parallel(jobs)


def git_line(facts):
    if facts is None:
        return "Git: this folder is not a Git repository yet (no save points, nothing backed up)"
    s = facts.get("status")
    if not s:
        return "Git: repository found but Git did not answer"
    parts = ["branch " + untrusted.fence("branch", untrusted.neutralize(s.get("branch") or "(unknown)", 40)),
             "%d change%s not saved" % (s["changed"], "" if s["changed"] == 1 else "s") if s["changed"] else "no unsaved changes"]
    days = facts.get("push")
    if s.get("upstream") and days is not None:
        parts.append("last push %d days ago" % days if days else "pushed today")
    else:
        parts.append("never pushed (nothing is backed up outside this computer)")
    return "Git: " + ", ".join(parts)


def now_block(max_lines):
    path = paths.sub("now.md")
    text = fsio.read_text(path, "", 6000)
    lines = [untrusted.neutralize(ln, 160) for ln in text.split("\n")[:max_lines + 6] if ln.strip()][:max_lines]
    if not lines:
        return None
    try:
        import datetime
        mtime = datetime.datetime.fromtimestamp(os.path.getmtime(path)).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError):
        mtime = "?"
    head = "Notes written earlier (may contain text copied from untrusted files), now.md updated %s:" % mtime
    return head + "\n" + untrusted.fence("now.md", "\n".join(lines))


def adr_block():
    folder = os.path.join(paths.project_root(), "docs", "decisions")
    if not os.path.isdir(folder):
        return None
    names = sorted((n for n in os.listdir(folder) if n.lower().endswith(".md") and n.lower() != "readme.md"),
                   reverse=True)[:3]
    titles = []
    for n in names:
        first = ""
        for ln in fsio.read_text(os.path.join(folder, n), "", 600).split("\n"):
            if ln.startswith("#"):
                first = ln.lstrip("# ").strip()
                break
        titles.append(untrusted.neutralize(first or n, 80))
    return ("Newest decisions: " + untrusted.fence("decisions", " | ".join(titles))) if titles else None


def profile_lines(profile, warnings):
    free = [k + ": " + untrusted.neutralize(profile[k], 40) for k in ("language", "call_me", "learn_first") if profile.get(k)]
    out = ["Profile: onboarded: %s; level: %s; teaching: %s; comments: %s; tree: %s%s." % (
        profile["onboarded"], profile["level"], profile["teaching"], profile["comments"], profile["tree"],
        "; chat_copy: on" if profile["chat_copy"] == "on" else "")]
    out.append(untrusted.fence("profile", "; ".join(free)) if free else
               "Profile language: not set (reply in the language of the learner's first message).")
    if warnings:
        out.append("Profile problems: " + "; ".join(warnings[:3]))
    return out


def skills_line():
    present = [s for s in SKILLS if os.path.isfile(os.path.join(paths.product_dir(), "skills", s, "SKILL.md"))]
    return ("Skills (start by name or in plain words): " + ", ".join(present) + ".") if present else None
