"""test_mock_cli.py - scenarios M-1 .. M-29: the REAL Claude Code CLI against a MOCK Anthropic API (SPEC 15, layer 3).

What: each scenario starts `claude -p` in a scratch copy of the product, with a fake model that can only
echo text or make scripted tool calls, and checks what Claude Code did: what it loaded and sent to the model,
which hooks ran and with what exit code, which tool calls were denied, asked or allowed.
Why: a hook script can be perfect and still never run, or its text can be dropped on the way to the model.
These tests prove delivery, wording, ordering and exit codes. They do NOT prove how a real model behaves.
How it fails safely: every scenario works in its own temp folders (removed at the end), a private config
folder and a placeholder key; nothing touches the real ~/.claude or any account. If `claude` is not on PATH
the whole file prints SKIP and exits 0. Every scripted command is harmless if the guard fails to stop it.
Run:  python test_mock_cli.py [--list] [--only M-3,M-12] [--product DIR] [--json FILE] [-v]
Exit code: 1 when any scenario FAILs or the command line is wrong, else 0 (SKIP counts as 0). Python 3.9 syntax, standard library only.
"""
from __future__ import annotations

import json
import os
import random
import re
import string
import subprocess
import sys
import time
import traceback
import uuid
from typing import Any, Callable, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "harness"))

import mock_api  # noqa: E402
import mockcli as m  # noqa: E402

MODEL_200K = "claude-sonnet-4-5"        # a model whose context window is 200,000 tokens
MIN_VERSION = (2, 1, 288)
SIX_MODES = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SubagentStart")

PRODUCT = ""
EVIDENCE: List[str] = []


class Skip(Exception):
    """Raised by a scenario that cannot run honestly; the message is the reason."""


class Scratch(object):
    """Collects the projects a scenario makes so the runner can remove them, even after an error."""

    def __init__(self) -> None:
        self.projects: List[m.ProjectPath] = []

    def project(self, **kw: Any) -> m.ProjectPath:
        proj = m.make_project(PRODUCT, **kw)
        self.projects.append(proj)
        return proj

    def cleanup(self) -> None:
        for proj in self.projects:
            m.cleanup_project(proj)
        self.projects = []


S = Scratch()
TESTS: Dict[int, Tuple[str, Callable[[], List[str]]]] = {}


def scenario(number: int) -> Callable[[Callable[[], List[str]]], Callable[[], List[str]]]:
    def deco(fn: Callable[[], List[str]]) -> Callable[[], List[str]]:
        doc = (fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else fn.__name__
        TESTS[number] = (doc, fn)
        return fn
    return deco


def ev(text: str) -> None:
    """Record one evidence line for the report (what was seen, exactly)."""
    EVIDENCE.append(text)


def clip(text: Any, n: int = 160) -> str:
    return " ".join(str(text).split())[:n]


# --------------------------------------------------------------------------- shared helpers

def run(proj: str, prompt: str, **kw: Any) -> m.Run:
    r = m.run_claude(proj, prompt, **kw)
    return r


def sane(r: m.Run, label: str, f: List[str]) -> bool:
    """False (and a failure line) when the run itself is broken: no result, mock not reached, bad exit."""
    ok = True
    blockers = [e for e in r.hook_responses() if e.get("exit_code") == 2]
    if blockers and not r.model_requests:
        f.append("%s: hook %s exited 2 and blocked the prompt: %s" % (label, blockers[0].get("hook_name"), clip(blockers[0].get("stderr") or (r.result or {}).get("result"), 200)))
        ok = False
    elif r.api_error or not r.model_requests:
        f.append("%s: the model API was not reached (stderr: %s)" % (label, clip(r.stderr, 200)))
        ok = False
    elif r.returncode != 0:
        f.append("%s: claude exit code %s (stderr: %s)" % (label, r.returncode, clip(r.stderr, 200)))
        ok = False
    return ok


def listing_of(r: m.Run, index: int = 0) -> List[Tuple[str, str]]:
    """[(skill name, description)] from the skill list the model got; a skill cut to its name alone has ''."""
    block = r.find_text("The following skills are available", index)
    i = block.find("The following skills are available")
    out = []
    for line in block[i:].splitlines() if i >= 0 else []:
        mt = re.match(r"^- ([A-Za-z0-9_:\-]+)(?:: (.*))?$", line)
        if mt:
            out.append((mt.group(1), mt.group(2) or ""))
    return out


CAPSULE_RE = re.compile(r"SessionStart(?::\w+)? hook (?:success|additional context):\s*=== Tutor session state ===")


def capsule_delivered(text: str) -> bool:
    """True when the hook-made capsule (not just the words in CLAUDE.md) is in the text the model got."""
    return bool(CAPSULE_RE.search(text))


def classify(r: m.Run) -> List[Dict[str, Any]]:
    """One row per tool call: kind = deny (hook exit 2) | ask (hook ask) | floor (settings rule) | prompt (would ask a
    human) | error | pass, plus the text the model got back."""
    asked = {e.get("tool_use_id"): e for e in r.events if e.get("subtype") == "permission_denied"}
    denied = {d.get("tool_use_id") for d in r.denials}
    results = {t["tool_use_id"]: t for t in r.tool_results}
    rows = []
    for use in r.tool_uses:
        res = results.get(use["id"], {})
        text = str(res.get("text", ""))
        if use["id"] in asked and asked[use["id"]].get("decision_reason_type") == "hook":
            kind = "ask"
        elif re.match(r"^PreToolUse:\w+ hook error", text):
            kind = "deny"
        elif text.startswith("Stopped on purpose"):
            kind = "ask"
        elif "has been denied" in text or "denied by your permission settings" in text or "covered by a Read deny rule" in text:
            kind = "floor"
        elif use["id"] in denied or "requested permissions" in text or "needs approval" in text or "requires approval" in text:
            kind = "prompt"
        elif res.get("is_error"):
            kind = "error"
        else:
            kind = "pass"
        rows.append({"id": use["id"], "name": use["name"], "input": use["input"], "kind": kind, "text": text})
    return rows


def tools_prompt(calls: List[Dict[str, Any]], words: str = "") -> str:
    """A prompt that makes the mock call several tools in ONE assistant message."""
    return (words + "\n" if words else "") + "TOOLS: " + json.dumps(calls)


def bash_calls(commands: List[str]) -> List[Dict[str, Any]]:
    return [{"name": "Bash", "input": {"command": c, "description": "scripted"}} for c in commands]


def expect_kinds(f: List[str], rows: List[Dict[str, Any]], expected: List[Tuple[str, str]], label: str,
                 accept: Optional[Dict[str, Tuple[str, ...]]] = None) -> None:
    """Compare each row with its expected kind (deny | ask | ask-or-rule | pass | stop = deny or ask | any)."""
    accept = accept or {}
    for row, (want, note) in zip(rows, expected):
        shown = clip(row["input"].get("command") or row["input"].get("file_path") or row["input"], 70)
        ev("%s | %-5s | %-5s | %s" % (label, row["kind"], want, shown))
        ok = {"deny": row["kind"] == "deny", "ask": row["kind"] == "ask", "pass": row["kind"] == "pass",
              "stop": row["kind"] in ("deny", "ask"), "any": True,
              # "ask-or-rule": the command did not run and a person is asked: by the hook (teaching text reaches the model)
              # or by an ask rule of the permission floor (generic text; the floor answers first, decision 2026-10-07)
              "ask-or-rule": row["kind"] in ("ask", "prompt")}.get(want, False)
        if not ok and want in ("ask", "stop") and row["kind"] == "prompt":
            f.append("%s: a static ask rule of settings.json answered first, so the hook's teaching reason never reached the model (expected the hook's ask) for %s -> %s" % (
                label, shown, clip(row["text"], 100)))
        elif not ok:
            f.append("%s: expected %s, got %s for %s -> %s" % (label, want, row["kind"], shown, clip(row["text"], 120)))
    if len(rows) != len(expected):
        f.append("%s: expected %d tool calls, saw %d" % (label, len(expected), len(rows)))


def fake_secret() -> str:
    """A secret-shaped value built at run time from fragments (never stored as a literal)."""
    rnd = random.SystemRandom()
    body = "".join(rnd.choice(string.ascii_letters + string.digits) for _ in range(44))
    return "sk-" + "ant-" + "api03-" + body


def hook_durations(proj: str) -> Dict[str, List[int]]:
    """durationMs of hook attachments in the session transcripts of the private config folder (only hooks that
    printed text leave such an attachment; silent hooks do not, so this is a sample, not a full count)."""
    import glob
    found: Dict[str, List[int]] = {}
    for path in glob.glob(os.path.join(m.config_dir_for(proj), "projects", "**", "*.jsonl"), recursive=True):
        try:
            with open(path, encoding="utf-8") as fh:
                for line in fh:
                    if '"durationMs"' not in line or '"attachment"' not in line:
                        continue
                    try:
                        att = json.loads(line).get("attachment") or {}
                    except ValueError:
                        continue
                    if isinstance(att, dict) and isinstance(att.get("durationMs"), (int, float)):
                        found.setdefault(str(att.get("hookEvent") or att.get("type")), []).append(int(att["durationMs"]))
        except OSError:
            continue
    return found


def product_rules() -> List[str]:
    root = os.path.join(PRODUCT, "rules")
    return sorted(x for x in os.listdir(root) if x.endswith(".md")) if os.path.isdir(root) else []


def read_text(path: str) -> str:
    with open(path, encoding="utf-8-sig") as f:
        return f.read()


def no_settings(proj: m.ProjectPath, f: List[str], what: str) -> bool:
    """True (and one failure line) when the product has no settings.json, so a floor test cannot judge it."""
    if proj.settings_source != "product":
        f.append("MISSING settings.json in the product (%s cannot be judged); owner: settings" % what)
        return True
    return False


# --------------------------------------------------------------------------- context delivery

@scenario(1)
def m01() -> List[str]:
    """CLAUDE.md reaches the model whole, with its HTML comment stripped, on both prompt families."""
    f: List[str] = []
    proj = S.project()
    text = read_text(os.path.join(PRODUCT, "CLAUDE.md"))
    visible = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    lines = [ln.strip() for ln in visible.splitlines() if ln.strip()]
    for label, model in (("default model", None), ("200K model", MODEL_200K)):
        r = run(proj, "hello", model=model)
        if not sane(r, label, f):
            continue
        sent = r.first_user_text(0)
        if "Developer Tutor, installed in this project" not in sent:
            f.append("%s: heading 'Developer Tutor, installed in this project' not in the first user message" % label)
        if not re.search(r"Contents of [^\n]*\.claude[\\/]CLAUDE\.md", sent):
            f.append("%s: no 'Contents of ...\\.claude\\CLAUDE.md' block" % label)
        missing = [ln for ln in lines if ln not in sent]
        if missing:
            f.append("%s: %d CLAUDE.md lines were not delivered, first: %s" % (label, len(missing), clip(missing[0], 80)))
        if "Maintainer note" in sent:
            f.append("%s: the HTML comment of CLAUDE.md was delivered (it should be stripped)" % label)
        ev("%s: CLAUDE.md delivered, %d of %d visible lines present, model %s, window %d" % (label, len(lines) - len(missing), len(lines), (r.init or {}).get("model"), r.context_window))
    return f


@scenario(2)
def m02() -> List[str]:
    """Output style 'tutor' is in the model's context; keep-coding-instructions keeps the coding section."""
    f: List[str] = []
    proj = S.project()
    style = read_text(os.path.join(PRODUCT, "output-styles", "tutor.md"))
    if proj.settings_source != "product":
        f.append("MISSING settings.json in the product: outputStyle cannot come from the product (owner: settings)")
        ev("fallback settings.json {outputStyle: tutor} used for the remaining checks")
    r = run(proj, "hello")
    if sane(r, "default model", f):
        block = r.find_text("# Output Style: tutor")
        if not block:
            f.append("default model: '# Output Style: tutor' is not in the model's context")
        else:
            body_headings = re.findall(r"^## .*$", style, re.M)
            missing = [h for h in body_headings if h not in block]
            if missing:
                f.append("default model: style headings missing from the delivered style: %s" % missing[:3])
            ev("default model: '# Output Style: tutor' present, %d of %d style headings delivered" % (len(body_headings) - len(missing), len(body_headings)))
        top = mock_api.system_text(r.model_requests[0])
        if 'according to your "Output Style"' not in top:
            f.append("default model: the base prompt does not say it follows the Output Style (style not active)")
    kept = run(proj, "hello", model=MODEL_200K)
    if sane(kept, "200K model", f):
        top = mock_api.system_text(kept.model_requests[0])
        has_coding = "# Doing tasks" in top
        ev("200K model keep-coding-instructions: true -> '# Doing tasks' in base prompt: %s (system %d chars)" % (has_coding, len(top)))
        if "keep-coding-instructions: true" not in style:
            f.append("the style file does not say keep-coding-instructions: true")
        elif not has_coding:
            f.append("200K model: keep-coding-instructions is true but the coding section '# Doing tasks' is not in the base prompt")
    # control: with the flag off the coding section must disappear, or this test could not fail
    ctl = S.project()
    path = os.path.join(ctl, ".claude", "output-styles", "tutor.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(style.replace("keep-coding-instructions: true", "keep-coding-instructions: false"))
    off = run(ctl, "hello", model=MODEL_200K)
    if sane(off, "control", f):
        gone = "# Doing tasks" not in mock_api.system_text(off.model_requests[0])
        ev("control (flag false): coding section removed = %s" % gone)
        if not gone:
            f.append("control: with keep-coding-instructions false the coding section is still there, so the check proves nothing")
    return f


@scenario(3)
def m03() -> List[str]:
    """All 6 rule files are loaded into the first user message (default model and 200K model)."""
    f: List[str] = []
    rules = product_rules()
    if len(rules) != 6:
        f.append("the product has %d rule files, SPEC says 6: %s" % (len(rules), rules))
    proj = S.project()
    for label, model in (("default model", None), ("200K model", MODEL_200K)):
        r = run(proj, "hello", model=model)
        if not sane(r, label, f):
            continue
        sent = r.first_user_text(0)
        for name in rules:
            body = [ln.strip() for ln in re.sub(r"<!--.*?-->", "", read_text(os.path.join(PRODUCT, "rules", name)), flags=re.S).splitlines() if ln.strip()]
            if not re.search(r"Contents of [^\n]*rules[\\/]%s" % re.escape(name), sent):
                f.append("%s: rule %s has no 'Contents of' block" % (label, name))
            elif body and body[0] not in sent:
                f.append("%s: rule %s first line missing" % (label, name))
        ev("%s: %d rule blocks delivered: %s" % (label, len([n for n in rules if re.search(r'rules[\\/]%s' % re.escape(n), sent)]), ", ".join(n[:-3] for n in rules)))
    return f


@scenario(4)
def m04() -> List[str]:
    """All 11 skills are listed with their full descriptions under a 200K window (and the default model)."""
    f: List[str] = []
    skills = m.product_skills(PRODUCT)
    if len(skills) != 11:
        f.append("the product has %d skills, SPEC says 11: %s" % (len(skills), [s[0] for s in skills]))
    proj = S.project()
    for label, model in (("200K model", MODEL_200K), ("default model", None)):
        r = run(proj, "hello", model=model)
        if not sane(r, label, f):
            continue
        listed = dict(listing_of(r))
        full, short, bare, missing = 0, [], [], []
        for name, desc in skills:
            if name not in listed:
                missing.append(name)
            elif not listed[name].strip():
                bare.append(name)
            elif listed[name].strip() == desc.strip():
                full += 1
            else:
                short.append("%s(%d/%d chars)" % (name, len(listed[name]), len(desc)))
        total = len(r.find_text("The following skills are available"))
        if label == "200K model":
            for line in r.find_text("The following skills are available").splitlines():
                if line.startswith("- "):
                    ev("listing line (%d chars): %s" % (len(line), clip(line, 110)))
        others = [n for n in listed if n not in [s[0] for s in skills]]
        ev("%s (contextWindow=%d, model=%s): of %d product skills %d listed with the full description, %d name only (no description), %d shortened, %d not listed; %d other (bundled) skills listed; listing block %d chars" % (
            label, r.context_window, (r.init or {}).get("model"), len(skills), full, len(bare), len(short), len(missing), len(others), total))
        if bare:
            ev("%s: name-only skills (the model sees no trigger words for them): %s" % (label, ", ".join(bare)))
        if missing:
            f.append("%s: skills not listed: %s" % (label, missing))
        if bare:
            f.append("%s: Claude Code listed these skills by name only, without their description: %s (listing budget used up by %d other skills)" % (label, bare, len(others)))
        if short:
            f.append("%s: skill descriptions shortened by Claude Code: %s" % (label, short))
        if label == "200K model" and r.context_window != 200000:
            f.append("the model chosen for the 200K check reports a window of %d tokens, not 200000" % r.context_window)
    return f


@scenario(5)
def m05() -> List[str]:
    """Both agents are listed to the model with description and read-only tools, and appear in the init event."""
    f: List[str] = []
    agents = m.product_agents(PRODUCT)
    proj = S.project()
    r = run(proj, "hello")
    if not sane(r, "run", f):
        return f
    block = r.find_text("Available agent types")
    init_agents = (r.init or {}).get("agents") or []
    for name, desc in agents:
        mt = re.search(r"^- %s: (.*?) \(Tools: ([^)]*)\)\s*$" % re.escape(name), block, re.M)
        if not mt:
            f.append("agent %s is not in the 'Available agent types' list" % name)
            continue
        if mt.group(1).strip() != desc.strip():
            f.append("agent %s: listed description differs from the file" % name)
        if mt.group(2).strip() != "Read, Grep, Glob":
            f.append("agent %s: tools are '%s', expected 'Read, Grep, Glob'" % (name, mt.group(2)))
        if name not in init_agents:
            f.append("agent %s is not in init.agents" % name)
        ev("agent %s listed, tools: %s" % (name, mt.group(2) if mt else "?"))
    if len(agents) != 2:
        f.append("the product has %d agents, SPEC says 2" % len(agents))
    return f


@scenario(6)
def m06() -> List[str]:
    """The init event shows the wiring (style, skills, agents), the CLI version, and the placeholder key in use."""
    f: List[str] = []
    proj = S.project()
    r = run(proj, "hello")
    if not sane(r, "run", f):
        return f
    init = r.init or {}
    version = str(init.get("claude_code_version") or "")
    ev("claude_code_version=%s output_style=%s apiKeySource=%s permissionMode=%s" % (version, init.get("output_style"), init.get("apiKeySource"), init.get("permissionMode")))
    try:
        parts = tuple(int(x) for x in version.split(".")[:3])
    except ValueError:
        parts = (0, 0, 0)
    if parts < MIN_VERSION:
        f.append("Claude Code %s is older than the tested minimum %s" % (version, ".".join(map(str, MIN_VERSION))))
    if init.get("output_style") != "tutor":
        f.append("init.output_style is %r, expected 'tutor'" % init.get("output_style"))
    names = [s[0] for s in m.product_skills(PRODUCT)]
    absent = [n for n in names if n not in (init.get("skills") or [])]
    if absent:
        f.append("skills missing from init.skills: %s" % absent)
    if init.get("apiKeySource") != "ANTHROPIC_API_KEY":
        f.append("apiKeySource is %r: the run did not use the placeholder key" % init.get("apiKeySource"))
    if not all(rec.get("has_key_header") for rec in r.request_records):
        f.append("a request carried no key header (unexpected auth path)")
    return f


# --------------------------------------------------------------------------- hooks on

@scenario(7)
def m07() -> List[str]:
    """Hooks ON: state capsule in the FIRST request, per-message line in the SECOND request of a resumed session."""
    f: List[str] = []
    proj = S.project(hooks=True)
    sid = str(uuid.uuid4())
    one = run(proj, "hello, I want to make a recipe page", session_id=sid)
    if not sane(one, "turn 1", f):
        return f
    start = one.hook_responses("SessionStart")
    if not start or start[0].get("exit_code") != 0:
        f.append("turn 1: SessionStart hook did not exit 0: %s" % one.hook_summary())
    capsule = (start[0].get("stdout") if start else "") or ""
    if "=== Tutor session state ===" not in capsule:
        f.append("turn 1: SessionStart stdout has no '=== Tutor session state ===' canary")
    if not capsule_delivered(one.request_text(0)):
        f.append("turn 1: the hook-made capsule is not in the first request to the model")
    if len(capsule) > 3000:
        f.append("turn 1: the capsule is %d chars, the cap is 3000" % len(capsule))
    ev("turn 1 capsule: %d chars; first line: %s" % (len(capsule), clip(capsule.splitlines()[0] if capsule else "", 60)))
    up1 = one.hook_responses("UserPromptSubmit")
    two = run(proj, "second message: what next?", resume=sid)
    if not sane(two, "turn 2", f):
        return f
    resumed = two.hook_responses("SessionStart")
    rtext = (resumed[0].get("stdout") if resumed else "") or ""
    ev("turn 2 SessionStart(resume): %d chars; has canary: %s; hook_name %s" % (len(rtext), "=== Tutor session state ===" in rtext, resumed[0].get("hook_name") if resumed else None))
    if resumed and len(rtext) > 600:
        f.append("turn 2: the resume capsule is %d chars, the cap is 600" % len(rtext))
    if resumed and "=== Tutor session state ===" not in rtext:
        f.append("turn 2: the resume output has no canary")
    ups = two.hook_responses("UserPromptSubmit")
    line = (ups[0].get("stdout") if ups else "") or ""
    if not line.strip():
        f.append("turn 2: UserPromptSubmit printed nothing (expected the time line)")
    else:
        sent = two.request_text(0)
        if clip(line, 40) not in " ".join(sent.split()):
            f.append("turn 2: the UserPromptSubmit line is not in the request to the model")
        count = sent.count("UserPromptSubmit hook success:")
        ev("turn 2 UserPromptSubmit line (%d chars): %s | occurrences in request: %d (replayed turn 1 + turn 2)" % (len(line), clip(line, 110), count))
    if up1 and ups and (up1[0].get("stdout") or "") == line and "Last answer" not in line:
        ev("note: the per-message line of turn 2 equals turn 1 (no changed facts)")
    ev("hook durations seen by Claude Code (transcript, ms, informational): %s" % hook_durations(proj))
    return f


def check_six_modes(proj: m.ProjectPath, f: List[str], tag: str) -> None:
    """One session that triggers all six hook events; checks exit codes, stderr, output shapes and the helper text."""
    target = os.path.join(proj, "notes", tag + ".txt")
    calls = [{"name": "Bash", "input": {"command": "echo " + tag, "description": "scripted"}},
             {"name": "Write", "input": {"file_path": target, "content": tag + chr(10)}},
             {"name": "Agent", "input": {"description": "mock helper", "prompt": "say hi", "subagent_type": "general-purpose", "run_in_background": False}}]
    r = run(proj, tools_prompt(calls), permission_mode="acceptEdits", allowed_tools=["Bash", "Write", "Agent"], timeout=180)
    if not sane(r, tag, f):
        return
    seen = {}
    for e in r.hook_responses():
        event = str(e.get("hook_event"))
        seen.setdefault(event, []).append(e)
        out, err = str(e.get("stdout") or ""), str(e.get("stderr") or "")
        if e.get("exit_code") != 0:
            f.append("%s exit_code %s (stderr: %s)" % (e.get("hook_name"), e.get("exit_code"), clip(err, 150)))
        if err.strip():
            f.append("%s printed to stderr: %s" % (e.get("hook_name"), clip(err, 150)))
        if out.lstrip().startswith("{"):
            try:
                obj = json.loads(out)
                special = obj.get("hookSpecificOutput") or {}
                if special.get("hookEventName") not in (None, event):
                    f.append("%s: hookEventName %r does not match the event" % (e.get("hook_name"), special.get("hookEventName")))
                if "additionalContext" in obj:
                    f.append("%s: additionalContext at the top level is ignored by Claude Code" % e.get("hook_name"))
                if special.get("permissionDecision") == "allow":
                    f.append("%s: printed permissionDecision allow (auto-approves the call)" % e.get("hook_name"))
            except ValueError:
                f.append("%s: stdout starts with '{' but is not valid JSON" % e.get("hook_name"))
        if event == "Stop" and out.strip():
            f.append("Stop printed text (it must print nothing)")
        ev("%-24s exit=%s stdout=%d chars %s" % (e.get("hook_name"), e.get("exit_code"), len(out), clip(out, 70)))
    for event in SIX_MODES:
        if event not in seen:
            f.append("hook event %s did not run (events seen: %s)" % (event, sorted(seen)))
    if not os.path.isfile(target):
        f.append("the scripted Write did not create %s (hooks or permissions blocked it)" % target)
    helper = [b for b in r.requests if "cc_is_subagent=true" in mock_api.system_text(b)]
    if not helper:
        f.append("no request from the helper agent reached the mock (the Agent call did not run)")
    elif "The reader of your final report is a beginner" not in json.dumps(helper[0], ensure_ascii=False):
        f.append("the SubagentStart text did not reach the helper agent's request")
    else:
        ev("SubagentStart text reached the helper agent's own request: yes")


@scenario(8)
def m08() -> List[str]:
    """Hooks ON: all 6 hook modes fire through the real launcher with exit 0, empty stderr and valid output."""
    f: List[str] = []
    check_six_modes(S.project(hooks=True, git=True), f, "m8")
    return f


@scenario(9)
def m09() -> List[str]:
    """A missing hook script, handler or library never blocks (exit 0, or exit 1 with one line; never 2)."""
    f: List[str] = []
    variants = [
        ("dispatch.py missing", [os.path.join("hooks", "dispatch.py")], {"SessionStart": (0,), "UserPromptSubmit": (0,), "PreToolUse": (0,), "PostToolUse": (0,), "Stop": (0,)}),
        ("hooks folder missing", [os.path.join("hooks")], {"SessionStart": (0,), "UserPromptSubmit": (0,), "PreToolUse": (0,), "PostToolUse": (0,), "Stop": (0,)}),
        ("pre_tool.py missing", [os.path.join("hooks", "handlers", "pre_tool.py")], {"PreToolUse": (0,), "SessionStart": (0,), "UserPromptSubmit": (0,)}),
        ("lib folder missing", [os.path.join("hooks", "lib")], {"PreToolUse": (0,), "SessionStart": (1, 0), "UserPromptSubmit": (1, 0), "Stop": (1, 0)}),
    ]
    for label, moves, allowed in variants:
        proj = S.project(hooks=True)
        for rel in moves:
            src = os.path.join(proj, ".claude", rel)
            if os.path.exists(src):
                os.rename(src, src + ".moved")
        r = run(proj, "RUN: echo m9ok", allowed_tools=["Bash"])
        if not sane(r, label, f):
            continue
        codes = {}
        for e in r.hook_responses():
            codes.setdefault(str(e.get("hook_event")), []).append(e.get("exit_code"))
            if e.get("exit_code") == 2:
                f.append("%s: %s exited 2 (this blocks the user)" % (label, e.get("hook_name")))
        for event, ok_codes in allowed.items():
            for code in codes.get(event, []):
                if code not in ok_codes:
                    f.append("%s: %s exit code %s, allowed %s" % (label, event, code, ok_codes))
        if not any("m9ok" in t["text"] for t in r.tool_results):
            f.append("%s: the Bash command did not run or its output is missing: %s" % (label, [clip(t["text"], 60) for t in r.tool_results]))
        stderrs = sorted({clip(e.get("stderr"), 110) for e in r.hook_responses() if e.get("stderr")})
        ev("%s: exit codes %s; stderr lines: %s; prompt and tool reached the model: yes" % (label, {k: v for k, v in codes.items()}, stderrs or "none"))
    return f


@scenario(10)
def m10() -> List[str]:
    """Hooks ON but python3 not on PATH: records the exact hook error text; nothing blocks, session continues."""
    f: List[str] = []
    proj = S.project(hooks=True)
    bare = m.path_without(("python", "python3", "py"))
    r = run(proj, "RUN: echo m10ok", allowed_tools=["Bash"], path_env=bare)
    if not sane(r, "run", f):
        return f
    texts = {}
    for e in r.hook_responses():
        texts.setdefault(str(e.get("hook_name")), (e.get("exit_code"), clip(e.get("stderr"), 200), e.get("outcome")))
        if e.get("exit_code") == 2:
            f.append("%s exited 2: a missing Python must not block the user" % e.get("hook_name"))
        if e.get("exit_code") != 1:
            f.append("%s: expected the non-blocking exit code 1 for a missing interpreter, got %s" % (e.get("hook_name"), e.get("exit_code")))
    for name, (code, err, outcome) in sorted(texts.items()):
        ev("HOOK ERROR TEXT | %s | exit=%s outcome=%s | %s" % (name, code, outcome, err))
    ev("hook errors per prompt with one tool call: %d (every hook event of the turn)" % len(r.hook_responses()))
    if not any("m10ok" in t["text"] for t in r.tool_results):
        f.append("the Bash command did not run with hooks failing: %s" % [clip(t["text"], 80) for t in r.tool_results])
    if r.result and r.result.get("terminal_reason") != "completed":
        f.append("the turn did not complete: %s" % (r.result or {}).get("terminal_reason"))
    if capsule_delivered(r.all_request_text()):
        f.append("a hook-made capsule reached the model although Python was missing")
    return f


@scenario(25)
def m25() -> List[str]:
    """Hooks OFF (the shipped state) with PATH stripped of python/py: no hook error anywhere; text-only first hour."""
    f: List[str] = []
    proj = S.project(hooks=False)
    bare = m.path_without(("python", "python3", "py"))
    sid = str(uuid.uuid4())
    r1 = run(proj, "hello", path_env=bare, session_id=sid)
    first_file = os.path.join(proj, "docs", "index.html")
    calls = [{"name": "Write", "input": {"file_path": first_file, "content": "<h1>My recipes</h1>" + chr(10)}},
             {"name": "Bash", "input": {"command": "echo m25ok", "description": "scripted"}}]
    r2 = run(proj, tools_prompt(calls, "build me a recipe page"), path_env=bare, resume=sid, allowed_tools=["Bash"], permission_mode="acceptEdits")
    if not os.path.isfile(first_file):
        f.append("turn 2: the first file (the first win) was not created with hooks off and a stripped PATH")
    for label, r in (("turn 1", r1), ("turn 2", r2)):
        if not sane(r, label, f):
            continue
        if r.hook_events:
            f.append("%s: %d hook events appeared with hooks off: %s" % (label, len(r.hook_events), r.hook_summary()))
        noise = [ln for ln in (r.stderr + "\n" + "\n".join(str(e.get("stderr") or "") for e in r.events)).splitlines() if re.search(r"(?i)hook|python|executable", ln)]
        if noise:
            f.append("%s: hook or python noise on screen: %s" % (label, clip(noise[0], 120)))
        if capsule_delivered(r.all_request_text()):
            f.append("%s: a hook-made state capsule reached the model with hooks off" % label)
        if "Developer Tutor, installed in this project" not in r.first_user_text(0):
            f.append("%s: CLAUDE.md did not reach the model" % label)
    if r2.tool_results and not any("m25ok" in t["text"] for t in r2.tool_results):
        f.append("turn 2: the Bash command did not run with a stripped PATH: %s" % [clip(t["text"], 80) for t in r2.tool_results])
    ev("PATH without python/py: %d entries kept of %d; hook events: %d; stderr: %r" % (len(bare.split(os.pathsep)), len(os.environ.get("PATH", "").split(os.pathsep)), len(r1.hook_events) + len(r2.hook_events), clip(r1.stderr + r2.stderr, 80)))
    return f


@scenario(27)
def m27() -> List[str]:
    """Hooks ON: a Turkish prompt (non-ASCII) reaches the hook through the launcher intact and is stored as typed."""
    f: List[str] = []
    proj = S.project(hooks=True)
    text = "Merhaba, bir tarif sayfası yapmak istiyorum. Şüphelerim var: çok zor mu?"
    r = run(proj, text)
    if not sane(r, "run", f):
        return f
    bad = [e.get("hook_name") for e in r.hook_responses() if e.get("exit_code") != 0]
    if bad:
        f.append("hooks failed with a Turkish prompt: %s" % bad)
    data = os.path.join(proj, ".claude", "agent-memory", "tutor-data")
    path = os.path.join(data, "state", "recent-user.json")
    stored = []
    try:
        with open(path, encoding="utf-8") as fh:
            stored = [str(x.get("text")) for x in json.load(fh)]
    except (OSError, ValueError):
        f.append("state/recent-user.json was not written")
    if stored and stored[-1] != text:
        f.append("the stored prompt differs from what was typed: %r" % stored[-1][:80])
    if text not in r.all_request_text():
        f.append("the Turkish prompt is not intact in the request to the model")
    ev("stored prompt equals typed prompt: %s; hook exit codes: %s" % (bool(stored) and stored[-1] == text, [e.get("exit_code") for e in r.hook_responses()]))
    log = os.path.join(data, "state", "hook-errors.log")
    if os.path.isfile(log) and os.path.getsize(log) > 0:
        f.append("hook-errors.log is not empty after a clean run: %s" % clip(read_text(log), 120))
    return f


@scenario(28)
def m28() -> List[str]:
    """Hooks ON: a machine-made prompt (background helper finished) prints nothing and is not stored as learner words."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    calls = [{"name": "Agent", "input": {"description": "bg helper", "prompt": "say hi", "subagent_type": "general-purpose", "run_in_background": True}}]
    r = run(proj, tools_prompt(calls, "please ask a helper to say hi"), allowed_tools=["Agent"], timeout=180)
    if not sane(r, "run", f):
        return f
    prompts = r.hook_responses("UserPromptSubmit")
    if len(prompts) < 2:
        raise Skip("the CLI did not send a second (machine-made) prompt in this run; %d UserPromptSubmit events" % len(prompts))
    machine = prompts[1]
    ev("second UserPromptSubmit (machine-made): exit=%s stdout=%r" % (machine.get("exit_code"), clip(machine.get("stdout"), 60)))
    if machine.get("exit_code") != 0:
        f.append("the machine-made prompt made the hook fail: exit %s" % machine.get("exit_code"))
    if str(machine.get("stdout") or "").strip():
        f.append("the hook printed text for a machine-made prompt: %s" % clip(machine.get("stdout"), 100))
    path = os.path.join(proj, ".claude", "agent-memory", "tutor-data", "state", "recent-user.json")
    try:
        stored = read_text(path)
    except OSError:
        stored = ""
    if "task-notification" in stored or "SYSTEM NOTIFICATION" in stored:
        f.append("the machine-made prompt was stored as learner words in recent-user.json")
    return f


@scenario(29)
def m29() -> List[str]:
    """tools/doctor.py enable-hooks writes a settings.json that Claude Code accepts; all 6 events fire; disable-hooks undoes it."""
    f: List[str] = []
    if not os.path.isfile(os.path.join(PRODUCT, "tools", "doctor.py")):
        raise Skip("tools/doctor.py is not in the product")
    proj = S.project(hooks=False, git=True)
    doctor = os.path.join(proj, ".claude", "tools", "doctor.py")
    settings_path = os.path.join(proj, ".claude", "settings.json")

    def doctor_cmd(word: str) -> Tuple[int, str]:
        proc = subprocess.run([sys.executable, doctor, word], cwd=proj, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, timeout=120, env=dict(os.environ, PYTHONUTF8="1"))
        return proc.returncode, (proc.stdout + proc.stderr).decode("utf-8", errors="replace")

    code, text = doctor_cmd("enable-hooks")
    ev("doctor.py enable-hooks: exit %d; %s" % (code, clip(text, 150)))
    if code != 0:
        f.append("doctor.py enable-hooks exited %d: %s" % (code, clip(text, 150)))
        return f
    settings = m.read_json(settings_path, None)
    events = sorted((settings or {}).get("hooks", {}).keys()) if isinstance(settings, dict) else []
    if events != sorted(SIX_MODES):
        f.append("settings.json hooks after enable-hooks: %s, expected %s" % (events, sorted(SIX_MODES)))
    dcode, dout, _ = m.run_command(proj, ["doctor"])
    if "Invalid settings" in dout:
        f.append("claude doctor flags the settings.json written by enable-hooks: %s" % clip(dout[dout.find("Invalid settings"):], 250))
    check_six_modes(proj, f, "m29")
    code, text = doctor_cmd("disable-hooks")
    after = m.read_json(settings_path, None)
    left = sorted((after or {}).get("hooks", {}).keys()) if isinstance(after, dict) else ["(settings.json unreadable)"]
    ev("doctor.py disable-hooks: exit %d; hooks left in settings.json: %s" % (code, left or "none"))
    if code != 0 or left:
        f.append("disable-hooks exit %d, hooks left: %s" % (code, left))
    r = run(proj, "hello")
    if sane(r, "after disable-hooks", f) and r.hook_events:
        f.append("hooks still ran after disable-hooks: %s" % r.hook_summary())
    return f


# --------------------------------------------------------------------------- guard through the real CLI

GUARD_MODES = {"deny": "deny", "ask": "ask", "pass": "pass"}


def guard_run(proj: str, commands: List[str], expected: List[str], label: str, f: List[str], tool: str = "Bash",
              env: Optional[Dict[str, str]] = None) -> List[Dict[str, Any]]:
    calls = [{"name": tool, "input": {"command": c, "description": "scripted"}} for c in commands]
    r = run(proj, tools_prompt(calls), allowed_tools=[tool], env=env, timeout=150)
    if not sane(r, label, f):
        return []
    rows = classify(r)
    expect_kinds(f, rows, [(w, "") for w in expected], label)
    return rows


@scenario(11)
def m11() -> List[str]:
    """Guard: force pushes are DENIED with the 'Stopped on purpose' text; a plain push ASKS (hook or floor rule); status passes."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    cmds = ["git push --force origin main", "git push -f origin main", "git push origin main --force", "git push origin +main",
            "git -C . push --force origin main", "bash -c 'git push --force origin main'", "git push --force-with-lease origin main",
            "git push origin main", "git push --force-with-lease origin feature", "git status --short"]
    want = ["deny"] * 7 + ["ask-or-rule", "ask-or-rule", "pass"]
    rows = guard_run(proj, cmds, want, "bash-guard", f)
    if rows:
        first = rows[0]
        ev("DENY looks like | hook exit 2, is_error=true, tool_result: %s" % clip(first["text"], 330))
        if not first["text"].startswith("PreToolUse:Bash hook error: Stopped on purpose by the tutor safety guard"):
            f.append("deny text does not start with 'PreToolUse:Bash hook error: Stopped on purpose by the tutor safety guard': %s" % clip(first["text"], 100))
        for needle in ("This is a safety stop, not a setup error", "Safe way:", "tell the user in two plain sentences"):
            if needle not in first["text"]:
                f.append("deny text lacks the required sentence %r" % needle)
        ask = next((r_ for r_ in rows if r_["kind"] == "ask"), None)
        if ask:
            ev("ASK looks like | hook exit 0 + permissionDecision ask; in -p it is a denial, tool_result (no prefix): %s" % clip(ask["text"], 200))
    if not os.path.isdir(os.path.join(proj, ".git")):
        f.append("scratch repo missing")
    return f


@scenario(16)
def m16() -> List[str]:
    """Guard: rm -rf of a project subfolder (and other hard-to-undo commands) ASK and change nothing."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    os.makedirs(os.path.join(proj, "src"), exist_ok=True)
    with open(os.path.join(proj, "src", "app.py"), "w", encoding="utf-8") as fh:
        fh.write("print('work that exists nowhere else')\n")
    cmds = ["rm -rf src", "rm -r src", "git reset --hard", "git clean -fd", "git checkout -- .", "git branch -D feature"]
    # rm -rf has no floor rule, so the hook's own ask text must reach the model; the git commands also have an ask rule in
    # settings.json that answers first (generic text in -p): either way the command must not run.
    rows = guard_run(proj, cmds, ["ask"] * 2 + ["ask-or-rule"] * 4, "ask-table", f)
    for row in rows[2:]:
        ev("floor-or-hook ask for %s -> %s | text: %s" % (clip(row["input"].get("command"), 40), row["kind"], clip(row["text"], 90)))
    if not os.path.isfile(os.path.join(proj, "src", "app.py")):
        f.append("src/app.py was deleted: the guard did not stop rm -rf")
    return f


@scenario(17)
def m17() -> List[str]:
    """Guard: rm -rf of regenerable folders (node_modules, dist, build, __pycache__) is NOT asked and runs."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    names = ["node_modules", "dist", "build", "__pycache__"]
    for name in names:
        os.makedirs(os.path.join(proj, name, "x"), exist_ok=True)
    cmds = ["rm -rf %s" % n for n in names]
    guard_run(proj, cmds, ["pass"] * len(cmds), "regenerable", f)
    left = [n for n in names if os.path.exists(os.path.join(proj, n))]
    if left:
        f.append("these folders were not removed: %s" % left)
    return f


@scenario(18)
def m18() -> List[str]:
    """Guard: reading a secret file with a shell program is DENIED; mentioning the name or .env.example passes."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    with open(os.path.join(proj, ".env"), "w", encoding="utf-8") as fh:
        fh.write("GREETING=hello\n")
    with open(os.path.join(proj, ".env.example"), "w", encoding="utf-8") as fh:
        fh.write("GREETING=\n")
    cmds = ["cat .env", "cat ./.env", "head -n 3 .env", "type .env", "git add .env", "cat .env.example",
            "echo remember to create the .env file", "git status --short"]
    want = ["deny"] * 5 + ["pass"] * 3
    guard_run(proj, cmds, want, "secret-file", f)
    return f


@scenario(19)
def m19() -> List[str]:
    """Guard: writing a secret-shaped value (built at run time) into a file or a command is DENIED."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    secret = fake_secret()
    notes = os.path.join(proj, "notes.txt")
    ok_file = os.path.join(proj, "docs", "ok.md")
    calls = [{"name": "Write", "input": {"file_path": notes, "content": "API_KEY=" + secret + "\n"}},
             {"name": "Bash", "input": {"command": "echo KEY=" + secret + " > keys.txt", "description": "scripted"}},
             {"name": "Write", "input": {"file_path": ok_file, "content": "hello, nothing secret here\n"}}]
    r = run(proj, tools_prompt(calls), permission_mode="acceptEdits", allowed_tools=["Write", "Bash"])
    if not sane(r, "run", f):
        return f
    rows = classify(r)
    expect_kinds(f, rows, [("deny", ""), ("deny", ""), ("pass", "")], "secret-write")
    for row in rows[:2]:
        if secret in row["text"]:
            f.append("the deny text repeats the secret value")
    if os.path.exists(notes) or os.path.exists(os.path.join(proj, "keys.txt")):
        f.append("a file with the secret was created")
    if not os.path.isfile(ok_file):
        f.append("the harmless Write was blocked")
    if secret in "\n".join(x for x in (r.stderr,)):
        f.append("the secret appears on stderr")
    return f


@scenario(20)
def m20() -> List[str]:
    """Guard through the PowerShell tool: same decisions as Bash (needs CLAUDE_CODE_USE_POWERSHELL_TOOL=1)."""
    f: List[str] = []
    if os.name != "nt":
        raise Skip("the PowerShell tool is a Windows feature; this machine is not Windows")
    proj = S.project(hooks=True, git=True)
    for name in ("src", "sandbox", "node_modules"):
        os.makedirs(os.path.join(proj, name), exist_ok=True)
    with open(os.path.join(proj, "src", "app.py"), "w", encoding="utf-8") as fh:
        fh.write("print('work')\n")
    with open(os.path.join(proj, ".env"), "w", encoding="utf-8") as fh:
        fh.write("GREETING=hello\n")
    sandbox = os.path.join(proj, "sandbox")
    cmds = ["git push --force origin main", "Get-Content .env", "cat .env", "Remove-Item -Recurse -Force src",
            "Set-Location -LiteralPath '%s'; Get-ChildItem | Remove-Item -Recurse -Force" % sandbox,
            "Remove-Item -Recurse -Force node_modules", "Write-Output m20ok"]
    want = ["deny", "deny", "deny", "ask", "stop", "pass", "pass"]
    probe = run(proj, "PS: Write-Output probe", allowed_tools=["PowerShell"], env={"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"})
    if not any(t.get("name") == "PowerShell" for body in probe.model_requests[:1] for t in body.get("tools", [])):
        raise Skip("the PowerShell tool is not offered to the model on this machine, even with CLAUDE_CODE_USE_POWERSHELL_TOOL=1")
    guard_run(proj, cmds, want, "ps-guard", f, tool="PowerShell", env={"CLAUDE_CODE_USE_POWERSHELL_TOOL": "1"})
    if not os.path.isfile(os.path.join(proj, "src", "app.py")):
        f.append("src/app.py was deleted through PowerShell: the guard did not stop it")
    return f


# --------------------------------------------------------------------------- permission floor (settings.json)

def read_probe(proj: str, extra_settings: Optional[Dict[str, Any]] = None) -> Tuple[List[Dict[str, Any]], m.Run]:
    base = proj
    calls = [{"name": "Read", "input": {"file_path": os.path.join(base, ".env")}},
             {"name": "Read", "input": {"file_path": os.path.join(base, "src", "..", ".env")}},
             {"name": "Read", "input": {"file_path": os.path.join(base, ".env.local")}},
             {"name": "Write", "input": {"file_path": os.path.join(base, ".env.example"), "content": "GREETING=\n"}},
             {"name": "Read", "input": {"file_path": os.path.join(base, ".env.example")}}]
    r = run(proj, tools_prompt(calls), permission_mode="acceptEdits", allowed_tools=["Read"])
    return classify(r), r


def seed_env_files(proj: str) -> None:
    os.makedirs(os.path.join(proj, "src"), exist_ok=True)
    for name in (".env", ".env.local"):
        with open(os.path.join(proj, name), "w", encoding="utf-8") as fh:
            fh.write("GREETING=hello\n")


@scenario(12)
def m12() -> List[str]:
    """Floor: Read of .env (3 spellings) and .env.local is denied; Write of .env.example is allowed."""
    f: List[str] = []
    proj = S.project(hooks=False)
    broken = no_settings(proj, f, "the permission floor")
    seed_env_files(proj)
    rows, r = read_probe(proj)
    if not rows:
        f.append("no tool calls ran: %s" % clip(r.stderr, 150))
        return f
    names = [".env (absolute)", "src\\..\\.env", ".env.local", "Write .env.example", "Read .env.example"]
    for name, row in zip(names, rows):
        ev("floor | %-20s | %-6s | %s" % (name, row["kind"], clip(row["text"], 90)))
    if not broken:
        for name, row in list(zip(names, rows))[:3]:
            if row["kind"] not in ("floor", "deny"):
                f.append("Read %s was not denied by the floor (kind %s)" % (name, row["kind"]))
        if rows[3]["kind"] != "pass" or not os.path.isfile(os.path.join(proj, ".env.example")):
            f.append("Write of .env.example was not allowed (kind %s: %s)" % (rows[3]["kind"], clip(rows[3]["text"], 100)))
    # Experiments for the settings owner: which deny shapes keep Write .env.example possible? (evidence only)
    variants = [("deny .env and .env.* globs", ["Read(./.env)", "Read(./.env.*)"]),
                ("deny enumerated .env .env.local .env.production .env.development", ["Read(./.env)", "Read(./.env.local)", "Read(./.env.production)", "Read(./.env.development)"]),
                ("deny glob plus negation Read(!./.env.example)", ["Read(./.env)", "Read(./.env.*)", "Read(!./.env.example)"]),
                ("deny **/.env and **/.env.* with negation !**/.env.example", ["Read(**/.env)", "Read(**/.env.*)", "Read(!**/.env.example)"]),
                ("deny bare .env and .env.* with negation Read(!.env.example)", ["Read(.env)", "Read(.env.*)", "Read(!.env.example)"]),
                ("control: deny **/.env and **/.env.* WITHOUT negation", ["Read(**/.env)", "Read(**/.env.*)"]),
                ("control: deny bare .env and .env.* WITHOUT negation", ["Read(.env)", "Read(.env.*)"])]
    for label, deny in variants:
        exp = S.project(hooks=False, settings_from_product=False, extra_settings={"outputStyle": "tutor", "permissions": {"deny": deny}})
        seed_env_files(exp)
        erows, _ = read_probe(exp)
        kinds = [x["kind"] for x in erows]
        ev("experiment | %s | Read .env=%s, Read .env.local=%s, Write .env.example=%s, Read .env.example=%s" % (label, kinds[0] if kinds else "?", kinds[2] if len(kinds) > 2 else "?", kinds[3] if len(kinds) > 3 else "?", kinds[4] if len(kinds) > 4 else "?"))
    return f


@scenario(13)
def m13() -> List[str]:
    """Floor (hooks off): the inbox Write raises no prompt in default mode; a Write to state/x.json is blocked."""
    f: List[str] = []
    proj = S.project(hooks=False)
    data = os.path.join(proj, ".claude", "agent-memory", "tutor-data")
    targets = [("inbox/x.md", "model file, must pass"), ("learner/profile.md", "model file, must pass"), ("now.md", "model file, must pass"),
               ("journal/2026-10-07.md", "model file, must pass"), ("state/x.json", "hook-only, must be blocked or asked"),
               ("learner/progress.jsonl", "hook-only, must be blocked or asked"), ("docs/control.md", "control: default mode must ask")]
    calls = []
    for rel, _ in targets:
        base = proj if rel.startswith("docs/") else data
        calls.append({"name": "Write", "input": {"file_path": os.path.join(base, *rel.split("/")), "content": "x\n"}})
    r = run(proj, tools_prompt(calls), permission_mode="default")
    if not sane(r, "run", f):
        return f
    rows = classify(r)
    for (rel, why), row in zip(targets, rows):
        written = os.path.exists(os.path.join(proj if rel.startswith("docs/") else data, *rel.split("/")))
        ev("write | %-24s | %-6s | written=%s | %s" % (rel, row["kind"], written, clip(row["text"], 100)))
        if "must pass" in why:
            if row["kind"] != "pass" or not written:
                f.append("%s: expected a silent write, got %s (written=%s): %s" % (rel, row["kind"], written, clip(row["text"], 100)))
        else:
            if written or row["kind"] == "pass":
                f.append("%s: expected blocked or asked (%s), got kind %s, written=%s" % (rel, why, row["kind"], written))
    if len(rows) != len(targets):
        f.append("expected %d results, got %d" % (len(targets), len(rows)))
    return f


@scenario(14)
def m14() -> List[str]:
    """Hooks ON: an inbox Write is answered 'Saved:' / 'Refused:' by PostToolUse; a state/ Write is denied."""
    f: List[str] = []
    proj = S.project(hooks=True)
    data = os.path.join(proj, ".claude", "agent-memory", "tutor-data")
    words = "I think a save point is a saved copy of my files that I can go back to later."
    good = os.path.join(data, "inbox", "m14-good.md")
    forged = os.path.join(data, "inbox", "m14-forged.md")
    state = os.path.join(data, "state", "x.json")
    # The tool calls come from a server-side script, so the forged words are NOT in the learner's prompt.
    nl = chr(10)
    script = [{"tool_uses": [{"name": "Write", "input": {"file_path": good, "content": "learned git-commit | " + words + nl}},
                             {"name": "Write", "input": {"file_path": forged, "content": "learned git-commit | the learner never said these words at all today" + nl}},
                             {"name": "Write", "input": {"file_path": state, "content": "{}" + nl}}]},
              {"text": "done"}]
    r = run(proj, words, permission_mode="default", scenario=script)
    if not sane(r, "run", f):
        return f
    rows = classify(r)
    answers = []
    for p in r.hook_responses("PostToolUse"):
        out = str(p.get("stdout") or "")
        try:
            answers.append(str(((json.loads(out) if out.strip() else {}).get("hookSpecificOutput") or {}).get("additionalContext") or ""))
        except ValueError:
            answers.append("INVALID JSON: " + clip(out, 60))
    for i, a in enumerate(answers):
        ev("PostToolUse answer %d: %s" % (i + 1, clip(a, 160)))
    if not any(a.startswith("Saved:") for a in answers):
        f.append("no 'Saved:' answer for the true quote; answers: %s" % [clip(a, 60) for a in answers])
    if not any(a.startswith("Refused:") for a in answers):
        f.append("no 'Refused:' answer for the forged quote; answers: %s" % [clip(a, 60) for a in answers])
    rows_file = os.path.join(data, "learner", "progress.jsonl")
    progress = []
    for ln in (open(rows_file, encoding="utf-8").read().splitlines() if os.path.isfile(rows_file) else []):
        try:
            progress.append(json.loads(ln))
        except ValueError:
            pass
    learned = [p for p in progress if p.get("event") == "learned"]
    ev("progress.jsonl rows: %d (learned: %d)" % (len(progress), len(learned)))
    if len(learned) != 1 or (learned and learned[0].get("quote") != words):
        f.append("expected exactly 1 learned row with the true quote, found %d" % len(learned))
    if os.path.exists(forged) or os.path.exists(good):
        ev("note: inbox files left on disk: good=%s forged=%s" % (os.path.exists(good), os.path.exists(forged)))
    if rows and rows[-1]["kind"] not in ("deny", "ask"):
        f.append("the Write to state/x.json was not stopped (kind %s): %s" % (rows[-1]["kind"], clip(rows[-1]["text"], 100)))
    elif rows:
        ev("state/ write -> %s: %s" % (rows[-1]["kind"], clip(rows[-1]["text"], 200)))
    if os.path.exists(state):
        f.append("state/x.json exists: a hook-only path was written by the model")
    if "Saved:" not in r.all_request_text():
        f.append("the 'Saved:' answer did not reach the model in a later request")
    return f


def skills_with_allowed_tools() -> List[str]:
    out = []
    for name, _ in m.product_skills(PRODUCT):
        path = os.path.join(PRODUCT, "skills", name, "SKILL.md")
        if os.path.isfile(path) and re.search(r"^allowed-tools:", read_text(path), re.M):
            out.append(name)
    return out


@scenario(15)
def m15() -> List[str]:
    """Floor: Skill(...) allow rules start all 11 skills with no prompt in default mode (needs a trusted folder)."""
    f: List[str] = []
    names = [s[0] for s in m.product_skills(PRODUCT)]
    needy = skills_with_allowed_tools()
    proj = S.project(hooks=False)
    broken = no_settings(proj, f, "the Skill allow rules")
    calls = [{"name": "Skill", "input": {"skill": n}} for n in names]
    r = run(proj, tools_prompt(calls), permission_mode="default", trusted=True, timeout=150)
    if sane(r, "trusted", f):
        rows = classify(r)
        bad = [x["input"].get("skill") for x in rows if x["kind"] != "pass"]
        ev("PRODUCT settings, trusted folder, default mode: %d of %d skill starts passed with no prompt; not passed: %s" % (len(rows) - len(bad), len(names), bad or "none"))
        if not broken and bad:
            f.append("skills that asked for permission or failed: %s (first: %s)" % (bad, clip(next(x["text"] for x in rows if x["kind"] != "pass"), 120)))
    # Experiment 1: no allow rules at all. Which skills ask by themselves? (Claude Code asks for skills that declare allowed-tools.)
    ctl = S.project(hooks=False, settings_from_product=False, extra_settings={"outputStyle": "tutor"})
    c = run(ctl, tools_prompt(calls), permission_mode="default", trusted=True, timeout=150)
    if sane(c, "no allow rules", f):
        asks = [x["input"].get("skill") for x in classify(c) if x["kind"] != "pass"]
        ev("EXPERIMENT without any allow rule: skills that ask for permission: %s; skills with allowed-tools in their file: %s" % (asks, needy))
        if not asks:
            f.append("no skill asked without allow rules, so the allow rules prove nothing in this mode")
    # Experiment 2: Skill(name) allow rules written by the harness, trusted vs untrusted folder.
    rules = {"outputStyle": "tutor", "permissions": {"allow": ["Skill(%s)" % n for n in names]}}
    for label, trusted in (("trusted", True), ("untrusted", False)):
        exp = S.project(hooks=False, settings_from_product=False, extra_settings=rules)
        e = run(exp, tools_prompt(calls), permission_mode="default", trusted=trusted, timeout=150)
        if sane(e, "allow rules, " + label, f):
            kinds = classify(e)
            bad = [x["input"].get("skill") for x in kinds if x["kind"] != "pass"]
            ev("EXPERIMENT with 11 Skill(name) allow rules, %s folder: %d of %d pass; asking: %s; stderr: %s" % (label, len(kinds) - len(bad), len(names), bad or "none", clip(e.stderr, 160) or "(empty)"))
    return f


# --------------------------------------------------------------------------- start places

@scenario(21)
def m21() -> List[str]:
    """Started in a sub-folder: CLAUDE.md, rules and skills load; no SessionStart hook runs; style stays default."""
    f: List[str] = []
    proj = S.project(hooks=True, git=True)
    sub = os.path.join(proj, "src", "app")
    os.makedirs(sub, exist_ok=True)
    r = run(proj, "hello", cwd=sub)
    if not sane(r, "sub-folder start", f):
        return f
    sent = r.first_user_text(0)
    init = r.init or {}
    claude_md = "Developer Tutor, installed in this project" in sent
    rules_n = len([n for n in product_rules() if re.search(r"rules[\\/]%s" % re.escape(n), sent)])
    skills_n = len([s for s in m.product_skills(PRODUCT) if s[0] in (init.get("skills") or [])])
    style = "# Output Style: tutor" in r.all_request_text()
    ev("sub-folder start (git repo): CLAUDE.md=%s rules=%d/6 skills(init)=%d/11 hooks run=%d output_style(init)=%s style text in request=%s" % (
        claude_md, rules_n, skills_n, len(r.hook_responses()), init.get("output_style"), style))
    if not claude_md:
        f.append("CLAUDE.md did not load from the sub-folder")
    if rules_n != 6:
        f.append("%d of 6 rules loaded from the sub-folder" % rules_n)
    if skills_n != 11:
        f.append("%d of 11 skills known when started in a sub-folder" % skills_n)
    if r.hook_responses("SessionStart"):
        f.append("a SessionStart hook ran from a sub-folder (SPEC 4.3 says no hook runs there)")
    if r.hook_responses():
        f.append("hooks ran from a sub-folder: %s" % r.hook_summary())
    if style:
        f.append("the output style is active when started in a sub-folder (SPEC 4.3 says the default style)")
    # the same without a git repo, for the record
    plain = S.project(hooks=True, git=False)
    sub2 = os.path.join(plain, "src", "app")
    os.makedirs(sub2, exist_ok=True)
    r2 = run(plain, "hello", cwd=sub2)
    if sane(r2, "sub-folder start (no git)", f):
        s2 = r2.first_user_text(0)
        ev("sub-folder start (no git repo): CLAUDE.md=%s rules=%d/6 skills(init)=%d/11 hooks run=%d" % (
            "Developer Tutor, installed in this project" in s2, len([n for n in product_rules() if re.search(r"rules[\\/]%s" % re.escape(n), s2)]),
            len([s for s in m.product_skills(PRODUCT) if s[0] in ((r2.init or {}).get("skills") or [])]), len(r2.hook_responses())))
    return f


@scenario(22)
def m22() -> List[str]:
    """/compact in one process: CLAUDE.md, rules and style stay, the skill list is gone, SessionStart(compact) re-injects."""
    f: List[str] = []
    skills = [s[0] for s in m.product_skills(PRODUCT)]
    for label, model in (("200K model", MODEL_200K), ("default model", None)):
        proj = S.project(hooks=True)
        r = m.run_claude_stream(proj, ["hello first", "/compact", "second question after the compact"], model=model)
        if not sane(r, label, f):
            continue
        reqs = [b for b in r.model_requests]
        if len(reqs) < 3:
            f.append("%s: expected 3 model requests (before, compaction, after), saw %d" % (label, len(reqs)))
            continue
        before_idx, after_idx = 0, len(reqs) - 1
        before = r.request_text(before_idx)
        after = r.request_text(after_idx)
        listing_before = "The following skills are available" in before
        listing_after = "The following skills are available" in after
        ev("%s: skill list before compaction=%s, after=%s" % (label, listing_before, listing_after))
        for what, needle in (("CLAUDE.md", "Developer Tutor, installed in this project"), ("style", "# Output Style: tutor"), ("rule safety.md", "safety.md")):
            if needle not in after:
                f.append("%s: %s missing after /compact" % (label, what))
        if not listing_before:
            f.append("%s: no skill list before compaction (test premise broken)" % label)
        comp = r.hook_responses("SessionStart:compact")
        if not comp:
            f.append("%s: no SessionStart(compact) hook event: %s" % (label, r.hook_summary()))
            continue
        text = str(comp[0].get("stdout") or "")
        in_after = " ".join(text.split())[:60] in " ".join(after.split()) if text.strip() else False
        has_menu = "Say:" in text
        named = [s for s in skills if s in text]
        ev("%s: SessionStart(compact) printed %d chars, canary=%s, menu line 'Say:'=%s, skill names in it=%d/11, reached the model=%s" % (
            label, len(text), "=== Tutor session state ===" in text, has_menu, len(named), in_after))
        if "=== Tutor session state ===" not in text:
            f.append("%s: SessionStart(compact) did not re-inject the canary capsule" % label)
        if not has_menu:
            f.append("%s: SessionStart(compact) output has no menu line ('Say: where are we | ...')" % label)
        if not in_after:
            f.append("%s: the compact capsule did not reach the model after compaction" % label)
        if len(text) > 3000:
            f.append("%s: compact output is %d chars (cap 3000)" % (label, len(text)))
        if r.hook_responses("SessionStart:startup") and "SessionStart:startup hook success" in after:
            ev("%s: note: the old startup capsule is still in the request after compaction" % label)
    return f


# --------------------------------------------------------------------------- settings validity

@scenario(23)
def m23() -> List[str]:
    """`claude doctor` finds no invalid settings in the product's settings.json, also after hooks are enabled."""
    f: List[str] = []
    off = S.project(hooks=False)
    broken = no_settings(off, f, "settings validity")
    on = S.project(hooks=True)
    for label, proj in (("hooks off", off), ("hooks on (enable-hooks result)", on)):
        code, out, err = m.run_command(proj, ["doctor"])
        invalid = "Invalid settings" in out
        ev("claude doctor, %s: exit %s, 'Invalid settings' section: %s%s" % (label, code, invalid, "" if not invalid else " -> " + clip(out[out.find('Invalid settings'):], 300)))
        if code != 0:
            f.append("%s: claude doctor exited %s" % (label, code))
        if invalid and not broken:
            f.append("%s: doctor reports invalid settings: %s" % (label, clip(out[out.find("Invalid settings"):], 250)))
    # controls: doctor must be able to say 'invalid', or the checks above prove nothing
    for label, patch in (("permissions.deny is a string", {"permissions": {"deny": "oops"}}),
                         ("hooks.Stop has a number as command", {"hooks": {"Stop": [{"hooks": [{"type": "command", "command": 5}]}]}})):
        ctl = S.project(hooks=False, settings_from_product=False)
        with open(os.path.join(ctl, ".claude", "settings.json"), "w", encoding="utf-8") as fh:
            json.dump(patch, fh)
        code, out, err = m.run_command(ctl, ["doctor"])
        flagged = "Invalid settings" in out
        ev("control (%s): doctor flags it = %s" % (label, flagged))
        if not flagged:
            f.append("control '%s': doctor did not flag it, so a clean result proves little" % label)
    return f


@scenario(24)
def m24() -> List[str]:
    """defaultMode acceptEdits from settings.json shows in the init event when no mode is passed."""
    f: List[str] = []
    proj = S.project(hooks=False)
    if no_settings(proj, f, "defaultMode"):
        pass
    r = run(proj, "hello", permission_mode=None)
    if sane(r, "no --permission-mode", f):
        mode = (r.init or {}).get("permissionMode")
        ev("init.permissionMode without --permission-mode: %s" % mode)
        if proj.settings_source == "product" and mode != "acceptEdits":
            f.append("init.permissionMode is %r, expected 'acceptEdits' from settings.json" % mode)
    d = run(proj, "hello", permission_mode="default")
    if sane(d, "--permission-mode default", f):
        ev("with --permission-mode default: %s (the flag overrides settings)" % (d.init or {}).get("permissionMode"))
    return f


# --------------------------------------------------------------------------- harness self-check

@scenario(26)
def m26() -> List[str]:
    """Harness: a planted token reaches the mock; the child has no real credential; tests/ holds no key or path."""
    f: List[str] = []
    proj = S.project(hooks=False)
    with open(os.path.join(proj, "CLAUDE.md"), "w", encoding="utf-8") as fh:
        fh.write("Planted: SELFTOK-1\n")
    r = run(proj, "hello")
    if sane(r, "run", f):
        if "SELFTOK-1" not in r.final_text():
            f.append("the planted token did not come back from the mock: %s" % clip(r.final_text(), 100))
        else:
            ev("planted token reached the model: %s" % clip(r.final_text(), 80))
    env = m.child_env("http://127.0.0.1:1", "x")
    for var in ("CLAUDE_CODE_SDK_HAS_HOST_AUTH_REFRESH", "CLAUDE_CODE_OAUTH_TOKEN"):
        if var in env:
            f.append("child environment contains %s" % var)
    if env.get("ANTHROPIC_API_KEY", "").startswith("sk-"):
        f.append("the placeholder key looks like a real key")
    if not env["ANTHROPIC_BASE_URL"].startswith("http://127.0.0.1:"):
        f.append("the base URL is not loopback")
    # hygiene: no key-shaped literal, no machine path, no e-mail address in anything under tests/
    bad = []
    patterns = [r"sk-ant-[A-Za-z0-9_-]{10,}", r"AKIA[0-9A-Z]{16}", r"gh[ps]_[A-Za-z0-9]{30,}", r"[A-Za-z]:[\\/]+Users[\\/]+[A-Za-z]", r"[\w.+-]+@(?!(?:users\.noreply|example\.))[\w-]+\.[a-z]{2,}"]   # neutral example addresses are allowed
    for root, dirs, files in os.walk(HERE):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", "runs")]   # runs/ is git-ignored scratch output
        for name in files:
            if name.endswith((".py", ".md")):          # corpora (.txt, .tsv) hold deliberate example commands and are not scanned
                text = read_text(os.path.join(root, name))
                for pat in patterns:
                    mt = re.search(pat, text)
                    if mt:
                        bad.append("%s: %s" % (name, mt.group(0)[:30]))
    if bad:
        f.append("tests/ contains key, path or e-mail shaped text: %s" % bad[:3])
    ev("hygiene scan of tests/: %d findings" % len(bad))
    return f


# --------------------------------------------------------------------------- runner

def parse_only(values: List[str]) -> List[int]:
    wanted = []
    for value in values:
        for part in value.split(","):
            part = part.strip().upper().replace("M-", "").replace("M", "")
            if part:
                wanted.append(int(part))
    return wanted


def main(argv: Optional[List[str]] = None) -> int:
    global PRODUCT
    args = list(sys.argv[1:] if argv is None else argv)
    only: List[str] = []
    product_arg: Optional[str] = None
    json_out: Optional[str] = None
    verbose = False
    listing = False
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--list":
            listing = True
        elif a == "--only" and i + 1 < len(args):
            only.append(args[i + 1])
            i += 1
        elif a.startswith("--only="):
            only.append(a.split("=", 1)[1])
        elif a == "--product" and i + 1 < len(args):
            product_arg = args[i + 1]
            i += 1
        elif a == "--json" and i + 1 < len(args):
            json_out = args[i + 1]
            i += 1
        elif a in ("-v", "--verbose"):
            verbose = True
        elif a in ("-h", "--help"):
            m.say(__doc__ or "")
            return 0
        else:
            m.say("unknown argument: %s (use --help)" % a)
            return 1
        i += 1
    numbers = sorted(TESTS)
    if only:
        wanted = parse_only(only)
        unknown = [n for n in wanted if n not in TESTS]
        if unknown:
            m.say("unknown scenario(s): %s" % ", ".join("M-%d" % n for n in unknown))
            return 1
        numbers = [n for n in numbers if n in wanted]
    if listing:
        for n in numbers:
            m.say("M-%d  %s" % (n, TESTS[n][0]))
        return 0
    if not m.have_claude():
        m.say("SKIP all: claude is not on PATH, so the mock-CLI scenarios cannot run")
        return 0
    try:
        PRODUCT = m.find_product(product_arg)
    except m.HarnessError as exc:
        m.say("FAIL setup: %s" % exc)
        return 1
    m.say("claude %s | product %s | mock API on loopback, placeholder key, private config folders" % (m.claude_version(), "(auto)" if not product_arg else product_arg))
    results = []
    failed = 0
    for n in numbers:
        doc, fn = TESTS[n]
        del EVIDENCE[:]
        started = time.time()
        status, problems = "OK", []
        try:
            problems = fn()
            if problems:
                status = "FAIL"
        except Skip as exc:
            status, problems = "SKIP", [str(exc)]
        except Exception as exc:  # noqa: BLE001
            status = "FAIL"
            problems = ["scenario crashed: %s: %s" % (type(exc).__name__, clip(exc, 200)), clip(traceback.format_exc().splitlines()[-3:], 300)]
        finally:
            S.cleanup()
        secs = time.time() - started
        failed += status == "FAIL"
        m.say("%-4s M-%d  %s  (%.1fs)" % (status, n, doc, secs))
        for p in problems:
            m.say("       - %s" % p)
        if verbose or status != "OK":
            for line in EVIDENCE:
                m.say("       . %s" % line)
        results.append({"id": "M-%d" % n, "doc": doc, "status": status, "problems": problems, "evidence": list(EVIDENCE), "seconds": round(secs, 1)})
    counts = {k: len([r for r in results if r["status"] == k]) for k in ("OK", "FAIL", "SKIP")}
    m.say("summary: %d OK, %d FAIL, %d SKIP" % (counts["OK"], counts["FAIL"], counts["SKIP"]))
    if json_out:
        with open(json_out, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"claude": m.claude_version(), "date": time.strftime("%Y-%m-%d"), "results": results}, fh, indent=1)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
