"""requests_view.py - look at what the mock API received, which is exactly what the model would have seen.

What: reads a mock log (requests.jsonl, written by mock_api.py when it has a logdir) and prints an overview of
every request, the text blocks of one request, tool call / tool result pairs, or where a token appears.
Why: "did my text reach the model, and where?" is the main question of every mock-CLI test.
How it fails safely: read-only; unreadable lines are skipped; output is UTF-8 bytes (safe on a cp1252 console).
Python 3.9 syntax, standard library only.
Use:
  python requests_view.py LOG                      overview of all requests
  python requests_view.py LOG -r 2 --blocks        every text block of request 2 (role, size, first 160 chars)
  python requests_view.py LOG -r 2 --system        the top-level system prompt of request 2
  python requests_view.py LOG -r 2 --msgs [--max N]  all messages of request 2, cut at N characters (default 2500)
  python requests_view.py LOG --pairs              tool_use -> tool_result pairs seen in the longest conversation
  python requests_view.py LOG -g TOKEN1 TOKEN2     which request and which part contains each token
LOG is requests.jsonl or the folder that holds it.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

sys.dont_write_bytecode = True


def say(text: str) -> None:
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))
    sys.stdout.flush()


def load(path: str) -> List[Dict[str, Any]]:
    if os.path.isdir(path):
        path = os.path.join(path, "requests.jsonl")
    rows = []
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            line = line.strip()
            if line.startswith("{"):
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    return rows


def system_text(body: Dict[str, Any]) -> str:
    system = body.get("system")
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(str(b.get("text", "")) for b in system if isinstance(b, dict))
    return ""


def blocks(content: Any) -> List[Tuple[str, str]]:
    if isinstance(content, str):
        return [("text", content)]
    out: List[Tuple[str, str]] = []
    for c in content or []:
        if not isinstance(c, dict):
            continue
        kind = c.get("type")
        if kind == "text":
            out.append(("text", str(c.get("text", ""))))
        elif kind == "tool_use":
            out.append(("tool_use", json.dumps({"name": c.get("name"), "input": c.get("input")}, ensure_ascii=False)))
        elif kind == "tool_result":
            inner = c.get("content")
            if isinstance(inner, list):
                inner = "\n".join(str(x.get("text", "")) for x in inner if isinstance(x, dict))
            out.append(("tool_result" + ("(ERR)" if c.get("is_error") else ""), str(inner)))
        else:
            out.append((str(kind), json.dumps(c)[:300]))
    return out


def main(argv: List[str]) -> int:
    ap = argparse.ArgumentParser(description="Look at what the mock API received.")
    ap.add_argument("log")
    ap.add_argument("-r", type=int, help="request number (n in the overview)")
    ap.add_argument("--blocks", action="store_true")
    ap.add_argument("--system", action="store_true")
    ap.add_argument("--msgs", action="store_true")
    ap.add_argument("--pairs", action="store_true")
    ap.add_argument("-g", nargs="*")
    ap.add_argument("--max", type=int, default=2500)
    args = ap.parse_args(argv)
    rows = load(args.log)
    if args.g:
        for row in rows:
            body = row["body"]
            places = {"system": system_text(body)}
            for i, msg in enumerate(body.get("messages", [])):
                places["msg%d(%s)" % (i, msg.get("role"))] = "\n".join(v for _, v in blocks(msg.get("content")))
            found = ["%s=%s" % (tok, [k for k, v in places.items() if tok in v] or "-") for tok in args.g]
            say("req%03d tools=%d | %s" % (row["n"], len(body.get("tools") or []), " | ".join(found)))
        return 0
    if args.pairs:
        best = max(rows, key=lambda r: len(r["body"].get("messages", [])), default=None)
        uses: Dict[str, Dict[str, Any]] = {}
        for msg in (best["body"].get("messages", []) if best else []):
            if isinstance(msg.get("content"), list):
                for c in msg["content"]:
                    if c.get("type") == "tool_use":
                        uses[c["id"]] = c
        for msg in (best["body"].get("messages", []) if best else []):
            if isinstance(msg.get("content"), list):
                for c in msg["content"]:
                    if c.get("type") == "tool_result":
                        use = uses.get(c.get("tool_use_id"), {})
                        text = dict(blocks([c])).get("tool_result", "") or dict(blocks([c])).get("tool_result(ERR)", "")
                        say("%s %s\n    => %s%s" % (use.get("name"), json.dumps(use.get("input"), ensure_ascii=False)[:200],
                                                   "[ERR] " if c.get("is_error") else "", text[:args.max].replace("\n", " | ")))
        return 0
    if args.r is None:
        for row in rows:
            body = row["body"]
            msgs = body.get("messages", [])
            last = msgs[-1] if msgs else {}
            kinds = ",".join(k for k, _ in blocks(last.get("content"))) if last else ""
            say("req%03d model=%s stream=%s system=%dch tools=%d msgs=%d last=[%s:%s]" % (
                row["n"], body.get("model"), body.get("stream"), len(system_text(body)), len(body.get("tools") or []), len(msgs), last.get("role"), kinds))
        return 0
    chosen = [r for r in rows if r["n"] == args.r]
    if not chosen:
        say("no request number %d" % args.r)
        return 1
    body = chosen[0]["body"]
    if args.system:
        say(system_text(body))
    if args.blocks or args.msgs:
        for i, msg in enumerate(body.get("messages", [])):
            for j, (kind, text) in enumerate(blocks(msg.get("content"))):
                if args.msgs:
                    shown = text if len(text) <= args.max else text[:args.max] + "...[+%d chars]" % (len(text) - args.max)
                    say("=== msg%d %s %s ===\n%s" % (i, msg.get("role"), kind, shown))
                else:
                    say("msg%d.%d %-8s %-12s %6d  %s" % (i, j, msg.get("role"), kind, len(text), text[:160].replace("\n", " | ")))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
