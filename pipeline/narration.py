"""Narration stage: one WAV per scene, loudness-normalized, plus caption timings.

    uv run python -m pipeline.narration episodes/<id> [--scene N] [--force] [--takes N]
    uv run python -m pipeline.narration episodes/<id> --pick 9:2:3      # scene 9, segment 2 → take 3
    uv run python -m pipeline.narration episodes/<id> --mode scene       # v0: one TTS call per scene
    uv run python -m pipeline.narration episodes/<id> --align-only       # word timings only, no TTS

Mode `segments` (default, config narration.mode):
  1. Each scene is split into segments at sentence marks (। ? !) and pause marks (| ||), see
     pipeline/prosody.py. Each segment gets a delivery style (explicit {style} or automatic:
     question, numbers → slow, purpose) = a Parler voice description from config.
  2. Every segment is synthesized `takes` times with different seeds → audio/takes/<hash>.wav
     (cached by text + style + seed, so edits only redo what changed).
  3. Takes are scored (Whisper transcription vs. the script, length, pitch range, mid-sentence gaps,
     question rise; pipeline/take_scoring.py). The best is picked unless overridden with --pick.
  4. Picked takes are trimmed, compressed, joined with controlled pauses → audio/work/scene-XX.wav.
  Report of every take and score: audio/takes.md. Per-scene picks: audio/segments/scene-XX.json.

Mode `scene` (v0): one TTS call per scene → audio/raw/scene-XX.wav → audio/work/scene-XX.wav.

Both modes: ONE loudness gain for the whole episode (+ limiter if needed) and a very quiet room
tone → audio/scene-XX.wav; duration_sec, segments and captions go into episode.json.

Word timing (segments mode, config narration.word_timing): Whisper word timestamps on each final
scene wav, aligned to the script's words (pipeline/word_align.py) → audio.words in episode.json.
`--align-only` redoes just this step from the existing audio (e.g. for episodes narrated before
word timing existed).
"""

from __future__ import annotations

import hashlib
import json
import re
import statistics
from pathlib import Path

from pipeline import audio
from pipeline.captions import build_captions
from pipeline.common import (
    format_config, load_config, voice_preset, load_episode, resolve_episode_dir, save_episode,
    selected_scenes, setup_logging, stage_parser, stage_timer, write_json,
)
from pipeline.prosody import auto_style, paired_segments, strip_markup
from pipeline.schema import Audio, AudioSegment, Caption, Episode, Scene, Status
from pipeline.take_scoring import TakeMetrics, cer, measure, score_takes
from pipeline.text_normalize import apply_pronunciations
from pipeline.tts_backends import TTSJob, get_backend, voice_description
from pipeline.word_align import time_scene_words, word_timing_config

LATIN_OR_DIGIT = re.compile(r"[A-Za-z0-9०-९]")
CHECK_CER = 0.12  # in the listen list: picked takes whose transcription differs more than this


def voice_config(cfg: dict, ep: Episode) -> dict:
    """config.yaml tts settings, overridden by the episode's own voice (so an episode keeps its voice)."""
    v = {k: val for k, val in cfg["tts"].items() if k not in ("voices", "default_voice")}
    v.update(voice_preset(cfg, ep.voice.preset or None))
    for k, val in ep.voice.model_dump().items():
        if val not in (None, ""):
            v[k] = val
    return v


def job_key(text: str, v: dict) -> str:
    blob = json.dumps({"text": text, "backend": v["backend"], "model": v.get("model"),
                       "description": voice_description(v), "seed": v.get("seed")},
                      ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()


def caption_max_words(cfg: dict, fmt: str) -> int:
    return int(format_config(cfg, fmt).get("caption_max_words", cfg["captions"]["max_words_per_chunk"]))


def scene_name(s: Scene) -> str:
    return f"scene-{s.id:02d}.wav"


# ---------- mode: scene (v0) ----------

def synth_scene_mode(ep: Episode, ep_dir: Path, v: dict, backend, args, run, sr: int) -> dict[int, list]:
    raw_dir, work_dir = ep_dir / "audio" / "raw", ep_dir / "audio" / "work"
    jobs, keys = [], {}
    for s in selected_scenes(ep, args.scenes):
        raw = raw_dir / scene_name(s)
        side = raw.with_suffix(".json")
        text = strip_markup(s.narration_spoken)
        key = job_key(text, v)
        fresh = raw.exists() and side.exists() and json.loads(side.read_text()).get("key") == key
        if fresh and not args.force:
            continue
        jobs.append(TTSJob(text, raw))
        keys[raw] = (key, text)
    if jobs:
        for r in backend.synthesize_many(jobs, v):
            key, text = keys[r.out]
            r.out.with_suffix(".json").write_text(json.dumps(
                {"key": key, "text": text, "backend": backend.name, "speaker": v.get("speaker"),
                 "sec_audio": r.sec_audio, "sec_compute": r.sec_compute, "device": r.device},
                ensure_ascii=False, indent=2), encoding="utf-8")
            rtf = r.sec_compute / r.sec_audio if r.sec_audio else 0
            run.note(f"{r.out.name}: {r.sec_audio:.2f}s audio in {r.sec_compute:.1f}s ({rtf:.1f}× realtime, {r.device})")
    else:
        run.note("all raw narration up to date; skipping TTS")
    missing = [s.id for s in ep.scenes if not (raw_dir / scene_name(s)).exists()]
    if missing:
        raise SystemExit(f"no raw audio for scenes {missing}; run narration without --scene first")
    for s in ep.scenes:
        audio.resample_trim(raw_dir / scene_name(s), work_dir / scene_name(s), sr)
    return {s.id: [] for s in ep.scenes}  # no segment spans


# ---------- mode: segments ----------

def style_voice(cfg: dict, v: dict, style: str) -> tuple[str, float, dict]:
    """(Parler description, tempo, model params) for a delivery style.
    'neutral' or unknown → the voice's own description. `params.<backend>` in a style gives
    model-specific options, keyed by the voice's `family` (e.g. chatterbox: exaggeration);
    Parler uses the description instead."""
    st = (cfg.get("narration", {}).get("styles") or {}).get(style) or {}
    desc = st.get("description") or v.get("description", "")
    params = dict(((st.get("params") or {}).get(v.get("family") or v["backend"])) or {})
    return str(desc).format(speaker=v.get("speaker", "")), float(st.get("tempo", 1.0)), params


def take_key(text: str, v: dict, description: str, seed: int, params: dict | None = None) -> str:
    ident = {"text": text, "backend": v["backend"], "model": v.get("model"), "seed": seed}
    if v["backend"] == "parler":
        ident["description"] = description  # (kept identical to the first pilot so cached takes stay valid)
    else:
        ident.update(voice=v.get("speaker"), ref=v.get("ref_audio"), lang=v.get("lang", "hi"),
                     params={**(v.get("params") or {}), **(params or {})})
    return hashlib.sha1(json.dumps(ident, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def plan_scene(s: Scene, cfg: dict, v: dict, n_takes: int, takes_dir: Path) -> list[dict]:
    """Segments of a scene with their style and the take files they need."""
    rules = cfg.get("narration", {}).get("auto_style", {}) or {}
    base_seed = int(v.get("seed", 42))
    plan = []
    prev_pause, prev_style = None, None
    for i, (d, sp) in enumerate(paired_segments(s.narration_display, s.narration_spoken)):
        if prev_pause == "short" and not sp.style:
            style = prev_style  # after a | breath the same sentence goes on: keep its delivery
        else:
            style = auto_style(sp, d.text, s.purpose, i, rules)
        prev_pause, prev_style = sp.pause, style
        desc, tempo, params = style_voice(cfg, v, style)
        # per-voice respellings (voice preset `pronunciation`): only what this model is sent changes;
        # scoring still compares with the normal spelling, i.e. what the listener should hear
        tts_text = apply_pronunciations(sp.text, {str(a): str(b) for a, b in (v.get("pronunciation") or {}).items()})
        takes = []
        for k in range(n_takes):
            seed = base_seed + k
            key = take_key(tts_text, v, desc, seed, params)
            takes.append({"take": k + 1, "seed": seed, "file": f"takes/{key}.wav"})
        plan.append({"segment": i + 1, "display": d.text, "spoken": sp.text, "tts_text": tts_text, "pause": sp.pause,
                     "style": style, "description": desc, "tempo": tempo, "params": params, "takes": takes})
    return plan


def synth_segment_mode(ep: Episode, ep_dir: Path, v: dict, backend, args, run, cfg: dict, sr: int) -> dict[int, list]:
    ncfg = cfg.get("narration", {})
    n_takes = int(args.takes or v.get("takes") or ncfg.get("takes", 4))  # CLI > voice preset > config
    adir = ep_dir / "audio"
    takes_dir, seg_dir, work_dir = adir / "takes", adir / "segments", adir / "work"
    asr_cfg = dict(ncfg.get("asr", {}) or {})
    if args.asr:
        asr_cfg["backend"] = args.asr
    if backend.name == "stub":
        asr_cfg["backend"] = "none"  # tones can't be transcribed
    selected = {s.id for s in selected_scenes(ep, args.scenes)}
    plans = {s.id: plan_scene(s, cfg, v, n_takes, takes_dir) for s in ep.scenes}

    # 1. synthesize missing takes (all scenes; --force redoes the selected scenes)
    jobs, meta = [], {}
    for s in ep.scenes:
        for seg in plans[s.id]:
            for t in seg["takes"]:
                wav = adir / t["file"]
                if wav.exists() and not (args.force and s.id in selected):
                    continue
                if not wav.exists() and s.id not in selected:
                    continue  # only synthesize what was asked for; missing scenes fail below
                jobs.append(TTSJob(seg["tts_text"], wav, description=seg["description"], seed=t["seed"],
                                   params=seg["params"] or None))
                meta[wav] = {"text": seg["tts_text"], "style": seg["style"], "description": seg["description"],
                             "params": seg["params"], "seed": t["seed"], "backend": backend.name,
                             "model": v.get("model"), "speaker": v.get("speaker") or v.get("ref_audio")}
    if jobs:
        run.note(f"synthesizing {len(jobs)} take(s) ({n_takes} per segment)")
        sec_a = sec_c = 0.0
        for r in backend.synthesize_many(jobs, v):
            sec_a, sec_c = sec_a + r.sec_audio, sec_c + r.sec_compute
            write_json(r.out.with_suffix(".json"), {**meta[r.out], "sec_audio": r.sec_audio,
                                                    "sec_compute": r.sec_compute, "device": r.device})
        run.note(f"TTS: {sec_a:.1f}s audio in {sec_c:.0f}s compute ({sec_c / sec_a if sec_a else 0:.1f}× realtime)")
    else:
        run.note("all takes up to date; skipping TTS")

    missing = [s.id for s in ep.scenes for seg in plans[s.id] for t in seg["takes"] if not (adir / t["file"]).exists()]
    if missing:
        raise SystemExit(f"takes missing for scenes {sorted(set(missing))}; run narration without --scene first")

    # 2. measure takes that have no metrics yet (or --rescore)
    def side(t: dict) -> Path:
        return (adir / t["file"]).with_suffix(".json")
    todo = sorted({adir / t["file"] for s in ep.scenes for seg in plans[s.id] for t in seg["takes"]
                   if args.rescore or "metrics" not in json.loads(side(t).read_text())
                   or json.loads(side(t).read_text())["metrics"].get("asr") != asr_cfg.get("backend", "whisper")})
    if todo:
        run.note(f"scoring {len(todo)} take(s) (asr: {asr_cfg.get('backend', 'whisper')})")
        for wav, m in measure(todo, asr_cfg).items():
            sc = wav.with_suffix(".json")
            d = json.loads(sc.read_text())
            d["metrics"] = {"asr": asr_cfg.get("backend", "whisper"), "heard": m.heard, "speech_sec": m.speech_sec,
                            "f0_range_st": m.f0_range_st, "end_rise_st": m.end_rise_st, "max_gap_sec": m.max_gap_sec,
                            "f0_median_hz": m.f0_median_hz}
            write_json(sc, d)

    # 3. score, pick (keeping manual picks while the segment is unchanged), assemble
    picks = parse_picks(args.pick)
    weights = ncfg.get("score_weights") or {}
    pauses = {k: float(x) for k, x in (ncfg.get("pauses_sec") or {}).items()}
    spans: dict[int, list] = {}
    # typical register per delivery style (a question is meant to sit higher than neutral):
    # median pitch over every take of that style in the episode; overall median if too few takes
    by_style: dict[str, list[float]] = {}
    for s in ep.scenes:
        for seg in plans[s.id]:
            for t in seg["takes"]:
                f0 = json.loads(side(t).read_text())["metrics"].get("f0_median_hz", 0.0)
                if f0:
                    by_style.setdefault(seg["style"], []).append(f0)
    every = [f for fs in by_style.values() for f in fs]
    overall = statistics.median(every) if every else None  # the episode's voice
    STYLE_SPAN = 2 ** (3 / 12)  # a style may sit at most 3 semitones from the voice (questions higher)
    ref_f0 = {st: min(max(statistics.median(fs) if len(fs) >= 5 else overall, overall / STYLE_SPAN), overall * STYLE_SPAN)
              for st, fs in by_style.items()} if overall else {}
    if ref_f0:
        run.note(f"voice pitch {overall:.0f} Hz; per style: "
                 + ", ".join(f"{st} {hz:.0f} Hz" for st, hz in sorted(ref_f0.items())))
    for s in ep.scenes:
        mpath = seg_dir / f"scene-{s.id:02d}.json"
        old = {(x["spoken"], x["style"]): x.get("override") for x in
               (json.loads(mpath.read_text()) if mpath.exists() else [])}
        parts, gaps = [], []
        for seg in plans[s.id]:
            ms = []
            for t in seg["takes"]:
                m = json.loads(side(t).read_text())["metrics"]
                tm = TakeMetrics(heard=m["heard"], speech_sec=m["speech_sec"], f0_range_st=m["f0_range_st"],
                                 end_rise_st=m["end_rise_st"], max_gap_sec=m["max_gap_sec"],
                                 f0_median_hz=m.get("f0_median_hz", 0.0))
                tm.cer = cer(seg["spoken"], tm.heard) if m["asr"] != "none" else None
                ms.append(tm)
            scores = score_takes(seg["spoken"], ms, weights, ref_f0.get(seg["style"], overall), overall)
            for t, tm, sc in zip(seg["takes"], ms, scores):
                t.update(score=sc, cer=None if tm.cer is None else round(tm.cer, 3), heard=tm.heard,
                         speech_sec=tm.speech_sec, f0_range_st=tm.f0_range_st, end_rise_st=tm.end_rise_st,
                         max_gap_sec=tm.max_gap_sec, f0_median_hz=tm.f0_median_hz)
            seg["auto"] = max(range(len(scores)), key=lambda i: scores[i]) + 1
            seg["override"] = picks.get((s.id, seg["segment"]), old.get((seg["spoken"], seg["style"])))
            if seg["override"] is not None and not 1 <= seg["override"] <= len(seg["takes"]):
                raise SystemExit(f"scene {s.id} segment {seg['segment']}: no take {seg['override']}")
            seg["chosen"] = seg["override"] or seg["auto"]
            chosen = seg["takes"][seg["chosen"] - 1]
            part = work_dir / "segs" / f"scene-{s.id:02d}-s{seg['segment']:02d}.wav"
            audio.prepare_segment(adir / chosen["file"], part, sr, seg["tempo"])
            parts.append(part)
            gaps.append(pauses.get(seg["pause"], 0.3))
        write_json(mpath, plans[s.id])
        spans[s.id] = audio.join_with_pauses(parts, gaps, work_dir / scene_name(s), sr)
    write_report(ep, plans, adir / "takes.md")
    return spans


def parse_picks(items: list[str] | None) -> dict[tuple[int, int], int]:
    out = {}
    for it in items or []:
        try:
            sc, seg, take = (int(x) for x in it.split(":"))
        except ValueError:
            raise SystemExit(f"--pick wants SCENE:SEGMENT:TAKE (e.g. 9:2:3), got {it!r}")
        out[(sc, seg)] = take
    return out


def write_report(ep: Episode, plans: dict[int, list], path: Path) -> None:
    lines = [f"# Narration takes: {ep.id}", "",
             "Picked take marked ✓ (✎ = picked by hand with --pick). `heard` = Whisper's transcription; "
             "cer = character difference from the script (lower is better).",
             "Override: `uv run python -m pipeline.narration episodes/<id> --pick SCENE:SEGMENT:TAKE`", ""]
    for s in ep.scenes:
        lines.append(f"## Scene {s.id} ({s.purpose})")
        for seg in plans[s.id]:
            lines.append(f"\n**{s.id}:{seg['segment']}** [{seg['style']}, pause after: {seg['pause']}] {seg['display']}\n")
            lines.append("| take | score | cer | pitch Hz | pitch range st | end rise st | longest gap s | length s | heard |")
            lines.append("|---|---|---|---|---|---|---|---|---|")
            for t in seg["takes"]:
                mark = ("✎" if seg.get("override") else "✓") if t["take"] == seg["chosen"] else ""
                lines.append(f"| {t['take']}{mark} | {t['score']} | {t['cer']} | {t.get('f0_median_hz', '')} | {t['f0_range_st']} | {t['end_rise_st']} "
                             f"| {t['max_gap_sec']} | {t['speech_sec']} | {t['heard']} |")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- captions ----------

def segment_captions(display_segments: list[str], spans: list[tuple[float, float]], duration: float,
                     max_words: int) -> list[Caption]:
    """Each segment's captions are timed within its own speech; a caption stays up through the
    pause that follows it (until the next segment starts)."""
    out: list[Caption] = []
    for i, (text, (a, _b)) in enumerate(zip(display_segments, spans)):
        end = spans[i + 1][0] if i + 1 < len(spans) else duration
        start = 0.0 if i == 0 else a
        for c in build_captions(text, max(end - start, 0.05), max_words):
            out.append(Caption(text=c.text, start=round(start + c.start, 3), end=round(start + c.end, 3)))
    return out


# ---------- word timing ----------

def add_word_timings(ep: Episode, ep_dir: Path, cfg: dict, run, asr_backend: str | None = None,
                     force: bool = False) -> None:
    wt = word_timing_config(cfg)
    if not wt["enabled"]:
        run.note("word timing off (narration.word_timing.enabled)")
        return
    asr_cfg = dict(cfg.get("narration", {}).get("asr", {}) or {})
    if asr_backend:
        asr_cfg["backend"] = asr_backend
    res = time_scene_words(ep_dir, ep.scenes, asr_cfg, wt, force=force)
    weak = []
    for s in ep.scenes:
        if s.id in res:
            words, ratios = res[s.id]
            s.audio.words = words
            weak += [f"{s.id}:{i + 1} ({r:.0%})" for i, r in enumerate(ratios) if r < float(wt["min_segment_match"])]
    n = sum(len(s.audio.words) for s in ep.scenes if s.audio)
    timed = sum(w.timed for s in ep.scenes if s.audio for w in s.audio.words)
    run.note(f"word timing: {timed}/{n} words matched to Whisper ({asr_cfg.get('backend', 'whisper')})"
             + (f"; proportional fallback for segments {', '.join(weak)}" if weak else ""))


# ---------- main ----------

def main() -> None:
    p = stage_parser(__doc__)
    p.add_argument("--backend", help="override tts backend (e.g. stub for testing)")
    p.add_argument("--mode", choices=["segments", "scene"], help="override config narration.mode")
    p.add_argument("--takes", type=int, help="takes per segment (segments mode)")
    p.add_argument("--asr", choices=["whisper", "none"], help="override take scoring backend")
    p.add_argument("--rescore", action="store_true", help="re-measure every take (e.g. after changing the asr model)")
    p.add_argument("--pick", action="append", metavar="SCENE:SEG:TAKE", help="use this take (repeatable)")
    p.add_argument("--align-only", action="store_true",
                   help="only (re)compute word timings from the existing scene audio; no TTS, no loudness pass")
    p.add_argument("--allow-unapproved", action="store_true",
                   help="testing only: narrate a script that hasn't passed checkpoint 1")
    args = p.parse_args()
    setup_logging(args.verbose)
    ep_dir = resolve_episode_dir(args.episode)
    cfg = load_config()
    ncfg = cfg.get("narration", {})

    with stage_timer(ep_dir, "narration") as run:
        ep = load_episode(ep_dir)
        if not ep.status.at_least(Status.script_approved) and not args.allow_unapproved:
            raise SystemExit("script is not approved yet (checkpoint 1). "
                             "Run `pipeline.validate <ep> --set-status script_approved` after approval.")
        empty = [s.id for s in ep.scenes if not s.narration_spoken.strip()]
        if empty:
            raise SystemExit(f"narration_spoken is empty for scenes {empty}; run pipeline.text_normalize first")

        if args.align_only:
            no_audio = [s.id for s in ep.scenes if not (s.audio and s.audio.segments)]
            if no_audio:
                raise SystemExit(f"--align-only needs narrated scenes with segments; missing for {no_audio}")
            add_word_timings(ep, ep_dir, cfg, run, args.asr, force=args.force)
            save_episode(ep_dir, ep)
            return

        v = voice_config(cfg, ep)
        if args.backend:
            v["backend"] = args.backend
        backend = get_backend(v["backend"])
        mode = args.mode or ncfg.get("mode", "scene")
        run.note(f"mode={mode} backend={backend.name} speaker={v.get('speaker')} seed={v.get('seed')}")
        sr = int(cfg["tts"]["out_sample_rate"])
        out_dir, work_dir = ep_dir / "audio", ep_dir / "audio" / "work"

        if mode == "segments":
            spans = synth_segment_mode(ep, ep_dir, v, backend, args, run, cfg, sr)
        else:
            spans = synth_scene_mode(ep, ep_dir, v, backend, args, run, sr)

        # one loudness gain for the whole episode
        work = [work_dir / scene_name(s) for s in ep.scenes]
        before = audio.measure_loudness(work)
        target, ceiling = float(cfg["audio"]["target_lufs"]), float(cfg["audio"]["true_peak_db"])
        room = ncfg.get("room_tone_db")
        gain = target - before["lufs"]
        limit = ceiling - 0.5 if before["true_peak"] + gain > ceiling else None
        for _ in range(3):  # the limiter lowers loudness a little; top up the gain until within 0.5 LU
            for s in ep.scenes:
                audio.apply_gain(work_dir / scene_name(s), out_dir / scene_name(s), gain, limit)
            after = audio.measure_loudness([out_dir / scene_name(s) for s in ep.scenes])
            if abs(after["lufs"] - target) <= 0.5:
                break
            gain += target - after["lufs"]
        run.note(f"loudness {before['lufs']:.1f} → {after['lufs']:.1f} LUFS (target {target}), "
                 f"true peak {after['true_peak']:.1f} dBTP, gain {gain:+.1f} dB"
                 + (", limiter on" if limit is not None else "")
                 + (f", room tone {room} dB" if room is not None else ""))
        # one continuous room-tone track for the whole video (render plays it looped under everything)
        rt = out_dir / "room-tone.wav"
        if room is None:
            rt.unlink(missing_ok=True)
        else:
            audio.make_room_tone(rt, float(room), sr)

        # durations, segments, captions → episode.json
        max_words = caption_max_words(cfg, ep.format)
        for s in ep.scenes:
            dur = round(audio.duration(out_dir / scene_name(s)), 3)
            sp = spans.get(s.id) or []
            if sp:
                segs = paired_segments(s.narration_display, s.narration_spoken)
                styles = [x["style"] for x in json.loads((out_dir / "segments" / f"scene-{s.id:02d}.json").read_text())]
                s.audio = Audio(file=f"audio/{scene_name(s)}", duration_sec=dur, segments=[
                    AudioSegment(text=d.text, start=a, end=min(b, dur), style=st)
                    for (d, _), (a, b), st in zip(segs, sp, styles)])
                s.captions = segment_captions([d.text for d, _ in segs], sp, dur, max_words)
            else:
                s.audio = Audio(file=f"audio/{scene_name(s)}", duration_sec=dur)
                s.captions = build_captions(strip_markup(s.narration_display), dur, max_words)
        if mode == "segments":
            add_word_timings(ep, ep_dir, cfg, run, "none" if backend.name == "stub" else args.asr)
        save_episode(ep_dir, ep)
        total = sum(s.audio.duration_sec for s in ep.scenes if s.audio)
        run.note(f"{len(ep.scenes)} scenes, narration total {total:.1f}s")

    # quick-listen list
    check = [s for s in ep.scenes if s.id <= ep.scenes[0].id + 1 or LATIN_OR_DIGIT.search(strip_markup(s.narration_display))]
    print("\nListen to these (first two scenes + any with numbers or English terms):")
    for s in check:
        print(f"  {ep_dir.name}/audio/{scene_name(s)}  — {strip_markup(s.narration_display)[:70]}")
    if mode == "segments":
        flagged = []
        for s in ep.scenes:
            mp = out_dir / "segments" / f"scene-{s.id:02d}.json"
            for seg in json.loads(mp.read_text()):
                t = seg["takes"][seg["chosen"] - 1]
                if t.get("cer") is not None and t["cer"] > CHECK_CER:
                    flagged.append(f"  {s.id}:{seg['segment']} take {seg['chosen']} cer {t['cer']}: heard “{t['heard']}”")
        if flagged:
            print("\nPicked takes Whisper heard differently from the script (listen; maybe --pick another):")
            print("\n".join(flagged))
        print(f"\nAll takes and scores: {ep_dir.name}/audio/takes.md")


if __name__ == "__main__":
    main()
