"""pre_tool.py - PreToolUse handler: the safety guard in front of Bash, PowerShell, Write, Edit and NotebookEdit.

What: reads the tool call, asks lib/guardrules.py for findings (and lib/scanner.py for the commit and push
scan), picks one decision and prints it (SPEC 4.3): nothing when there is no finding (never an "allow", which
would auto-approve the call), a context line for a warning, `ask` or `deny` with the teaching text.
Why: the permission rules in settings.json cannot read `git -C . push -f`, `bash -c "..."` or a PowerShell
pipeline. This handler can, and it explains every stop in plain words (first hit: why and safe way; later
hits: short). The model then tells the learner, because hook text is invisible to the user.
How it fails safely (SPEC P6, F4): the short panic list runs first in its own try block. If the rich analysis
fails, the panic block stands; a command with a danger word becomes the ask `guard-error`; any other command is
allowed (the guard fails open on its own bugs). A call whose input is over 16 MB is asked, never silent. Counters in
state.json are best effort. Budget: 4 s.
Imports only hookio, paths, fsio, secrets, guardrules, scanner, gitq, untrusted, config (selftest checks that
the learner and knowledge engines are not loaded here).
Reads: stdin JSON, hooks/guard-messages.json, state/state.json, package.json/scripts (through guardrules).
Writes: only state/state.json keys guard_hits, guard_last, guard_warned (never creates the data folder).
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Tuple

from lib import fsio, guardrules, hookio, paths

sys.dont_write_bytecode = True

SHELL_TOOLS = {"Bash": "bash", "PowerShell": "powershell"}
FILE_TOOLS = ("Write", "Edit", "NotebookEdit")         # MultiEdit is not a tool of Claude Code 2.1.288: Edit covers it
_GIT_WORDS = re.compile(r"(?i)(?<![\w-])(?:git|gh)(?:\.exe)?(?![\w-])")
TOO_LARGE_REASON = ("This tool call is over 16 MB, so the safety check could not read all of it. "
                    "It needs your approval. Split the change into smaller steps to get a full check.")


def _file_fields(tool: str, tin: Dict[str, Any]) -> Tuple[str, str]:
    path = str(tin.get("file_path") or tin.get("notebook_path") or tin.get("path") or "")
    if tool == "Write":
        content = tin.get("content")
    elif tool == "Edit":
        content = tin.get("new_string")
    elif tool == "NotebookEdit":
        content = tin.get("new_source")
    else:
        content = ""
    return path, content if isinstance(content, str) else ""


def _as_finding(raw: Any) -> Any:
    """The scanner returns plain dicts; keep them as Finding objects so decide() treats all findings alike."""
    try:
        if isinstance(raw, dict) and raw.get("rule_id"):
            return guardrules.Finding(str(raw["rule_id"]), str(raw.get("tier") or "ask"),
                                      str(raw.get("message_key") or raw["rule_id"]), str(raw.get("detail") or ""))
    except Exception as exc:  # noqa: BLE001
        hookio.log_error("pre-tool", exc)
    return None


def _scan_staged(command: str, cwd: str) -> List[Any]:
    """The commit and push scanner (SPEC 7.6), only for commands that mention git or gh, and only with time left."""
    if not _GIT_WORDS.search(command):
        return []
    left = hookio.budget().left()
    if left < 1.0:
        return [guardrules.F("scan-incomplete", "I could not check for secrets: there was no time left.")]
    try:
        from lib import scanner
        found = scanner.scan_staged(cwd or paths.project_root(), command, min(float(getattr(scanner, "TOTAL_SECONDS", 5.0)), left - 0.5))
        return [f for f in (_as_finding(x) for x in found) if f]
    except ImportError:
        return []                                  # the scanner is optional: no scanner, no scan
    except Exception as exc:  # noqa: BLE001
        hookio.log_error("pre-tool", exc)
        return [guardrules.F("scan-incomplete", "I could not check for secrets: the scanner failed.")]


def _shell_findings(command: str, shell: str, cwd: str) -> List[Any]:
    panic: List[Any] = []
    try:
        panic = guardrules.panic_check(command)
    except Exception as exc:  # noqa: BLE001
        hookio.log_error("pre-tool", exc)
    try:
        found = guardrules.analyze_shell(command, shell, cwd, raise_errors=True)
    except Exception as exc:  # noqa: BLE001
        hookio.log_error("pre-tool", exc)
        found = list(panic) if panic else guardrules.guard_error_findings(command)
    found = list(found) + _scan_staged(command, cwd)
    seen, out = set(), []
    for f in found:
        key = (f["rule_id"], f["tier"])
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _state_path() -> str:
    return paths.sub("state", "state.json")


def _read_state() -> Dict[str, Any]:
    return fsio.read_json(_state_path(), {})


def _record(top: Any, decision: str, session: str, warned: bool) -> None:
    """Count the hit (teach once), remember the last one for the lesson offer, remember warnings of this session."""
    if not os.path.isdir(paths.sub("state")) or paths.is_link(paths.sub("state")):
        return                                      # never create the data folder from the guard
    text = fsio.read_text(_state_path(), "")
    if text.strip():
        try:
            if not isinstance(json.loads(text), dict):
                return
        except ValueError:
            return                                  # a damaged state file is never replaced by the guard

    def mutate(state: Any) -> Any:
        if not isinstance(state, dict):
            state = {}
        hits = state.get("guard_hits")
        if not isinstance(hits, dict):
            hits = {}
        rid = str(top["rule_id"])
        hits[rid] = int(hits.get(rid, 0) or 0) + 1
        if len(hits) > 150:
            hits = dict(list(hits.items())[-150:])
        state["guard_hits"] = hits
        state["guard_last"] = {"rule_id": rid, "tier": str(top["tier"]), "decision": decision,
                               "lesson": guardrules.lesson_of(str(top.get("message_key") or rid)),
                               "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        if warned:
            w = state.get("guard_warned")
            rules = list(w.get("rules", [])) if isinstance(w, dict) and w.get("session") == session else []
            if rid not in rules:
                rules.append(rid)
            state["guard_warned"] = {"session": session, "rules": rules[-30:]}
        return state

    fsio.update_json(_state_path(), mutate, {})


def handle(data: Dict[str, Any]) -> None:
    if hookio.input_too_large():
        # the call was cut before it could be read, so it cannot be called safe: ask, never silent, never allow
        hookio.log_note("pre-tool", "input over 16 MB: asked")
        hookio.emit_pre_tool("ask", TOO_LARGE_REASON)
        return
    tool = str(data.get("tool_name") or "")
    tin = data.get("tool_input")
    tin = tin if isinstance(tin, dict) else {}
    mode = str(data.get("permission_mode") or "")
    cwd = str(data.get("cwd") or "")
    session = str(data.get("session_id") or "")
    state = _read_state()
    warned = state.get("guard_warned")
    quiet = warned.get("rules", []) if isinstance(warned, dict) and warned.get("session") == session else []
    guardrules.set_quiet(quiet if isinstance(quiet, list) else [])
    if tool in SHELL_TOOLS:
        command = tin.get("command")
        if not isinstance(command, str) or not command.strip():
            return
        findings = _shell_findings(command, SHELL_TOOLS[tool], cwd)
    elif tool in FILE_TOOLS:
        path, content = _file_fields(tool, tin)
        try:
            findings = guardrules.analyze_file_op(tool, path, content, cwd, str(data.get("scratchpad_dir") or ""))
        except Exception as exc:  # noqa: BLE001
            hookio.log_error("pre-tool", exc)
            findings = []
    else:
        return
    if not findings:
        return                                      # no finding: print nothing, so the normal permission flow decides
    hits = state.get("guard_hits") if isinstance(state.get("guard_hits"), dict) else {}
    decision, text = guardrules.decide(findings, mode, hits)
    if decision == "none":
        return
    top = sorted(findings, key=lambda f: {"block": 0, "ask": 1}.get(str(f["tier"]), 2))[0]
    if decision == "warn":
        if top["rule_id"] in quiet:
            return                                  # once per rule per session
        hookio.emit_pre_tool_context(text)
        _record(top, decision, session, True)
        return
    hookio.emit_pre_tool(decision, text)
    _record(top, decision, session, False)
