# Timings on this Mac

MacBook Air M4, 16 GB unified memory, fanless (since 2026-11-22; entries before that date were measured on an M5 with 16 GB). Heavy jobs run one at a time; long jobs may slow down from thermal throttling.

## Smoke tests

| Date | Tool / stage | Test | Result | Time | Notes |
|---|---|---|---|---|---|
| 2026-11-19 | pipeline.new_episode | create empty episode | ok | <0.1s | |
| 2026-11-19 | pipeline.validate | 4-scene fixture | ok | <0.1s | |
| 2026-11-19 | Remotion still (first run) | FontTest 1920×1080 PNG | ok | 10.8s | includes bundling; later stills ~3–5s with cached bundle |
| 2026-11-19 | Remotion render, software x264 | 20.5s test episode, 1080p30, concurrency 4 | ok | 12.1s wall, 41s CPU | ≈0.6× realtime; 9.1 MB |
| 2026-11-19 | Remotion render, `--hardware-acceleration required` (VideoToolbox) | same | ok | 11.0s wall, 19s CPU | same wall time (frame rendering is the bottleneck) but half the CPU → less heat on fanless Air; 25 MB (higher bitrate) |
| 2026-11-19 | Parler-TTS first run | model download (gated, ~3.6 GB) + load | ok | ~80s download (connection-dependent); load 11s on MPS | weights cached in ~/.cache/huggingface |
| 2026-11-19 | Parler-TTS on MPS (indic-parler-tts, F32) | 3 Hindi sentences × 4 speakers, 6–11.6s each | ok | **≈1.8–2.1 s compute per 1 s of audio** | plus ~11s model load per run. Peak heat noticeable but no slowdown over 4 min of continuous work |
| 2026-11-19 | Speaking pace, description "moderate speed" | same sentences | — | — | Divya 161, Rohit 171, Aman 191, Rani 190 words/min (target 130–150) |
| 2026-11-19 | Speaking pace, description "slightly slow … patient teacher" | same sentences | — | — | Divya **150**, Rohit 161 words/min |
| 2026-11-19 | Voice decision | user listened | — | — | **Rohit, normal pace (~171 wpm) = default**; Aman (~191 wpm) kept as preset `aman` |
| 2026-11-19 | narration post-processing (ffmpeg) | trim + 48 kHz + loudness over 4 scenes | ok | ~1s | integrated loudness lands within ±1 LU of −14 LUFS |
| 2026-11-19 | mflux, FLUX.2 klein 4B q4, first run | download 4.6 GB + 1 image 1344×768 | ok | 111s (mostly download) | peak MLX memory 3.67 GB |
| 2026-11-19 | mflux, FLUX.2 klein 4B q4 | 1344×768 (16:9), 4 steps | ok | **18.3s per image** incl. model load | 3 images + 1 retry, steady time, no throttling seen |
| 2026-11-19 | mflux, FLUX.2 klein 4B q4 | 768×1344 (9:16 Short), 4 steps | ok | 18.6s | |
| 2026-11-22 | mflux, FLUX.3 Klein q8 (quantized on load, `--low-ram`) | 1344×768, 16 steps | ok | **~120 s per image** (median of 39) | peak 7.8 GB; bake-off, see bakeoff/report.md |
| 2026-11-22 | mflux, FLUX.3 Klein q8 edit, 1 head-crop reference | 1344×768 | ok | ~185 s (163–203) | peak 9.0 GB |
| 2026-11-22 | mflux, FLUX.3 Klein q8 edit, 2 head-crop references | 1344×768 | ok | ~260 s (257–273) | full-figure references instead: 475 s |
| 2026-11-22 | mflux, FLUX.3 Klein q8 edit, 1 reference, production `images` one-off | 768×1344 (Short) | ok | 140 s | |
| 2026-11-22 | mflux, FLUX.3 Klein base q8 (pre-saved, 50 steps) | 1344×768 | ok | ~713 s | peak 11.2 GB; not used |
| 2026-11-22 | vlm/vlm_worker.py text-only (`images: []`), Ministral 3 14B 4-bit | one shot spec (JSON) from a Hindi sentence + 2 example specs, 1.5k prompt tokens | ok | 60 s + 8 s load | peak 9.2 GB, 782 tokens; plan P2 |
| 2026-11-22 | same, Qwen3.5 9B 4-bit | same | ok | 41 s + 2 s load | peak 7.1 GB, 923 tokens |
| 2026-11-22 | **M4** mflux, FLUX.3 Klein q8 (quantized on load, `--low-ram`) | 1344×768, 16 steps, setup smoke | ok | **351 s** (≈21 s/step, load <1 min) | peak 7.6 GB; ≈2.9× the M5. The very first run after download took >30 min (cold 19 GB read + quantize, swapping); stopped and re-run |
| 2026-11-22 | **M4** Maya2 Native Vasant (mlx-audio) | 3 sentences, setup smoke | ok | 2.1 s compute per s audio (first clip 4.8 incl. warm-up), load 11.5 s | ≈2.2× the M5 (0.9–1.0) |
| 2026-11-22 | **M4** Veena varun (mlx-lm bf16 + SNAC) | 3 sentences, setup smoke | ok | 5.6 s compute per s audio, 137 s wall incl. load | M5 was 4.7: only ≈1.2× slower. A 4-min episode × 5 takes ≈ 1.9 h of narration vs ≈ 42 min with maya_vasant |
| 2026-11-19 | broll index | 2 short test clips | ok | <1s | probe + 3-frame contact strip |
| 2026-11-19 | narration, real episode (4 scenes, 30 s audio) | Rohit, MPS | ok | 59s TTS + 1s post | 1.8–2.1 s compute per s audio. Loudness −14.4 LUFS after adding the compressor (−15.4 before) |
| 2026-11-19 | render draft (540p, scale 0.5) | 30.6 s long video | ok | 14s | 12.6 MB |
| 2026-11-19 | render final (1080p, VideoToolbox) | 30.6 s long video | ok | 14s | 45.8 MB (~12 Mbit/s) |
| 2026-11-19 | render final, Short 1080×1920 | 30.6 s | ok | 14s | 45.7 MB |
| 2026-11-19 | review | 30.6 s video → 16 frames, 2 sheets + checks | ok | 4–5s | |
| 2026-11-19 | package | thumbnail still + youtube.md | ok | ~2s (cached bundle) | |

Estimate for a 4-minute long video (≈680 words at Rohit pace): ≈8 min of TTS compute (+11s load). A 45-second Short: ≈1.5 min.
Render: ≈0.45 s per second of video (a 4-min final ≈ 2 min). Images: ≈18 s each with FLUX.2 klein (until 2026-11-22); FLUX.3 Klein takes ≈2 min (≈3 min with a cast reference), so ~15 image scenes with ~2 shots each and some retries take ≈1–1.5 h on the M5. **On the M4 (from 2026-11-22): ≈6 min per image (≈8–9 min with a cast reference, estimated), so ≈3–4 h of images per long episode; narration ≈2.2× slower than above.**

## Per-stage summary (phase 6 demo episode)

Episode `2026-11-19-mitti-ki-jaanch`: long 16:9, Rohit voice, 23 scenes (15 images + 8 graphics), 4 min 11 s final video. Times are machine time from `log.md` (not counting human review).

| Stage | Time | Slow? | Notes |
|---|---|---|---|
| new_episode, text_normalize, validate | <1 s each | no | |
| narration (Parler-TTS, MPS) | **8 min 36 s** for 250 s of audio | **yes, the slowest stage** | ≈1.9–2.0 s compute per s of audio + model load. Re-runs with cached raw audio take ~11 s (captions/loudness only) |
| images (FLUX.2 klein 4B q4) | **5 min 31 s** for 15 images (≈22 s each incl. load) | **yes** | each retry ≈18–20 s. This episode needed 9 retries (anatomy, fused tools, text), ≈3 min more. Inspecting images is the real time cost (human/Claude attention) |
| render draft (540p) | 1 min 45 s | moderate | ≈0.42 s per s of video. Re-rendered 6× after checkpoint-2 fixes |
| render final (1080p, VideoToolbox) | 1 min 36 s | moderate | ≈0.38 s per s of video; 414 MB (~13 Mbit/s) |
| review (126 frames, 11 sheets, loudness, black/freeze) | 13–34 s | no | |
| package (thumbnail + youtube.md) | ~2 s | no | |
| **Total machine time, first pass** | **≈18 min** | | narration + images + draft + final + review. Checkpoint fixes added ~15 min (mostly 6 draft re-renders) |

**Takeaways for this Mac:**
- Narration and images are the bottlenecks (~14 of the ~18 min). Both run on the GPU, so run them one at a time.
- Each draft re-render costs ~1 min 45 s. Batch checkpoint-2 notes before re-rendering.
- No thermal throttling was visible: per-unit times stayed flat across 8.5 min of continuous TTS and 5.5 min of image generation.

## Narration, segments mode (pilot, 2026-11-19)

4 scenes (1, 9, 16, 23) of the soil episode, 10 segments × 5 takes, Parler on MPS:

| Step | Time |
|---|---|
| TTS, 50 takes (211.9 s of audio) | 413 s compute (2.0× realtime) + model load; stage total 460 s |
| Whisper large-v3-turbo + pitch, per take | ~0.5–0.7 s (first run also downloads ~1.6 GB) |
| Re-pick + assemble + loudness (cached takes) | ~2 s |

Estimate for a 4-minute episode with 5 takes: ≈ 40–50 min TTS + ~2 min scoring.
Scenes got ~0–2 s longer from controlled pauses and the slower number style (scene 9: 10.1 → 12.2 s).

## Narration model comparison (2026-11-19)

Same 4 pilot scenes, 10 segments × 5 takes, scored by Whisper large-v3-turbo. Compute per second of audio on this Mac:

| Model / voice | Runtime | s compute per s audio | Model load | Peak RSS | Mean take error | Picked takes word-perfect |
|---|---|---|---|---|---|---|
| Parler Rohit | torch MPS | 2.0 | ~20 s | — | 0.041 | 6/10 |
| **Maya2 Native Vasant** (production, male) | mlx-audio | 0.9–1.0 | ~2 min first time | — | 0.021 | 7/10 |
| Chatterbox Multilingual (synthetic Rohit ref) | mlx-audio | 1.0 | — | — | 0.034 | 7/10 |
| Indic-Speak Amit | mlx-lm bf16 + torch decode | 5.3 | 129 s | 3.3 GB | 0.039 | 9/10 |
| **Veena varun** (production, female) | mlx-lm bf16 + SNAC | 4.7 | 124 s | 4.1 GB | 0.068 | 6/10 (after identity fix) |

## Word timing (2026-11-20, phase B1)

`narration --align-only` on 2026-11-20-mitti-ki-jaanch-v3 (23 scene wavs, 3.7 min of narration): Whisper large-v3-turbo with word timestamps + silence detection, **~30 s** total (~1.1–1.3 s per scene); alignment in the main env is instant. A re-run with unchanged audio reads `audio/words/` and takes < 1 s. Accuracy: §7.4a of ARCHITECTURE.md.
