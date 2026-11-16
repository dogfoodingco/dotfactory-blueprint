"""Measure frozen-plan text pasted into handoffs and Reworking prompts.

A paste is a run of at least ``MIN_RUN`` consecutive words that also appear, in
the same order, in the frozen ``.factory/plan.md``. URIs, bare paths, inline code without spaces
(paths, identifiers) and Markdown heading lines are blanked first, so a
handoff that points at ``.factory/plan.md#L12`` or quotes a section title stays
clean. The check reports; it never rewrites text or gates a transition.

Usage: python3 -m dotfactory.pasted_plan PLAN TEXT [TEXT ...]
A TEXT ending in ``.json`` is read as a recorded handoff and flattened with
``handoff_prose``. Prints one JSON report per TEXT; exits 1 when any pastes the plan.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple

# Twelve shared words in order is a copied sentence, not a shared phrase.
MIN_RUN = 12
MAX_RUNS = 20
EXCERPT = 160

_URI = re.compile(r"\b[a-z][a-z0-9+.-]*:(?://)?[^\s)\]>\"'`]+", re.I)
# A whitespace-delimited token with two slashes, or a slash then a dot, is a path.
_PATH = re.compile(r"(?<!\S)[\w.~-]*/[\w.~-]*[/.][^\s)\]>\"'`]*")
_POINTER_CODE = re.compile(r"`[^`\s]+`")
_HEADING = re.compile(r"(?m)^[ \t]{0,3}#{1,6}[ \t].*$")
_WORD = re.compile(r"[a-z0-9]+(?:['’][a-z]+)?", re.I)


class Run(NamedTuple):
    words: int
    start: int
    end: int
    text: str


def _blank(found: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", found.group(0))


def _mask(text: str) -> str:
    """Blank pointers and headings with spaces so offsets still index the original text."""
    for pattern in (_POINTER_CODE, _URI, _PATH, _HEADING):
        text = pattern.sub(_blank, text)
    return text


def words(text: str) -> list[tuple[str, int, int]]:
    """Lowercased words with their offsets in ``text``, after masking pointers and headings."""
    return [(item.group(0).lower().replace("’", "'"), item.start(), item.end())
            for item in _WORD.finditer(_mask(text))]


def _shingles(tokens: list[str], size: int) -> set[tuple[str, ...]]:
    return {tuple(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def scan(text: str, plan: str, min_run: int = MIN_RUN) -> list[Run]:
    """Maximal runs of ``min_run``+ words in ``text`` that occur verbatim in ``plan``."""
    plan_words = [word for word, _, _ in words(plan)]
    found = words(text)
    if min_run < 1 or len(plan_words) < min_run or len(found) < min_run:
        return []
    shared = _shingles(plan_words, min_run)
    tokens = [word for word, _, _ in found]
    hits = [tuple(tokens[index:index + min_run]) in shared for index in range(len(tokens) - min_run + 1)]
    runs: list[Run] = []
    index = 0
    while index < len(hits):
        if not hits[index]:
            index += 1
            continue
        last = index
        while last + 1 < len(hits) and hits[last + 1]:
            last += 1
        start, end = found[index][1], found[last + min_run - 1][2]
        runs.append(Run(last - index + min_run, start, end, text[start:end]))
        index = last + 1
    return runs


def handoff_prose(value: Any) -> str:
    """Prose string leaves of a recorded handoff; ids, URIs and timestamps contain no spaces."""
    if isinstance(value, dict):
        parts = [handoff_prose(item) for item in value.values()]
    elif isinstance(value, list):
        parts = [handoff_prose(item) for item in value]
    elif isinstance(value, str) and " " in value.strip():
        return value
    else:
        return ""
    return "\n\n".join(part for part in parts if part)


def report(text: str, plan: str, min_run: int = MIN_RUN) -> dict[str, object]:
    """Deterministic summary: whether ``text`` pastes ``plan``, and how much."""
    plan_words = len(words(plan))
    text_words = len(words(text))
    runs = scan(text, plan, min_run)
    copied = sum(run.words for run in runs)
    return {
        "measurable": plan_words >= min_run,
        "pasted": bool(runs),
        "min_run": min_run,
        "plan_words": plan_words,
        "text_words": text_words,
        "copied_words": copied,
        "copied_share": round(copied / text_words, 4) if text_words else 0.0,
        "longest_run": max((run.words for run in runs), default=0),
        "runs": [{"words": run.words, "start": run.start, "end": run.end,
                  "excerpt": " ".join(run.text.split())[:EXCERPT]} for run in runs[:MAX_RUNS]],
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: python3 -m dotfactory.pasted_plan PLAN TEXT [TEXT ...]", file=sys.stderr)
        return 2
    plan = Path(argv[0]).read_text(encoding="utf-8")
    pasted = False
    for name in argv[1:]:
        text = Path(name).read_text(encoding="utf-8")
        if name.endswith(".json"):
            text = handoff_prose(json.loads(text))
        result = report(text, plan)
        pasted = pasted or bool(result["pasted"])
        print(json.dumps({"source": name, **result}, sort_keys=True))
    return 1 if pasted else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
