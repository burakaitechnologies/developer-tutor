"""mock_api.py - a tiny stand-in for the Anthropic Messages API, so the REAL Claude Code CLI can run offline.

What: an HTTP server on 127.0.0.1 that answers POST /v1/messages (streaming and not) and
/v1/messages/count_tokens. It logs every request body, which is exactly what a real model would receive
(system prompt, CLAUDE.md block, skill list, hook text, tool results).
Why: the login of a build machine may be expired, and a model is not needed to test what Claude Code loads,
delivers, permits, blocks and which hooks it runs. The mock is NOT a model: it proves delivery, wording,
order and exit codes, never how a real model reacts.
How it fails safely: it binds to 127.0.0.1 only, uses a free port, answers every unknown path with a 404 and
never contacts any other host. Standard library only, Python 3.9 syntax.
Who calls it: harness/mockcli.py (start_mock). It can also be started by hand:
  python mock_api.py --logdir DIR [--port N] [--scenario FILE.json]

Directives (a line of the LAST user message, outside system-reminder blocks; the mock answers with a tool call):
  RUN: <command>            Bash tool call
  PS: <command>             PowerShell tool call
  READ: <path>              Read tool call
  WRITE: <path>             Write tool call with the content "written by mock"
  TOOL: <json>              one tool call: {"name": "Write", "input": {...}}
  TOOLS: <json list>        several tool calls in ONE assistant message
  SKILL: <name>             Skill tool call
  AGENT: <prompt>           Agent tool call (foreground, general-purpose)
  anything else             text "MOCK-REPLY seen_tokens=[...]"; a token is any string like ABCTOK-1 found
                            anywhere in the request, so a planted token proves whether text reached the model.
After a tool result the mock answers with text:
  MOCK-AFTER-TOOL is_error=<bool> result=<the result text>      (several results: numbered)
A request without tools (title, summary, side queries) gets a short text. A request that looks like a
conversation summary request is answered with a <summary> block so that /compact works.
A scenario file (JSON list) can replace the directives: each entry answers one request that offers tools:
  {"text": "hello", "tool_uses": [{"name": "Read", "input": {"file_path": "a"}}]}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple

sys.dont_write_bytecode = True

TOKEN_RE = re.compile(r"[A-Z]{2,}TOK[-_A-Za-z0-9]*")
DIRECTIVE_RE = re.compile(r"^[ \t]*(RUN|PS|READ|WRITE|TOOL|TOOLS|SKILL|AGENT):[ \t]*(.*)$", re.MULTILINE)
SUMMARY_HINTS = ("create a detailed summary", "summary of the conversation", "summarize the conversation",
                 "write a summary", "<summary>")
SECRET_HEADERS = ("x-api-key", "authorization", "cookie")
KEPT_HEADERS = ("anthropic-beta", "anthropic-version", "user-agent", "x-app", "x-claude-code-session-id")


def flatten_text(content: Any) -> str:
    """Plain text of a message content (string or list of blocks); tool results are marked."""
    if isinstance(content, str):
        return content
    parts: List[str] = []
    for block in content or []:
        if not isinstance(block, dict):
            continue
        kind = block.get("type")
        if kind == "text":
            parts.append(str(block.get("text", "")))
        elif kind == "tool_result":
            inner = block.get("content")
            parts.append("[tool_result:%s]" % (flatten_text(inner) if inner is not None else ""))
        elif kind == "tool_use":
            parts.append("[tool_use:%s %s]" % (block.get("name"), json.dumps(block.get("input"), ensure_ascii=False)))
    return "\n".join(parts)


def system_text(body: Dict[str, Any]) -> str:
    system = body.get("system")
    if isinstance(system, str):
        return system
    if isinstance(system, list):
        return "\n".join(str(b.get("text", "")) for b in system if isinstance(b, dict))
    return ""


def tool_names(body: Dict[str, Any]) -> List[str]:
    return [str(t.get("name")) for t in (body.get("tools") or []) if isinstance(t, dict)]


def last_user_message(messages: List[Any]) -> Optional[Dict[str, Any]]:
    """The newest message with role user (the CLI may append trailing system-role messages)."""
    for message in reversed(messages or []):
        if isinstance(message, dict) and message.get("role") == "user":
            return message
    return None


def user_directive_text(content: Any) -> str:
    """The text blocks of a user message that are not system-reminder blocks, joined."""
    if isinstance(content, str):
        return content
    texts = []
    for block in content or []:
        if isinstance(block, dict) and block.get("type") == "text":
            text = str(block.get("text", ""))
            if not text.lstrip().startswith("<system-reminder>"):
                texts.append(text)
    return "\n".join(texts)


def _tool_use(name: str, tool_input: Dict[str, Any]) -> Dict[str, Any]:
    return {"id": "toolu_" + uuid.uuid4().hex[:20], "name": name, "input": tool_input}


def decide(body: Dict[str, Any]) -> Tuple[Optional[str], List[Dict[str, Any]]]:
    """(text, tool_uses) for one request. Pure function of the request body."""
    names = tool_names(body)
    message = last_user_message(body.get("messages") or [])
    content = message.get("content") if message else ""
    flat_request = json.dumps(body, ensure_ascii=False)
    last_text = flatten_text(content)
    # The /compact request offers tools but asks for text only; answer it with a summary block.
    if "Respond with TEXT ONLY" in last_text or (not names and any(h in last_text.lower() for h in SUMMARY_HINTS)):
        return "<analysis>mock</analysis>\n<summary>MOCK-COMPACT-SUMMARY of the conversation so far.</summary>", []
    if not names:
        return "MOCK-SIDE-REPLY", []
    results = []
    if isinstance(content, list):
        results = [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]
    if results:
        shown = []
        for index, block in enumerate(results):
            text = flatten_text(block.get("content"))[:3000]
            line = "is_error=%s result=%s" % (block.get("is_error"), text)
            shown.append(line if len(results) == 1 else "[%d] %s" % (index + 1, line))
        return "MOCK-AFTER-TOOL " + " ".join(shown), []
    wanted = user_directive_text(content)
    found = {m.group(1): m.group(2).strip() for m in DIRECTIVE_RE.finditer(wanted)}
    # Which directive wins when several are present: the first one in the text.
    first = DIRECTIVE_RE.search(wanted)
    if first:
        kind, arg = first.group(1), found[first.group(1)]
        tool_for = {"RUN": "Bash", "PS": "PowerShell", "READ": "Read", "WRITE": "Write", "SKILL": "Skill", "AGENT": "Agent"}
        if kind in tool_for and tool_for[kind] not in names:
            return "MOCK-NO-TOOL %s (tools offered: %s)" % (tool_for[kind], ",".join(names)), []
        if kind == "RUN":
            return None, [_tool_use("Bash", {"command": arg, "description": "mock run"})]
        if kind == "PS":
            return None, [_tool_use("PowerShell", {"command": arg, "description": "mock ps run"})]
        if kind == "READ":
            return None, [_tool_use("Read", {"file_path": arg})]
        if kind == "WRITE":
            return None, [_tool_use("Write", {"file_path": arg, "content": "written by mock\n"})]
        if kind == "SKILL":
            return None, [_tool_use("Skill", {"skill": arg})]
        if kind == "AGENT":
            return None, [_tool_use("Agent", {"description": "mock subagent", "prompt": arg, "subagent_type": "general-purpose",
                                              "run_in_background": False})]
        try:
            parsed = json.loads(arg)
        except ValueError:
            return "MOCK-BAD-DIRECTIVE %s: not valid JSON" % kind, []
        items = [parsed] if kind == "TOOL" else parsed
        uses = []
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get("name") in names:
                uses.append(_tool_use(str(item["name"]), item.get("input") if isinstance(item.get("input"), dict) else {}))
            elif isinstance(item, dict):
                return "MOCK-NO-TOOL %s (tools offered: %s)" % (item.get("name"), ",".join(names)), []
        return (None, uses) if uses else ("MOCK-BAD-DIRECTIVE %s" % kind, [])
    tokens = sorted(set(TOKEN_RE.findall(flat_request)))
    return "MOCK-REPLY seen_tokens=%s" % tokens, []


class MockServer(object):
    """The server plus its request log. Use start() / stop(); requests is a list of dicts (n, path, headers, body)."""

    def __init__(self, logdir: Optional[str] = None, port: int = 0, scenario: Optional[List[Dict[str, Any]]] = None,
                 req_files: bool = False) -> None:
        self.logdir = logdir
        self.req_files = req_files          # also write req-NNN.json per request (the layout of the first experiments)
        self.scenario = scenario
        self.scenario_index = 0
        self.requests: List[Dict[str, Any]] = []
        self.other_paths: List[str] = []
        self.lock = threading.Lock()
        outer = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args: Any) -> None:  # silent
                pass

            def handle(self) -> None:
                try:
                    super().handle()
                except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
                    pass

            def _send_json(self, code: int, obj: Any) -> None:
                raw = json.dumps(obj).encode("utf-8")
                self.send_response(code)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self) -> None:
                outer.other_paths.append("GET " + self.path)
                self._send_json(404, {"type": "error", "error": {"type": "not_found_error", "message": "mock"}})

            def do_POST(self) -> None:
                outer.handle_post(self)

        self.httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.url = "http://127.0.0.1:%d" % self.port
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    def start(self) -> "MockServer":
        if self.logdir:
            os.makedirs(self.logdir, exist_ok=True)
        self.thread.start()
        return self

    def stop(self) -> None:
        try:
            self.httpd.shutdown()
            self.httpd.server_close()
        except OSError:
            pass

    # ------------------------------------------------------------------ request handling

    def _scenario_reply(self, body: Dict[str, Any]) -> Optional[Tuple[Optional[str], List[Dict[str, Any]], bool]]:
        """(text, tool_uses, consumed an entry) from the scenario list, or None when there is no scenario."""
        if self.scenario is None or not tool_names(body):
            return None
        with self.lock:
            if self.scenario_index >= len(self.scenario):
                return "MOCK_DONE", [], False
            entry = self.scenario[self.scenario_index]
            self.scenario_index += 1
        uses = [_tool_use(str(u["name"]), u.get("input") or {}) for u in entry.get("tool_uses", [])]
        text = entry.get("text")
        return (text if text is not None else (None if uses else "MOCK_EMPTY")), uses, True

    def handle_post(self, h: BaseHTTPRequestHandler) -> None:
        length = int(h.headers.get("content-length") or 0)
        raw = h.rfile.read(length) if length else b""
        path = h.path.split("?")[0]
        if path.endswith("/messages/count_tokens"):
            self.other_paths.append("POST " + h.path)
            return h._send_json(200, {"input_tokens": 1234})  # type: ignore[attr-defined]
        if not path.endswith("/messages"):
            self.other_paths.append("POST " + h.path)
            return h._send_json(404, {"type": "error", "error": {"type": "not_found_error", "message": "mock " + h.path}})  # type: ignore[attr-defined]
        try:
            body = json.loads(raw.decode("utf-8"))
        except ValueError:
            return h._send_json(400, {"type": "error", "error": {"type": "invalid_request_error", "message": "bad json"}})  # type: ignore[attr-defined]
        headers = {k: v for k, v in h.headers.items() if k.lower() in KEPT_HEADERS}
        scripted = self._scenario_reply(body)
        text, uses = (scripted[0], scripted[1]) if scripted else decide(body)
        with self.lock:
            number = len(self.requests) + 1
            record = {"n": number, "ts": time.time(), "path": h.path, "headers": headers,
                      "has_key_header": any(h.headers.get(k) for k in SECRET_HEADERS),
                      "consumed_scenario_entry": bool(scripted and scripted[2]), "body": body}
            self.requests.append(record)
        if self.logdir:
            try:
                with open(os.path.join(self.logdir, "requests.jsonl"), "a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
                if self.req_files:
                    with open(os.path.join(self.logdir, "req-%03d.json" % number), "w", encoding="utf-8", newline="\n") as f:
                        json.dump(dict(record, has_api_key_header=record["has_key_header"]), f, indent=1, ensure_ascii=False)
            except OSError:
                pass
        model = str(body.get("model") or "claude-mock")
        message_id = "msg_" + uuid.uuid4().hex[:20]
        if not body.get("stream"):
            blocks: List[Dict[str, Any]] = [dict(type="tool_use", **u) for u in uses] if uses else [{"type": "text", "text": text or ""}]
            return h._send_json(200, {"id": message_id, "type": "message", "role": "assistant", "model": model, "content": blocks,  # type: ignore[attr-defined]
                                      "stop_reason": "tool_use" if uses else "end_turn", "stop_sequence": None,
                                      "usage": {"input_tokens": 100, "output_tokens": 20}})
        h.send_response(200)
        h.send_header("content-type", "text/event-stream")
        h.send_header("cache-control", "no-cache")
        h.send_header("transfer-encoding", "chunked")
        h.end_headers()

        def event(name: str, obj: Dict[str, Any]) -> None:
            payload = ("event: %s\ndata: %s\n\n" % (name, json.dumps(obj))).encode("utf-8")
            h.wfile.write(("%x\r\n" % len(payload)).encode("ascii") + payload + b"\r\n")
            h.wfile.flush()

        try:
            event("message_start", {"type": "message_start", "message": {
                "id": message_id, "type": "message", "role": "assistant", "model": model, "content": [],
                "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 100, "output_tokens": 1}}})
            index = 0
            if text:
                event("content_block_start", {"type": "content_block_start", "index": index, "content_block": {"type": "text", "text": ""}})
                event("content_block_delta", {"type": "content_block_delta", "index": index, "delta": {"type": "text_delta", "text": text}})
                event("content_block_stop", {"type": "content_block_stop", "index": index})
                index += 1
            for use in uses:
                event("content_block_start", {"type": "content_block_start", "index": index,
                                              "content_block": {"type": "tool_use", "id": use["id"], "name": use["name"], "input": {}}})
                event("content_block_delta", {"type": "content_block_delta", "index": index,
                                              "delta": {"type": "input_json_delta", "partial_json": json.dumps(use["input"])}})
                event("content_block_stop", {"type": "content_block_stop", "index": index})
                index += 1
            event("message_delta", {"type": "message_delta", "delta": {"stop_reason": "tool_use" if uses else "end_turn", "stop_sequence": None},
                                    "usage": {"output_tokens": 20}})
            event("message_stop", {"type": "message_stop"})
            h.wfile.write(b"0\r\n\r\n")
            h.wfile.flush()
        except (ConnectionResetError, BrokenPipeError, ConnectionAbortedError):
            pass


def serve(logdir: Optional[str] = None, port: int = 0, scenario: Optional[List[Dict[str, Any]]] = None,
          req_files: bool = False) -> MockServer:
    return MockServer(logdir, port, scenario, req_files).start()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Mock of the Anthropic Messages API for offline Claude Code tests.")
    parser.add_argument("--logdir", required=True)
    parser.add_argument("--port", type=int, default=0, help="0 = any free port")
    parser.add_argument("--scenario", help="JSON list of scripted replies")
    args = parser.parse_args(argv)
    scenario = None
    if args.scenario:
        with open(args.scenario, encoding="utf-8-sig") as f:
            scenario = json.load(f)
    server = serve(args.logdir, args.port, scenario)
    sys.stdout.write("mock listening on %s, log in %s\n" % (server.url, args.logdir))
    sys.stdout.flush()
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
