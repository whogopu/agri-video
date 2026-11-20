"""Split narration_display into caption chunks and time them across the scene's audio.

Chunks: break at punctuation first (। ? ! , ; : —), then split long clauses into near-equal
parts of at most `max_words`, then fold tiny leftovers (1–2 words) into a neighbour.
Timing: from word timings when the scene has them (`word_captions`: a chunk appears just before
its first word is spoken and stays up until the next chunk, carrying its words for the
highlight); otherwise proportional to character length across the audio (`build_captions`).
"""

from __future__ import annotations

import math
import re

from pipeline.schema import AudioWord, Caption, CaptionWord

CLAUSE_RE = re.compile(r"(?<=[।?!,;:—])\s+")

# A chunk reads best when it ends after a postposition/auxiliary/conjunction…
GOOD_END = set("में से को का की के पर तक लिए है हैं था थे थी हो हों और या कि तो भी ही नहीं करें करते करना डालें लें".split())
# …and badly when it ends on a word that opens a phrase (कौन | सा, बिना | जांच).
BAD_END = set("कौन क्या कितना कितनी बिना हर एक इस उस यह वह अपने अपनी आपके आपका सबसे बहुत".split())
# Good words to START the next chunk with.
GOOD_START = set("और कि क्योंकि लेकिन पर तो कौन क्या जो जब अगर इसलिए ताकि".split())
POSTPOSITIONS = set("में से को का की के पर तक ने".split())


def _split_phrases(words: list[str], max_words: int) -> list[list[str]]:
    """Split a long clause into chunks of ≤ max_words, choosing each break at the best word boundary."""
    chunks, i = [], 0
    while len(words) - i > max_words:
        remaining = len(words) - i
        k = math.ceil(remaining / max_words)
        ideal = math.ceil(remaining / k)  # even split length
        best, best_score = None, None
        for n in range(max(2, ideal - 2), min(max_words, remaining - 1) + 1):
            last = words[i + n - 1].strip(".,?!।")
            nxt = words[i + n].strip(".,?!।")
            score = (-abs(n - ideal) + 3 * (last in GOOD_END) + 2 * (nxt in GOOD_START)
                     - 5 * (last in BAD_END) - 4 * (nxt in POSTPOSITIONS))
            if best_score is None or score > best_score:
                best, best_score = n, score
        chunks.append(words[i:i + best])
        i += best
    chunks.append(words[i:])
    return chunks


def chunk_text(text: str, max_words: int) -> list[str]:
    chunks: list[list[str]] = []
    for clause in CLAUSE_RE.split(text.strip()):
        words = clause.split()
        if not words:
            continue
        chunks.extend(_split_phrases(words, max_words) if len(words) > max_words else [words])

    merged: list[list[str]] = []
    for c in chunks:
        # fold 1–2 word fragments into a neighbour; a lone word may push it to max_words + 1
        # (still one line) rather than flash on screen by itself (e.g. lists: "ज़िंक, आयरन, कॉपर, …")
        if merged and len(c) <= 2 and len(merged[-1]) + len(c) <= max_words + (len(c) == 1):
            merged[-1] = merged[-1] + c
        elif merged and len(merged[-1]) <= 2 and len(merged[-1]) + len(c) <= max_words + (len(merged[-1]) == 1):
            merged[-1] = merged[-1] + c
        else:
            merged.append(c)
    return [" ".join(c) for c in merged]


def time_chunks(chunks: list[str], duration: float) -> list[Caption]:
    weights = [max(1, len(c.replace(" ", ""))) for c in chunks]
    total = sum(weights)
    out, t = [], 0.0
    for i, (c, w) in enumerate(zip(chunks, weights)):
        end = duration if i == len(chunks) - 1 else t + duration * w / total
        out.append(Caption(text=c, start=round(t, 3), end=round(end, 3)))
        t = end
    return out


def build_captions(text: str, duration: float, max_words: int) -> list[Caption]:
    return time_chunks(chunk_text(text, max_words), duration)


def word_captions(segment_texts: list[str], words: list[AudioWord], duration: float, max_words: int,
                  lead_sec: float = 0.1) -> list[Caption] | None:
    """Chunk each segment as usual, then time every chunk from its words: it appears `lead_sec`
    before its first word (never before the previous chunk), and stays up until the next chunk
    appears (through pauses), the last one until the end of the audio. None if the words don't
    match the text (e.g. narration edited after word timing ran)."""
    starts, chunks = [], []
    for i, text in enumerate(segment_texts):
        seg_words = [w for w in words if w.segment == i]
        p = 0
        for c in chunk_text(text, max_words):
            n = len(c.split())
            ws = seg_words[p:p + n]
            if [w.text for w in ws] != c.split():
                return None
            p += n
            prev = starts[-1] if starts else 0.0
            starts.append(max(prev, ws[0].start - lead_sec) if starts else 0.0)
            chunks.append((c, ws))
        if p != len(seg_words):
            return None
    out = []
    for k, ((c, ws), st) in enumerate(zip(chunks, starts)):
        end = starts[k + 1] if k + 1 < len(starts) else duration
        if end <= st:  # two chunks at the same instant (shouldn't happen with real timings)
            end = st + 0.04
        out.append(Caption(text=c, start=round(st, 3), end=round(end, 3),
                           words=[CaptionWord(text=w.text, start=w.start, end=w.end) for w in ws]))
    return out
