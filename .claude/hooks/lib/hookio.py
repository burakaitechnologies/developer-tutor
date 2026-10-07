"""hookio.py - everything a hook needs to talk to Claude Code: read stdin, print, log, run safely.

What: read_input(), input_too_large(), emit_plain(), emit_json(), emit_pre_tool(), emit_pre_tool_context(),
log_error(), run(mode, fn), Budget.
Why: the rules of hook output are strict and were learned the hard way (SPEC 4.3): plain stdout
reaches the model only for SessionStart and UserPromptSubmit; other events need ONE JSON object;
stdin and stdout must be UTF-8 bytes on Windows; exit code 2 blocks and must never happen by accident.
How it fails safely: run() catches every error, writes one plain stderr line plus one log line (the
error type, the module and the line number only, never prompt or command text) and exits 1, which
Claude Code treats as non-blocking. Only a deliberate guard denial exits 2. The pre-tool mode
fails open: on an internal error it logs and exits 0.
Who calls it: dispatch.py (run) and every handler (emit_*).
"""
from __future__ import annotations

import json
import os
import sys
import time
from typing import Any, Callable, Dict, Optional

sys.dont_write_bytecode = True

MAX_STDIN_BYTES = 16 * 1024 * 1024
OUTPUT_CAP = 9000                       # characters (UTF-16 units) per output string
BUDGETS = {"pre-tool": 4.0, "user-prompt": 8.0}
DEFAULT_BUDGET = 10.0
_NO_TEXT_EVENTS = ("Stop", "SubagentStop", "SessionEnd", "PreCompact", "StopFailure")

_state: Dict[str, Any] = {"input": None, "exit": 0, "budget": None, "mode": "", "too_large": False}


# --------------------------------------------------------------------------- budget

class Budget(object):
    """A time allowance for one hook run. Optional steps check left() and skip themselves."""

    def __init__(self, seconds: float) -> None:
        self.seconds = float(seconds)
        self.start = time.monotonic()

    def elapsed(self) -> float:
        return time.monotonic() - self.start

    def left(self) -> float:
        return max(self.seconds - self.elapsed(), 0.0)

    def expired(self) -> bool:
        return self.left() <= 0.0


def budget() -> Budget:
    """The budget of the running hook (created by run(); a fresh 10 s one when called standalone)."""
    if _state["budget"] is None:
        _state["budget"] = Budget(DEFAULT_BUDGET)
    return _state["budget"]


# --------------------------------------------------------------------------- input

def read_input() -> Dict[str, Any]:
    """The JSON object on stdin as a dict ({} when empty, damaged, too large or not an object). Read once, cached.
    Input over MAX_STDIN_BYTES is not parsed: input_too_large() is True, so the pre-tool guard can ask instead."""
    if _state["input"] is not None:
        return _state["input"]
    data: Dict[str, Any] = {}
    try:
        stream = getattr(sys.stdin, "buffer", None)
        # one byte past the cap: only a longer input shows up as too large (an input of exactly the cap is fine)
        raw = stream.read(MAX_STDIN_BYTES + 1) if stream is not None else b""
        if len(raw) > MAX_STDIN_BYTES:
            _state["too_large"] = True
            raw = b""                          # a cut JSON text would not parse anyway
        if raw.startswith(b"\xef\xbb\xbf"):
            raw = raw[3:]
        text = raw.decode("utf-8", errors="replace")
        if text.strip():
            value = json.loads(text)
            if isinstance(value, dict):
                data = value
    except (ValueError, OSError, RecursionError):
        data = {}
    _state["input"] = data
    return data


def input_too_large() -> bool:
    """True when stdin was longer than MAX_STDIN_BYTES (set by read_input(); the rest was never read)."""
    return bool(_state["too_large"])


def set_input(data: Dict[str, Any]) -> None:
    """For tests: pretend stdin held this dict."""
    _state["input"] = data
    _state["too_large"] = False


# --------------------------------------------------------------------------- output

def units(text: str) -> int:
    """Length the way JavaScript counts it (UTF-16 units): characters above U+FFFF count 2."""
    return len(text) + sum(1 for ch in text if ord(ch) > 0xFFFF)


def cap(text: str, limit: int = OUTPUT_CAP) -> str:
    if units(text) <= limit:
        return text
    cut = text[:limit - 40]
    extra = units(cut) - (limit - 40)
    if extra > 0:
        cut = cut[:len(cut) - extra]
    return cut.rstrip() + "\n(cut: output limit)"


def _write(stream_name: str, text: str) -> None:
    try:
        stream = getattr(sys, stream_name)
        stream.buffer.write(text.encode("utf-8", errors="replace"))
        stream.flush()
    except (OSError, ValueError, AttributeError):
        pass


def emit_plain(text: str) -> None:
    """Plain stdout text (model context for SessionStart and UserPromptSubmit only). Never starts with '{'."""
    if not text:
        return
    text = cap(text)
    if text.lstrip().startswith("{"):
        text = "Note: " + text
    _write("stdout", text.rstrip("\n") + "\n")


def _json_line(obj: Dict[str, Any]) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def emit_json(event: str, additional_context: Optional[str] = None, system_message: Optional[str] = None) -> None:
    """ONE JSON object {"hookSpecificOutput":{"hookEventName":event,"additionalContext":...}}.
    Raises ValueError for events whose context would make Claude take an extra turn or is ignored."""
    if event in _NO_TEXT_EVENTS:
        raise ValueError("emit_json: %s output is not allowed" % event)
    out: Dict[str, Any] = {}
    if additional_context:
        out["hookSpecificOutput"] = {"hookEventName": event, "additionalContext": cap(additional_context)}
    if system_message:
        out["systemMessage"] = cap(system_message, 2000)
    if out:
        _write("stdout", _json_line(out) + "\n")


def emit_pre_tool(decision: str, reason: str) -> None:
    """PreToolUse ask or deny. 'allow' is refused on purpose: it would auto-approve the call.
    A deny sets the exit code to 2 (run() applies it)."""
    if decision not in ("deny", "ask"):
        raise ValueError("emit_pre_tool: decision must be 'deny' or 'ask'")
    obj = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": decision,
                                  "permissionDecisionReason": cap(reason)}}
    _write("stdout", _json_line(obj) + "\n")
    if decision == "deny":
        _state["exit"] = 2


def emit_pre_tool_context(text: str) -> None:
    """PreToolUse warning: context for the model with NO permission decision."""
    if not text:
        return
    obj = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": cap(text)}}
    _write("stdout", _json_line(obj) + "\n")


def warn(text: str) -> None:
    """One plain line on stderr."""
    _write("stderr", text.rstrip("\n") + "\n")


# --------------------------------------------------------------------------- errors

def error_site(exc: BaseException) -> str:
    """'<ExceptionType> in <file>.py line <n>' of the innermost frame. No message text (it could hold user words)."""
    try:
        tb = exc.__traceback__
        last = None
        while tb is not None:
            last = tb
            tb = tb.tb_next
        if last is None:
            return type(exc).__name__
        return "%s in %s line %d" % (type(exc).__name__, os.path.basename(last.tb_frame.f_code.co_filename), last.tb_lineno)
    except Exception:
        return type(exc).__name__


def log_error(mode: str, exc: BaseException) -> None:
    """Append one line to state/hook-errors.log: type, module and line only."""
    try:
        from . import fsio
        fsio.log_line("%s %s" % (mode, error_site(exc)))
    except Exception:
        pass


def log_note(mode: str, note: str) -> None:
    """A fixed note (never user text), e.g. 'learner engine missing'."""
    try:
        from . import fsio
        fsio.log_line("%s %s" % (mode, note))
    except Exception:
        pass


# --------------------------------------------------------------------------- run

def run(mode: str, fn: Callable[..., Any]) -> None:
    """Run a handler: fn(data) (or fn() when it takes no argument). Never lets an error escape.
    Exit codes: 0 normally, 2 only after a deliberate guard denial, 1 after an internal error
    (0 for pre-tool, which fails open)."""
    _state["mode"] = mode
    _state["budget"] = Budget(BUDGETS.get(mode, DEFAULT_BUDGET))
    code = 0
    try:
        data = read_input()
        argc = getattr(getattr(fn, "__code__", None), "co_argcount", 1)
        if argc == 0:
            fn()
        else:
            fn(data)
        code = _state["exit"]
    except SystemExit as stop:
        raw = stop.code
        code = raw if isinstance(raw, int) else (0 if raw is None else 1)
        if code == 2 and _state["exit"] != 2:
            code = 1 if mode != "pre-tool" else 0
    except BaseException as exc:  # noqa: BLE001 - the last line of defence
        log_error(mode, exc)
        if mode == "pre-tool":
            code = 0
        else:
            warn("tutor hook %s failed: %s (details in .claude/agent-memory/tutor-data/state/hook-errors.log)"
                 % (mode, error_site(exc)))
            code = 1
    if code == 2 and _state["exit"] != 2:
        code = 1
    try:
        sys.stdout.flush()
    except (OSError, ValueError, AttributeError):
        pass
    sys.exit(code)
