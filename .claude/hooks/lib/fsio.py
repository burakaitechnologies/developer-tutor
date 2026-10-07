"""fsio.py - safe file reading and writing: text, JSON, JSON lines, one coarse lock, slugs.

What: read_text (BOM and UTF-16 aware), atomic write_text, append_text, read/write/update JSON,
jsonl_read / jsonl_append, trim_file / trim_jsonl, safe_slug, and Lock.
Why: hooks run in parallel (a prompt hook, a post-tool hook and a stop hook can overlap), on Windows
(antivirus and editors briefly lock files), and the data must never end up half-written.
How it fails safely: every function swallows IO errors and returns a default (False, None or the
given default); nothing here raises into a handler. Lock never blocks longer than its timeout.
Lock: ONE coarse OS-level lock per project (msvcrt.locking on Windows, fcntl.flock elsewhere; if
that is unavailable an O_EXCL file with the owner's pid and time, stale after 30 s). The OS drops
the lock when the holder dies, so a killed hook never leaves the project stuck. The lock is
re-entrant inside one process. On timeout one line goes to hook-errors.log and the caller goes on.
Who calls it: nearly every module.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional

from . import paths

sys.dont_write_bytecode = True

_LOG_MAX_BYTES = 200 * 1024
_ESCAPES = {" ": "\\u2028", " ": "\\u2029", "\u0085": "\\u0085"}
_RESERVED = {"con", "prn", "aux", "nul", "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
             "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9"}


# --------------------------------------------------------------------------- reading

def _decode(raw: bytes, truncated: bool = False) -> str:
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", errors="replace")
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        if truncated:
            for cut in (1, 2, 3):
                try:
                    return raw[:-cut].decode("utf-8")
                except UnicodeDecodeError:
                    continue
        # Not UTF-8: most likely a Windows editor (cp1252). Replace what cannot be read.
        return raw.decode("cp1252", errors="replace")


def read_text(p: str, default: str = "", max_bytes: Optional[int] = None) -> str:
    """The text of a file as str with LF line ends. UTF-8 (with or without BOM), UTF-16 with BOM,
    else cp1252. max_bytes limits how much is read. Missing or unreadable file: default."""
    try:
        with open(p, "rb") as f:
            raw = f.read(max_bytes + 1) if max_bytes is not None else f.read()
        truncated = False
        if max_bytes is not None and len(raw) > max_bytes:
            raw = raw[:max_bytes]
            truncated = True
        text = _decode(raw, truncated)
        if "\r" in text:
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        return text
    except (OSError, ValueError):
        return default


def read_json(p: str, default: Any = None) -> Any:
    """Parsed JSON, or default when missing, damaged or of another top-level type than default."""
    text = read_text(p, "")
    if not text.strip():
        return default
    try:
        value = json.loads(text)
    except ValueError:
        return default
    if isinstance(default, dict) and not isinstance(value, dict):
        return default
    if isinstance(default, list) and not isinstance(value, list):
        return default
    return value


def jsonl_read(p: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """The rows (dicts) of a JSON-lines file, oldest first; damaged lines are skipped.
    limit keeps the last N rows. Lines are split on LF only."""
    rows: List[Dict[str, Any]] = []
    text = read_text(p, "")
    if not text:
        return rows
    for line in text.split("\n"):
        line = line.strip()
        if not line or line[0] != "{":
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rows.append(obj)
    if limit is not None and limit >= 0:
        rows = rows[-limit:] if limit else []
    return rows


# --------------------------------------------------------------------------- the lock

_HELD = {"count": 0, "fd": None, "mode": "", "path": ""}


def _lock_path() -> str:
    folder = os.environ.get("TEMP") or os.environ.get("TMP") or os.environ.get("TMPDIR") or "/tmp"
    code = hashlib.sha1(os.path.normcase(os.path.abspath(paths.project_root())).encode("utf-8", "replace")).hexdigest()[:12]
    return os.path.join(folder, "claude-tutor-%s.lock" % code)


def _os_lock(fd: int) -> None:
    """Try to take the OS lock once; raises OSError when somebody else holds it."""
    if os.name == "nt":
        import msvcrt
        os.lseek(fd, 0, 0)
        msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
    else:
        import fcntl
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)


def _os_unlock(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_UN)
    except (OSError, ImportError):
        pass


class Lock(object):
    """with Lock("data"): ... - one coarse lock for all tutor data of this project."""

    def __init__(self, name: str = "data", timeout: float = 3.0) -> None:
        self.name = name
        self.timeout = timeout
        self.held = False

    def __enter__(self) -> "Lock":
        if _HELD["count"] > 0:
            _HELD["count"] += 1
            self.held = True
            return self
        deadline = time.time() + max(self.timeout, 0.0)
        path = _lock_path()
        fd = None
        try:
            fd = os.open(path, os.O_RDWR | os.O_CREAT, 0o600)
        except OSError:
            fd = None
        if fd is not None:
            try:
                while True:
                    try:
                        _os_lock(fd)
                        _HELD.update(count=1, fd=fd, mode="os", path=path)
                        self.held = True
                        return self
                    except ImportError:
                        break  # no OS lock on this system: use the file fallback
                    except OSError:
                        if time.time() >= deadline:
                            self._timeout(fd)
                            return self
                        time.sleep(0.01)
            except Exception:
                pass
            try:
                os.close(fd)
            except OSError:
                pass
        return self._fallback(path + ".x", deadline)

    def _timeout(self, fd: int) -> None:
        try:
            os.close(fd)
        except OSError:
            pass
        log_line("lock %s: waited %.1f s, went on without the lock" % (self.name, self.timeout))

    def _fallback(self, path: str, deadline: float) -> "Lock":
        """O_EXCL lock file holding 'pid time'; a lock older than 30 s counts as left over."""
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                try:
                    os.write(fd, ("%d %d" % (os.getpid(), int(time.time()))).encode("ascii"))
                finally:
                    os.close(fd)
                _HELD.update(count=1, fd=None, mode="file", path=path)
                self.held = True
                return self
            except FileExistsError:
                try:
                    if time.time() - os.path.getmtime(path) > 30:
                        os.remove(path)
                        continue
                except OSError:
                    pass
            except OSError:
                return self  # temp folder not writable: work without a lock
            if time.time() >= deadline:
                log_line("lock %s: waited %.1f s, went on without the lock" % (self.name, self.timeout))
                return self
            time.sleep(0.02)

    def __exit__(self, *args: Any) -> None:
        if not self.held:
            return
        self.held = False
        _HELD["count"] -= 1
        if _HELD["count"] > 0:
            return
        try:
            if _HELD["mode"] == "os" and _HELD["fd"] is not None:
                _os_unlock(_HELD["fd"])
                os.close(_HELD["fd"])
            elif _HELD["mode"] == "file":
                os.remove(_HELD["path"])
        except OSError:
            pass
        _HELD.update(count=0, fd=None, mode="", path="")


# --------------------------------------------------------------------------- writing

def _mkparent(p: str) -> bool:
    try:
        folder = os.path.dirname(p)
        if folder:
            os.makedirs(folder, exist_ok=True)
        return True
    except OSError:
        return False


def _to_bytes(text: str) -> bytes:
    if "\r" in text:
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.encode("utf-8", errors="replace")


def write_text(p: str, text: str) -> bool:
    """Replace a file with text: write a temporary file, then rename it over the target. Retries
    the rename for about 1 second (20 tries, 50 ms apart) on PermissionError, which Windows raises
    while another program has the file open. If it still fails, the old file stays as it was (no
    in-place overwrite, which a crash could leave cut short) and one note goes to the hook error log.
    Returns True on success."""
    if not _mkparent(p):
        return False
    tmp = "%s.tmp%d" % (p, os.getpid())
    try:
        with open(tmp, "wb") as f:
            f.write(_to_bytes(text))
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False
    for _ in range(20):
        try:
            os.replace(tmp, p)
            return True
        except PermissionError:
            time.sleep(0.05)
        except OSError:
            break
    try:
        os.remove(tmp)
    except OSError:
        pass
    log_line("write_text: the new copy could not replace the file; the old copy was kept")
    return False


def append_text(p: str, text: str) -> bool:
    """Append text with ONE os.write on an O_APPEND descriptor, under the lock."""
    if not _mkparent(p):
        return False
    data = _to_bytes(text)
    try:
        with Lock("append"):
            fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
            try:
                os.write(fd, data)
            finally:
                os.close(fd)
        return True
    except OSError:
        return False


def write_json(p: str, obj: Any) -> bool:
    try:
        text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return False
    return write_text(p, text + "\n")


def update_json(p: str, mutate: Callable[[Any], Any], default: Any = None) -> Any:
    """Read-modify-write under the lock. mutate(data) may change data in place or return a new value.
    Returns the stored value, or None when the write failed."""
    if default is None:
        default = {}
    with Lock("update"):
        data = read_json(p, default)
        try:
            result = mutate(data)
        except Exception:
            return None
        if result is not None:
            data = result
        return data if write_json(p, data) else None


def _row_text(obj: Dict[str, Any]) -> str:
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    for ch, esc in _ESCAPES.items():
        if ch in text:
            text = text.replace(ch, esc)
    return text


def jsonl_append(p: str, obj: Dict[str, Any]) -> bool:
    """Append one compact JSON row. Repairs a missing final newline first."""
    try:
        line = _row_text(obj)
    except (TypeError, ValueError):
        return False
    if not _mkparent(p):
        return False
    try:
        with Lock("append"):
            prefix = b""
            try:
                with open(p, "rb") as f:
                    f.seek(0, 2)
                    if f.tell() > 0:
                        f.seek(-1, 2)
                        if f.read(1) != b"\n":
                            prefix = b"\n"
            except OSError:
                pass
            fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
            try:
                os.write(fd, prefix + line.encode("utf-8", errors="replace") + b"\n")
            finally:
                os.close(fd)
        return True
    except OSError:
        return False


def trim_file(p: str, max_bytes: int) -> bool:
    """Keep only the last part of a file when it is larger than max_bytes (cut at a line start)."""
    try:
        size = os.path.getsize(p)
        if size <= max_bytes:
            return False
        keep = max(int(max_bytes * 0.75), 1)
        with Lock("trim"):
            with open(p, "rb") as f:
                f.seek(max(size - keep, 0))
                tail = f.read()
            nl = tail.find(b"\n")
            if 0 <= nl < len(tail) - 1:
                tail = tail[nl + 1:]
            tmp = "%s.tmp%d" % (p, os.getpid())
            with open(tmp, "wb") as f:
                f.write(tail)
            os.replace(tmp, p)
        return True
    except OSError:
        return False


def trim_jsonl(p: str, keep_rows: int) -> bool:
    """Keep only the last keep_rows rows of a JSON-lines file."""
    try:
        with Lock("trim"):
            text = read_text(p, "")
            lines = [ln for ln in text.split("\n") if ln.strip()]
            if len(lines) <= keep_rows:
                return False
            return write_text(p, "\n".join(lines[-keep_rows:]) + "\n")
    except OSError:
        return False


def log_line(text: str) -> None:
    """One line to state/hook-errors.log (only when the state folder exists). No prompt or command text."""
    try:
        folder = paths.sub("state")
        if not os.path.isdir(folder) or paths.is_link(folder):
            return
        from . import clock
        log = os.path.join(folder, "hook-errors.log")
        line = "%s %s\n" % (clock.stamp(), text.replace("\n", " ")[:300])
        fd = os.open(log, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o666)
        try:
            os.write(fd, line.encode("utf-8", errors="replace"))
        finally:
            os.close(fd)
        if os.path.getsize(log) > _LOG_MAX_BYTES:
            trim_file(log, _LOG_MAX_BYTES)
    except Exception:
        pass


# --------------------------------------------------------------------------- names

def safe_slug(text: str, max_words: int = 6, max_len: int = 40) -> str:
    """Lower-case letters and digits of any language joined by '-', at most max_words words and
    max_len characters; never empty, never a Windows device name. Combining marks are dropped without
    splitting the word: lower() turns the Turkish capital I into 'i' plus a dot, so 'Istanbul' stays one word."""
    try:
        text = unicodedata.normalize("NFC", str(text)).lower()
    except (TypeError, ValueError):
        text = ""
    words: List[str] = []
    current = ""
    for ch in text:
        if unicodedata.category(ch) == "Mn":
            continue
        if ch.isalnum():
            current += ch
        elif current:
            words.append(current)
            current = ""
    if current:
        words.append(current)
    out = ""
    for word in words[:max_words]:
        candidate = word if not out else out + "-" + word
        if len(candidate) > max_len:
            if not out:
                out = word[:max_len]
            break
        out = candidate
    if not out:
        out = "item"
    if out in _RESERVED:
        out += "-x"
    return out
