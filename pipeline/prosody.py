"""Delivery markup and sentence segmentation for narration.

The script may carry light markup in `narration_display` (it survives text_normalize into
`narration_spoken`):

    |        short breath pause (also splits the TTS segment there)
    ||       long pause, e.g. after a question or before the key point
    {style}  at the start of a segment: delivery style from config `narration.styles`
             (e.g. {slow} before a number, {warm} for the closing line)

Captions, word counts and validate always see the text with markup stripped.

Narration is synthesized one segment at a time. A segment ends at a sentence mark
(। ? !) or a pause mark, and records which pause follows it. Without markup, a scene
is simply split into sentences.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

STYLE_RE = re.compile(r"\{([a-z_]+)\}\s*")
# a segment boundary: || or | (pause marks), or whitespace after a sentence mark
_BOUNDARY = re.compile(r"\s*(\|\||\|)\s*|(?<=[।?!])\s+")


@dataclass
class Segment:
    text: str              # text to speak/show, markup removed
    pause: str             # what follows: sentence | question | exclaim | short | long | end
    style: str | None = None  # explicit {style}, if any


def strip_markup(text: str) -> str:
    """Text as the viewer sees it: no | || or {style}."""
    t = STYLE_RE.sub("", text)
    t = re.sub(r"\s*\|\|?\s*", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def has_markup(text: str) -> bool:
    return "|" in text or bool(STYLE_RE.search(text))


def _ending_pause(text: str) -> str:
    t = text.rstrip()
    if t.endswith("?"):
        return "question"
    if t.endswith("!"):
        return "exclaim"
    return "sentence"


def split_segments(text: str) -> list[Segment]:
    segs: list[Segment] = []
    pos = 0
    for m in list(_BOUNDARY.finditer(text)) + [None]:
        end = m.start() if m else len(text)
        piece = text[pos:end].strip()
        if piece:
            style = None
            sm = STYLE_RE.match(piece)
            if sm:
                style, piece = sm.group(1), piece[sm.end():].strip()
            piece = STYLE_RE.sub("", piece).strip()  # stray {style} mid-segment: ignore
            if m is None:
                pause = "end"
            elif m.group(1) == "||":
                pause = "long"
            elif m.group(1) == "|":
                pause = "short"
            else:
                pause = _ending_pause(piece)
            if piece:
                segs.append(Segment(piece, pause, style))
            elif segs and m is not None and m.group(1):
                # a pause mark right after a sentence mark: the longer pause wins
                segs[-1].pause = "long" if m.group(1) == "||" else max(segs[-1].pause, "short", key=_PAUSE_RANK.get)
        if m:
            pos = m.end()
    return segs


_PAUSE_RANK = {"end": 0, "short": 1, "sentence": 2, "exclaim": 3, "question": 4, "long": 5}


def paired_segments(display: str, spoken: str) -> list[tuple[Segment, Segment]]:
    """Split display and spoken text the same way. They must line up one to one,
    because captions are timed from the spoken segments' audio."""
    d, s = split_segments(display), split_segments(spoken)
    if len(d) != len(s):
        raise ValueError(f"display has {len(d)} segments but spoken has {len(s)}; rebuild narration_spoken "
                         f"(text_normalize --force) so both carry the same punctuation and markup")
    return list(zip(d, s))


def auto_style(seg: Segment, display_text: str, purpose: str, index: int, rules: dict) -> str:
    """Delivery style for a segment: explicit {style} first, then config rules
    (question mark, digits in what the viewer sees, scene purpose), else 'neutral'."""
    if seg.style:
        return seg.style
    if seg.text.rstrip().endswith("?") and rules.get("question"):
        return rules["question"]
    if re.search(r"[0-9०-९]", display_text) and rules.get("digits"):
        return rules["digits"]
    by_purpose = rules.get("purpose", {}) or {}
    if purpose in by_purpose:
        return by_purpose[purpose]
    return "neutral"
