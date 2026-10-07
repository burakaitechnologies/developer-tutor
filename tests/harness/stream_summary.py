"""stream_summary.py - print a readable summary of claude stream-json capture files.

What: for each file (or - for stdin) it lists the hook events (name, exit code, outcome, stderr), the init facts
(model, output style, permission mode, agent and skill counts), tool calls and their results, permission
denials and the final result line.
Why: a stream-json capture of a real CLI run is the best evidence of what a hook did; this makes it quick to read.
How it fails safely: unreadable or damaged lines are reported and skipped; output is written as UTF-8 bytes so a
Turkish letter or an arrow cannot crash a cp1252 console. Read-only. Python 3.9 syntax, standard library only.
Use:  python stream_summary.py capture1.jsonl [capture2.jsonl ...]
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, Iterable, List

sys.dont_write_bytecode = True


def say(text: str) -> None:
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.flush()


def summarize(lines: Iterable[str], label: str) -> None:
    say("== %s" % label)
    for raw in lines:
        raw = raw.strip()
        if not raw:
            continue
        if not raw.startswith("{"):
            say("  RAW: %s" % raw[:300])
            continue
        try:
            o: Dict[str, Any] = json.loads(raw)
        except ValueError:
            say("  unparsable line: %s" % raw[:100])
            continue
        t, st = o.get("type"), o.get("subtype")
        if t == "system" and st == "hook_response":
            say("  hook %-28s exit=%s outcome=%s stderr=%r" % (o.get("hook_name"), o.get("exit_code"), o.get("outcome"), (o.get("stderr") or "")[:160]))
        elif t == "system" and st == "permission_denied":
            say("  permission_denied %s via %s: %s" % (o.get("tool_name"), o.get("decision_reason_type"), str(o.get("decision_reason") or "")[:200]))
        elif t == "system" and st in ("informational", "notification"):
            say("  system/%s: %s" % (st, json.dumps(o, ensure_ascii=False)[:260]))
        elif t == "system" and st == "init":
            say("  init: model=%s output_style=%s permissionMode=%s agents=%d skills=%d version=%s" % (
                o.get("model"), o.get("output_style"), o.get("permissionMode"), len(o.get("agents", [])), len(o.get("skills", [])), o.get("claude_code_version")))
        elif t == "system" and st in ("status", "compact_boundary"):
            say("  system/%s: %s" % (st, json.dumps({k: v for k, v in o.items() if k not in ("session_id", "uuid")}, ensure_ascii=False)[:220]))
        elif t == "assistant":
            for b in (o.get("message") or {}).get("content", []):
                if b.get("type") == "tool_use":
                    say("  tool_use %s %s" % (b.get("name"), json.dumps(b.get("input"), ensure_ascii=False)[:160]))
                elif b.get("type") == "text":
                    say("  assistant: %s" % str(b.get("text"))[:200].replace("\n", " "))
        elif t == "user":
            content = (o.get("message") or {}).get("content")
            if isinstance(content, list):
                for b in content:
                    if b.get("type") == "tool_result":
                        inner = b.get("content")
                        inner = inner if isinstance(inner, str) else json.dumps(inner, ensure_ascii=False)
                        say("  tool_result is_error=%s %s" % (b.get("is_error"), inner[:200].replace("\n", " ")))
        elif t == "result":
            say("  RESULT subtype=%s is_error=%s turns=%s terminal=%s denials=%d" % (
                o.get("subtype"), o.get("is_error"), o.get("num_turns"), o.get("terminal_reason"), len(o.get("permission_denials", []))))


def main(argv: List[str]) -> int:
    if not argv:
        say(__doc__ or "")
        return 0
    for path in argv:
        if path == "-":
            summarize(sys.stdin.read().splitlines(), "stdin")
            continue
        try:
            with open(path, encoding="utf-8-sig") as f:
                summarize(f.read().splitlines(), path)
        except OSError as exc:
            say("== %s\n  cannot read: %s" % (path, exc))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
