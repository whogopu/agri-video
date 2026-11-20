"""Word timings for captions and graphics: align the script's words to Whisper's timed words.

Whisper (asr/ env, word_timestamps=True) hears the scene audio and returns timed words in its
own spelling (digits vs number words, nukta, nasal marks, sometimes a wrong word). We know
what was actually said: the script. So instead of trusting Whisper's words, we align the two
letter by letter:

1. Every script word (narration_display, per audio segment) and every heard word is reduced
   to `canon()` letters (numbers → words, nukta/nasal/punctuation unified, as in take scoring).
2. The two letter strings are aligned (difflib). Each heard letter gets a time by spreading its
   word's start..end evenly over its letters.
3. A script word takes its start/end from its matched letters. Words with too few matched
   letters are filled in proportionally (by letter count) between their timed neighbours.
4. Each word is kept inside its segment's speech span, which the narration stage knows
   exactly (it joined the picked takes itself). That also bounds any Whisper error.

The quality per segment (share of script letters matched) is kept; a segment below
`min_match` falls back to proportional timing inside its span (today's caption method).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from pipeline.common import log, write_json
from pipeline.schema import AudioWord
from pipeline.take_scoring import canon, run_asr_worker

MIN_WORD_MATCH = 0.4   # a script word needs this share of its letters (and >= 2) matched to take Whisper's time
MIN_SEG_MATCH = 0.6    # below this a segment's words are timed proportionally inside its span


@dataclass
class Word:
    text: str          # as shown (display spelling, punctuation kept)
    start: float
    end: float
    segment: int       # index of the audio segment it belongs to
    timed: bool        # True = from Whisper; False = filled in proportionally


@dataclass
class HeardWord:
    text: str
    start: float
    end: float


def snap_to_speech(heard: list[HeardWord], silences: list[tuple[float, float]], tol: float = 0.05) -> list[HeardWord]:
    """Whisper starts a word that follows a pause inside the silence (~0.2–0.3 s early) and lets a
    word run on into the next pause. Move starts that fall in a silence to its end (speech
    resumes) and ends that fall in one to its start. `tol`: Whisper's times come in 20 ms steps and
    run early, so a start just before a silence counts as inside it."""
    out = []
    for hw in heard:
        s, e = hw.start, hw.end
        for gs, ge in silences:
            if gs - tol <= s < ge:
                s = ge
            if gs < e <= ge:
                e = gs
        if e <= s:  # the whole word sat in a silence: keep Whisper's times
            s, e = hw.start, hw.end
        out.append(HeardWord(hw.text, s, e))
    return out


def _letters(word: str) -> str:
    return canon(word)


def _proportional(words: list[str], a: float, b: float) -> list[tuple[float, float]]:
    w = [max(1, len(_letters(x))) for x in words]
    total, t, out = sum(w), a, []
    for x in w:
        e = t + (b - a) * x / total
        out.append((t, e))
        t = e
    return out


def align_segment_words(seg_texts: list[str], spans: list[tuple[float, float]],
                        heard: list[HeardWord], min_seg_match: float = MIN_SEG_MATCH
                        ) -> tuple[list[Word], list[float]]:
    """Time every display word of a scene. Returns (words, match ratio per segment)."""
    script = [(w, i) for i, t in enumerate(seg_texts) for w in t.split()]
    s_chars, s_owner = [], []
    for k, (w, _) in enumerate(script):
        for ch in _letters(w):
            s_chars.append(ch)
            s_owner.append(k)
    h_chars, h_time, h_word = [], [], []
    for hi, hw in enumerate(heard):
        letters = _letters(hw.text)
        n = len(letters)
        for j, ch in enumerate(letters):
            h_chars.append(ch)
            h_time.append((hw.start + (hw.end - hw.start) * j / n, hw.start + (hw.end - hw.start) * (j + 1) / n))
            h_word.append(hi)

    # letter alignment
    matched: dict[int, list[tuple[float, float]]] = {}
    m_heard: dict[int, list[int]] = {}       # script word → heard words its letters matched
    sharers: dict[int, set[int]] = {}        # heard word → script words with letters in it
    sm = SequenceMatcher(None, "".join(s_chars), "".join(h_chars), autojunk=False)
    for blk in sm.get_matching_blocks():
        for d in range(blk.size):
            k, hj = s_owner[blk.a + d], blk.b + d
            matched.setdefault(k, []).append(h_time[hj])
            m_heard.setdefault(k, []).append(h_word[hj])
            sharers.setdefault(h_word[hj], set()).add(k)

    n_letters = [max(1, len(_letters(w))) for w, _ in script]
    # a stray matched vowel sign must not time a short word: need >= 2 letters (or the whole word)
    ok = [len(matched.get(k, [])) / n_letters[k] >= MIN_WORD_MATCH and len(matched.get(k, [])) >= min(2, n_letters[k])
          for k in range(len(script))]
    sharers = {hi: {k for k in ks if ok[k]} for hi, ks in sharers.items()}
    times: list[tuple[float, float] | None] = []
    for k in range(len(script)):
        m = matched.get(k, [])
        if not ok[k]:
            times.append(None)
            continue
        # take the heard word's own edges unless another script word shares that heard word
        # (Whisper sometimes merges or splits words); then use the letter's spread-out time
        first, last = m_heard[k][0], m_heard[k][-1]
        start = heard[first].start if sharers[first] <= {k} else m[0][0]
        end = heard[last].end if sharers[last] <= {k} else m[-1][1]
        times.append((start, end))

    # per-segment quality; weak segments fall back to proportional timing
    ratios = []
    for i, (a, b) in enumerate(spans):
        ks = [k for k, (_, si) in enumerate(script) if si == i]
        tot = sum(n_letters[k] for k in ks)
        got = sum(min(len(matched.get(k, [])), n_letters[k]) for k in ks)
        ratio = got / tot if tot else 0.0
        ratios.append(round(ratio, 3))
        if ratio < min_seg_match:
            for k in ks:
                times[k] = None

    words: list[Word] = []
    for i, (a, b) in enumerate(spans):
        ks = [k for k, (_, si) in enumerate(script) if si == i]
        # keep Whisper times inside the known speech span, in order
        seg_times: list[tuple[float, float] | None] = []
        last = a
        for k in ks:
            t = times[k]
            if t is not None:
                s0, e0 = max(a, min(t[0], b)), max(a, min(t[1], b))
                if s0 < last - 1e-6 or e0 <= s0:
                    t = times[k] = None  # out of order or collapsed: let it be filled in
                else:
                    last = e0
                    t = (s0, e0)
            seg_times.append(t)
        # fill untimed runs between timed neighbours (or the span edges)
        j = 0
        while j < len(ks):
            if seg_times[j] is not None:
                j += 1
                continue
            r = j
            while r < len(ks) and seg_times[r] is None:
                r += 1
            lo = seg_times[j - 1][1] if j > 0 else a
            hi = seg_times[r][0] if r < len(ks) else b
            if hi <= lo:
                hi = lo + 0.05 * (r - j)
            for off, se in enumerate(_proportional([script[k][0] for k in ks[j:r]], lo, hi)):
                seg_times[j + off] = se
            j = r
        for k, t in zip(ks, seg_times):
            words.append(Word(text=script[k][0], start=round(t[0], 3), end=round(t[1], 3), segment=i,
                              timed=times[k] is not None))
    return words, ratios


# ---------- per scene: run Whisper (cached), align, return schema words ----------

def word_timing_config(cfg: dict) -> dict:
    defaults = {"enabled": True, "prompt_script": True, "silence_db": 35.0, "silence_min_sec": 0.08,
                "snap_tol_sec": 0.05, "min_segment_match": MIN_SEG_MATCH}
    return {**defaults, **((cfg.get("narration", {}) or {}).get("word_timing") or {})}


def _cache_key(wav: Path, prompt: str, asr_cfg: dict, wt: dict) -> str:
    h = hashlib.sha1(wav.read_bytes())
    h.update(json.dumps({"prompt": prompt, "model": asr_cfg.get("model"), "lang": asr_cfg.get("language"),
                         "silence_db": wt["silence_db"], "silence_min_sec": wt["silence_min_sec"]},
                        ensure_ascii=False, sort_keys=True).encode())
    return h.hexdigest()[:16]


def time_scene_words(ep_dir: Path, scenes: list, asr_cfg: dict, wt: dict, force: bool = False
                     ) -> dict[int, tuple[list[AudioWord], list[float]]]:
    """Word timings for scenes whose audio has segments. Raw Whisper output is cached in
    audio/words/scene-XX.json (keyed by the wav's bytes, prompt and settings), so only changed
    audio is transcribed again. asr backend 'none' → proportional timing (tests / stub audio)."""
    todo = [s for s in scenes if s.audio and s.audio.segments]
    cache_dir = ep_dir / "audio" / "words"
    raw: dict[int, dict] = {}
    jobs, job_scene = [], {}
    use_whisper = asr_cfg.get("backend", "whisper") == "whisper"
    for s in todo:
        texts = [g.text for g in s.audio.segments]
        if not use_whisper:
            raw[s.id] = {"words": [], "silences": []}
            continue
        wav = ep_dir / s.audio.file
        prompt = " ".join(texts) if wt["prompt_script"] else ""
        key = _cache_key(wav, prompt, asr_cfg, wt)
        cp = cache_dir / f"scene-{s.id:02d}.json"
        if cp.exists() and not force:
            d = json.loads(cp.read_text())
            if d.get("key") == key:
                raw[s.id] = d
                continue
        jobs.append({"wav": str(wav), "words": True, "prompt": prompt,
                     "silence_db": wt["silence_db"], "silence_min_sec": wt["silence_min_sec"]})
        job_scene[str(wav)] = (s.id, key, cp)
    if jobs:
        log.info("word timing: transcribing %d scene(s)", len(jobs))
        for d in run_asr_worker(jobs, asr_cfg):
            sid, key, cp = job_scene[d["wav"]]
            rec = {"key": key, "heard": d["text"], "words": d["words"], "silences": d["silences"]}
            write_json(cp, rec)
            raw[sid] = rec
    missing = [s.id for s in todo if s.id not in raw]
    if missing:
        raise RuntimeError(f"word timing: no Whisper result for scenes {missing}")

    out = {}
    for s in todo:
        r = raw[s.id]
        heard = [HeardWord(w["w"], w["start"], w["end"]) for w in r["words"]]
        heard = snap_to_speech(heard, [tuple(x) for x in r["silences"]], wt["snap_tol_sec"])
        words, ratios = align_segment_words([g.text for g in s.audio.segments],
                                            [(g.start, g.end) for g in s.audio.segments], heard,
                                            float(wt["min_segment_match"]))
        out[s.id] = ([AudioWord(text=w.text, start=w.start, end=w.end, segment=w.segment, timed=w.timed)
                      for w in words], ratios)
    return out
