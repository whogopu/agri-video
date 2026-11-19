# 2026-11-19-mitti-ki-jaanch-v2

Copy of 2026-11-19-mitti-ki-jaanch (approved script, inspected images) re-narrated with the new narration pipeline and voice maya_vasant (Maya2 Native). Script text unchanged from checkpoint 1.

## validate — 2026-11-19 16:34:05
- duration: 0.0s
- outcome: ok
- PASS as script_approved: 0 errors, 0 warnings
- status packaged → script_approved

## narration — 2026-11-19 16:34:09
- duration: 1694.0s
- outcome: ok
- mode=segments backend=mlx_audio speaker=Vasant seed=42
- synthesizing 220 take(s) (5 per segment)
- TTS: 1063.0s audio in 1295s compute (1.2× realtime)
- scoring 220 take(s) (asr: whisper)
- voice pitch 140 Hz; per style: firm 136 Hz, neutral 142 Hz, question 167 Hz, slow 136 Hz, warm 132 Hz
- loudness -28.1 → -14.2 LUFS (target -14.0), true peak -1.8 dBTP, gain +14.7 dB, limiter on, room tone -66 dB
- 23 scenes, narration total 219.3s

## validate — 2026-11-19 17:02:35
- duration: 0.0s
- outcome: ok
- PASS as narrated: 0 errors, 0 warnings
- status script_approved → narrated

## validate — 2026-11-19 17:02:35
- duration: 0.0s
- outcome: ok
- PASS as visuals_ready: 0 errors, 0 warnings
- status narrated → visuals_ready

## render (draft) — 2026-11-19 17:02:35
- duration: 101.9s
- outcome: ok
- rendering draft.mp4: 1920x1080 × 0.5, expected 220.13s
- episodes/2026-11-19-mitti-ki-jaanch-v2/render/draft.mp4: 220.14s (99.2 MB)

## validate — 2026-11-19 17:04:25
- duration: 0.0s
- outcome: ok
- PASS as draft_rendered: 0 errors, 0 warnings
- status visuals_ready → draft_rendered
- 2026-11-19 17:04 CHECKPOINT 2 pending: draft render/draft.mp4 sent to user for review (new narration pipeline, voice maya_vasant).
- 2026-11-19 17:06 User: respelled जांच (→ जाञ्च, Vasant only) sounds better than the original spelling; keep it.

## render (draft) — 2026-11-19 17:30:14
- duration: 99.6s
- outcome: ok
- rendering draft.mp4: 1920x1080 × 0.5, expected 239.60s
- episodes/2026-11-19-mitti-ki-jaanch-v2/render/draft.mp4: 239.62s (107.7 MB)
- 2026-11-19 17:32 Checkpoint 2 note: scene changes too short (sounded like one sentence). Fixed globally: padding 0.35 → 0.8 s + 0.4 s picture-first lead-in; scene gaps now 0.91–1.01 s. Draft re-rendered (239.6 s).

## narration — 2026-11-19 17:55:43
- duration: 12.1s
- outcome: ok
- mode=segments backend=mlx_audio speaker=Vasant seed=42
- all takes up to date; skipping TTS
- voice pitch 140 Hz; per style: firm 136 Hz, neutral 142 Hz, question 167 Hz, slow 136 Hz, warm 132 Hz
- loudness -28.1 → -14.2 LUFS (target -14.0), true peak -1.8 dBTP, gain +14.7 dB, limiter on, room tone -66 dB
- 23 scenes, narration total 219.3s

## render (draft) — 2026-11-19 17:55:55
- duration: 100.8s
- outcome: ok
- rendering draft.mp4: 1920x1080 × 0.5, expected 239.60s
- episodes/2026-11-19-mitti-ki-jaanch-v2/render/draft.mp4: 239.62s (107.7 MB)

## narration — 2026-11-19 17:58:23
- duration: 11.9s
- outcome: ok
- mode=segments backend=mlx_audio speaker=Vasant seed=42
- all takes up to date; skipping TTS
- voice pitch 140 Hz; per style: firm 136 Hz, neutral 142 Hz, question 167 Hz, slow 136 Hz, warm 132 Hz
- loudness -28.2 → -14.2 LUFS (target -14.0), true peak -1.8 dBTP, gain +14.7 dB, limiter on, room tone -66 dB
- 23 scenes, narration total 218.6s

## render (draft) — 2026-11-19 17:58:35
- duration: 99.9s
- outcome: ok
- rendering draft.mp4: 1920x1080 × 0.5, expected 238.93s
- episodes/2026-11-19-mitti-ki-jaanch-v2/render/draft.mp4: 238.93s (107.4 MB)
- 2026-11-19 18:01 Checkpoint 2 note: disturbance still audible at some joins. Causes: long Maya2 end bursts kept as speech + post-roll re-adding bursts + per-scene room tone switching on/off. Fixed (D25); narration reassembled from cached takes, draft re-rendered (238.9 s); scan finds no blips at joins; all scene endings intact.
- 2026-11-19 22:01 CHECKPOINT 2 APPROVED by user: "joins are clean now, render the final video".

## render (final) — 2026-11-19 22:01:18
- duration: 92.1s
- outcome: ok
- rendering video.mp4: 1920x1080, expected 238.93s
- episodes/2026-11-19-mitti-ki-jaanch-v2/render/video.mp4: 238.93s (395.2 MB)

## validate — 2026-11-19 22:02:50
- duration: 0.0s
- outcome: ok
- PASS as final_rendered: 0 errors, 0 warnings
- status draft_rendered → final_rendered
