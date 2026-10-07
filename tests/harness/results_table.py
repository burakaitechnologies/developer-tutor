"""results_table.py - turn a results file of test_mock_cli.py (--json) into the release table of RESULTS-TEMPLATE.md.

What: prints a Markdown table with one row per scenario: id, what it proves, result, date, Claude Code version.
Why: the release notes (docs/test-report.md) must say, for every scenario, when it ran and with which Claude Code.
How it fails safely: read-only; a missing or damaged file is reported in one line. Python 3.9 syntax, stdlib only.
Use:  python results_table.py results.json [more.json ...]
"""
from __future__ import annotations

import json
import sys
from typing import Any, Dict, List

sys.dont_write_bytecode = True


def say(text: str) -> None:
    sys.stdout.buffer.write((text + "\n").encode("utf-8", errors="replace"))


def cell(text: Any) -> str:
    return " ".join(str(text).split()).replace("|", "/")


def main(argv: List[str]) -> int:
    if not argv:
        say(__doc__ or "")
        return 0
    say("| Test id | What it proves | Result | Date | Claude Code version |")
    say("|---|---|---|---|---|")
    for path in argv:
        try:
            with open(path, encoding="utf-8-sig") as f:
                data: Dict[str, Any] = json.load(f)
        except (OSError, ValueError) as exc:
            say("| (%s) | cannot read: %s | | | |" % (cell(path), cell(exc)))
            continue
        version = cell(data.get("claude", "")).replace("(Claude Code)", "").strip()
        for row in data.get("results", []):
            result = row.get("status", "")
            if result == "FAIL":
                result = "FAIL: " + cell(row.get("problems", [""])[0])[:90]
            elif result == "SKIP":
                result = "SKIP: " + cell(row.get("problems", [""])[0])[:90]
            say("| %s | %s | %s | %s | %s |" % (cell(row.get("id")), cell(row.get("doc")), cell(result), cell(data.get("date", "")), version))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
