"""Graphic cues: when each part of a graphic appears, from the narration's word timings.

A KeyPoints point should appear when the narrator starts talking about it, and a BigNumber's
number when the number is spoken. The script usually paraphrases (point "10–15 जगहों से मिट्टी",
narration "खेत की कई जगहों से लें"), so cues are found by matching the point's meaningful words:

- words are compared as `canon()` letters (numbers → words, so "3" matches "तीन" and "2.5–3"
  matches "2.5-3"; nukta and nasal marks unified), and match when equal or when they share their
  first 4 letters (सुखाएं / सुखाकर, चीज़ों / चीज़ें);
- small words (से, के, और, …) are ignored unless the phrase has nothing else;
- for each point, in order, the window of narration words (after the previous point's cue)
  with the longest in-order match of the point's words wins; ties go to the earliest; the cue
  is the start of the first matched word of the tightest match.

Explicit cues override the automatic match: `props.cues` (KeyPoints, one phrase or null per
point) and `props.cue` (BigNumber), written as they appear in narration_display. An explicit cue
that isn't found is an error (validate); an automatic miss falls back to the old timing
(points spread over the first 60% of the scene; the number from the scene start) with a warning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from pipeline.schema import AudioWord, Scene
from pipeline.take_scoring import canon

STOP = set("में से को का की के पर तक ने और या कि तो भी ही है हैं हो एक इस उस यह वह जो".split())
STEM = 4  # letters two words must share to count as the same word (inflections)


def _tok(text: str) -> list[str]:
    return [c for c in (canon(w) for w in text.split()) if c]


def _same(a: str, b: str) -> bool:
    if a == b:
        return True
    return len(a) >= STEM and len(b) >= STEM and a[:STEM] == b[:STEM]


def _lcs(ws: list[str], key: list[str]) -> int:
    """Longest in-order match between narration words and the phrase's words."""
    prev = [0] * (len(key) + 1)
    for w in ws:
        cur = [0]
        for j, k in enumerate(key, 1):
            cur.append(prev[j - 1] + 1 if _same(w, k) else max(prev[j], cur[j - 1]))
        prev = cur
    return prev[-1]


def find_phrase(words: list[AudioWord], phrase: str, after: int = 0) -> tuple[int | None, int, int]:
    """(index of the first matched word, words matched in order, meaningful words in the phrase).
    Index None when nothing matched. Words must come in the phrase's order, so a repeated word
    (the "पास" ending the previous point) can't pull the cue back."""
    toks = _tok(phrase)
    key = [t for t in toks if t not in STOP] or toks
    if not key:
        return None, 0, 0
    wt = [canon(w.text) for w in words]
    span = len(toks) + 3
    best: tuple[int, int] | None = None  # (score, first matched index)
    for j in range(after, len(words)):
        window = wt[j:j + span]
        score = _lcs(window, key)
        if not score or (best is not None and score <= best[0]):
            continue
        # the tightest match: the latest start that still matches as many words
        start = max(i for i in range(len(window)) if _lcs(window[i:], key) == score)
        best = (score, j + start)
    if best is None:
        return None, 0, len(key)
    return best[1], best[0], len(key)


@dataclass
class SceneCues:
    times: list[float | None] = field(default_factory=list)   # seconds in the scene audio, per cue
    problems: list[tuple[str, str]] = field(default_factory=list)  # (error|warning, message)


def scene_cues(scene: Scene) -> SceneCues | None:
    """Cue times for a graphic scene (KeyPoints: one per point; BigNumber: one), or None when the
    scene has no cueable graphic. Without word timings every time is None (old timing)."""
    v = scene.visual
    if v.type != "graphic" or v.template not in ("KeyPoints", "BigNumber") or not v.props:
        return None
    if v.template == "KeyPoints":
        phrases = [str(p) for p in v.props.get("points") or []]
        explicit = list(v.props.get("cues") or [])
        explicit += [None] * (len(phrases) - len(explicit))
    else:
        phrases = [str(v.props.get("number", ""))]
        explicit = [v.props.get("cue")]
    out = SceneCues()
    words = scene.audio.words if scene.audio else []
    if not words:
        out.times = [None] * len(phrases)
        return out
    after = 0
    for n, (phrase, cue) in enumerate(zip(phrases, explicit), 1):
        what = f"point {n}" if v.template == "KeyPoints" else "number"
        if cue:
            idx, got, need = find_phrase(words, str(cue), after)
            if idx is None or got < need:
                out.problems.append(("error", f"{what}: cue “{cue}” not found in the narration"
                                     + (" after the previous cue" if after else "")))
                idx = None
        else:
            idx, got, need = find_phrase(words, phrase, after)
            if idx is None and v.template == "BigNumber":  # number not spoken as written: try unit, label
                for alt in (v.props.get("unit"), v.props.get("label")):
                    if alt:
                        idx, got, need = find_phrase(words, str(alt), after)
                        if idx is not None:
                            break
            if idx is None:
                out.problems.append(("warning", f"{what} “{phrase}”: no matching words in the narration; "
                                     "it appears on the old schedule (set props.cue/cues to fix)"))
        out.times.append(None if idx is None else words[idx].start)
        if idx is not None:
            after = idx + 1
    return out
