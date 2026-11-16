"""AI-slop phrase patterns: one list for receipt warnings and renderer tests.

Matches are reported, never rewritten. Code spans, fenced blocks and short
double-quoted phrases are skipped, so identifiers such as ``leverage_ratio`` and
text that names a pattern ("serves as") do not match.
Negative parallelism is limited to "not just X, but Y" and "not only X but also
Y"; house style such as "a finding, not a pass" must stay clean.
"""
from __future__ import annotations

import re
from typing import NamedTuple

# (id, description, compiled pattern). Order is the report order.
PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("ai-vocabulary", "inflated vocabulary: delve, pivotal, seamless, leverage, tapestry, testament, underscore",
     re.compile(r"\b(?:delv(?:e|es|ed|ing)|pivotal|seamless(?:ly)?|leverag(?:e|es|ed|ing)"
                r"|tapestr(?:y|ies)|testament|underscor(?:e|es|ed|ing))\b", re.I)),
    ("copula-avoidance", "'serve(s) as', 'stand(s) as', 'act(s) as a' in place of 'is'",
     re.compile(r"\b(?:serves? as|stands? as|acts? as an?)\b", re.I)),
    ("chatbot-frame", "chat-assistant framing",
     re.compile(r"\b(?:great question|I hope this helps|let me know if)\b", re.I)),
    ("generic-close", "line opening 'In summary', 'Overall,' or 'In conclusion'",
     re.compile(r"(?m)^[ \t>*_-]*(?:in summary\b|overall,|in conclusion\b)", re.I)),
    ("negative-parallelism", "'not just X, but Y' or 'not only X but also Y'",
     re.compile(r"\bnot just\b[^.;:\n]{1,80}?\bbut\b|\bnot only\b[^.;:\n]{1,80}?\bbut also\b", re.I)),
)
PATTERN_IDS = tuple(identifier for identifier, _, _ in PATTERNS)

_CODE = re.compile(r"(?ms)^[ \t]*(```|~~~).*?^[ \t]*\1[^\n]*$|`[^`\n]+`")
# A quoted phrase names words rather than using them; capped so a stray quote cannot hide a paragraph.
_QUOTED = re.compile(r'"[^"\n]{1,80}"|\u201c[^\u201d\n]{1,80}\u201d')
MAX_WARNINGS = 20
# Three or more vocabulary words joined only by separators enumerate the words; they do not use them.
LIST_MENTION = 3
_LIST_GAP = re.compile(r"(?:\([a-z]{1,3}\))?\s*(?:[,;/|]\s*(?:(?:and|or)\s+)?|(?:and|or)\s+)", re.I)


class Match(NamedTuple):
    pattern: str
    start: int
    end: int
    text: str


def _blank(found: re.Match[str]) -> str:
    return re.sub(r"[^\n]", " ", found.group(0))


def _mask(text: str) -> str:
    """Blank code and quoted phrases with spaces so offsets still index the original text."""
    return _QUOTED.sub(_blank, _CODE.sub(_blank, text))


def scan(text: str, patterns: tuple[str, ...] = PATTERN_IDS) -> list[Match]:
    """Every match in ``text`` as (pattern id, span, matched text), sorted by offset."""
    masked = _mask(text)
    found = [Match(identifier, item.start(), item.end(), text[item.start():item.end()])
             for identifier, _, pattern in PATTERNS if identifier in patterns
             for item in pattern.finditer(masked)]
    return sorted(_drop_lists(text, found), key=lambda item: (item.start, item.pattern))


def _drop_lists(text: str, found: list[Match]) -> list[Match]:
    """Drop vocabulary hits that form an enumeration such as "delve, pivotal, seamless(ly)"."""
    vocabulary = [item for item in found if item.pattern == "ai-vocabulary"]
    listed: set[Match] = set()
    run = vocabulary[:1]
    for previous, item in zip(vocabulary, vocabulary[1:]):
        if _LIST_GAP.fullmatch(text[previous.end:item.start]):
            run.append(item)
            continue
        if len(run) >= LIST_MENTION:
            listed.update(run)
        run = [item]
    if len(run) >= LIST_MENTION:
        listed.update(run)
    return [item for item in found if item not in listed]


def warnings(sources: dict[str, str]) -> list[dict[str, object]]:
    """Receipt warnings for named texts; bounded so a sloppy file cannot bloat the receipt."""
    result = []
    for source, text in sources.items():
        for item in scan(text):
            line = text.count("\n", 0, item.start) + 1
            result.append({"pattern": item.pattern, "source": source, "line": line,
                           "text": " ".join(item.text.split())[:120]})
    return result[:MAX_WARNINGS]
