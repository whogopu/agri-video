---
name: narration
description: Generate per-scene Hindi narration audio and caption timings for an approved AgriGate episode. Use after checkpoint 1, or to redo narration for specific scenes.
---

# narration

Requires status `script_approved`.

```bash
uv run python -m pipeline.text_normalize episodes/<id>      # if narration_spoken is empty
uv run python -m pipeline.narration episodes/<id> [--scene N] [--force] [--takes N]
uv run python -m pipeline.narration episodes/<id> --pick 9:2:3   # scene 9, segment 2 → use take 3
uv run python -m pipeline.validate episodes/<id> --set-status narrated
```

Voices: `maya_vasant` (male, default) or `veena_varun` (female), per episode (`new_episode --voice`). Both run in the `tts-mlx/` env. Maya2 has no style control (styles only change pauses and tempo); Veena sometimes drifts to another voice, which the identity score rejects (6 takes per sentence).

How it works (`config.yaml: narration`, mode `segments`):
- Each scene is split into **segments** at । ? ! and at the script's pause marks `|` (breath) and `||` (long pause). Each segment is one TTS call, so Parler never rushes through a long scene.
- Each segment gets a **delivery style** (a Parler description): `{style}` in the script, else automatic. Questions use `question`, numbers use `slow`, CTA uses `warm` and mistakes use `firm`. After a `|`, the sentence keeps its style.
- Every segment is synthesized **`takes` times** (seeds = voice seed + 0..N-1). Each take is transcribed by Whisper (`asr/` env) and measured. The best is picked by score: transcription matches the script, length isn't odd, pitch isn't flat, no strange mid-sentence gaps, and questions rise at the end.
- Picked takes are joined with **controlled pauses** (`narration.pauses_sec`), with a very quiet room tone under everything, and one loudness gain for the whole episode.
- Captions are timed **per segment from the real audio**. `episode.json: audio.segments` stores each sentence's start/end (for cuts and graphics later).
- Takes are cached by text + style + seed. Editing one sentence only redoes that sentence. `--pick` choices stick while the segment text stays the same.
- `--mode scene` = v0 behaviour (one call per scene), kept for comparison.

After running:
- Read `audio/takes.md`. The command prints picked takes where Whisper heard something different from the script; listen to those first. Whisper's own spelling quirks (ज़/ज, digits) are already ignored, but it may still mishear a correct take, so the ear decides.
- Tell the user which files to check: scenes 1–2, every scene with numbers or English terms, and every flagged segment. For a flagged segment, name the alternative takes (`audio/takes/<hash>.wav` from `audio/segments/scene-XX.json`) so they can compare.
- Don't play audio automatically.
- Mispronunciation in every take? Add a `pronunciation.yaml` fix, rebuild `narration_spoken` (`text_normalize --scene N --force`), rerun with `--scene N`.
- Speed per take: Maya2 ≈ 1× realtime (5 takes of a 4-minute episode ≈ 20 min), Veena ≈ 4.7× (6 takes ≈ 1.9 h), Parler ≈ 2×. Run nothing else heavy at the same time.
